"""Small, bounded workload used by the functional MVP.

The sample values are synthetic. The worker does not execute uploaded code or
process real personal data.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal


MAX_VALUES = 1000
MAX_ABS_VALUE = 1_000_000


def parse_numbers(raw: str) -> list[int]:
    parts = [part.strip() for part in raw.replace("\n", ",").split(",")]
    if not parts or len(parts) > MAX_VALUES or any(not part for part in parts):
        raise ValueError("Informe de 1 a 1000 numeros inteiros separados por virgula.")
    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise ValueError("O lote deve conter apenas numeros inteiros.") from exc
    if any(abs(value) > MAX_ABS_VALUE for value in values):
        raise ValueError("Cada numero deve estar entre -1000000 e 1000000.")
    return values


def compute_workload(payload: dict, expected_node: str) -> dict:
    if payload.get("node") != expected_node:
        raise ValueError("Esta tarefa foi alocada para outro no.")
    job = payload.get("job")
    values = payload.get("numbers")
    if not isinstance(job, str) or not job:
        raise ValueError("Identificador da tarefa ausente.")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
        raise ValueError("Lote numerico invalido.")
    if any(type(value) is not int or abs(value) > MAX_ABS_VALUE for value in values):
        raise ValueError("Lote numerico invalido.")

    total = sum(values)
    canonical = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return {
        "status": "COMPLETED",
        "node_code": expected_node,
        "job_code": job,
        "result": {
            "count": len(values),
            "sum": total,
            "minimum": min(values),
            "maximum": max(values),
            "average": str((Decimal(total) / Decimal(len(values))).quantize(Decimal("0.01"))),
        },
        "input_sha256": hashlib.sha256(canonical).hexdigest(),
    }
