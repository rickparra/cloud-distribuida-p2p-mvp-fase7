from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import oracledb
from policy import CLASSES, rejection_reason, parse_submission
from operator_onboarding import parse_operator
from hosting import HELLO_HTML, HOST_SECONDS, html_for_node, validate_html
from topology import render_topology
from workload import parse_numbers


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
APP_PORT = 8000
WORKER_PORTS = {"BR-TEE-01": 8001, "BR-TEE-02": 8002}
CSRF_TOKEN = secrets.token_urlsafe(32)
HOST_TIMERS: dict[int, threading.Timer] = {}
HOST_TIMERS_LOCK = threading.Lock()
GROUP_TIMERS: dict[str, threading.Timer] = {}
SITE_GROUPS: dict[str, dict] = {}
SITE_GROUPS_LOCK = threading.Lock()


def connection():
    user = os.environ.get("ORACLE_USER")
    password = os.environ.get("ORACLE_PASSWORD")
    dsn = os.environ.get("ORACLE_DSN", "oracle.fiap.com.br:1521/ORCL")
    if not user or not password:
        raise RuntimeError("Configure ORACLE_USER e ORACLE_PASSWORD. Inicie pelo run.ps1.")
    return oracledb.connect(user=user, password=password, dsn=dsn)


def sql_statements(path: Path):
    source = path.read_text(encoding="utf-8")
    for chunk in source.split("-- @statement"):
        statement = "\n".join(line for line in chunk.splitlines() if not line.lstrip().startswith("--")).strip()
        if not statement:
            continue
        statement = statement.removesuffix("/").strip()
        if statement.upper().startswith(("CREATE TABLE", "CREATE INDEX", "MERGE INTO")):
            statement = statement.removesuffix(";").strip()
        yield statement


def setup_schema():
    conn = connection()
    try:
        cur = conn.cursor()
        for statement in sql_statements(ROOT / "schema.sql"):
            try:
                cur.execute(statement)
            except oracledb.DatabaseError as exc:
                error = exc.args[0]
                code = getattr(error, "code", None)
                if code == 955 and statement.upper().startswith(("CREATE TABLE", "CREATE INDEX")):
                    continue
                if code == 1430 and statement.upper().startswith("ALTER TABLE"):
                    continue
                if code == 2264 and statement.upper().startswith("ALTER TABLE"):
                    continue
                if code == 2443 and statement.upper().startswith("ALTER TABLE") and " DROP CONSTRAINT " in statement.upper():
                    continue
                if code == 904 and statement.upper().startswith("ALTER TABLE") and " DROP COLUMN " in statement.upper():
                    continue
                raise
        conn.commit()
        for statement in sql_statements(ROOT / "seed.sql"):
            cur.execute(statement)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def node_catalog(data_class: str, vcpu_req: Decimal, max_price: Decimal):
    sql = """
        SELECT NODE_CODE, NODE_LABEL, COUNTRY_CODE, TEE_ENABLED,
               LOCAL_PERSISTENCE, APPROVED, VCPU_CAPACITY, VCPU_RESERVED,
               PRICE_PER_VCPU_HOUR, OPERATOR_CNPJ, OPERATOR_NAME,
               OPERATOR_UF, GUARANTEE_BRL
          FROM F6POC_NODES ORDER BY PRICE_PER_VCPU_HOUR, NODE_CODE
    """
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
    nodes = [
        {
            "code": row[0], "label": row[1], "country": row[2].strip(),
            "tee": bool(row[3]), "persistence": bool(row[4]),
            "approved": int(row[5]), "capacity": row[6], "reserved": row[7],
            "rate": Decimal(str(row[8])), "operator_cnpj": row[9],
            "operator_name": row[10], "operator_uf": row[11],
            "guarantee": row[12],
        }
        for row in rows
    ]
    for node in nodes:
        node["reason"] = rejection_reason(data_class, vcpu_req, max_price, node)
        node["price"] = (node["rate"] * vcpu_req).quantize(Decimal("0.01"))
    nodes.sort(key=lambda node: (node["price"], node["code"]))
    return nodes


def register_job(job_code: str, data_class: str, vcpu_req: Decimal, max_price: Decimal, numbers: list[int]):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO F6POC_JOBS (JOB_CODE, DATA_CLASSIFICATION, VCPU_REQ, MAX_PRICE_BRL) VALUES (:code,:class,:vcpu,:budget)",
            {"code": job_code, "class": data_class, "vcpu": vcpu_req, "budget": max_price},
        )
        cur.execute("SELECT JOB_ID FROM F6POC_JOBS WHERE JOB_CODE=:code", {"code": job_code})
        job_id = cur.fetchone()[0]
        input_hash = hashlib.sha256(json.dumps(numbers, separators=(",", ":")).encode("utf-8")).hexdigest()
        cur.execute(
            "INSERT INTO F7MVP_EXECUTIONS (JOB_ID, INPUT_SHA256, INPUT_COUNT) VALUES (:job,:hash,:count)",
            {"job": job_id, "hash": input_hash, "count": len(numbers)},
        )
        conn.commit()
        cur.close()


def register_host_job(job_code: str, vcpu_req: Decimal, max_price: Decimal, content: str):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO F6POC_JOBS (JOB_CODE, DATA_CLASSIFICATION, VCPU_REQ, MAX_PRICE_BRL) VALUES (:code,'PUBLICO',:vcpu,:budget)",
            {"code": job_code, "vcpu": vcpu_req, "budget": max_price},
        )
        cur.execute("SELECT JOB_ID FROM F6POC_JOBS WHERE JOB_CODE=:code", {"code": job_code})
        job_id = cur.fetchone()[0]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        cur.execute(
            "INSERT INTO F7MVP_EXECUTIONS (JOB_ID, INPUT_SHA256, INPUT_COUNT) VALUES (:job,:hash,1)",
            {"job": job_id, "hash": content_hash},
        )
        conn.commit()
        cur.close()


def mark_job_failed(job_code: str):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE F6POC_JOBS SET STATUS='FAILED' WHERE JOB_CODE=:code AND STATUS='OPEN'", {"code": job_code})
        conn.commit()
        cur.close()


def register_operator_node(data: dict):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO F6POC_NODES
                   (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,
                    APPROVED,VCPU_CAPACITY,VCPU_RESERVED,PRICE_PER_VCPU_HOUR,
                    OPERATOR_CNPJ,OPERATOR_NAME,OPERATOR_UF,GUARANTEE_BRL)
                 VALUES (:code,:label,'BR',:tee,:persistence,0,:capacity,0,:rate,
                         :cnpj,:name,:uf,:guarantee)""",
            data,
        )
        conn.commit()
        cur.close()


def record_rejection(job_code: str, node_code: str | None, reason: str):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT JOB_ID FROM F6POC_JOBS WHERE JOB_CODE=:code", {"code": job_code})
        job_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO F6POC_REJECTIONS (JOB_ID,NODE_CODE,REASON) VALUES (:job,:node,:reason)",
            {"job": job_id, "node": node_code, "reason": reason[:200]},
        )
        conn.commit()
        cur.close()


def allocate(job_code: str, node_code: str):
    conn = connection()
    try:
        cur = conn.cursor()
        cur.callproc("F6POC_ALLOCATE", [job_code, node_code])
        cur.execute(
            "SELECT l.LEASE_ID, l.TOTAL_PRICE_BRL FROM F6POC_LEASES l JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID WHERE j.JOB_CODE=:code",
            {"code": job_code},
        )
        lease_id, total_price = cur.fetchone()
        total = Decimal(str(total_price))
        fee = (total * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cur.execute(
            """INSERT INTO F7MVP_SETTLEMENTS
                   (LEASE_ID,GROSS_BRL,PLATFORM_FEE_BRL,PROVIDER_BRL,STATUS)
                 VALUES (:lease,:gross,:fee,:provider,'RESERVED')""",
            {"lease": lease_id, "gross": total, "fee": fee, "provider": total - fee},
        )
        conn.commit()
        cur.close()
        return int(lease_id), total
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_lease(lease_id: int, result: dict):
    with connection() as conn:
        cur = conn.cursor()
        result_hash = hashlib.sha256(json.dumps(result["result"], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        cur.execute(
            """UPDATE F7MVP_EXECUTIONS SET RESULT_SHA256=:result_hash, COMPLETED_AT=SYSTIMESTAMP
                 WHERE JOB_ID=(SELECT JOB_ID FROM F6POC_LEASES WHERE LEASE_ID=:id)""",
            {"result_hash": result_hash, "id": lease_id},
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"Execucao do lease #{lease_id} nao encontrada.")
        cur.execute("UPDATE F6POC_LEASES SET STATUS='COMPLETED' WHERE LEASE_ID=:id AND STATUS='AUTHORIZED'", {"id": lease_id})
        if cur.rowcount != 1:
            raise RuntimeError(f"Lease #{lease_id} nao esta mais autorizado para conclusao.")
        cur.execute("UPDATE F7MVP_SETTLEMENTS SET STATUS='RELEASED', UPDATED_AT=SYSTIMESTAMP WHERE LEASE_ID=:id AND STATUS='RESERVED'", {"id": lease_id})
        if cur.rowcount != 1:
            raise RuntimeError(f"Registro financeiro do lease #{lease_id} nao encontrado.")
        conn.commit()
        cur.close()


def fail_lease(lease_id: int):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE F6POC_LEASES SET STATUS='FAILED' WHERE LEASE_ID=:id AND STATUS='AUTHORIZED'", {"id": lease_id})
        if cur.rowcount != 1:
            raise RuntimeError(f"Lease #{lease_id} nao esta mais autorizado para falha.")
        cur.execute("UPDATE F7MVP_SETTLEMENTS SET STATUS='REFUNDED', UPDATED_AT=SYSTIMESTAMP WHERE LEASE_ID=:id AND STATUS='RESERVED'", {"id": lease_id})
        if cur.rowcount != 1:
            raise RuntimeError(f"Registro financeiro do lease #{lease_id} nao encontrado.")
        conn.commit()
        cur.close()


def lease_status(lease_id: int):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT STATUS FROM F6POC_LEASES WHERE LEASE_ID=:id", {"id": lease_id})
        row = cur.fetchone()
        cur.close()
    return row[0] if row else None


def audit_for_job(job_code: str):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT a.LEASE_ID, a.EVENT_SEQ, a.EVENT_TYPE, a.ACTOR, a.DETAILS,
                      a.PREVIOUS_HASH, a.EVENT_HASH, TO_CHAR(a.CREATED_AT,'YYYY-MM-DD HH24:MI:SS')
                 FROM F6POC_AUDIT_EVENTS a
                 JOIN F6POC_LEASES l ON l.LEASE_ID=a.LEASE_ID
                 JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID
                WHERE j.JOB_CODE=:code ORDER BY a.EVENT_SEQ""",
            {"code": job_code},
        )
        rows = cur.fetchall()
        cur.close()
    return rows


