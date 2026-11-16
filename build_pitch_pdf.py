from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "pdf" / "Pitch_Fase7_Cloud_Distribuida.pdf"
# 16:9 canvas sized like a presentation slide; coordinates below are in points.
W, H = 1280, 720
NAVY = colors.HexColor("#102C42")
BLUE = colors.HexColor("#1467A8")
CYAN = colors.HexColor("#5CC8D7")
GREEN = colors.HexColor("#2BA66B")
INK = colors.HexColor("#152A3A")
MUTED = colors.HexColor("#587080")
PALE = colors.HexColor("#EEF7FC")
LINE = colors.HexColor("#C9DDEA")
WHITE = colors.white


def rounded_card(c, x, y, w, h, fill=WHITE, stroke=LINE, radius=12):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def text(c, x, y, value, size=14, color=INK, font="Helvetica", leading=None):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString(x, y, value)
    return y - (leading or size * 1.3)


def wrapped(c, x, y, value, width, size=14, color=INK, font="Helvetica", leading=None):
    leading = leading or size * 1.35
    max_chars = max(18, int(width / (size * 0.49)))
    for line in wrap(value, max_chars):
        y = text(c, x, y, line, size, color, font, leading)
    return y


def bullet_list(c, x, y, items, width, size=14, color=INK, gap=8):
    for item in items:
        c.setFillColor(CYAN)
        c.circle(x + 4, y + 3, 3, fill=1, stroke=0)
        y = wrapped(c, x + 16, y, item, width - 16, size, color) - gap
    return y


def header(c, number, title, kicker=None):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(BLUE)
    c.rect(0, H - 8, W, 8, fill=1, stroke=0)
    if kicker:
        text(c, 54, H - 58, kicker.upper(), 10, CYAN, "Helvetica-Bold")
    text(c, 54, H - 92, title, 28, WHITE, "Helvetica-Bold")
    text(c, W - 72, H - 58, f"{number:02d} / 10", 10, colors.HexColor("#B7D1DF"), "Helvetica-Bold")


def footer(c):
    c.setStrokeColor(colors.HexColor("#36566A"))
    c.line(54, 31, W - 54, 31)
    text(c, 54, 17, "Cloud Distribuida P2P | MVP Fase 7 | Grupo 101", 8, colors.HexColor("#A9C0CD"))


def page_cover(c):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(BLUE)
    c.circle(W - 85, H - 65, 160, fill=1, stroke=0)
    c.setFillColor(CYAN)
    c.circle(W - 150, H - 130, 54, fill=1, stroke=0)
    text(c, 62, H - 88, "STARTUP ONE | FASE 7", 12, CYAN, "Helvetica-Bold")
    text(c, 62, H - 168, "Cloud Distribuída", 44, WHITE, "Helvetica-Bold")
    text(c, 62, H - 218, "Compute ocioso transformado em capacidade sob demanda", 18, colors.HexColor("#D8E8EF"))
    rounded_card(c, 62, 112, 440, 120, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 86, 193, "Pitch executivo", 14, CYAN, "Helvetica-Bold")
    wrapped(c, 86, 166, "Um marketplace P2P com Oracle como plano de controle, dois workers simulados e uma experiência simples para reservar, executar e auditar capacidade.", 380, 15, WHITE)
    text(c, 62, 52, "Henrique Parra Benitez | Grupo 101", 11, colors.HexColor("#B7D1DF"))
    c.showPage()


