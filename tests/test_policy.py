import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import parse_submission, rejection_reason


def node(**overrides):
    data = {
        "country": "BR", "tee": 1, "persistence": 0, "approved": 1,
        "capacity": 100, "rate": Decimal("0.50"),
    }
    data.update(overrides)
    return data


class EligibilityTests(unittest.TestCase):
    def test_sensitive_load_requires_brazil_and_tee(self):
        self.assertEqual(rejection_reason("PESSOAL_SENSIVEL", 4, 20, node(country="US")), "NO_FORA_DO_BRASIL")
        self.assertEqual(rejection_reason("PESSOAL", 4, 20, node(tee=0)), "NO_SEM_EXECUCAO_CONFIDENCIAL")

    def test_all_loads_require_approved_ephemeral_node_and_capacity(self):
        self.assertEqual(rejection_reason("PUBLICO", 4, 20, node(approved=0)), "OPERADOR_NAO_HOMOLOGADO")
        self.assertEqual(rejection_reason("PUBLICO", 4, 20, node(persistence=1)), "NO_COM_PERSISTENCIA_LOCAL")
        self.assertEqual(rejection_reason("PUBLICO", 101, 100, node()), "CAPACIDADE_INSUFICIENTE")

    def test_public_load_can_use_foreign_node_without_tee(self):
        self.assertEqual(rejection_reason("PUBLICO", 4, 20, node(country="US", tee=0)), "ELEGIVEL")

    def test_budget_is_enforced(self):
        self.assertEqual(rejection_reason("PUBLICO", 4, 1, node()), "ACIMA_DO_TETO")
        self.assertEqual(rejection_reason("PUBLICO", 4, 2, node()), "ELEGIVEL")

    def test_reserved_capacity_is_not_offered_twice(self):
        self.assertEqual(rejection_reason("PUBLICO", 1, 2, node(capacity=4, reserved=4)), "CAPACIDADE_INSUFICIENTE")

    def test_submission_validation(self):
        self.assertEqual(parse_submission({"classification":"INTERNO", "vcpu":"2", "budget":"2"}),
                         ("INTERNO", Decimal("2"), Decimal("2")))
        self.assertEqual(parse_submission({"classification":"PUBLICO", "vcpu":"1", "budget":"1.230"})[2], Decimal("1.230"))
        for values in (
            {"classification":"INVENTADO", "vcpu":"1", "budget":"2"},
            {"classification":"PUBLICO", "vcpu":"abc", "budget":"2"},
            {"classification":"PUBLICO", "vcpu":"0", "budget":"2"},
            {"classification":"PUBLICO", "vcpu":"1.5", "budget":"2"},
            {"classification":"PUBLICO", "vcpu":"1", "budget":"-1"},
            {"classification":"PUBLICO", "vcpu":"1", "budget":"1.999"},
            {"classification":"PUBLICO", "vcpu":"1000000", "budget":"10"},
            {"classification":"PUBLICO", "vcpu":"1", "budget":"10000000000"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                parse_submission(values)


if __name__ == "__main__":
    unittest.main()
