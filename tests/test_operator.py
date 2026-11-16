import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operator_onboarding import parse_operator


class OperatorFormTests(unittest.TestCase):
    def test_pending_operator_data_is_parsed(self):
        result = parse_operator({
            "node_code": "br-demo-02", "cnpj": "12.345.678/0001-90",
            "operator_name": "Operador de Teste Ltda", "uf": "RS",
            "node_label": "No local de teste", "capacity": "16",
            "rate": "0.75", "guarantee": "5000.00", "tee": "on",
        })
        self.assertEqual(result["code"], "BR-DEMO-02")
        self.assertEqual(result["cnpj"], "12345678000190")
        self.assertEqual(result["tee"], 1)
        self.assertEqual(result["persistence"], 0)

    def test_invalid_registration_is_rejected(self):
        base = {
            "node_code": "BR-DEMO-02", "cnpj": "12345678000190",
            "operator_name": "Operador de Teste Ltda", "uf": "RS",
            "node_label": "No local de teste", "capacity": "16",
            "rate": "0.75", "guarantee": "5000.00",
        }
        for changed in ({"node_code": "x"}, {"cnpj": "123"}, {"uf": "XX"},
                        {"capacity": "0"}, {"rate": "-1"}, {"guarantee": "1.234"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                parse_operator({**base, **changed})


if __name__ == "__main__":
    unittest.main()