def page_problem(c):
    header(c, 2, "O problema", "Por que agora")
    rounded_card(c, 54, 125, 510, 265, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 82, 350, "Compute barato precisa de controle.", 22, WHITE, "Helvetica-Bold")
    wrapped(c, 82, 310, "Nuvem tradicional concentra capacidade e pode aumentar custo, latência e dependência. Em ambientes regulados, ainda é difícil provar onde a carga rodou, sob quais regras e se o dado permaneceu no nó.", 430, 16, colors.HexColor("#D8E8EF"))
    c.setFillColor(CYAN)
    c.rect(82, 175, 340, 4, fill=1, stroke=0)
    text(c, 82, 150, "Fase 5: soberania, conformidade e custo", 13, CYAN, "Helvetica-Bold")
    rounded_card(c, 620, 125, 610, 265, PALE, LINE)
    text(c, 650, 350, "Dois lados do mercado", 22, BLUE, "Helvetica-Bold")
    bullet_list(c, 650, 305, [
        "Demanda: startups, PMEs, laboratórios e equipes de dados que buscam compute barato e baixa latência.",
        "Oferta: empresas e pessoas com máquinas subutilizadas que querem monetizar capacidade ociosa.",
        "Primeiro recorte: cargas batch simples, com clientes no Brasil e sem dados sensíveis no piloto.",
    ], 530, 15, INK)
    footer(c)
    c.showPage()


