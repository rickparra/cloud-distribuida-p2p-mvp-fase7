import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import ROOT, sql_statements


class SchemaSetupTests(unittest.TestCase):
    def test_immutable_node_trigger_is_one_complete_setup_statement(self):
        statements = list(sql_statements(ROOT / "schema.sql"))
        trigger = next(
            statement for statement in statements
            if "TRG_F6POC_LEASE_NODE_IMMUTABLE" in statement
        )
        self.assertIn("BEFORE UPDATE OF NODE_CODE ON F6POC_LEASES", trigger)
        self.assertIn("RAISE_APPLICATION_ERROR(-20019, 'LEASE_NODE_IMMUTABLE')", trigger)
        self.assertTrue(trigger.rstrip().endswith("END;"))

    def test_active_lease_delete_guard_is_loaded(self):
        statements = list(sql_statements(ROOT / "schema.sql"))
        trigger = next(
            statement for statement in statements
            if "TRG_F6POC_LEASE_DELETE_GUARD" in statement
        )
        self.assertIn("BEFORE DELETE ON F6POC_LEASES", trigger)
        self.assertIn("RAISE_APPLICATION_ERROR(-20020, 'LEASE_ACTIVE_DELETE_FORBIDDEN')", trigger)

    def test_oracle_smoke_test_covers_both_lease_guards(self):
        smoke_source = (ROOT / "smoke_oracle.py").read_text(encoding="utf-8")
        self.assertIn("TRG_F6POC_LEASE_NODE_IMMUTABLE", smoke_source)
        self.assertIn("TRG_F6POC_LEASE_DELETE_GUARD", smoke_source)
        self.assertIn("!= 20019", smoke_source)
        self.assertIn("!= 20020", smoke_source)

    def test_concurrency_cleanup_releases_before_deleting_test_lease(self):
        smoke_source = (ROOT / "smoke_oracle.py").read_text(encoding="utf-8")
        start = smoke_source.index("def run_concurrent_capacity_check")
        cleanup = smoke_source.index("UPDATE F6POC_LEASES SET STATUS='FAILED'", start)
        delete_events = smoke_source.index("DELETE FROM F6POC_AUDIT_EVENTS", cleanup)
        delete_leases = smoke_source.index("DELETE FROM F6POC_LEASES", delete_events)
        self.assertLess(cleanup, delete_events)
        self.assertLess(delete_events, delete_leases)

    def test_seed_does_not_reset_operator_approval_or_price_on_restart(self):
        seed = (ROOT / "seed.sql").read_text(encoding="utf-8")
        self.assertNotIn("WHEN MATCHED THEN UPDATE", seed)

    def test_mvp_schema_stores_only_hashes_of_customer_workload(self):
        schema = (ROOT / "schema.sql").read_text(encoding="utf-8")
        start = schema.index("CREATE TABLE F7MVP_EXECUTIONS")
        end = schema.index("-- @statement", start)
        table = schema[start:end]
        self.assertIn("INPUT_SHA256", table)
        self.assertIn("RESULT_SHA256", table)
        self.assertNotIn("INPUT_JSON", table)
        self.assertNotIn("RESULT_JSON", table)


if __name__ == "__main__":
    unittest.main()
