"""Smoke tests against the actual Oracle schema; every test transaction rolls back."""
from __future__ import annotations

import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import oracledb

from app import connection


def run():
    conn = connection()
    cur = conn.cursor()
    cur.execute("SELECT OBJECT_NAME, STATUS FROM USER_OBJECTS WHERE (OBJECT_NAME LIKE 'F6POC_%' OR OBJECT_NAME LIKE 'F7MVP_%' OR OBJECT_NAME LIKE 'TRG_F6POC_%' OR OBJECT_NAME LIKE 'IX_F6POC_%') AND OBJECT_TYPE IN ('TABLE','INDEX','PROCEDURE','TRIGGER') ORDER BY OBJECT_NAME")
    objects = cur.fetchall()
    invalid = [name for name, status in objects if status != "VALID"]
    if invalid:
        raise AssertionError("Objetos Oracle invalidos: " + ", ".join(invalid))
    required = {"F6POC_NODES", "F6POC_JOBS", "F6POC_LEASES", "F6POC_AUDIT_EVENTS", "F6POC_REJECTIONS", "F7MVP_EXECUTIONS", "F7MVP_SETTLEMENTS", "F7MVP_HOSTING", "F6POC_ALLOCATE", "IX_F6POC_JOB_STATUS", "TRG_F6POC_LEASE_GUARD", "TRG_F6POC_LEASE_NODE_IMMUTABLE", "TRG_F6POC_LEASE_DELETE_GUARD", "TRG_F6POC_LEASE_AUDIT"}
    names = {name for name, _ in objects}
    if not required.issubset(names):
        raise AssertionError("Faltam objetos: " + ", ".join(sorted(required - names)))
    print(f"PASS: {len(objects)} objetos do MVP encontrados e VALID.")

    cur.execute("SELECT COUNT(*) FROM F6POC_NODES")
    count = cur.fetchone()[0]
    if count < 4:
        raise AssertionError(f"Esperados 4 nos ou mais; encontrados {count}.")
    print(f"PASS: {count} nos simulados carregados no Oracle.")
    cur.close()
    conn.close()

    run_concurrent_capacity_check()
    run_fractional_vcpu_check()
    run_maximum_total_price_check()

    valid_code = "T6-OK-" + secrets.token_hex(4).upper()
    conn = connection()
    cur = conn.cursor()
    cur.execute("UPDATE F6POC_NODES SET VCPU_CAPACITY=4 WHERE NODE_CODE='BR-TEE-01'")
    cur.execute("INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:c,'PESSOAL_SENSIVEL',4,10)", {"c": valid_code})
    cur.callproc("F6POC_ALLOCATE", [valid_code, "BR-TEE-01"])
    cur.execute("SELECT l.LEASE_ID,l.STATUS,l.TOTAL_PRICE_BRL,j.STATUS FROM F6POC_LEASES l JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID WHERE j.JOB_CODE=:c", {"c": valid_code})
    lease_id, lease_status, price, job_status = cur.fetchone()
    if lease_status != "AUTHORIZED" or job_status != "ALLOCATED" or float(price) != 2.0:
        raise AssertionError("Lease elegivel nao foi criado com preco/estado esperado.")
    cur.execute("SELECT VCPU_RESERVED FROM F6POC_NODES WHERE NODE_CODE='BR-TEE-01'")
    if cur.fetchone()[0] != 4:
        raise AssertionError("A capacidade do no nao foi reservada ao criar o lease.")
    try:
        cur.execute("DELETE FROM F6POC_LEASES WHERE LEASE_ID=:id", {"id": lease_id})
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) != 20020:
            raise
    else:
        raise AssertionError("Oracle aceitou apagar um lease autorizado.")
    cur.execute("SELECT VCPU_RESERVED FROM F6POC_NODES WHERE NODE_CODE='BR-TEE-01'")
    if cur.fetchone()[0] != 4:
        raise AssertionError("Tentativa de exclusao liberou ou corrompeu a reserva ativa.")
    print("PASS: Oracle impede excluir lease ativo sem liberar capacidade (ORA-20020).")
    try:
        cur.execute("UPDATE F6POC_LEASES SET NODE_CODE='EXT-TEE-01' WHERE LEASE_ID=:id", {"id": lease_id})
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) != 20019:
            raise
    else:
        raise AssertionError("Oracle aceitou mudar o no de um lease autorizado.")
    cur.execute("SELECT VCPU_RESERVED FROM F6POC_NODES WHERE NODE_CODE='EXT-TEE-01'")
    if cur.fetchone()[0] != 0:
        raise AssertionError("Tentativa de alterar o no moveu reserva de capacidade indevidamente.")
    print("PASS: Oracle impede alterar o no de um lease autorizado (ORA-20019).")
    capacity_code = "T6-CAP-" + secrets.token_hex(4).upper()
    cur.execute("INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:c,'PESSOAL_SENSIVEL',1,10)", {"c": capacity_code})
    try:
        cur.callproc("F6POC_ALLOCATE", [capacity_code, "BR-TEE-01"])
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) != 20014:
            raise
    else:
        raise AssertionError("Oracle aceitou mais vCPU do que a capacidade reservada permite.")
    cur.execute("SELECT LEASE_ID,EVENT_SEQ,EVENT_TYPE,ACTOR,DETAILS,PREVIOUS_HASH,EVENT_HASH FROM F6POC_AUDIT_EVENTS WHERE LEASE_ID=:id ORDER BY EVENT_SEQ", {"id": lease_id})
    audit1 = cur.fetchall()
    first_canonical = f"{audit1[0][0]}|{audit1[0][1]}|{audit1[0][2]}|{audit1[0][3]}|{audit1[0][4]}|-" if audit1 else ""
    if len(audit1) != 1 or audit1[0][1] != 1 or audit1[0][5] != "-" or audit1[0][6] != hashlib.sha256(first_canonical.encode()).hexdigest().upper():
        raise AssertionError("Evento inicial da trilha nao foi gerado corretamente.")
    cur.execute("UPDATE F6POC_LEASES SET STATUS='COMPLETED' WHERE LEASE_ID=:id", {"id": lease_id})
    cur.execute("SELECT VCPU_RESERVED FROM F6POC_NODES WHERE NODE_CODE='BR-TEE-01'")
    if cur.fetchone()[0] != 0:
        raise AssertionError("Capacidade nao foi liberada ao concluir o lease.")
    cur.execute("SELECT LEASE_ID,EVENT_SEQ,EVENT_TYPE,ACTOR,DETAILS,PREVIOUS_HASH,EVENT_HASH FROM F6POC_AUDIT_EVENTS WHERE LEASE_ID=:id ORDER BY EVENT_SEQ", {"id": lease_id})
    audit2 = cur.fetchall()
    second_canonical = f"{audit2[1][0]}|{audit2[1][1]}|{audit2[1][2]}|{audit2[1][3]}|{audit2[1][4]}|{audit2[0][6]}" if len(audit2) == 2 else ""
    if len(audit2) != 2 or audit2[1][5] != audit2[0][6] or audit2[1][6] != hashlib.sha256(second_canonical.encode()).hexdigest().upper():
        raise AssertionError("Encadeamento da trilha nao foi mantido ao concluir.")
    cur.execute("SAVEPOINT failed_lease_test")
    failed_code = "T6-FAIL-" + secrets.token_hex(4).upper()
    cur.execute("INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:c,'PESSOAL_SENSIVEL',2,10)", {"c": failed_code})
    cur.callproc("F6POC_ALLOCATE", [failed_code, "BR-TEE-01"])
    cur.execute("SELECT LEASE_ID FROM F6POC_LEASES l JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID WHERE j.JOB_CODE=:c", {"c": failed_code})
    failed_lease_id = cur.fetchone()[0]
    cur.execute("UPDATE F6POC_LEASES SET STATUS='FAILED' WHERE LEASE_ID=:id", {"id": failed_lease_id})
    cur.execute("SELECT VCPU_RESERVED FROM F6POC_NODES WHERE NODE_CODE='BR-TEE-01'")
    if cur.fetchone()[0] != 0:
        raise AssertionError("Falha do worker nao liberou a capacidade reservada.")
    cur.execute("SELECT STATUS FROM F6POC_JOBS WHERE JOB_CODE=:c", {"c": failed_code})
    if cur.fetchone()[0] != "FAILED":
        raise AssertionError("Falha nao propagou o estado terminal ao job.")
    try:
        cur.execute("UPDATE F6POC_LEASES SET STATUS='COMPLETED' WHERE LEASE_ID=:id", {"id": failed_lease_id})
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) != 20018:
            raise
    else:
        raise AssertionError("Oracle aceitou a alteracao de um lease terminal.")
    cur.execute("ROLLBACK TO SAVEPOINT failed_lease_test")
    print("PASS: concluir/falhar lease libera capacidade; no do lease e estado terminal sao imutaveis (ORA-20019 / ORA-20018).")
    conn.rollback()
    cur.close()
    conn.close()
    print("PASS: Oracle autorizou o no elegivel, reservou/liberou capacidade, calculou R$ 2,00 e encadeou dois eventos SHA-256.")
    print("PASS: trigger Oracle recusou alocacao acima da capacidade (ORA-20014).")

    invalid_code = "T6-NO-" + secrets.token_hex(4).upper()
    conn = connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:c,'PESSOAL_SENSIVEL',4,10)", {"c": invalid_code})
    try:
        cur.callproc("F6POC_ALLOCATE", [invalid_code, "BR-SEM-TEE"])
    except oracledb.DatabaseError as exc:
        error = exc.args[0]
        if getattr(error, "code", None) != 20016:
            raise AssertionError(f"Esperado bloqueio ORA-20016; recebido: {error}") from exc
        conn.rollback()
        cur.close()
        conn.close()
        print("PASS: trigger Oracle recusou carga sensivel no no sem TEE (ORA-20016).")
    else:
        conn.rollback()
        cur.close()
        conn.close()
        raise AssertionError("Oracle aceitou uma alocacao incompatível.")

    public_code = "T6-PUB-" + secrets.token_hex(4).upper()
    conn = connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:c,'PUBLICO',4,10)", {"c": public_code})
    cur.callproc("F6POC_ALLOCATE", [public_code, "EXT-TEE-01"])
    cur.execute("SELECT l.TOTAL_PRICE_BRL FROM F6POC_LEASES l JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID WHERE j.JOB_CODE=:c", {"c": public_code})
    if float(cur.fetchone()[0]) != 0.48:
        raise AssertionError("Carga publica nao foi precificada/alocada como esperado.")
    conn.rollback()
    cur.close()
    conn.close()
    print("PASS: regra proporcional permitiu carga publica no no externo, por R$ 0,48.")
    print("PASS: smoke test concluido; todas as transacoes de teste foram revertidas.")


