from decimal import Decimal, InvalidOperation


CLASSES = ("PUBLICO", "INTERNO", "PESSOAL", "PESSOAL_SENSIVEL")
PERSONAL_CLASSES = ("PESSOAL", "PESSOAL_SENSIVEL")


def rejection_reason(data_class, vcpu_req, max_price, node):
    """Explicacao para a tela; TRG_F6POC_LEASE_GUARD continua sendo a autoridade."""
    if node["approved"] != 1:
        return "OPERADOR_NAO_HOMOLOGADO"
    if node["persistence"] != 0:
        return "NO_COM_PERSISTENCIA_LOCAL"
    if Decimal(str(node["capacity"])) - Decimal(str(node.get("reserved", 0))) < Decimal(str(vcpu_req)):
        return "CAPACIDADE_INSUFICIENTE"
    if data_class in PERSONAL_CLASSES and node["country"] != "BR":
        return "NO_FORA_DO_BRASIL"
    if data_class in PERSONAL_CLASSES and node["tee"] != 1:
        return "NO_SEM_EXECUCAO_CONFIDENCIAL"
    total = (Decimal(str(node["rate"])) * Decimal(str(vcpu_req))).quantize(Decimal("0.01"))
    if total > Decimal(str(max_price)):
        return "ACIMA_DO_TETO"
    return "ELEGIVEL"


def parse_submission(values):
    data_class = values.get("classification", "PESSOAL_SENSIVEL")
    if data_class not in CLASSES:
        raise ValueError("Classificacao invalida.")
    try:
        vcpu = Decimal(values.get("vcpu", "4"))
        budget = Decimal(values.get("budget", "10"))
    except InvalidOperation as exc:
        raise ValueError("Informe volume e teto numericos.") from exc
    if not vcpu.is_finite() or not budget.is_finite() or vcpu <= 0 or budget < 0 or vcpu != vcpu.to_integral_value():
        raise ValueError("vCPU deve ser inteiro positivo e teto nao pode ser negativo.")
    if vcpu > Decimal("999999"):
        raise ValueError("O limite suportado e de 999999 vCPU por carga.")
    try:
        if budget != budget.quantize(Decimal("0.01")):
            raise ValueError("O teto de preco deve ter no maximo duas casas decimais.")
    except InvalidOperation as exc:
        raise ValueError("Teto de preco fora do limite suportado.") from exc
    if budget > Decimal("9999999999.99"):
        raise ValueError("O teto de preco excede o limite de R$ 9.999.999.999,99.")
    return data_class, vcpu, budget
