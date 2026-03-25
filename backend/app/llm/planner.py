from __future__ import annotations

import json
import os
import re
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def _load_system_prompt() -> str:
    return (
        "You are a query planner for an Order-to-Cash (O2C) data system. Your only job is to convert\n"
        "natural language questions into a structured JSON query plan. You do not answer questions\n"
        "directly. You do not write SQL. You do not explain your reasoning. You output JSON only.\n"
        "\n"
        "────────────────────────────────────────────\n"
        "OUTPUT CONTRACT\n"
        "────────────────────────────────────────────\n"
        "Your entire response must be a single, valid JSON object.\n"
        "- No markdown. No code fences. No explanation text before or after.\n"
        "- No keys outside the schema. No null placeholders for required fields.\n"
        "- If you are not certain of a value, use the reject intent.\n"
        "\n"
        "────────────────────────────────────────────\n"
        "AVAILABLE INTENTS — choose exactly one per response\n"
        "────────────────────────────────────────────\n"
        "  trace_flow              — follow a document/entity through the O2C pipeline\n"
        "  top_products_by_billing — rank products by billed amount, count, or quantity\n"
        "  find_broken_flows       — surface data quality issues and missing links\n"
        "  lookup_entity           — fetch a single entity record with optional related data\n"
        "  reject                  — mutation request / ambiguous / out of scope / multiple intents\n"
        "\n"
        "────────────────────────────────────────────\n"
        "SCHEMAS\n"
        "────────────────────────────────────────────\n"
        "trace_flow:\n"
        "  {\"intent\":\"trace_flow\",\"entity_type\":\"sales_order|billing_document|delivery|customer\",\n"
        "   \"entity_id\":\"<id>\",\"stages\":[\"sales_order\",\"delivery\",\"billing\",\"journal_entry\",\"payment\"],\n"
        "   \"filters\":{\"company_code\":null,\"fiscal_year\":null,\"include_cancelled\":false}}\n"
        "\n"
        "top_products_by_billing:\n"
        "  {\"intent\":\"top_products_by_billing\",\"limit\":10,\"sort_by\":\"total_net_amount|invoice_count|quantity\",\n"
        "   \"filters\":{\"date_from\":null,\"date_to\":null,\"company_code\":null,\"customer_id\":null,\n"
        "   \"exclude_cancelled\":false,\"product_group\":null}}\n"
        "\n"
        "find_broken_flows:\n"
        "  {\"intent\":\"find_broken_flows\",\n"
        "   \"break_types\":[\"billing_without_delivery\",\"delivery_without_sales_order\",\n"
        "   \"billing_without_journal_entry\",\"journal_entry_without_clearing\",\n"
        "   \"cancelled_without_accounting_doc\",\"active_txn_on_blocked_partner\",\n"
        "   \"amount_mismatch_billing_vs_journal\"],\n"
        "   \"filters\":{\"date_from\":null,\"date_to\":null,\"company_code\":null,\"fiscal_year\":null}}\n"
        "\n"
        "lookup_entity:\n"
        "  {\"intent\":\"lookup_entity\",\"entity_type\":\"customer|product|plant|sales_order|delivery|billing_document\",\n"
        "   \"entity_id\":\"<id>\",\"include_related\":[\"items\",\"billing_documents\",\"journal_entries\",\"payments\",\n"
        "   \"schedule_lines\",\"addresses\",\"sales_area_config\",\"company_config\",\n"
        "   \"product_descriptions\",\"storage_locations\",\"cancellations\"]}\n"
        "\n"
        "reject:\n"
        "  {\"intent\":\"reject\",\"reason\":\"out_of_scope|ambiguous_entity|unsupported_operation|\n"
        "   missing_required_parameter|multiple_intents_detected\",\n"
        "   \"clarification_needed\":\"<message>\"}\n"
        "\n"
        "────────────────────────────────────────────\n"
        "FIELD RULES\n"
        "────────────────────────────────────────────\n"
        "  entity_id:  output exactly as given. If user gives a name not an ID → reject(ambiguous_entity).\n"
        "  dates:      ISO-8601 (YYYY-MM-DD). Resolve relative dates. If year unknown → reject.\n"
        "  null:       only for optional filter fields not specified by the user.\n"
        "  filters:    always include the filters object even if all values are null.\n"
        "  include_cancelled / exclude_cancelled: default false; set true only if user says so.\n"
        "  top_products default: limit=10, sort_by=\"total_net_amount\" unless user specifies.\n"
        "  broken_flows default: include ALL break_types unless user specifies a subset.\n"
        "\n"
        "────────────────────────────────────────────\n"
        "DECISION RULES\n"
        "────────────────────────────────────────────\n"
        "  Two questions in one message → reject(multiple_intents_detected).\n"
        "  Vague request with no ID or scope → reject(missing_required_parameter).\n"
        "  Mutation verb (delete/update/create/cancel/reverse/post) → reject(unsupported_operation).\n"
        "  Schema or system design question → reject(out_of_scope).\n"
        "  Customer name instead of ID → reject(ambiguous_entity).\n"
        "  General knowledge question not about this dataset → reject(out_of_scope).\n"
        "\n"
        "────────────────────────────────────────────\n"
        "EXAMPLES\n"
        "────────────────────────────────────────────\n"
        "\"Show order 740506\" → {\"intent\":\"lookup_entity\",\"entity_type\":\"sales_order\",\"entity_id\":\"740506\",\"include_related\":[\"items\",\"schedule_lines\",\"billing_documents\"]}\n"
        "\"Top 5 products by invoice count\" → {\"intent\":\"top_products_by_billing\",\"limit\":5,\"sort_by\":\"invoice_count\",\"filters\":{\"date_from\":null,\"date_to\":null,\"company_code\":null,\"customer_id\":null,\"exclude_cancelled\":false,\"product_group\":null}}\n"
        "\"Find data quality issues\" → {\"intent\":\"find_broken_flows\",\"break_types\":[\"billing_without_delivery\",\"delivery_without_sales_order\",\"billing_without_journal_entry\",\"journal_entry_without_clearing\"],\"filters\":{\"date_from\":null,\"date_to\":null,\"company_code\":null,\"fiscal_year\":null}}\n"
        "\"Delete invoices for customer X\" → {\"intent\":\"reject\",\"reason\":\"unsupported_operation\",\"clarification_needed\":\"This system is read-only. Mutations must be made in the source ERP system.\"}\n"
        "\"What is the capital of France?\" → {\"intent\":\"reject\",\"reason\":\"out_of_scope\",\"clarification_needed\":\"This system is designed to answer questions about the O2C dataset only.\"}\n"
    )