def run_concurrent_capacity_check():
    node_code = "T6-RACE-NODE-" + secrets.token_hex(8).upper()
    codes = ["T6-RACE-" + secrets.token_hex(16).upper() for _ in range(2)]
    owned_codes = []
    conn = connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO F6POC_NODES (NODE_CODE,NODE_LABEL,COUNTRY_CODE,TEE_ENABLED,LOCAL_PERSISTENCE,APPROVED,VCPU_CAPACITY,VCPU_RESERVED,PRICE_PER_VCPU_HOUR) VALUES (:code,'No temporario de teste','BR',1,0,1,3,0,0.50)",
        {"code": node_code},
    )
    conn.commit()
    cur.close()
    conn.close()

    barrier = Barrier(2)

    def try_allocate(code):
        test_conn = connection()
        test_cur = test_conn.cursor()
        try:
            test_cur.execute(
                "INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:code,'PESSOAL_SENSIVEL',3,10)",
                {"code": code},
            )
            owned_codes.append(code)
            barrier.wait(timeout=15)
            test_cur.callproc("F6POC_ALLOCATE", [code, node_code])
            test_conn.commit()
            return "accepted"
        except oracledb.DatabaseError as exc:
            test_conn.rollback()
            if getattr(exc.args[0], "code", None) == 20014:
                return "capacity_rejected"
            raise
        finally:
            test_cur.close()
            test_conn.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(try_allocate, codes))
        if sorted(outcomes) != ["accepted", "capacity_rejected"]:
            raise AssertionError(f"Concorrencia Oracle produziu resultado inesperado: {outcomes}")
        print("PASS: duas sessoes concorrentes disputaram 3 vCPU; uma alocacao foi autorizada e a outra bloqueada (ORA-20014).")
    finally:
        cleanup = connection()
        cleanup_cur = cleanup.cursor()
        if owned_codes:
            binds = {f"code_{i}": code for i, code in enumerate(owned_codes)}
            code_list = ",".join(f":code_{i}" for i in range(len(owned_codes)))
            cleanup_cur.execute(
                f"UPDATE F6POC_LEASES SET STATUS='FAILED' WHERE STATUS='AUTHORIZED' AND JOB_ID IN (SELECT JOB_ID FROM F6POC_JOBS WHERE JOB_CODE IN ({code_list}))",
                binds,
            )
            cleanup_cur.execute("SELECT VCPU_RESERVED FROM F6POC_NODES WHERE NODE_CODE=:node", {"node": node_code})
            if cleanup_cur.fetchone()[0] != 0:
                raise AssertionError("Encerrar lease temporario nao liberou a capacidade do no de teste.")
            cleanup_cur.execute(f"DELETE FROM F6POC_AUDIT_EVENTS WHERE LEASE_ID IN (SELECT l.LEASE_ID FROM F6POC_LEASES l JOIN F6POC_JOBS j ON j.JOB_ID=l.JOB_ID WHERE j.JOB_CODE IN ({code_list}))", binds)
            cleanup_cur.execute(f"DELETE FROM F6POC_LEASES WHERE JOB_ID IN (SELECT JOB_ID FROM F6POC_JOBS WHERE JOB_CODE IN ({code_list}))", binds)
            cleanup_cur.execute(f"DELETE FROM F6POC_JOBS WHERE JOB_CODE IN ({code_list})", binds)
        cleanup_cur.execute("DELETE FROM F6POC_NODES WHERE NODE_CODE=:node", {"node": node_code})
        cleanup_cur.execute("SELECT COUNT(*) FROM F6POC_NODES WHERE NODE_CODE=:node", {"node": node_code})
        if cleanup_cur.fetchone()[0] != 0:
            raise AssertionError("No temporario de concorrencia permaneceu apos a limpeza.")
        if owned_codes:
            cleanup_cur.execute(f"SELECT COUNT(*) FROM F6POC_JOBS WHERE JOB_CODE IN ({code_list})", binds)
            if cleanup_cur.fetchone()[0] != 0:
                raise AssertionError("Jobs temporarios de concorrencia permaneceram apos a limpeza.")
        cleanup.commit()
        cleanup_cur.close()
        cleanup.close()


