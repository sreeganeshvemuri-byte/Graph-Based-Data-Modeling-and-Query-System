from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from typing import Any

from sqlalchemy import func, select


# Allow `from app...` imports when tests run from repo root.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


from app.db.session import SessionLocal, init_db
from app.db.models import GraphEdge, SalesOrderHeader
from app.query.execute import execute_query_plan
from app.query.validation import validate_query_plan


def _db_has_graph_data(session) -> bool:
    cnt = session.execute(select(func.count()).select_from(GraphEdge)).scalar_one()
    return int(cnt) > 0


def _db_has_sales_orders(session) -> bool:
    cnt = session.execute(select(func.count()).select_from(SalesOrderHeader)).scalar_one()
    return int(cnt) > 0


class QuerySystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def setUp(self) -> None:
        self.session = SessionLocal()
        if not _db_has_graph_data(self.session) or not _db_has_sales_orders(self.session):
            self.skipTest("Database is empty. Run ingestion + graph edge build first.")

    def tearDown(self) -> None:
        self.session.close()

    def test_trace_flow_plan_returns_delivery_billing_accounting(self) -> None:
        plan: dict[str, Any] = {
            "intent": "trace_flow",
            "entity_type": "sales_order",
            "entity_id": "740509",
            "stages": [
                "sales_order",
                "schedule_lines",
                "delivery",
                "billing",
                "journal_entry",
                "payment",
            ],
            "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
        }
        result = execute_query_plan(self.session, plan)
        self.assertEqual(result["intent"], "trace_flow")

        nodes = result["path"]["nodes"]
        edges = result["path"]["edges"]
        node_types = {n["type"] for n in nodes}
        edge_types = {e["edge_type"] for e in edges}

        # Expected path segments
        self.assertIn("delivery", node_types)
        self.assertIn("billing_document", node_types)
        self.assertIn("accounting_document", node_types)
        self.assertIn("FULFILLED_BY", edge_types)
        self.assertIn("BILLED_AS", edge_types)
        self.assertIn("POSTS_TO", edge_types)

        # No duplicate nodes
        node_keys = {(n["type"], n["id"]) for n in nodes}
        self.assertEqual(len(node_keys), len(nodes))

        # Traversal stops within requested stages: since we didn't request "cancellation",
        # ensure no cancellation nodes appear.
        cancellation_nodes = [n for n in nodes if n["type"] == "cancellation"]
        self.assertEqual(len(cancellation_nodes), 0)

    def test_top_products_by_billing_returns_sorted_top_n(self) -> None:
        plan: dict[str, Any] = {
            "intent": "top_products_by_billing",
            "limit": 5,
            "sort_by": "total_net_amount",
            "filters": {
                "date_from": date(2025, 4, 1),
                "date_to": date(2025, 4, 30),
                "company_code": None,
                "customer_id": None,
                "exclude_cancelled": True,
                "product_group": None,
            },
        }
        result = execute_query_plan(self.session, plan)
        self.assertEqual(result["intent"], "top_products_by_billing")
        self.assertEqual(len(result["results"]), 5)
        self.assertTrue(all("product_id" in r for r in result["results"]))

        amounts = [r["total_net_amount"] for r in result["results"]]
        self.assertTrue(all(a >= b for a, b in zip(amounts, amounts[1:])))

    def test_find_broken_flows_returns_issues_list(self) -> None:
        plan: dict[str, Any] = {
            "intent": "find_broken_flows",
            "break_types": [
                "billing_without_delivery",
                "delivery_without_sales_order",
                "billing_without_journal_entry",
                "journal_entry_without_clearing",
            ],
            "filters": {"date_from": None, "date_to": None, "company_code": None, "fiscal_year": "2025"},
        }
        result = execute_query_plan(self.session, plan)
        self.assertEqual(result["intent"], "find_broken_flows")
        self.assertIn("issues", result)
        self.assertTrue(isinstance(result["issues"], list))
        self.assertTrue(len(result["issues"]) > 0)
        self.assertTrue(all("break_type" in i for i in result["issues"][:10]))

    def test_lookup_entity_customer_returns_details(self) -> None:
        plan: dict[str, Any] = {
            "intent": "lookup_entity",
            "entity_type": "customer",
            "entity_id": "320000083",
            "include_related": ["addresses", "sales_area_config", "company_config"],
        }
        result = execute_query_plan(self.session, plan)
        self.assertEqual(result["intent"], "lookup_entity")
        self.assertIn("entity", result)
        self.assertEqual(result["entity"]["businessPartner"], "320000083")
        self.assertIn("related", result)
        self.assertIn("addresses", result["related"])

    def test_guardrails_reject_invalid_intent(self) -> None:
        # Validation layer: invalid intent should become a reject response.
        raw_plan = {"intent": "write_poem", "foo": "bar"}
        rejected = validate_query_plan(raw_plan)
        self.assertEqual(rejected["intent"], "reject")
        self.assertIn("reason", rejected)
        self.assertIn("clarification_needed", rejected)

    @unittest.skipUnless(os.environ.get("RUN_LLM_TESTS") == "1", "Set RUN_LLM_TESTS=1 to run LLM-dependent tests.")
    def test_llm_inputs_smoke(self) -> None:
        """
        Optional integration test that exercises:
        user input -> LLM planner -> validation -> execution.
        """
        from app.llm.planner import generate_query_plan
        from app.query.execute import execute_query_plan as _exec
        from app.query.plans import parse_query_plan_or_reject
        from app.query.validation import validate_query_plan as _validate

        def run(raw_input: str) -> dict[str, Any]:
            plan = generate_query_plan(raw_input)
            validated = _validate(plan)
            res = _exec(self.session, validated)
            return {"plan": validated, "result": res}

        # 1) trace_flow
        out1 = run("Show full journey for sales order 740509")
        self.assertEqual(out1["plan"]["intent"], "trace_flow")
        self.assertEqual(out1["result"]["intent"], "trace_flow")
        self.assertTrue(len(out1["result"]["path"]["edges"]) > 0)

        # 2) top_products_by_billing
        out2 = run("Top 5 products by revenue")
        self.assertEqual(out2["plan"]["intent"], "top_products_by_billing")
        self.assertIn("results", out2["result"])
        self.assertTrue(isinstance(out2["result"]["results"], list))
        self.assertTrue(len(out2["result"]["results"]) > 0)

        # 3) find_broken_flows
        out3 = run("Show broken flows")
        self.assertEqual(out3["plan"]["intent"], "find_broken_flows")
        self.assertIn("issues", out3["result"])
        self.assertTrue(isinstance(out3["result"]["issues"], list))

        # 4) lookup_entity
        out4 = run("Show customer 320000083")
        self.assertEqual(out4["plan"]["intent"], "lookup_entity")
        self.assertEqual(out4["result"]["intent"], "lookup_entity")
        self.assertEqual(out4["result"]["entity"]["businessPartner"], "320000083")

        # 5) guardrails
        out5 = run("Write me a poem")
        self.assertEqual(out5["plan"]["intent"], "reject")


if __name__ == "__main__":
    unittest.main()