def _safe_extract_json(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*```$", "", candidate)

    try:
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Parsed JSON is not an object")
        return parsed
    except Exception:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")

    sub = candidate[start : end + 1]
    parsed = json.loads(sub)
    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object")
    return parsed


def _groq_chat_completion(system_prompt: str, user_input: str, *, model: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY environment variable")

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")

    data = json.loads(body)
    return data["choices"][0]["message"]["content"]


def _gemini_generate_content(system_prompt: str, user_input: str, *, model: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "systemInstruction": {"role": "system", "parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_input}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")

    data = json.loads(body)
    return data["candidates"][0]["content"]["parts"][0]["text"]


ALL_BREAK_TYPES = [
    "billing_without_delivery",
    "delivery_without_sales_order",
    "billing_without_journal_entry",
    "journal_entry_without_clearing",
    "cancelled_without_accounting_doc",
    "active_txn_on_blocked_partner",
    "amount_mismatch_billing_vs_journal",
]


def _rule_based_plan(user_input: str) -> dict[str, Any] | None:
    """
    Rule-based fallback for common patterns to avoid LLM round-trip.
    """
    text = user_input.strip().lower()

    # Trace sales order flow
    sales_order_match = re.search(r"sales\s*order\s*(?:id\s*)?(\d+)", text)
    if sales_order_match and any(k in text for k in ["full journey", "full flow", "trace", "journey", "flow", "what happened"]):
        so_id = sales_order_match.group(1)
        return {
            "intent": "trace_flow",
            "entity_type": "sales_order",
            "entity_id": so_id,
            "stages": ["sales_order", "schedule_lines", "delivery", "billing", "journal_entry", "payment"],
            "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
        }

    # Trace billing doc flow
    billing_match = re.search(r"billing\s*(?:doc(?:ument)?|invoice)?\s*(\d+)", text)
    if billing_match and any(k in text for k in ["full journey", "full flow", "trace", "journey", "flow", "what happened"]):
        billing_id = billing_match.group(1)
        return {
            "intent": "trace_flow",
            "entity_type": "billing_document",
            "entity_id": billing_id,
            "stages": ["billing", "journal_entry", "payment"],
            "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
        }

    # Broken/quality/issues
    if any(k in text for k in ["broken", "data quality", "issues", "missing link", "incomplete", "broken flow"]):
        break_types = ALL_BREAK_TYPES
        # Refine by keyword
        if "delivery" in text and "sales" not in text:
            break_types = ["delivery_without_sales_order", "billing_without_delivery"]
        elif "journal" in text:
            break_types = ["billing_without_journal_entry", "journal_entry_without_clearing"]
        elif "billing" in text and "delivery" in text:
            break_types = ["billing_without_delivery"]
        elif "cancelled" in text or "cancel" in text:
            break_types = ["cancelled_without_accounting_doc"]
        return {
            "intent": "find_broken_flows",
            "break_types": break_types,
            "filters": {"date_from": None, "date_to": None, "company_code": None, "fiscal_year": None},
        }

    # Top products - simple patterns
    top_match = re.search(r"top\s*(\d+)?\s*products?", text)
    if top_match or "highest.*billing" in text or "most billed" in text or "revenue" in text and "product" in text:
        limit = int(top_match.group(1)) if (top_match and top_match.group(1)) else 10
        sort_by = "invoice_count" if "invoice" in text or "count" in text else "total_net_amount"
        if "quantity" in text or "qty" in text:
            sort_by = "quantity"
        return {
            "intent": "top_products_by_billing",
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "filters": {"date_from": None, "date_to": None, "company_code": None, "customer_id": None, "exclude_cancelled": False, "product_group": None},
        }

    # Lookup patterns
    lookup_patterns = [
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+"
         r"(?:customer|client)\s+(?:id\s*)?(\d+)", "customer"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+"
         r"(?:sales\s*order)\s+(?:id\s*)?(\d+)", "sales_order"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+"
         r"(?:delivery|shipment)\s+(?:id\s*)?(\d+)", "delivery"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+"
         r"(?:billing\s*(?:doc(?:ument)?)?|invoice)\s+(?:id\s*)?(\d+)", "billing_document"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+"
         r"(?:product|material)\s+(\S+)", "product"),
        # Also handle: "customer 310000108" directly
        (r"\bcustomer\s+(?:id\s*)?(\d+)\b", "customer"),
        (r"\bsales\s*order\s+(?:id\s*)?(\d+)\b", "sales_order"),
        (r"\bdelivery\s+(?:id\s*)?(\d+)\b", "delivery"),
        (r"\bproduct\s+(\S+)\b", "product"),
    ]

    for pattern, entity_type in lookup_patterns:
        m = re.search(pattern, text)
        if m:
            entity_id = m.group(1)
            related_map = {
                "customer": ["addresses", "sales_area_config", "company_config"],
                "sales_order": ["items", "schedule_lines", "billing_documents"],
                "delivery": ["billing_documents"],
                "billing_document": ["journal_entries", "payments", "cancellations"],
                "product": ["product_descriptions", "storage_locations"],
            }
            return {
                "intent": "lookup_entity",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "include_related": related_map.get(entity_type, []),
            }

    return None


def _apply_defaults(parsed: dict[str, Any]) -> dict[str, Any]:
    """Apply sane defaults to LLM output to avoid validation failures."""
    intent = parsed.get("intent")

    if intent == "trace_flow":
        if "stages" not in parsed or not parsed["stages"]:
            parsed["stages"] = ["sales_order", "delivery", "billing", "journal_entry", "payment"]
        if "filters" not in parsed:
            parsed["filters"] = {"company_code": None, "fiscal_year": None, "include_cancelled": False}

    if intent == "top_products_by_billing":
        parsed.setdefault("limit", 10)
        parsed.setdefault("sort_by", "total_net_amount")
        parsed.setdefault("filters", {})
        f = parsed["filters"]
        f.setdefault("date_from", None)
        f.setdefault("date_to", None)
        f.setdefault("company_code", None)
        f.setdefault("customer_id", None)
        f.setdefault("exclude_cancelled", False)
        f.setdefault("product_group", None)

    if intent == "find_broken_flows":
        if "break_types" not in parsed or not parsed["break_types"]:
            parsed["break_types"] = ALL_BREAK_TYPES
        parsed.setdefault("filters", {})
        f = parsed["filters"]
        f.setdefault("date_from", None)
        f.setdefault("date_to", None)
        f.setdefault("company_code", None)
        f.setdefault("fiscal_year", None)

    if intent == "lookup_entity":
        parsed.setdefault("include_related", [])

    return parsed


def generate_query_plan(user_input: str) -> dict[str, Any]:
    """
    Generate a structured query plan from natural language.

    Priority:
    1. Rule-based fast path (no LLM needed)
    2. GROQ if GROQ_API_KEY set
    3. Gemini if GEMINI_API_KEY set
    4. Reject with helpful message if no provider configured
    """
    direct_plan = _rule_based_plan(user_input)
    if direct_plan is not None:
        return direct_plan

    system_prompt = _load_system_prompt()

    provider = "groq" if os.environ.get("GROQ_API_KEY") else "gemini" if os.environ.get("GEMINI_API_KEY") else None
    if provider is None:
        return {
            "intent": "reject",
            "reason": "out_of_scope",
            "clarification_needed": (
                "No LLM provider configured. Set GROQ_API_KEY or GEMINI_API_KEY in backend/.env "
                "to enable natural language queries. Visit groq.com or ai.google.dev for free API keys."
            ),
        }

    try:
        if provider == "groq":
            model = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
            raw = _groq_chat_completion(system_prompt, user_input, model=model)
        else:
            preferred_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
            fallback_models = [
                preferred_model,
                "gemini-2.0-flash-001",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-flash-latest",
            ]
            last_err: Exception | None = None
            raw = None
            for m_name in fallback_models:
                try:
                    raw = _gemini_generate_content(system_prompt, user_input, model=m_name)
                    break
                except HTTPError as e:
                    last_err = e
                    if getattr(e, "code", None) == 404 or "404" in str(e):
                        continue
                    raise
            if raw is None:
                assert last_err is not None
                raise last_err
    except Exception as e:
        return {
            "intent": "reject",
            "reason": "out_of_scope",
            "clarification_needed": f"LLM request failed: {type(e).__name__}: {str(e)[:200]}",
        }

    try:
        parsed = _safe_extract_json(raw)
        parsed = _apply_defaults(parsed)
        return parsed
    except Exception as e:
        return {
            "intent": "reject",
            "reason": "out_of_scope",
            "clarification_needed": f"LLM returned invalid JSON: {type(e).__name__}: {str(e)[:200]}",
        }