def run_fractional_vcpu_check():
    conn = connection()
    cur = conn.cursor()
    code = "T6-FRAC-" + secrets.token_hex(4).upper()
    try:
        cur.execute(
            "INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:code,'PUBLICO',1.5,10)",
            {"code": code},
        )
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) != 2290:
            raise
        conn.rollback()
    else:
        conn.rollback()
        raise AssertionError("Oracle aceitou vCPU fracionaria por SQL direto.")
    finally:
        cur.close()
        conn.close()
    print("PASS: constraint Oracle rejeitou vCPU fracionaria enviada diretamente (ORA-02290).")


def run_maximum_total_price_check():
    conn = connection()
    cur = conn.cursor()
    code = "T6-MAXPRICE-" + secrets.token_hex(8).upper()
    cur.execute(
        "UPDATE F6POC_NODES SET VCPU_CAPACITY=99999999,PRICE_PER_VCPU_HOUR=99999999.99 WHERE NODE_CODE='BR-TEE-01'"
    )
    cur.execute(
        "INSERT INTO F6POC_JOBS (JOB_CODE,DATA_CLASSIFICATION,VCPU_REQ,MAX_PRICE_BRL) VALUES (:code,'PESSOAL_SENSIVEL',999999,9999999999.99)",
        {"code": code},
    )
    try:
        cur.callproc("F6POC_ALLOCATE", [code, "BR-TEE-01"])
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) != 20017:
            raise AssertionError(f"Esperado bloqueio ORA-20017 por teto; recebido: {exc.args[0]}") from exc
        conn.rollback()
    else:
        conn.rollback()
        raise AssertionError("Oracle aceitou total de lease acima do limite de armazenamento.")
    finally:
        cur.close()
        conn.close()
    print("PASS: total fora da precisao da coluna e recusado pelo teto (ORA-20017), sem overflow numerico.")


if __name__ == "__main__":
    run()
