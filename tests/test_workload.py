import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workload import compute_workload, parse_numbers


class WorkloadTests(unittest.TestCase):
    def test_worker_computes_a_real_result_for_the_allocated_node(self):
        result = compute_workload(
            {"job": "F7-DEMO", "node": "BR-TEE-01", "numbers": [12, 18, 30, 40]},
            "BR-TEE-01",
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["node_code"], "BR-TEE-01")
        self.assertEqual(result["result"], {
            "count": 4, "sum": 100, "minimum": 12, "maximum": 40, "average": "25.00",
        })
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_worker_rejects_a_task_allocated_to_another_node(self):
        with self.assertRaises(ValueError):
            compute_workload({"job": "F7-DEMO", "node": "EXT-TEE-01", "numbers": [1]}, "BR-TEE-01")

    def test_input_is_bounded_and_validated(self):
        self.assertEqual(parse_numbers("1, 2\n3"), [1, 2, 3])
        for value in ("", "1,,2", "abc", "1000001", ",".join(["1"] * 1001)):
            with self.subTest(value=value[:25]), self.assertRaises(ValueError):
                parse_numbers(value)
        with self.assertRaises(ValueError):
            compute_workload({"job": "F7-DEMO", "node": "BR-TEE-01", "numbers": [True]}, "BR-TEE-01")


if __name__ == "__main__":
    unittest.main()
