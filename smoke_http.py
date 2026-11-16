"""End-to-end checks against a running local MVP. Creates only demo jobs."""

from __future__ import annotations

import argparse
import http.cookiejar
import re
import urllib.error
import urllib.parse
import urllib.request


def run(base: str):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def submit(mode: str, node: str = "BR-TEE-01") -> str:
        page = opener.open(base + "/processar").read().decode("utf-8")
        if "Oracle conectado" not in page:
            raise AssertionError("Oracle indisponivel na interface.")
        token = re.search(r'name="csrf" value="([^"]+)"', page)
        if token is None:
            raise AssertionError("Token CSRF ausente.")
        values = {
            "csrf": token.group(1), "classification": "PESSOAL_SENSIVEL",
            "numbers": "12,18,30,40", "vcpu": "4", "budget": "10",
            "mode": mode, "node": node,
        }
        request = urllib.request.Request(
            base + "/allocate", data=urllib.parse.urlencode(values).encode("utf-8"),
            headers={"Origin": base},
        )
        return opener.open(request).read().decode("utf-8")

    success = submit("auto")
    if "soma 100" not in success or "media 25.00" not in success:
        raise AssertionError("O worker nao devolveu o calculo esperado.")
    match = re.search(r"Carga (F7-[A-Z0-9-]+) processada", success)
    if match is None:
        raise AssertionError("Codigo da tarefa concluida ausente.")
    code = match.group(1)
    reloaded = opener.open(base).read().decode("utf-8")
    if code not in reloaded or "hash do resultado" not in reloaded:
        raise AssertionError("Prova da execucao nao encontrada no historico Oracle.")
    report = opener.open(base + "/report?job=" + code).read().decode("utf-8")
    if ("INTEGRA" not in report or "SHA-256 do resultado" not in report or code not in report
            or "Datacenter Sul Infraestrutura Ltda" not in report or "RELEASED" not in report):
        raise AssertionError("Relatorio por execucao incompleto.")
    if "12,18,30,40" in report:
        raise AssertionError("Dados de entrada apareceram no relatorio persistido.")
    graph = opener.open(base + "/topologia?job=" + code).read().decode("utf-8")
    if ("Topologia da cloud distribuída" not in graph or code not in graph
            or "BR-TEE-01" not in graph or "BR-TEE-02" not in graph
            or "EXECUTOU" not in graph or "CANDIDATO" not in graph):
        raise AssertionError("Grafo da execucao concluida incompleto.")
    print("PASS: processamento, hashes persistidos e relatorio de custodia no Oracle.")

    rejection = submit("force", "BR-SEM-TEE")
    if "Oracle recusou" not in rejection or "exige TEE" not in rejection:
        raise AssertionError("Recusa Oracle do no sem TEE nao demonstrada.")
    if "<td>FAILED</td>" not in rejection:
        raise AssertionError("Tarefa recusada nao aparece como FAILED.")
    rejected_code = re.search(r"Carga (F7-[A-Z0-9-]+): Oracle recusou", rejection)
    if rejected_code is None:
        raise AssertionError("Codigo da tentativa recusada ausente.")
    rejected_graph = opener.open(base + "/topologia?job=" + rejected_code.group(1)).read().decode("utf-8")
    if "RECUSADO" not in rejected_graph or "BR-SEM-TEE" not in rejected_graph:
        raise AssertionError("Grafo da recusa incompleto.")
    print("PASS: recusa Oracle e historico da falha.")

    second = submit("force", "BR-TEE-02")
    if "processada no BR-TEE-02" not in second or "R$ 2,20" not in second:
        raise AssertionError("Segundo executor elegivel nao processou a tarefa.")
    print("PASS: segundo executor elegivel processou a tarefa por R$ 2,20.")

    hosting_form = opener.open(base + "/hosting").read().decode("utf-8")
    token = re.search(r"name=['\"]csrf['\"] value=['\"]([^'\"]+)['\"]", hosting_form)
    if token is None:
        raise AssertionError("Formulario de hospedagem sem CSRF.")
    start_request = urllib.request.Request(
        base + "/hosting/start",
        data=urllib.parse.urlencode({"csrf": token.group(1), "vcpu": "4", "budget": "10",
                                     "group_name": "Smoke Web", "group_mode": "split",
                                     "html_content": "<h1>Smoke custom</h1><p>__NODE__</p>"}).encode(),
        headers={"Origin": base},
    )
    hosted = opener.open(start_request).read().decode("utf-8")
    link = re.search(r'href="(http://127\.0\.0\.1:8000/site/[^"]+)"', hosted)
    group = re.search(r'name="group" value="([^"]+)"', hosted)
    if not link or not group or "3 minutos" not in hosted:
        raise AssertionError("Hospedagem temporaria nao apareceu na interface.")
    hosting_job = re.search(r'WEB-[A-Z0-9-]+', hosted)
    if hosting_job is None:
        raise AssertionError("Codigo Oracle da hospedagem ausente.")
    hosting_graph = opener.open(base + "/topologia?job=" + hosting_job.group()).read().decode("utf-8")
    if (hosting_graph.count("HOSPEDANDO") < 2 or "Lease reservado" not in hosting_graph
            or "BR-TEE-01" not in hosting_graph or "BR-TEE-02" not in hosting_graph):
        raise AssertionError("Grafo nao mostra a hospedagem ativa.")
    served_by = []
    for _ in range(6):
        with opener.open(link.group(1)) as response:
            page = response.read().decode("utf-8")
            served_by.append(response.headers.get("X-Served-By"))
            if "<h1>Smoke custom</h1>" not in page:
                raise AssertionError("Worker nao serviu o HTML customizado.")
            if served_by[-1] not in page:
                raise AssertionError("Pagina nao identificou o no que atendeu a visita.")
    if set(served_by) != {"BR-TEE-01", "BR-TEE-02"}:
        raise AssertionError(f"Visitas nao foram distribuidas entre os dois nos: {served_by}.")
    stop_request = urllib.request.Request(
        base + "/hosting/stop",
        data=urllib.parse.urlencode({"csrf": token.group(1), "group": group.group(1)}).encode(),
        headers={"Origin": base},
    )
    stopped = opener.open(stop_request).read().decode("utf-8")
    if "CANCELLED" not in stopped:
        raise AssertionError("Hospedagem nao foi encerrada no Oracle.")
    try:
        opener.open(link.group(1))
    except urllib.error.HTTPError as exc:
        if exc.code != 410:
            raise AssertionError(f"Site encerrado retornou HTTP {exc.code}, esperado 410.") from exc
    else:
        raise AssertionError("Site continuou acessivel apos encerramento.")
    print("PASS: Hello World servido por dois nos, seis visitas distribuidas e duas reservas canceladas.")

    topology = opener.open(base + "/topologia").read().decode("utf-8")
    toggle_token = re.search(r'name="csrf" value="([^"]+)"', topology)
    if toggle_token is None:
        raise AssertionError("Controle de nós sem CSRF.")
    toggle = urllib.request.Request(
        base + "/node/toggle",
        data=urllib.parse.urlencode({"csrf": toggle_token.group(1), "node": "BR-TEE-02", "enabled": "0"}).encode(),
        headers={"Origin": base},
    )
    toggled = opener.open(toggle).read().decode("utf-8")
    if "BR-TEE-02 desativado" not in toggled or "DESATIVADO" not in toggled:
        raise AssertionError("Controle de desativacao do no nao apareceu.")
    toggle_back = urllib.request.Request(
        base + "/node/toggle",
        data=urllib.parse.urlencode({"csrf": toggle_token.group(1), "node": "BR-TEE-02", "enabled": "1"}).encode(),
        headers={"Origin": base},
    )
    opener.open(toggle_back).read()
    print("PASS: grafo permite desativar e reativar um no simulado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    run(parser.parse_args().base.rstrip("/"))