def verify_audit_chain(rows):
    previous = "-"
    for lease_id, seq, event_type, actor, details, previous_hash, event_hash, _created in rows:
        if previous_hash != previous:
            return False
        canonical = f"{lease_id}|{seq}|{event_type}|{actor}|{details}|{previous}"
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
        if event_hash != expected:
            return False
        previous = event_hash
    return bool(rows)


def execute_worker(job_code: str, node_code: str, numbers: list[int]):
    port = WORKER_PORTS.get(node_code)
    if port is None:
        raise RuntimeError("O no selecionado nao possui executor conectado.")
    payload = json.dumps({"job": job_code, "node": node_code, "numbers": numbers}).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{port}/execute", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        result = json.loads(response.read().decode("utf-8"))
    if (result.get("status") != "COMPLETED" or result.get("node_code") != node_code
            or result.get("job_code") != job_code or not isinstance(result.get("result"), dict)):
        raise RuntimeError("O worker nao confirmou a tarefa e o no alocado.")
    expected_hash = hashlib.sha256(json.dumps(numbers, separators=(",", ":")).encode("utf-8")).hexdigest()
    if result.get("input_sha256") != expected_hash:
        raise RuntimeError("O worker respondeu para um lote diferente do enviado.")
    return result


def worker_is_ready(node_code: str) -> bool:
    health = worker_health(node_code)
    return health.get("status") == "READY" and health.get("node_code") == node_code


def worker_health(node_code: str) -> dict:
    port = WORKER_PORTS.get(node_code)
    if port is None:
        return {"status": "MISSING", "enabled": False, "node_code": node_code}
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=0.4) as response:
            health = json.loads(response.read().decode("utf-8"))
        return health if isinstance(health, dict) else {"status": "INVALID", "enabled": False}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return {"status": "OFFLINE", "enabled": False, "node_code": node_code}
def worker_request(node_code: str, path: str, payload: dict) -> dict:
    port = WORKER_PORTS.get(node_code)
    if port is None:
        raise RuntimeError("O no nao possui executor conectado.")
    request = urllib.request.Request(
        f"http://{HOST}:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def set_worker_enabled(node_code: str, enabled: bool) -> dict:
    if node_code not in WORKER_PORTS:
        raise ValueError("Nó sem executor local não pode ser controlado neste MVP.")
    return worker_request(node_code, "/control", {"node": node_code, "enabled": enabled})


def hosting_sessions(limit: int = 20):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT j.JOB_CODE, j.VCPU_REQ, l.NODE_CODE, l.TOTAL_PRICE_BRL,
                      h.LEASE_ID, h.SITE_TOKEN, h.WORKER_PORT, h.EXPIRES_EPOCH,
                      h.STATUS, h.GROUP_TOKEN, h.GROUP_NAME, n.OPERATOR_NAME
                 FROM F7MVP_HOSTING h
                 JOIN F6POC_LEASES l ON l.LEASE_ID=h.LEASE_ID
                 JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID
                 JOIN F6POC_NODES n ON n.NODE_CODE=l.NODE_CODE
                ORDER BY h.LEASE_ID DESC FETCH FIRST :limit ROWS ONLY""",
            {"limit": limit},
        )
        rows = cur.fetchall()
        cur.close()
    return [{"job": row[0], "vcpu": row[1], "node": row[2], "price": row[3],
             "lease": int(row[4]), "token": row[5], "port": int(row[6]),
             "expires": int(row[7]), "status": row[8], "group": row[9],
             "group_name": row[10], "operator": row[11]} for row in rows]


def hosting_record(lease_id: int):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT SITE_TOKEN, WORKER_PORT, STATUS FROM F7MVP_HOSTING WHERE LEASE_ID=:id",
            {"id": lease_id},
        )
        row = cur.fetchone()
        cur.close()
    return row


def stop_worker_site(token: str, port: int):
    try:
        request = urllib.request.Request(
            f"http://{HOST}:{port}/stop",
            data=json.dumps({"node": next(code for code, value in WORKER_PORTS.items() if value == port),
                             "token": token}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=1):
            pass
    except (OSError, StopIteration):
        pass  # O worker tem seu proprio limite de 180 segundos.


def close_hosting(lease_id: int, completed: bool) -> bool:
    """Close lease, ledger, hosting state and audit in one Oracle transaction."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT STATUS FROM F7MVP_HOSTING WHERE LEASE_ID=:id FOR UPDATE", {"id": lease_id})
        row = cur.fetchone()
        if row is None or row[0] != "ACTIVE":
            return False
        if completed:
            cur.execute("SELECT INPUT_SHA256 FROM F7MVP_EXECUTIONS WHERE JOB_ID=(SELECT JOB_ID FROM F6POC_LEASES WHERE LEASE_ID=:id)", {"id": lease_id})
            hash_row = cur.fetchone()
            if hash_row is None:
                raise RuntimeError("No do lease de hospedagem nao encontrado.")
            cur.execute(
                """UPDATE F7MVP_EXECUTIONS SET RESULT_SHA256=:hash, COMPLETED_AT=SYSTIMESTAMP
                     WHERE JOB_ID=(SELECT JOB_ID FROM F6POC_LEASES WHERE LEASE_ID=:id)""",
                {"hash": hash_row[0], "id": lease_id},
            )
            if cur.rowcount != 1:
                raise RuntimeError("Registro da pagina hospedada nao encontrado.")
        cur.execute(
            "UPDATE F6POC_LEASES SET STATUS=:status WHERE LEASE_ID=:id AND STATUS='AUTHORIZED'",
            {"status": "COMPLETED" if completed else "FAILED", "id": lease_id},
        )
        if cur.rowcount != 1:
            raise RuntimeError("Lease da hospedagem nao esta mais autorizado.")
        cur.execute(
            """UPDATE F7MVP_SETTLEMENTS SET STATUS=:status, UPDATED_AT=SYSTIMESTAMP
                 WHERE LEASE_ID=:id AND STATUS='RESERVED'""",
            {"status": "RELEASED" if completed else "REFUNDED", "id": lease_id},
        )
        if cur.rowcount != 1:
            raise RuntimeError("Reserva demonstrativa da hospedagem nao encontrada.")
        cur.execute(
            "UPDATE F7MVP_HOSTING SET STATUS=:status WHERE LEASE_ID=:id AND STATUS='ACTIVE'",
            {"status": "EXPIRED" if completed else "CANCELLED", "id": lease_id},
        )
        conn.commit()
        cur.close()
    return True


