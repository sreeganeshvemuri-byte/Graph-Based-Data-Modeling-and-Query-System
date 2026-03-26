"""
Rule-based planner for the 3 deterministic task examples.
Everything else falls through to the dynamic SQL engine.

Returns a plan dict (ready for validate_query_plan) or None.
"""
from __future__ import annotations

import re
from typing import Any

ALL_BREAK_TYPES = [
    "billing_without_delivery",
    "delivery_without_sales_order",
    "billing_without_journal_entry",
    "journal_entry_without_clearing",
    "cancelled_without_accounting_doc",
    "active_txn_on_blocked_partner",
    "amount_mismatch_billing_vs_journal",
]

_TRACE_KW = ["full journey", "full flow", "trace", "journey", "flow",
             "what happened", "end to end", "pipeline", "lifecycle",
             "walk me through", "show me the path"]

_BROKEN_KW = ["broken", "data quality", "issue", "missing link", "incomplete flow",
              "identify.*broken", "identify.*incomplete", "broken flow"]

_BROKEN_SPECIFIC = {
    "billing_without_delivery":     [r"billed.*no.*deliver", r"billing.*without.*deliver", r"not.*delivered.*billed"],
    "delivery_without_sales_order": [r"delivery.*no.*order", r"delivery.*without.*order", r"orphan.*deliver"],
    "billing_without_journal_entry":[r"billing.*no.*journal", r"not.*posted", r"billing.*journal.*missing"],
    "journal_entry_without_clearing":[r"uncleared", r"not.*cleared", r"journal.*without.*clear"],
    "amount_mismatch_billing_vs_journal": [r"amount.*mismatch", r"mismatch.*amount", r"discrepan"],
    "cancelled_without_accounting_doc":   [r"cancel.*without", r"cancel.*no.*account"],
    "active_txn_on_blocked_partner":      [r"blocked.*partner", r"blocked.*customer"],
}

def _trace(entity_type: str, entity_id: str, stages: list | None = None) -> dict:
    return {
        "intent": "trace_flow",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "stages": stages or {
            "sales_order": ["sales_order", "schedule_lines", "delivery", "billing", "journal_entry", "payment"],
            "billing_document": ["billing", "journal_entry", "payment"],
            "delivery": ["delivery", "billing", "journal_entry", "payment"],
            "customer": ["sales_order", "delivery", "billing", "journal_entry", "payment"],
        }.get(entity_type, ["sales_order", "delivery", "billing", "journal_entry", "payment"]),
        "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
    }

def _top_products(limit: int = 10, sort_by: str = "total_net_amount") -> dict:
    return {
        "intent": "top_products_by_billing",
        "limit": min(limit, 100),
        "sort_by": sort_by,
        "filters": {"date_from": None, "date_to": None, "company_code": None,
                    "customer_id": None, "exclude_cancelled": False, "product_group": None},
    }

def _broken(types: list | None = None) -> dict:
    return {
        "intent": "find_broken_flows",
        "break_types": types or ALL_BREAK_TYPES,
        "filters": {"date_from": None, "date_to": None, "company_code": None, "fiscal_year": None},
    }


def _resolve_entity_from_history(query: str, history: list[dict]) -> str:
    """If query has no explicit 6+ digit ID, try to pull one from history."""
    if re.search(r"\b\d{6,}\b", query):
        return query  # already has explicit ID

    text = query.lower()
    all_history = " ".join(t.get("content", "") for t in reversed(history)).lower()

    # If asking about a flow/trace — look for sales order first
    if any(k in text for k in ["flow", "journey", "trace", "full", "pipeline"]):
        m = re.search(r"\bsales[_ ]order[_ ](\d{6,})\b", all_history)
        if m:
            return f"{query} (sales order {m.group(1)})"

    # Determine what entity type user is hinting at
    type_map = [
        (["billing", "invoice", "bill"],  r"\bbilling[_ ](?:doc(?:ument)?[_ ])?(\d{6,})\b"),
        (["delivery", "shipment"],         r"\bdelivery[_ ](\d{6,})\b"),
        (["customer", "client", "partner"],r"\bcustomer[_ ](\d{6,})\b"),
        (["order"],                        r"\bsales[_ ]order[_ ](\d{6,})\b"),
    ]
    for keywords, pattern in type_map:
        if any(k in text for k in keywords):
            m = re.search(pattern, all_history)
            if m:
                label = keywords[0]
                return f"{query} ({label} {m.group(1)})"

    # Fallback: most recent entity in history
    for pattern, label in [
        (r"\bsales[_ ]order[_ ](\d{6,})\b", "sales order"),
        (r"\bbilling[_ ](?:doc[_ ])?(\d{6,})\b", "billing document"),
        (r"\bdelivery[_ ](\d{6,})\b", "delivery"),
        (r"\bcustomer[_ ](\d{6,})\b", "customer"),
    ]:
        m = re.search(pattern, all_history)
        if m:
            return f"{query} ({label} {m.group(1)})"

    return query


def rule_based_plan(query: str, history: list[dict] | None = None) -> dict | None:
    """
    Returns a structured plan for the 3 task examples, or None.
    None means: hand off to dynamic SQL engine.
    """
    history = history or []
    resolved = _resolve_entity_from_history(query, history)
    text = resolved.lower()

    # ── Trace flow ────────────────────────────────────────────────────────────
    so_m = re.search(r"(?:sales[_ ]order|order|so)[_ ](?:id[_ ])?(\d{6,})", text)
    bd_m = re.search(r"(?:billing[_ ](?:doc(?:ument)?)?|invoice)[_ ](?:id[_ ])?(\d{6,})", text)
    dl_m = re.search(r"(?:delivery|shipment)[_ ](?:id[_ ])?(\d{6,})", text)
    cu_m = re.search(r"(?:customer|client)[_ ](?:id[_ ])?(\d{6,})", text)

    has_trace = any(k in text for k in _TRACE_KW)

    if so_m and has_trace:
        return _trace("sales_order", so_m.group(1))
    if bd_m and has_trace:
        return _trace("billing_document", bd_m.group(1))
    if dl_m and has_trace:
        return _trace("delivery", dl_m.group(1))
    if cu_m and has_trace:
        return _trace("customer", cu_m.group(1))

    # ── Top products ──────────────────────────────────────────────────────────
    top_m = re.search(r"top\s*(\d+)?\s*products?", text)
    is_product_rank = (
        any(k in text for k in ["product", "material", "sku"]) and
        any(k in text for k in ["most", "highest", "top", "rank", "associated with", "number of billing", "number of invoice"])
    )
    if top_m or is_product_rank or ("products" in text and "revenue" in text):
        limit = int(top_m.group(1)) if (top_m and top_m.group(1)) else 10
        sort_by = "invoice_count" if any(k in text for k in ["count", "number", "frequency", "most"]) else "total_net_amount"
        if any(k in text for k in ["quantity", "qty", "units"]):
            sort_by = "quantity"
        return _top_products(limit, sort_by)

    # ── Broken flows ──────────────────────────────────────────────────────────
    # Check specific break type patterns first
    for break_type, patterns in _BROKEN_SPECIFIC.items():
        if any(re.search(p, text) for p in patterns):
            return _broken([break_type])

    # General broken flow catch
    if any(re.search(p, text) for p in [re.escape(k) for k in _BROKEN_KW] + list(_BROKEN_KW)):
        return _broken()

    return None  # → dynamic SQL engine