def page_solution(c):
    header(c, 3, "A solução", "Uma rede com regras verificáveis")
    text(c, 54, 420, "Um plano de controle comum para uma malha de computadores independentes.", 19, colors.HexColor("#D8E8EF"))
    boxes = [
        (54, "Cliente", "Escolhe lote, vCPU, teto e classificação."),
        (350, "Oracle", "Filtra elegibilidade, reserva e audita."),
        (646, "Nós", "Operadores ofertam capacidade ociosa."),
        (942, "Resultado", "Execução e relatório verificável."),
    ]
    for x, title, desc in boxes:
        rounded_card(c, x, 210, 240, 145, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
        text(c, x + 22, 320, title, 19, CYAN, "Helvetica-Bold")
        wrapped(c, x + 22, 285, desc, 195, 14, WHITE)
    for x in (294, 590, 886):
        c.setStrokeColor(CYAN)
        c.setLineWidth(3)
        c.line(x, 282, x + 40, 282)
        c.line(x + 32, 290, x + 40, 282)
        c.line(x + 32, 274, x + 40, 282)
    text(c, 54, 142, "Diferencial", 14, CYAN, "Helvetica-Bold")
    wrapped(c, 54, 116, "Conformidade e custo entram na decisão de alocação, não como aviso depois. O cliente vê o caminho da tarefa e o operador vê uma forma transparente de monetizar capacidade.", 1120, 16, WHITE)
    footer(c)
    c.showPage()


def page_mvp(c):
    header(c, 4, "MVP funcionando", "O que já é demonstrável")
    screenshot = ROOT / "evidencias" / "tela_mvp.png"
    if screenshot.exists():
        c.drawImage(ImageReader(str(screenshot)), 54, 102, width=515, height=290, preserveAspectRatio=True, anchor="sw", mask="auto")
    rounded_card(c, 620, 105, 610, 300, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 650, 365, "Fluxo principal", 22, CYAN, "Helvetica-Bold")
    bullet_list(c, 650, 325, [
        "Programar tarefa com lote sintético e seleção de nó.",
        "Criar grupo computacional dividido em dois nós ou concentrado em um.",
        "Hospedar HTML puro por 180 segundos e identificar o nó atendente.",
        "Visualizar topologia, auditoria e estado do lease no Oracle.",
        "Ativar ou desativar workers para simular disponibilidade.",
    ], 530, 15, WHITE)
    text(c, 54, 72, "Demonstração local em http://127.0.0.1:8000", 11, colors.HexColor("#B7D1DF"))
    footer(c)
    c.showPage()


def page_oracle(c):
    header(c, 5, "Oracle como plano de controle", "Tecnologia parceira integrada")
    rounded_card(c, 54, 118, 530, 280, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 84, 360, "Oracle Database", 24, CYAN, "Helvetica-Bold")
    bullet_list(c, 84, 315, [
        "Catálogo de nós e atributos declarados.",
        "Elegibilidade por classificação, território e persistência.",
        "Leases, capacidade reservada e liquidação demonstrativa.",
        "Hash de entrada, resultado e trilha de custódia.",
    ], 450, 15, WHITE)
    rounded_card(c, 640, 118, 590, 280, PALE, LINE)
    text(c, 670, 360, "O que o MVP não afirma", 22, BLUE, "Helvetica-Bold")
    bullet_list(c, 670, 315, [
        "Os workers locais simulam computadores dos operadores.",
        "TEE, território e homologação são atributos declarados.",
        "Execução confidencial, microVM e atestação física ficam no roadmap.",
        "O MVP valida o plano de controle e a jornada, não produção comercial.",
    ], 510, 15, INK)
    footer(c)
    c.showPage()


def page_business(c):
    header(c, 6, "Modelo de negócio", "Canvas em uma página")
    items = [
        (54, 260, "Clientes", "Startups, PMEs, labs e regulados"),
        (334, 260, "Valor", "Compute barato, baixa latência e evidência"),
        (614, 260, "Canais", "Comunidade, GitHub, parceiros e eventos"),
        (894, 260, "Receita", "10% sobre o consumo; plano corporativo futuro"),
        (54, 100, "Recursos", "Oracle, scheduler, rede e reputação"),
        (334, 100, "Atividades", "Homologar, alocar, auditar e suportar"),
        (614, 100, "Parceiros", "Oracle, OCI, universidades e operadores"),
        (894, 100, "Custos", "Infra, engenharia, segurança e compliance"),
    ]
    for x, y, title, desc in items:
        rounded_card(c, x, y, 240, 120, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
        text(c, x + 18, y + 84, title, 15, CYAN, "Helvetica-Bold")
        wrapped(c, x + 18, y + 58, desc, 200, 13, WHITE)
    footer(c)
    c.showPage()


def page_finance(c):
    header(c, 7, "Monetização e projeção", "Premissas explícitas")
    text(c, 54, 420, "A plataforma retém 10% do GMV; o restante vai para operadores.", 18, colors.HexColor("#D8E8EF"))
    cols = [54, 300, 515, 730, 945]
    heads = ["Ano", "GMV anual", "Receita 10%", "Custos", "Resultado"]
    vals = [
        ("1", "R$ 198.750", "R$ 19.875", "R$ 36.000", "-R$ 16.125"),
        ("2", "R$ 1.080.000", "R$ 108.000", "R$ 72.000", "R$ 36.000"),
        ("3", "R$ 3.600.000", "R$ 360.000", "R$ 180.000", "R$ 180.000"),
    ]
    for x, h in zip(cols, heads):
        text(c, x, 360, h, 13, CYAN, "Helvetica-Bold")
    c.setStrokeColor(colors.HexColor("#36566A"))
    c.line(54, 344, 1218, 344)
    for row_i, row in enumerate(vals):
        y = 304 - row_i * 55
        if row_i % 2 == 0:
            c.setFillColor(colors.HexColor("#183C55"))
            c.roundRect(44, y - 16, 1184, 38, 8, fill=1, stroke=0)
        for x, value in zip(cols, row):
            text(c, x, y, value, 15, WHITE, "Helvetica-Bold" if x == 54 else "Helvetica")
    wrapped(c, 54, 112, "Cenário de planejamento, não promessa de receita. A prioridade do ano 1 é criar liquidez dos dois lados; o ponto de equilíbrio depende de uso recorrente, não apenas de cadastro.", 1120, 15, colors.HexColor("#D8E8EF"))
    footer(c)
    c.showPage()


def page_growth(c):
    header(c, 8, "Aquisição e mercado", "Crescimento comunitário")
    rounded_card(c, 54, 112, 550, 286, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 84, 360, "Inspirada no início do Bitcoin", 21, CYAN, "Helvetica-Bold")
    bullet_list(c, 84, 315, [
        "Protocolo e código abertos para criar confiança.",
        "Comunidade técnica antes de mídia paga.",
        "Incentivo aos primeiros operadores por capacidade real.",
        "Indicação, métricas públicas e estudos de caso.",
        "Foco inicial em uma região e um workload.",
    ], 470, 15, WHITE)
    rounded_card(c, 650, 112, 580, 286, PALE, LINE)
    text(c, 680, 360, "Loop de crescimento", 21, BLUE, "Helvetica-Bold")
    wrapped(c, 680, 315, "Mais operadores aumentam a disponibilidade. Mais disponibilidade melhora preço e latência. Clientes recorrentes geram uso e reputação. A reputação atrai novos operadores e clientes.", 510, 16, INK)
    text(c, 680, 205, "Regra de comunicação", 14, BLUE, "Helvetica-Bold")
    wrapped(c, 680, 180, "Não vender especulação ou retorno garantido: vender utilidade, transparência e capacidade efetivamente entregue.", 510, 15, INK)
    footer(c)
    c.showPage()


def page_metrics(c):
    header(c, 9, "KPIs e roadmap", "Como medir escala")
    rounded_card(c, 54, 112, 535, 286, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 84, 360, "KPIs de decisão", 21, CYAN, "Helvetica-Bold")
    bullet_list(c, 84, 315, [
        "Demanda: ativação, jobs concluídos, recompra, GMV e CAC.",
        "Oferta: nós ativos, vCPU utilizada, ganhos e churn.",
        "Confiança: sucesso, p95 de latência, auditoria íntegra e incidentes.",
    ], 465, 15, WHITE)
    rounded_card(c, 635, 112, 595, 286, PALE, LINE)
    text(c, 665, 360, "Roadmap", 21, BLUE, "Helvetica-Bold")
    bullet_list(c, 665, 315, [
        "0-3 meses: OCI, autenticação, imagens, telemetria e piloto.",
        "3-6 meses: atestação, microVM, criptografia, billing e SLA.",
        "6-12 meses: múltiplas regiões, SDK, reputação e setores regulados.",
    ], 525, 15, INK)
    footer(c)
    c.showPage()


def page_close(c):
    header(c, 10, "Próximo passo", "Convite ao piloto")
    text(c, 54, 410, "Começar pequeno, medir tudo e ganhar confiança.", 28, WHITE, "Helvetica-Bold")
    wrapped(c, 54, 360, "O MVP já demonstra o plano de controle. O piloto precisa conectar operadores reais a clientes com cargas simples, medir custo e latência e transformar os resultados em um caso de uso repetível.", 920, 18, colors.HexColor("#D8E8EF"))
    rounded_card(c, 54, 145, 380, 120, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 80, 228, "Equipe", 15, CYAN, "Helvetica-Bold")
    text(c, 80, 195, "Henrique Parra Benitez", 17, WHITE, "Helvetica-Bold")
    text(c, 80, 170, "Grupo 101", 13, colors.HexColor("#B7D1DF"))
    rounded_card(c, 484, 145, 390, 120, colors.HexColor("#183C55"), colors.HexColor("#2C6079"))
    text(c, 510, 228, "MVP", 15, CYAN, "Helvetica-Bold")
    text(c, 510, 195, "Oracle + 2 workers locais", 17, WHITE, "Helvetica-Bold")
    text(c, 510, 170, "cloud-distribuida-p2p-mvp-fase7", 12, colors.HexColor("#B7D1DF"))
    text(c, 54, 62, "Obrigado", 18, CYAN, "Helvetica-Bold")
    footer(c)
    c.showPage()


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(W, H))
    c.setTitle("Pitch Fase 7 - Cloud Distribuida P2P")
    page_cover(c)
    page_problem(c)
    page_solution(c)
    page_mvp(c)
    page_oracle(c)
    page_business(c)
    page_finance(c)
    page_growth(c)
    page_metrics(c)
    page_close(c)
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