def schedule_hosting_close(lease_id: int, seconds: int):
    timer = threading.Timer(seconds, expire_hosting, args=(lease_id,))
    timer.daemon = True
    with HOST_TIMERS_LOCK:
        HOST_TIMERS[lease_id] = timer
    timer.start()


def expire_hosting(lease_id: int):
    try:
        record = hosting_record(lease_id)
        if record is None or record[2] != "ACTIVE":
            return
        token, port, _status = record
        stop_worker_site(token, int(port))
        close_hosting(lease_id, completed=True)
    except Exception as exc:
        print(f"[hosting] Falha ao encerrar lease #{lease_id}: {exc}; nova tentativa em 10 s.", flush=True)
        schedule_hosting_close(lease_id, 10)
        return
    with HOST_TIMERS_LOCK:
        HOST_TIMERS.pop(lease_id, None)


def cancel_hosting(lease_id: int):
    record = hosting_record(lease_id)
    if record is None or record[2] != "ACTIVE":
        return False
    token, port, _status = record
    stop_worker_site(token, int(port))
    changed = close_hosting(lease_id, completed=False)
    with HOST_TIMERS_LOCK:
        timer = HOST_TIMERS.pop(lease_id, None)
    if timer:
        timer.cancel()
    return changed


def cancel_active_hosting():
    with SITE_GROUPS_LOCK:
        for timer in GROUP_TIMERS.values():
            timer.cancel()
        GROUP_TIMERS.clear()
        SITE_GROUPS.clear()
    with HOST_TIMERS_LOCK:
        for timer in HOST_TIMERS.values():
            timer.cancel()
        HOST_TIMERS.clear()
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT LEASE_ID FROM F7MVP_HOSTING WHERE STATUS='ACTIVE'")
        lease_ids = [int(row[0]) for row in cur.fetchall()]
        cur.close()
    for lease_id in lease_ids:
        try:
            cancel_hosting(lease_id)
        except Exception as exc:
            print(f"[hosting] Lease #{lease_id} requer reconciliacao: {exc}", flush=True)


def group_lease_ids(group_token: str) -> list[int]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT LEASE_ID FROM F7MVP_HOSTING WHERE GROUP_TOKEN=:token ORDER BY LEASE_ID", {"token": group_token})
        result = [int(row[0]) for row in cur.fetchall()]
        cur.close()
    return result


def cancel_group(group_token: str) -> bool:
    lease_ids = group_lease_ids(group_token)
    if not lease_ids:
        return False
    with SITE_GROUPS_LOCK:
        group = SITE_GROUPS.get(group_token)
        if group:
            group["status"] = "CANCELLED"
        timer = GROUP_TIMERS.pop(group_token, None)
        if timer:
            timer.cancel()
    changed = False
    for lease_id in lease_ids:
        changed = cancel_hosting(lease_id) or changed
    return changed


def expire_group(group_token: str):
    with SITE_GROUPS_LOCK:
        group = SITE_GROUPS.get(group_token)
        if group:
            group["status"] = "EXPIRED"
        GROUP_TIMERS.pop(group_token, None)
    try:
        lease_ids = group_lease_ids(group_token)
    except Exception as exc:
        print(f"[hosting] Grupo requer reconciliacao: {exc}; nova tentativa em 10 s.", flush=True)
        timer = threading.Timer(10, expire_group, args=(group_token,))
        timer.daemon = True
        with SITE_GROUPS_LOCK:
            GROUP_TIMERS[group_token] = timer
        timer.start()
        return
    for lease_id in lease_ids:
        expire_hosting(lease_id)


def fetch_group_site(group_token: str):
    with SITE_GROUPS_LOCK:
        group = SITE_GROUPS.get(group_token)
        if group is None or group["status"] != "ACTIVE" or time.time() >= group["expires"]:
            return 410, b"<!doctype html><meta charset='utf-8'><h1>Hospedagem encerrada</h1>", None
        members = group["members"]
        index = group["next"] % len(members)
        group["next"] += 1
        candidates = members[index:] + members[:index]
    for member in candidates:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{member['port']}/site/{member['token']}", timeout=2) as response:
                body = response.read()
            with SITE_GROUPS_LOCK:
                group["counts"][member["node"]] += 1
            return 200, body, member["node"]
        except (urllib.error.URLError, TimeoutError):
            continue
    return 503, b"<!doctype html><meta charset='utf-8'><h1>Executores indisponiveis</h1>", None


def hosting_groups(limit: int = 20):
    groups: dict[str, dict] = {}
    for session in hosting_sessions(limit * 2):
        key = session["group"] or f"legacy-{session['lease']}"
        if key not in groups:
            groups[key] = {"token": session["group"], "group_name": session.get("group_name") or "Grupo sem nome", "members": [], "expires": session["expires"]}
        groups[key]["members"].append(session)
    for site in groups.values():
        site["members"].sort(key=lambda member: member["node"])
    return list(groups.values())[:limit]


