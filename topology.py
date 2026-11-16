"""Read-only topology view for the local distributed-cloud demonstration."""

from __future__ import annotations

import html
from urllib.parse import quote


STYLE = """<style>
.topology-toolbar{display:flex;flex-wrap:wrap;gap:14px;align-items:end;margin:0 0 18px}
.topology-toolbar label{margin:0;min-width:290px;flex:1}
.topology-toolbar select{margin-top:5px}
.topology-toolbar button{margin:0}
.topology-scroll{overflow-x:auto;border:1px solid #d9e3ea;border-radius:10px;background:#f9fcfe}
.topology-svg{display:block;width:100%;min-width:900px;height:auto}
.topology-svg text{font-family:system-ui,Segoe UI,Arial,sans-serif;fill:#152a3a}
.topology-svg .small{font-size:12px;fill:#587080}
.topology-svg .title{font-size:15px;font-weight:700}
.topology-svg .edge{fill:none;stroke-width:2.5;marker-end:url(#arrow)}
.topology-svg .edge.active{stroke:#159260;stroke-width:4;marker-end:url(#arrow-active)}
.topology-svg .edge.candidate{stroke:#4b8cbd;stroke-dasharray:7 5}
.topology-svg .edge.blocked{stroke:#d3a4a0;stroke-dasharray:3 6}
.topology-svg .edge.offline{stroke:#a9b6bf;stroke-dasharray:4 6}
.topology-svg .edge.rejected{stroke:#bd5147;stroke-width:4;marker-end:url(#arrow-rejected)}
.topology-svg .box{stroke-width:2;rx:12}
.topology-svg .box.base{fill:white;stroke:#9eb5c5}
.topology-svg .box.active{fill:#e7f7ef;stroke:#159260}
.topology-svg .box.candidate{fill:#eef6fc;stroke:#4b8cbd}
.topology-svg .box.blocked{fill:#fff2f0;stroke:#d3a4a0}
.topology-svg .box.offline{fill:#f2f4f6;stroke:#a9b6bf}
.topology-svg .box.rejected{fill:#fff2f0;stroke:#bd5147}
.topology-key{display:flex;flex-wrap:wrap;gap:9px;margin:14px 0 0}
.topology-key span{border-radius:99px;padding:4px 10px;font-size:13px;font-weight:650}
.topology-key .active{background:#e7f7ef;color:#126440}
.topology-key .candidate{background:#eef6fc;color:#225c8b}
.topology-key .blocked{background:#fff2f0;color:#9a4039}
.topology-key .offline{background:#f2f4f6;color:#52626d}
</style>"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_topology(nodes: list[dict], jobs: list[dict], selected_code: str = "", csrf_token: str = "") -> str:
    """Render current Oracle catalog plus one historical path, without simulating activity."""
    selected = next((job for job in jobs if job["code"] == selected_code), None)
    if selected is None:
        selected = next((job for job in jobs if job["status"] == "COMPLETED"), jobs[0] if jobs else None)
    group_jobs = ([job for job in jobs if job.get("group_token") == selected.get("group_token")]
                  if selected and selected.get("group_token") else [selected] if selected else [])
    group_jobs.sort(key=lambda job: job.get("node") or "")
    selected_nodes = {job.get("node") or job.get("rejected_node") for job in group_jobs}
    completed = bool(selected and selected["status"] == "COMPLETED")
    hosting_active = bool(selected and selected.get("hosting_status") == "ACTIVE")
    flow_active = completed or hosting_active
    rejected = bool(selected and selected["status"] == "FAILED")
    center_y = max(285, 85 + len(nodes) * 43)
    height = max(570, 145 + len(nodes) * 86)
    node_start = center_y - (len(nodes) - 1) * 43

    choices = "".join(
        f'<option value="{_esc(job["code"])}" {"selected" if selected and job["code"] == selected["code"] else ""}>'
        f'{_esc(job["code"])} · {_esc(job["status"])} · {_esc(job["node"] or job.get("rejected_node") or "sem nó")}</option>'
        for job in jobs
    )
    if not choices:
        choices = '<option value="">Nenhuma tarefa registrada</option>'

    edges = []
    boxes = []
    for index, node in enumerate(nodes):
        y = node_start + index * 86
        connected = bool(node.get("connected"))
        enabled = bool(node.get("enabled", connected))
        eligible = node["reason"] == "ELEGIVEL"
        is_selected = node["code"] in selected_nodes
        state = ("active" if is_selected and flow_active and enabled else
                 "rejected" if is_selected and rejected else
                 "candidate" if connected and eligible and enabled else
                 "blocked" if not eligible else "offline")
        status = ("DESATIVADO" if connected and not enabled else
                  "HOSPEDANDO" if state == "active" and hosting_active else
                  "EXECUTOU" if state == "active" else
                  "RECUSADO" if state == "rejected" else
                  "CANDIDATO" if state == "candidate" else
                  "INELEGÍVEL" if state == "blocked" else "DESATIVADO" if not enabled and connected else "SEM EXECUTOR")
        edges.append(f'<path class="edge {state}" d="M 435 {center_y} C 510 {center_y}, 505 {y}, 560 {y}"/>')
        if state == "active":
            edges.append(f'<path class="edge active" d="M 770 {y} C 830 {y}, 800 {center_y}, 845 {center_y}"/>')
        subtitle = f'{_esc(node["country"])} · TEE {"declarado" if node["tee"] else "não declarado"} · {_esc(node["price_label"])}'
        boxes.append(
            f'<rect class="box {state}" x="560" y="{y-32}" width="210" height="64"/>'
            f'<text class="title" x="573" y="{y-7}">{_esc(node["code"])}</text>'
            f'<text class="small" x="573" y="{y+11}">{subtitle}</text>'
            f'<text class="small" x="573" y="{y+26}">{status}</text>'
        )

    first_edge = "rejected" if rejected else "active" if flow_active else "offline"
    selected_label = (f'{_esc(selected["code"])} · {_esc(selected["status"])}'
                      if selected else "Nenhuma execução selecionada")
    if selected and selected.get("reason"):
        detail = f'Recusa registrada: {_esc(selected["reason"])}'
    elif selected:
        nodes_label = " + ".join(_esc(job.get("node") or "—") for job in group_jobs)
        detail = f'Nó(s) {nodes_label} · preço por lease {_esc(selected.get("price_label") or "—")}'
    else:
        detail = "Execute um lote no painel para destacar seu caminho."
    report_link = (f'<a href="/report?job={quote(selected["code"])}">Abrir relatório desta tarefa</a>'
                   if selected else "")
    total_vcpu = sum(int(job["vcpu"]) for job in group_jobs)
    requirements = (f'{total_vcpu} vCPU · teto {_esc(selected["budget_label"])}'
                    if selected else "4 vCPU · teto R$ 10,00")
    destination_title = "Hello World" if hosting_active else "Relatório"
    destination_line = ("Site ativo por 3 min" if hosting_active else
                        "Hashes persistidos" if completed else "Sem resultado de execução")
    destination_detail = ("Lease reservado" if hosting_active else
                          "Lease liberado" if completed else "Veja o estado da tarefa")
    source_label = "Site HTML + requisitos" if selected and selected.get("hosting_status") else "Lote sintético + requisitos"

    svg = f'''<svg class="topology-svg" viewBox="0 0 1100 {height}" role="img" aria-label="Fluxo da tarefa entre cliente, Oracle, nós e relatório">
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9" fill="#8599a7"/></marker>
<marker id="arrow-active" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9" fill="#159260"/></marker>
<marker id="arrow-rejected" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9" fill="#bd5147"/></marker></defs>
<text class="small" x="72" y="36">1 · ENVIO</text><text class="small" x="280" y="36">2 · POLÍTICA E RESERVA</text>
<text class="small" x="560" y="36">3 · CATÁLOGO / EXECUTORES</text><text class="small" x="845" y="36">4 · PROVA</text>
<path class="edge {first_edge}" d="M 240 {center_y} L 265 {center_y}"/>
{''.join(edges)}
<rect class="box base" x="50" y="{center_y-45}" width="190" height="90"/>
<text class="title" x="66" y="{center_y-13}">Cliente</text><text class="small" x="66" y="{center_y+9}">{source_label}</text>
<text class="small" x="66" y="{center_y+27}">{requirements}</text>
<rect class="box {'rejected' if rejected else 'base'}" x="265" y="{center_y-53}" width="170" height="106"/>
<text class="title" x="281" y="{center_y-24}">Oracle</text><text class="small" x="281" y="{center_y-4}">Elegibilidade</text>
<text class="small" x="281" y="{center_y+14}">Preço + lease</text><text class="small" x="281" y="{center_y+32}">Trilha de auditoria</text>
{''.join(boxes)}
<rect class="box {'active' if flow_active else 'offline'}" x="845" y="{center_y-45}" width="205" height="90"/>
<text class="title" x="861" y="{center_y-13}">{destination_title}</text>
<text class="small" x="861" y="{center_y+9}">{destination_line}</text>
<text class="small" x="861" y="{center_y+27}">{destination_detail}</text>
</svg>'''
    return (STYLE + '<p><a href="/">← Voltar ao painel</a></p>'
            '<section class="card"><h2>Topologia da cloud distribuída</h2>'
            '<p class="muted">Os nós desenhados são registros no Oracle que representam futuros computadores ociosos oferecidos para aluguel. O caminho destacado vem da tarefa registrada no banco; candidatos e bloqueios usam o catálogo atual.</p>'
            '<form class="topology-toolbar" action="/topologia" method="get">'
            f'<label for="job">Tarefa no Oracle<select id="job" name="job">{choices}</select></label>'
            '<button type="submit">Ver caminho</button></form>'
            f'<p><strong>{selected_label}</strong><br>{detail} {report_link}</p>'
            f'<div class="topology-scroll">{svg}</div>'
            '<div class="topology-key"><span class="active">Caminho ativo ou executado</span>'
            '<span class="candidate">Elegível e conectado</span>'
            '<span class="blocked">Bloqueado pela regra</span>'
            '<span class="offline">Sem executor local</span></div>'
            '<section class="card" style="margin-top:20px"><h2>Controle da simulação</h2>'
            '<p class="muted">Desative um nó para simular um computador ocioso ficando indisponível; o gateway tentará o outro nó ativo. Reative-o quando quiser.</p>'
            '<table><thead><tr><th>Nó</th><th>Estado</th><th>Ação</th></tr></thead><tbody>'
            + ''.join(
                f'<tr><td><strong>{_esc(node["code"])}</strong></td><td>{"ATIVO" if node.get("enabled") else "DESATIVADO" if node.get("connected") is not None else "OFFLINE"}</td>'
                f'<td><form method="post" action="/node/toggle"><input type="hidden" name="csrf" value="{_esc(csrf_token)}"><input type="hidden" name="node" value="{_esc(node["code"])}"><input type="hidden" name="enabled" value="{"0" if node.get("enabled") else "1"}"><button type="submit">{"Desativar nó" if node.get("enabled") else "Ativar nó"}</button></form></td></tr>'
                for node in nodes if node["code"] in ("BR-TEE-01", "BR-TEE-02")
            )
            + '</tbody></table></section>'
            '<p class="hint">As setas representam decisões e reservas no Oracle. Dois workers locais simulam os computadores ofertantes; no produto final, seriam máquinas reais de operadores independentes. Território e TEE são atributos declarados, sem atestação física.</p>'
            '</section>')
