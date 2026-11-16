"""Validation for a manual, demonstration-only provider onboarding flow."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
}


def parse_operator(values: dict[str, str]) -> dict:
    code = values.get("node_code", "").strip().upper()
    cnpj = re.sub(r"\D", "", values.get("cnpj", ""))
    name = values.get("operator_name", "").strip()
    uf = values.get("uf", "").strip().upper()
    label = values.get("node_label", "").strip()
    if not re.fullmatch(r"[A-Z0-9-]{3,30}", code):
        raise ValueError("Codigo do no deve ter 3 a 30 letras, numeros ou hifens.")
    if len(cnpj) != 14 or len(name) < 3 or len(name) > 100:
        raise ValueError("Informe CNPJ com 14 digitos e razao social de 3 a 100 caracteres.")
    if uf not in UF_CODES or len(label) < 3 or len(label) > 100:
        raise ValueError("Informe UF brasileira e descricao do no de 3 a 100 caracteres.")
    try:
        capacity = int(values.get("capacity", ""))
        rate = Decimal(values.get("rate", ""))
        guarantee = Decimal(values.get("guarantee", ""))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("Capacidade, preco e garantia devem ser numericos.") from exc
    if not 1 <= capacity <= 999999 or not rate.is_finite() or not guarantee.is_finite():
        raise ValueError("Capacidade, preco ou garantia fora do limite.")
    if rate < 0 or rate > Decimal("99999999.99") or guarantee < 0 or guarantee > Decimal("9999999999.99"):
        raise ValueError("Preco ou garantia fora do limite.")
    if rate != rate.quantize(Decimal("0.01")) or guarantee != guarantee.quantize(Decimal("0.01")):
        raise ValueError("Preco e garantia aceitam no maximo duas casas decimais.")
    return {
        "code": code, "cnpj": cnpj, "name": name, "uf": uf, "label": label,
        "capacity": capacity, "rate": rate, "guarantee": guarantee,
        "tee": 1 if values.get("tee") == "on" else 0,
        "persistence": 1 if values.get("persistence") == "on" else 0,
    }