def perform_hosting(values):
    _classification, vcpu, budget = parse_submission(
        {"classification": "PUBLICO", "vcpu": values.get("vcpu", "4"),
         "budget": values.get("budget", "10")}
    )
    group_name = (values.get("group_name") or "Grupo Web Demo").strip()
    if not 1 <= len(group_name) <= 80:
        raise ValueError("O nome do grupo deve ter de 1 a 80 caracteres.")
    group_mode = values.get("group_mode", "split")
    if group_mode not in ("split", "single"):
        raise ValueError("Modo de grupo invalido.")
    content = validate_html(values.get("html_content") or HELLO_HTML)
    if group_mode == "split" and not 2 <= vcpu <= 32:
        raise ValueError("No modo dividido, escolha de 2 a 32 vCPU no total.")
    if group_mode == "single" and not 1 <= vcpu <= 32:
        raise ValueError("Escolha de 1 a 32 vCPU para um unico no.")
    if group_mode == "split":
        shares = [int(vcpu) // 2, int(vcpu) - int(vcpu) // 2]
        target_nodes = list(WORKER_PORTS)
    else:
        shares = [int(vcpu)]
        target_nodes = [next(iter(WORKER_PORTS))]
    chosen = []
    for node, share in zip(target_nodes, shares):
        entry = next((item for item in node_catalog("PUBLICO", Decimal(share), budget) if item["code"] == node), None)
        if entry is None or entry["reason"] != "ELEGIVEL" or not worker_is_ready(node):
            return f"O executor {node} nao esta elegivel e conectado para {share} vCPU.", False
        chosen.append((node, share, entry["price"]))
    total_price = sum((entry[2] for entry in chosen), Decimal("0"))
    if total_price > budget:
        return f"O grupo custaria {format_brl(total_price)} por hora, acima do teto.", False
    group_token = secrets.token_urlsafe(18)
    base_code = "WEB-" + datetime.now().strftime("%y%m%d%H%M%S") + "-" + secrets.token_hex(4).upper()
    registered = []
    allocated = []
    started = []
    stored = False
    try:
        for suffix, (node, share, _price) in zip(("A", "B"), chosen):
            code = base_code + "-" + suffix
            register_host_job(code, Decimal(share), budget, content)
            registered.append(code)
            lease_id, price = allocate(code, node)
            allocated.append((lease_id, node, share, price))
            response = worker_request(node, "/host", {"node": node, "job": code, "html": content})
            if (response.get("status") != "ACTIVE" or response.get("node_code") != node
                    or response.get("job_code") != code or response.get("seconds") != HOST_SECONDS
                    or not isinstance(response.get("token"), str)):
                raise RuntimeError(f"Executor {node} nao confirmou a hospedagem.")
            started.append({"lease": lease_id, "node": node, "port": WORKER_PORTS[node],
                            "token": response["token"]})
        expires_epoch = int(time.time()) + HOST_SECONDS
        with connection() as conn:
            cur = conn.cursor()
            for member in started:
                cur.execute(
                    """INSERT INTO F7MVP_HOSTING
                           (LEASE_ID,SITE_TOKEN,GROUP_TOKEN,GROUP_NAME,WORKER_PORT,EXPIRES_EPOCH,STATUS)
                         VALUES (:id,:token,:group_token,:group_name,:port,:expires,'ACTIVE')""",
                    {"id": member["lease"], "token": member["token"],
                     "group_token": group_token, "group_name": group_name, "port": member["port"],
                     "expires": expires_epoch},
                )
            conn.commit()
            cur.close()
        stored = True
        with SITE_GROUPS_LOCK:
            SITE_GROUPS[group_token] = {"members": started, "expires": expires_epoch,
                                        "group_name": group_name, "content": content,
                                        "status": "ACTIVE", "next": 0,
                                        "counts": {node: 0 for node, _share, _price in chosen}}
            timer = threading.Timer(HOST_SECONDS, expire_group, args=(group_token,))
            timer.daemon = True
            GROUP_TIMERS[group_token] = timer
            timer.start()
    except Exception as exc:
        for member in started:
            stop_worker_site(member["token"], member["port"])
        for lease_id, _node, _share, _price in allocated:
            try:
                cancel_hosting(lease_id) if stored else fail_lease(lease_id)
            except Exception as cleanup_exc:
                print(f"[hosting] Lease #{lease_id} requer reconciliacao: {cleanup_exc}", flush=True)
        for code in registered:
            mark_job_failed(code)
        with SITE_GROUPS_LOCK:
            SITE_GROUPS.pop(group_token, None)
            timer = GROUP_TIMERS.pop(group_token, None)
            if timer:
                timer.cancel()
        return f"Hospedagem nao iniciada: {exc}", False
    split = " + ".join(f"{node} ({share} vCPU)" for node, share, _price in chosen)
    label = "grupo dividido" if group_mode == "split" else "grupo concentrado"
    return (f"Conteudo publicado no {label} {group_name}: {split} por 3 minutos. "
            f"Total de {vcpu} vCPU; preco demonstrativo de 1 hora: {format_brl(total_price)}."), True


def recent_jobs(limit: int = 10):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT j.JOB_CODE, j.DATA_CLASSIFICATION, j.VCPU_REQ, j.MAX_PRICE_BRL, j.STATUS,
                      TO_CHAR(j.CREATED_AT,'YYYY-MM-DD HH24:MI:SS'),
                      l.NODE_CODE, l.TOTAL_PRICE_BRL, e.INPUT_SHA256,
                      e.INPUT_COUNT, e.RESULT_SHA256, r.REASON, r.NODE_CODE,
                      h.STATUS, h.GROUP_TOKEN
                 FROM F6POC_JOBS j
                 JOIN F7MVP_EXECUTIONS e ON e.JOB_ID=j.JOB_ID
                 LEFT JOIN F6POC_LEASES l ON l.JOB_ID=j.JOB_ID
                 LEFT JOIN F6POC_REJECTIONS r ON r.JOB_ID=j.JOB_ID
                 LEFT JOIN F7MVP_HOSTING h ON h.LEASE_ID=l.LEASE_ID
                ORDER BY j.CREATED_AT DESC FETCH FIRST :limit ROWS ONLY""",
            {"limit": limit},
        )
        rows = cur.fetchall()
        jobs = []
        for code, data_class, vcpu, budget, status, created, node, price, input_hash, input_count, result_hash, reason, rejected_node, hosting_status, group_token in rows:
            jobs.append({"code": code, "class": data_class, "vcpu": vcpu,
                         "budget": budget, "status": status,
                         "created": created, "node": node, "price": price,
                         "input_hash": input_hash, "input_count": input_count,
                         "result_hash": result_hash, "reason": reason,
                         "rejected_node": rejected_node,
                         "hosting_status": hosting_status,
                         "group_token": group_token})
        cur.close()
    return jobs


def pretty_db_error(exc: Exception):
    try:
        message = exc.args[0].message
    except (AttributeError, IndexError):
        message = str(exc)
    for marker, friendly in (
        ("NO_CONNECTED_ELIGIBLE_NODE_WITHIN_BUDGET", "Nenhum executor conectado atende aos requisitos e ao teto de preco."),
        ("OPERADOR_NAO_HOMOLOGADO", "O operador ainda nao foi homologado."),
        ("NO_COM_PERSISTENCIA_LOCAL", "O no mantem persistencia local."),
        ("NO_FORA_DO_BRASIL", "Carga pessoal exige processamento no Brasil."),
        ("NO_SEM_EXECUCAO_CONFIDENCIAL", "Carga pessoal exige TEE (execucao confidencial)."),
        ("TETO_DE_PRECO_EXCEDIDO", "O valor ultrapassa o teto informado."),
        ("CAPACIDADE_INSUFICIENTE", "O no nao tem capacidade para esta carga."),
    ):
        if marker in message:
            return friendly
    return message.splitlines()[0]


def format_brl(value) -> str:
    return f"R$ {Decimal(str(value)):.2f}".replace(".", ",")


def html_page(content: str, title: str = "MVP | Cloud Distribuida"):
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,"><title>{html.escape(title)}</title>
<style>
:root{{--ink:#152a3a;--muted:#587080;--blue:#1467a8;--green:#17704c;--red:#a33d35;--line:#d9e3ea;--bg:#f2f6f9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,Segoe UI,Arial,sans-serif}}
header{{background:#102c42;color:white;padding:24px max(24px,calc((100vw - 1040px)/2))}}header h1{{font-size:23px;margin:0}}header p{{margin:4px 0 0;color:#d1e0e9}}
main{{max-width:1040px;margin:28px auto;padding:0 20px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}}.card{{background:white;border:1px solid var(--line);border-radius:13px;padding:20px;overflow-x:auto;box-shadow:0 4px 14px #152a3a0a}}h2{{font-size:18px;margin:0 0 14px}}label{{display:block;font-weight:650;margin:12px 0 5px}}input,select,textarea{{width:100%;padding:10px 11px;border:1px solid #b9c9d5;border-radius:7px;font:inherit}}textarea{{min-height:90px}}button{{margin-top:17px;border:0;background:var(--blue);color:white;border-radius:7px;padding:11px 16px;font:inherit;font-weight:700;cursor:pointer}}button:hover{{background:#0d558f}}a.site-button{{display:inline-block;background:var(--blue);color:white;text-decoration:none;border-radius:7px;padding:9px 12px;font-weight:700;margin:3px 0}}a.site-button:hover{{background:#0d558f}}.hero{{background:linear-gradient(135deg,#ffffff 0%,#eef7fc 100%);border:1px solid #c9dfea;border-radius:16px;padding:28px;margin-bottom:20px}}.hero h2{{font-size:26px;margin-bottom:6px}}.hero p{{max-width:700px;margin:0;color:var(--muted)}}.actions{{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:12px;margin-top:22px}}.action{{display:block;text-decoration:none;background:white;border:1px solid #b8cedc;border-radius:11px;padding:15px;color:var(--ink);transition:transform .12s,box-shadow .12s}}.action:hover{{transform:translateY(-1px);box-shadow:0 5px 14px #152a3a18}}.action.primary{{background:var(--blue);border-color:var(--blue);color:white}}.action strong{{display:block;font-size:16px;margin-bottom:3px}}.action span{{font-size:13px;opacity:.82}}.status-line{{display:inline-flex;align-items:center;gap:7px;color:var(--green);font-weight:700;font-size:14px}}.status-dot{{width:8px;height:8px;border-radius:50%;background:#2ba66b;display:inline-block}}.section-title{{display:flex;justify-content:space-between;align-items:center;gap:12px}}details{{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}}details summary{{cursor:pointer;font-weight:700;color:var(--blue)}}.compact-table{{max-height:320px;overflow:auto}}.hint,.muted{{color:var(--muted);font-size:14px}}.alert{{padding:14px 16px;border-radius:9px;margin:0 0 20px;background:#eaf4fb;border:1px solid #b8d8ed}}.ok{{background:#eaf6ef;border-color:#b8dfc5}}.bad{{background:#fff0ee;border-color:#e7c0bb}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;padding:9px 7px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-weight:650}}.tag{{display:inline-block;padding:2px 8px;border-radius:99px;background:#e8edf0;font-size:12px;font-weight:700}}.tag.good{{background:#e3f3e9;color:var(--green)}}.tag.no{{background:#fbe8e5;color:var(--red)}}code{{font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere}}.full{{grid-column:1/-1}}footer{{max-width:1040px;margin:20px auto 40px;padding:0 20px;color:var(--muted);font-size:13px}}
 .action.active{{background:var(--blue);border-color:var(--blue);color:white}}
@media(max-width:740px){{.grid{{grid-template-columns:1fr}}.full{{grid-column:auto}}.actions{{grid-template-columns:1fr}}.hero{{padding:20px}}.hero h2{{font-size:22px}}}}
</style></head><body><header><h1>Cloud Distribuida P2P · MVP funcional</h1><p>Alocacao conforme, processamento de um lote e historico no Oracle.</p></header>
<main>{content}</main><footer>MVP academico local · Oracle Database FIAP · No executor local; atributos TEE do catalogo nao sao atestados. Use somente dados sinteticos.</footer></body></html>"""


def flow_navigation(active: str = ""):
    items = (
        ("hosting", "/hosting", "Hospedar um site", "Publicar Hello World em dois nós por 3 minutos"),
        ("processar", "/processar", "Processar uma tarefa", "Enviar lote sintético e ver o resultado"),
        ("topologia", "/topologia", "Ver a topologia", "Visualizar clientes, Oracle e executores"),
    )
    cards = "".join(
        f'<a class="action {"active" if key == active else ""}" href="{href}">'
        f'<strong>{label}</strong><span>{description}</span></a>'
        for key, href, label, description in items
    )
    return f'<nav class="actions" aria-label="Fluxos principais">{cards}</nav>'


def render_nodes(data_class="PESSOAL_SENSIVEL", vcpu_req=Decimal("4"), budget=Decimal("10")):
    rows = node_catalog(data_class, vcpu_req, budget)
    ready = {code: worker_is_ready(code) for code in WORKER_PORTS}
    body = "".join(
        "<tr>"
        f"<td><strong>{html.escape(n['code'])}</strong><br><span class='muted'>{html.escape(n['label'])}</span></td>"
        f"<td>{n['country']}</td><td>{'Sim' if n['tee'] else 'Nao'}</td>"
        f"<td>{'Sim' if n['persistence'] else 'Nao'}</td><td>{n['capacity'] - n['reserved']}</td><td>{format_brl(n['price'])}</td>"
        f"<td>{'Conectado' if ready.get(n['code']) else 'Indisponivel' if n['code'] in WORKER_PORTS else 'Somente catalogo'}</td>"
        f"<td><span class='tag {'good' if n['reason']=='ELEGIVEL' else 'no'}'>{html.escape(n['reason'])}</span></td></tr>"
        for n in rows
    )
    return "<table><thead><tr><th>No</th><th>Pais</th><th>TEE declarado</th><th>Persiste</th><th>vCPU livres</th><th>Preco estimado</th><th>Executor</th><th>Elegibilidade</th></tr></thead><tbody>" + body + "</tbody></table>"


def render_history():
    jobs = recent_jobs()
    if not jobs:
        return "<p class='muted'>Nenhuma tarefa enviada nesta versao do MVP.</p>"
    body = ""
    for job in jobs:
        if job["hosting_status"]:
            summary = f"Hello World · hospedagem {job['hosting_status']} · HTML puro"
        elif job["result_hash"]:
            summary = f"{job['input_count']} valores processados · hash do resultado {job['result_hash'][:12]}…"
        elif job["reason"]:
            summary = "Recusa: " + pretty_db_error(RuntimeError(job["reason"]))
        else:
            summary = "Sem resultado gravado no Oracle"
        price = format_brl(job["price"]) if job["price"] is not None else "—"
        body += ("<tr>" +
                 f"<td><a href='/report?job={quote(job['code'])}'><code>{html.escape(job['code'])}</code></a><br>{html.escape(job['created'])}</td>" +
                 f"<td>{html.escape(job['status'])}</td>" +
                 f"<td>{html.escape(job['node'] or '—')}</td>" +
                 f"<td>{price}</td><td>{html.escape(summary)}</td></tr>")
    return "<table><thead><tr><th>Tarefa / relatorio</th><th>Estado</th><th>No</th><th>Preco</th><th>Prova persistida</th></tr></thead><tbody>" + body + "</tbody></table>"


def report_for_job(code: str):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT j.JOB_CODE, j.DATA_CLASSIFICATION, j.VCPU_REQ, j.MAX_PRICE_BRL,
                      j.STATUS, TO_CHAR(j.CREATED_AT,'YYYY-MM-DD HH24:MI:SS'),
                      l.LEASE_ID, l.NODE_CODE, l.TOTAL_PRICE_BRL,
                      n.COUNTRY_CODE, n.TEE_ENABLED, n.LOCAL_PERSISTENCE, n.APPROVED,
                      n.OPERATOR_CNPJ, n.OPERATOR_NAME, n.OPERATOR_UF, n.GUARANTEE_BRL,
                      e.INPUT_SHA256, e.INPUT_COUNT, e.RESULT_SHA256, r.REASON,
                      s.GROSS_BRL, s.PLATFORM_FEE_BRL, s.PROVIDER_BRL, s.STATUS,
                      h.STATUS, h.EXPIRES_EPOCH, h.WORKER_PORT, h.SITE_TOKEN
                 FROM F6POC_JOBS j
                 JOIN F7MVP_EXECUTIONS e ON e.JOB_ID=j.JOB_ID
                 LEFT JOIN F6POC_LEASES l ON l.JOB_ID=j.JOB_ID
                 LEFT JOIN F6POC_NODES n ON n.NODE_CODE=l.NODE_CODE
                 LEFT JOIN F6POC_REJECTIONS r ON r.JOB_ID=j.JOB_ID
                 LEFT JOIN F7MVP_SETTLEMENTS s ON s.LEASE_ID=l.LEASE_ID
                 LEFT JOIN F7MVP_HOSTING h ON h.LEASE_ID=l.LEASE_ID
                WHERE j.JOB_CODE=:code""",
            {"code": code},
        )
        row = cur.fetchone()
        cur.close()
    if row is None:
        return None
    (job_code, data_class, vcpu, budget, status, created, lease_id, node_code,
     price, country, tee, persistence, approved, operator_cnpj, operator_name,
     operator_uf, guarantee, input_hash, input_count,
     result_hash, reason, gross, fee, provider_value, settlement_status,
     hosting_status, hosting_expires, hosting_port, hosting_token) = row
    events = audit_for_job(code) if lease_id else []
    integrity = "INTEGRA" if verify_audit_chain(events) else "SEM TRILHA" if not events else "ROMPIDA"
    def cell(label, value):
        return f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value if value is not None else '—'))}</td></tr>"
    facts = "".join([
        cell("Tarefa", job_code), cell("Criada em", created),
        cell("Classificacao", data_class), cell("Estado", status),
        cell("vCPU solicitadas", vcpu), cell("Teto", format_brl(budget)),
        cell("Lease Oracle", lease_id), cell("No selecionado", node_code),
        cell("Preco", format_brl(price) if price is not None else None),
        cell("Pais declarado", country.strip() if country else None),
        cell("TEE declarado", "Sim" if tee else "Nao" if tee is not None else None),
        cell("Persistencia local declarada", "Sim" if persistence else "Nao" if persistence is not None else None),
        cell("No aprovado no catalogo", "Sim" if approved else "Nao" if approved is not None else None),
        cell("Operador cadastrado", operator_name),
        cell("CNPJ de demonstracao", operator_cnpj),
        cell("UF do operador declarada", operator_uf.strip() if operator_uf else None),
        cell("Garantia declarada", format_brl(guarantee) if guarantee is not None else None),
        cell("Quantidade de paginas HTML" if hosting_status else "Quantidade de valores", input_count),
        cell("SHA-256 da entrada", input_hash), cell("SHA-256 do resultado", result_hash),
        cell("Integridade da trilha", integrity),
        cell("Motivo de recusa", pretty_db_error(RuntimeError(reason)) if reason else None),
        cell("Reserva/liquidacao demonstrativa", settlement_status),
        cell("Valor bruto demonstrativo", format_brl(gross) if gross is not None else None),
        cell("Taxa da plataforma (10%)", format_brl(fee) if fee is not None else None),
        cell("Repasse ao operador", format_brl(provider_value) if provider_value is not None else None),
        cell("Estado da hospedagem", hosting_status),
        cell("Fim previsto da hospedagem", datetime.fromtimestamp(int(hosting_expires)).strftime("%Y-%m-%d %H:%M:%S") if hosting_expires else None),
    ])
    event_rows = "".join(
        "<tr>" + "".join(f"<td><code>{html.escape(str(value))}</code></td>" for value in
                           (seq, event_type, actor, details, previous_hash, event_hash, when)) + "</tr>"
        for _lease, seq, event_type, actor, details, previous_hash, event_hash, when in events
    )
    if not events:
        event_rows = "<tr><td colspan='7'>Sem eventos de lease; a tentativa nao foi autorizada.</td></tr>"
    premium = "—"
    if price is not None:
        catalog = node_catalog(data_class, Decimal(str(vcpu)), Decimal(str(budget)))
        rejected = [n["price"] for n in catalog if n["reason"] != "ELEGIVEL"]
        if rejected:
            premium = format_brl(Decimal(str(price)) - min(rejected))
    hosting_link = (f" · <a href='/hosting'>Ver hospedagens</a>" if hosting_status else "")
    content = (f"<p><a href='/'>← Voltar ao painel</a> · <a href='/topologia?job={quote(code)}'>Ver caminho no grafo</a>{hosting_link}</p><section class='card'>"
               f"<h2>Relatorio tecnico por execucao</h2><p class='muted'>Dados de controle persistidos no Oracle; o {'HTML do Hello World' if hosting_status else 'lote e o resultado'} nao {'e armazenado' if hosting_status else 'sao armazenados'} no banco.</p>"
               f"<table>{facts}</table><p>Premio ilustrativo frente ao menor no rejeitado do catalogo: <strong>{html.escape(premium)}</strong>.</p>"
               "<p class='muted'>Neste MVP, o nó é um registro no Oracle que representa um futuro computador ocioso oferecido para aluguel. Um worker local simula a execução desse computador. Os valores financeiros são demonstrativos; nenhum pagamento real foi movimentado. O cadastro de operador é fictício. O catálogo declara território, homologação e TEE; este MVP não atesta local físico, enclave ou ausência de gravação no hardware.</p>"
               "</section><section class='card' style='margin-top:20px'><h2>Trilha de custodia Oracle</h2>"
               f"<p>Verificacao SHA-256: <strong>{integrity}</strong>; {len(events)} evento(s).</p>"
               "<table><thead><tr><th>Seq</th><th>Evento</th><th>Ator</th><th>Detalhe</th><th>Hash anterior</th><th>Hash do evento</th><th>Horario</th></tr></thead>"
               f"<tbody>{event_rows}</tbody></table></section>")
    return html_page(content, f"Relatorio | {code}")


def home_page(message="", success=False, csrf_token=CSRF_TOKEN):
    try:
        nodes = render_nodes()
        history = render_history()
        db_status = "Oracle conectado · historico e catalogo carregados"
    except Exception as exc:
        nodes = "<p class='muted'>Nao foi possivel consultar os nos. Confira a conexao Oracle.</p>"
        history = "<p class='muted'>Historico indisponivel sem Oracle.</p>"
        db_status = f"Falha de conexao: {html.escape(pretty_db_error(exc))}"
    alert = ""
    if message:
        alert = f"<div class='alert {'ok' if success else 'bad'}'><strong>{'Concluido' if success else 'Resultado'}</strong><br>{html.escape(message)}</div>"
    content = f"""{alert}<section class='hero'><div class='status-line'><span class='status-dot'></span>{html.escape(db_status)}</div><h2>O que você quer demonstrar?</h2><p>Escolha um fluxo e acompanhe como o Oracle seleciona e reserva computadores ociosos ofertados para aluguel.</p>{flow_navigation()}</section><section class='card'><div class='section-title'><h2>Como funciona</h2><span class='tag'>3 passos</span></div><ol><li>O Oracle consulta os nós ofertantes e suas regras.</li><li>O sistema reserva capacidade no grupo escolhido.</li><li>O worker local simula o computador do operador.</li></ol><p class='muted'>No produto final, os workers seriam máquinas reais de pessoas ou empresas que alugam capacidade ociosa.</p><p><a href='/operator'>Cadastrar operador e nó de demonstração →</a></p></section><div class='grid'><section class='card full'><details><summary>Ver histórico e relatórios</summary><div class='compact-table' style='margin-top:14px'>{history}</div></details></section><section class='card full'><details><summary>Ver catálogo Oracle de computadores ofertantes</summary><div class='compact-table' style='margin-top:14px'>{nodes}</div></details></section></div>"""
    return html_page(content)


def processing_page(message="", success=False, csrf_token=CSRF_TOKEN):
    alert = (f"<div class='alert {'ok' if success else 'bad'}'><strong>{'Concluído' if success else 'Resultado'}</strong><br>{html.escape(message)}</div>"
             if message else "")
    try:
        db_status = "Oracle conectado · pronto para programar"
        history = render_history()
    except Exception as exc:
        db_status = f"Falha de conexão: {html.escape(pretty_db_error(exc))}"
        history = "<p class='muted'>Histórico indisponível sem Oracle.</p>"
    classification_options = "".join(
        f'<option value="{c}" {"selected" if c == "PESSOAL_SENSIVEL" else ""}>{c.replace("_", " ")}</option>'
        for c in CLASSES
    )
    form = f"""<section class="card"><div class="section-title"><h2>Programar uma tarefa</h2><span class="tag good">Oracle pronto</span></div>
<p class="muted">Envie um lote sintético e veja o Oracle escolher um computador ofertante elegível.</p>
<form method="post" action="/allocate"><input type="hidden" name="csrf" value="{csrf_token}">
<label for="numbers">Lote de números</label><textarea id="numbers" name="numbers" required>12, 18, 30, 40</textarea>
<div class="grid" style="gap:12px"><div><label for="vcpu">vCPU solicitadas</label><input id="vcpu" name="vcpu" type="number" min="1" step="1" value="4" required></div>
<div><label for="budget">Teto de preço (R$)</label><input id="budget" name="budget" type="number" min="0.01" step="0.01" value="10" required></div></div>
<details><summary>Regras avançadas do teste</summary>
<label for="classification">Classificação dos dados</label><select id="classification" name="classification">{classification_options}</select>
<label for="mode">Modo de alocação</label><select id="mode" name="mode"><option value="auto">Automático: menor preço elegível</option><option value="force">Escolher nó manualmente</option></select>
<label for="node">Nó no modo manual</label><select id="node" name="node"><option value="BR-SEM-TEE">BR-SEM-TEE · sem TEE</option><option value="EXT-TEE-01">EXT-TEE-01 · fora do Brasil</option><option value="BR-PERSIST-01">BR-PERSIST-01 · persiste localmente</option><option value="BR-TEE-01">BR-TEE-01 · executor conforme</option><option value="BR-TEE-02">BR-TEE-02 · segundo executor</option></select>
</details><button type="submit">Programar tarefa</button></form>
<p class="hint">Use apenas números fictícios. O lote e o resultado não são gravados no Oracle; ficam apenas na resposta imediata.</p></section>"""
    content = f"""{alert}<section class='hero'><div class='status-line'><span class='status-dot'></span>{db_status}</div><h2>Programar tarefa</h2><p>Escolha os requisitos da carga. O Oracle consulta os computadores ofertantes, reserva capacidade e envia o trabalho ao worker que simula o operador.</p>{flow_navigation('processar')}</section><div class='grid'>{form}<section class='card'><h2>Depois da execução</h2><p>Abra o relatório para conferir o lease, o preço, os hashes e a trilha de auditoria.</p><a href='/topologia'>Ver a topologia do grupo →</a><p class='muted'>Para hospedar um site em vez de processar um lote, use o fluxo de hospedagem no topo.</p></section><section class='card full'><details><summary>Ver histórico e relatórios</summary><div class='compact-table' style='margin-top:14px'>{history}</div></details></section></div>"""
    return html_page(content, "Programar tarefa | Cloud Distribuida")


def hosting_page(message="", success=False):
    alert = (f"<div class='alert {'ok' if success else 'bad'}'>{html.escape(message)}</div>"
             if message else "")
    rows = []
    for site in hosting_groups():
        members = site["members"]
        group_token = site["token"]
        states = {member["status"] for member in members}
        status = states.pop() if len(states) == 1 else "ENCERRANDO"
        if status == "ACTIVE" and time.time() >= site["expires"]:
            status = "ENCERRANDO"
        expires = datetime.fromtimestamp(site["expires"]).strftime("%H:%M:%S")
        url = (f"http://{HOST}:{APP_PORT}/site/{quote(group_token)}" if group_token else
               f"http://{HOST}:{members[0]['port']}/site/{quote(members[0]['token'])}")
        link = (f'<a class="site-button" href="{url}" target="_blank" rel="noopener">Abrir site hospedado</a>'
                if status == "ACTIVE" else "—")
        countdown = (f'<br><span class="muted" data-expires="{site["expires"]}">faltam até 03:00</span>'
                     if status == "ACTIVE" else "")
        group_value = (f'<input type="hidden" name="group" value="{html.escape(group_token)}">'
                       if group_token else f'<input type="hidden" name="lease" value="{members[0]["lease"]}">')
        stop_button = (f'<form method="post" action="/hosting/stop">'
                       f'<input type="hidden" name="csrf" value="{CSRF_TOKEN}">'
                       f'{group_value}'
                       '<button type="submit">Encerrar agora</button></form>'
                       if status == "ACTIVE" else "")
        demo_link = (f'<br><a href="/hosting/demo?group={quote(group_token)}">Simular 6 visitas</a>'
                     if group_token and status == "ACTIVE" else "")
        with SITE_GROUPS_LOCK:
            live = SITE_GROUPS.get(group_token) if group_token else None
            counts = dict(live["counts"]) if live else {}
        count_text = (f'<br><span class="muted">Visitas: ' + ", ".join(
            f'{html.escape(node)} {count}' for node, count in counts.items()) + '</span>'
                      if counts else "")
        nodes_text = "<br>".join(
            f'<strong>{html.escape(member["node"])} ({member["vcpu"]} vCPU)</strong>'
            f'<br><span class="muted">{html.escape(member["operator"] or "Operador demo")}</span>'
            for member in members
        )
        group_label = html.escape(site.get("group_name") or "Grupo sem nome")
        job_links = " + ".join(f'<a href="/report?job={quote(member["job"])}"><code>{html.escape(member["job"])}</code></a>' for member in members)
        rows.append(
            "<tr>" +
            f'<td>{job_links}</td>' +
            f'<td><strong>{group_label}</strong><br><span class="muted">{len(members)} nó(s)</span></td>' +
            f'<td>{nodes_text}{count_text}</td>' +
            f'<td>{html.escape(status)}<br><span class="muted">até {expires}</span>{countdown}</td>' +
            f'<td>{link}{demo_link}{stop_button}</td></tr>'
        )
    history = ("<table><thead><tr><th>Tarefa</th><th>Grupo computacional</th><th>Executor</th><th>Estado / expira às</th><th>Site</th></tr></thead>"
               f"<tbody>{''.join(rows)}</tbody></table>" if rows else
               "<p class='muted'>Nenhuma hospedagem iniciada.</p>")
    content = f"""<p><a href='/'>← Voltar ao painel</a></p>{alert}{flow_navigation('hosting')}
<div class='grid'><section class='card'><h2>Hospedar conteúdo por 3 minutos</h2>
<p>Um <strong>grupo computacional</strong> é um conjunto nomeado de leases da mesma tarefa. No modo dividido, a capacidade é repartida entre dois nós; no modo concentrado, todo o pedido vai para um nó. O Oracle simula o catálogo e os leases; os workers locais simulam os computadores dos operadores.</p>
<form method='post' action='/hosting/start'><input type='hidden' name='csrf' value='{CSRF_TOKEN}'>
<label for='group_name'>Nome do grupo computacional</label>
<input id='group_name' name='group_name' maxlength='80' value='Grupo Web Demo' required>
<label for='group_mode'>Distribuição da capacidade</label>
<select id='group_mode' name='group_mode'><option value='split' selected>Dividir entre 2 nós (recomendado)</option><option value='single'>Concentrar em 1 nó</option></select>
<label for='vcpu'>Poder computacional total (vCPU)</label>
<select id='vcpu' name='vcpu'><option>1</option><option selected>2</option><option>4</option><option>8</option><option>16</option><option>32</option></select>
<label for='budget'>Teto de preço demonstrativo de 1 hora (R$)</label>
<input id='budget' name='budget' type='number' min='0.01' step='0.01' value='10' required>
<label for='html_content'>HTML puro a hospedar (sem scripts)</label>
<textarea id='html_content' name='html_content' maxlength='20000' required>&lt;h1&gt;Minha página&lt;/h1&gt;
&lt;p&gt;Hospedada pela Cloud Distribuída.&lt;/p&gt;
&lt;p&gt;Nó atual: &lt;strong&gt;__NODE__&lt;/strong&gt;&lt;/p&gt;</textarea>
<button type='submit'>Hospedar conteúdo</button>
<button type='button' id='hello-button' style='background:#587080'>Preencher e hospedar Hello World</button></form>
<p class='hint'>A vCPU é capacidade reservada no Oracle; não muda a velocidade do HTML. O preço é demonstrativo, sem cobrança real. Os dois workers rodam neste computador, sem criar instância OCI.</p></section>
<section class='card'><h2>O que o cliente verá</h2><pre style='white-space:pre-wrap;background:#f2f6f9;padding:14px;border-radius:8px'>&lt;h1&gt;Hello World&lt;/h1&gt;</pre>
<p>O mesmo HTML puro fica nos nós do grupo. Clique em <strong>Abrir site hospedado</strong> para ver o conteúdo e o nome do nó que atendeu a visita. Atualize a página para alternar entre os nós. Quando o prazo termina, o link responde <code>410 Gone</code> e o Oracle libera as reservas.</p>
<p class='hint'>A conexão com Oracle é aberta somente para registrar e encerrar a tarefa; não fica aberta durante os 3 minutos.</p></section>
<section class='card full'><h2>Hospedagens recentes</h2>{history}</section></div>
<script>const timers=[...document.querySelectorAll('[data-expires]')];
function updateTimers(){{for(const el of timers){{const left=Math.max(0,Number(el.dataset.expires)-Math.floor(Date.now()/1000));
el.textContent='faltam '+String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0');
if(left===0){{location.href='/hosting';return;}}}}}}
updateTimers();if(timers.length)setInterval(updateTimers,1000);</script>"""
    content += "<script>const hello=document.getElementById('hello-button');if(hello)hello.addEventListener('click',()=>{document.getElementById('html_content').value='<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Hello World</title><h1>Hello World</h1><p>Hospedado por 3 minutos no executor local do MVP.</p><p>Servido pelo nó <strong>__NODE__</strong>.</p></html>';hello.form.submit();});</script>"
    return html_page(content, "Hospedagem | Cloud Distribuida")


def topology_page(selected_code="", message="", success=False):
    jobs = recent_jobs(20)
    selected = next((job for job in jobs if job["code"] == selected_code), None)
    if selected is None:
        selected = next((job for job in jobs if job["status"] == "COMPLETED"), jobs[0] if jobs else None)
    data_class = selected["class"] if selected else "PESSOAL_SENSIVEL"
    vcpu = Decimal(str(selected["vcpu"])) if selected else Decimal("4")
    budget = Decimal(str(selected["budget"])) if selected else Decimal("10")
    nodes = node_catalog(data_class, vcpu, budget)
    for node in nodes:
        health = worker_health(node["code"])
        node["connected"] = health.get("status") == "READY" and health.get("node_code") == node["code"]
        node["enabled"] = bool(health.get("enabled"))
        node["price_label"] = format_brl(node["price"])
    for job in jobs:
        job["price_label"] = format_brl(job["price"]) if job["price"] is not None else None
        job["budget_label"] = format_brl(job["budget"])
    alert = f"<div class='alert {'ok' if success else 'bad'}'>{html.escape(message)}</div>" if message else ""
    return html_page(alert + flow_navigation('topologia') + render_topology(nodes, jobs, selected["code"] if selected else "", CSRF_TOKEN), "Topologia | Cloud Distribuida")


def operator_page(message="", success=False):
    alert = ""
    if message:
        alert = f"<div class='alert {'ok' if success else 'bad'}'>{html.escape(message)}</div>"
    content = f"""<p><a href='/'>← Voltar ao painel</a></p>{alert}{flow_navigation()}
<section class="card"><h2>Cadastro demonstrativo de operador e no</h2>
<p class="muted">O cadastro entra como pendente e nao participa de alocacoes. CNPJ, garantia e atributos tecnicos declarados aqui nao constituem verificacao real.</p>
<form method="post" action="/operator/register"><input type="hidden" name="csrf" value="{CSRF_TOKEN}">
<div class="grid">
<div><label for="operator_name">Razao social</label><input id="operator_name" name="operator_name" maxlength="100" required></div>
<div><label for="cnpj">CNPJ (14 digitos)</label><input id="cnpj" name="cnpj" maxlength="18" required></div>
<div><label for="uf">UF do operador</label><input id="uf" name="uf" maxlength="2" value="SP" required></div>
<div><label for="guarantee">Garantia declarada (R$)</label><input id="guarantee" name="guarantee" type="number" min="0" step="0.01" value="0" required></div>
<div><label for="node_code">Codigo do no</label><input id="node_code" name="node_code" maxlength="30" placeholder="BR-DEMO-02" required></div>
<div><label for="node_label">Descricao do no</label><input id="node_label" name="node_label" maxlength="100" required></div>
<div><label for="capacity">Capacidade em vCPU</label><input id="capacity" name="capacity" type="number" min="1" step="1" value="4" required></div>
<div><label for="rate">Preco por vCPU-hora (R$)</label><input id="rate" name="rate" type="number" min="0" step="0.01" value="0.50" required></div>
</div><p><label><input name="tee" type="checkbox" style="width:auto"> TEE declarado no equipamento</label></p>
<p><label><input name="persistence" type="checkbox" style="width:auto"> No mantem persistencia local</label></p>
<button type="submit">Enviar para homologacao manual</button></form>
<p class="hint">A decisao manual de homologacao e demonstrada pelo script <code>approve_node.py</code> apos conferencia externa. O MVP nao atesta hardware nem valida deposito financeiro.</p></section>"""
    return html_page(content, "Cadastro de operador | MVP")


def perform_allocation(values):
    classification, vcpu, budget = parse_submission(values)
    numbers = parse_numbers(values.get("numbers", ""))

    code = "F7-" + datetime.now().strftime("%y%m%d%H%M%S") + "-" + secrets.token_hex(4).upper()
    register_job(code, classification, vcpu, budget, numbers)
    catalog = node_catalog(classification, vcpu, budget)
    eligible = [n for n in catalog if n["reason"] == "ELEGIVEL" and worker_is_ready(n["code"])]
    mode = values.get("mode", "auto")
    if mode == "force":
        chosen = values.get("node", "")
    elif eligible:
        chosen = eligible[0]["code"]
    else:
        record_rejection(code, None, "NO_CONNECTED_ELIGIBLE_NODE_WITHIN_BUDGET")
        mark_job_failed(code)
        return f"Carga {code}: nenhum executor conectado atende aos requisitos e ao teto de preco.", False

    chosen_entry = next((node for node in catalog if node["code"] == chosen), None)
    if chosen_entry is None:
        record_rejection(code, None, "NO_DESCONHECIDO")
        mark_job_failed(code)
        return f"Carga {code}: no escolhido nao existe no catalogo.", False
    if chosen_entry["reason"] == "ELEGIVEL" and not worker_is_ready(chosen):
        record_rejection(code, chosen, "EXECUTOR_INDISPONIVEL")
        mark_job_failed(code)
        return f"Carga {code}: o no {chosen} e elegivel, mas nao possui executor ativo.", False

    try:
        lease_id, total = allocate(code, chosen)
    except oracledb.DatabaseError as exc:
        reason = pretty_db_error(exc)
        record_rejection(code, chosen, reason)
        mark_job_failed(code)
        return f"Carga {code}: Oracle recusou a tentativa no {chosen}. Motivo: {reason} Tentativa registrada; nenhum lease foi criado.", False

    try:
        result = execute_worker(code, chosen, numbers)
        complete_lease(lease_id, result)
    except (urllib.error.URLError, TimeoutError, KeyError, RuntimeError, oracledb.DatabaseError) as exc:
        try:
            fail_lease(lease_id)
            return f"Lease #{lease_id} falhou; o Oracle marcou FAILED e liberou a capacidade: {str(exc)}", False
        except RuntimeError:
            status = lease_status(lease_id)
            if status in ("COMPLETED", "FAILED"):
                return (f"O worker sinalizou falha, mas o lease #{lease_id} ja esta em estado terminal "
                        f"{status} no Oracle; o estado nao foi alterado."), False
            return f"Lease #{lease_id} nao foi marcado como FAILED; estado atual: {status or 'desconhecido'}. Verifique a reconciliacao.", False
        except oracledb.DatabaseError as release_exc:
            return (f"Lease #{lease_id} autorizado, mas a falha precisa de reconciliacao: "
                    f"{str(release_exc)}; causa original: {str(exc)}"), False

    events = audit_for_job(code)
    integrity = "integra" if verify_audit_chain(events) else "COM ATENCAO: hash nao confere"
    summary = result["result"]
    return (f"Carga {code} processada no {chosen} por {format_brl(total)}: "
            f"{summary['count']} numeros, soma {summary['sum']}, media {summary['average']}. Lease #{lease_id} concluido; "
            f"{len(events)} eventos no Oracle, integridade da trilha {integrity}."), True


class AppHandler(BaseHTTPRequestHandler):
    def send_html(self, source: str, status=200, set_csrf_cookie=False):
        raw = source.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if set_csrf_cookie:
            self.send_header("Set-Cookie", f"f6poc_csrf={CSRF_TOKEN}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self.send_html(home_page(csrf_token=CSRF_TOKEN), set_csrf_cookie=True)
        elif parsed.path == "/processar":
            self.send_html(processing_page(csrf_token=CSRF_TOKEN), set_csrf_cookie=True)
        elif parsed.path == "/operator":
            self.send_html(operator_page(), set_csrf_cookie=True)
        elif parsed.path == "/hosting":
            self.send_html(hosting_page(), set_csrf_cookie=True)
        elif parsed.path.startswith("/site/"):
            group_token = parsed.path.removeprefix("/site/")
            if not group_token or len(group_token) > 64:
                self.send_error(404)
                return
            status, body, node = fetch_group_site(group_token)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if node:
                self.send_header("X-Served-By", node)
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/hosting/demo":
            group_token = parse_qs(parsed.query).get("group", [""])[0]
            if not group_token or len(group_token) > 64:
                self.send_error(400)
                return
            results = [fetch_group_site(group_token)[2] for _ in range(6)]
            if not any(results):
                self.send_html(hosting_page("O site nao esta mais ativo."), set_csrf_cookie=True)
            else:
                summary = ", ".join(f"{node}: {results.count(node)}" for node in WORKER_PORTS)
                self.send_html(hosting_page(f"Seis visitas enviadas: {summary}.", True), set_csrf_cookie=True)
        elif parsed.path == "/topologia":
            code = parse_qs(parsed.query).get("job", [""])[0]
            if len(code) > 40:
                self.send_error(400)
                return
            self.send_html(topology_page(code))
        elif parsed.path == "/report":
            code = parse_qs(parsed.query).get("job", [""])[0]
            if not code or len(code) > 40:
                self.send_error(400)
                return
            report = report_for_job(code)
            if report is None:
                self.send_error(404)
            else:
                self.send_html(report)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/allocate", "/operator/register", "/hosting/start", "/hosting/stop", "/node/toggle"):
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size > 32768:
            self.send_error(413)
            return
        values = {key: items[0] for key, items in parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True).items()}
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        cookie_token = cookie.get("f6poc_csrf")
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://{HOST}:{APP_PORT}", f"http://localhost:{APP_PORT}"}
        if not cookie_token or cookie_token.value != CSRF_TOKEN or values.get("csrf") != CSRF_TOKEN or (origin and origin not in allowed_origins):
            error_page = (operator_page if self.path == "/operator/register" else
                          hosting_page if self.path.startswith("/hosting/") else
                          lambda msg: topology_page(message=msg) if self.path == "/node/toggle" else home_page(msg))
            self.send_html(error_page("Formulario expirado ou origem invalida. Atualize a pagina e tente novamente."), 403, set_csrf_cookie=True)
            return
        try:
            if self.path == "/operator/register":
                operator_data = parse_operator(values)
                register_operator_node(operator_data)
                self.send_html(operator_page(f"No {operator_data['code']} cadastrado como pendente. Homologacao manual necessaria.", True))
            elif self.path == "/hosting/start":
                message, success = perform_hosting(values)
                self.send_html(hosting_page(message, success))
            elif self.path == "/hosting/stop":
                group_token = values.get("group", "")
                if group_token:
                    if len(group_token) > 64:
                        raise ValueError("Identificador de hospedagem invalido.")
                    stopped = cancel_group(group_token)
                else:
                    lease_id = int(values.get("lease", "0"))
                    if lease_id <= 0:
                        raise ValueError("Identificador de hospedagem invalido.")
                    stopped = cancel_hosting(lease_id)
                self.send_html(hosting_page("Hospedagem encerrada e capacidade liberada." if stopped else
                                            "Hospedagem ja encerrada ou nao encontrada.", stopped))
            elif self.path == "/node/toggle":
                node_code = values.get("node", "")
                enabled_value = values.get("enabled", "")
                if enabled_value not in ("0", "1"):
                    raise ValueError("Estado do nó inválido.")
                result = set_worker_enabled(node_code, enabled_value == "1")
                state = "ativado" if result.get("enabled") else "desativado"
                self.send_html(topology_page(message=f"Nó {node_code} {state} na simulação.", success=True))
            else:
                message, success = perform_allocation(values)
                self.send_html(processing_page(message, success))
        except (ValueError, RuntimeError, oracledb.DatabaseError) as exc:
            error_page = (operator_page if self.path == "/operator/register" else
                          hosting_page if self.path.startswith("/hosting/") else
                          topology_page if self.path == "/node/toggle" else home_page)
            self.send_html(error_page(pretty_db_error(exc)), 400)

    def log_message(self, fmt, *args):
        print("[app] " + fmt % args)


def serve():
    cancel_active_hosting()  # Uma reinicializacao encerra sites que perderam o worker em memoria.
    app = ThreadingHTTPServer((HOST, APP_PORT), AppHandler)
    print(f"Aplicacao: http://{HOST}:{APP_PORT}")
    print("Oracle: conexao ativa por solicitacao; pressione Ctrl+C para encerrar.")
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o MVP.")
    finally:
        app.server_close()
        cancel_active_hosting()


def main():
    parser = argparse.ArgumentParser(description="MVP de alocacao e processamento com Oracle")
    parser.add_argument("--setup", action="store_true", help="Cria objetos F6POC_* e cadastra nos de demonstracao")
    parser.add_argument("--serve", action="store_true", help="Inicia somente a interface web")
    args = parser.parse_args()
    if args.setup:
        setup_schema()
        print("Setup Oracle concluido. Objetos F6POC_* criados/verificados e nos de demo carregados.")
    if args.serve or not args.setup:
        serve()


if __name__ == "__main__":
    main()
