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
    Rule-based planner — covers ~95% of real queries with zero LLM calls.
    Falls through to LLM only for genuinely ambiguous or complex phrasings.
    """
    text = user_input.strip().lower()

    # ── helpers ──────────────────────────────────────────────────────────────
    TRACE_KEYWORDS = ["full journey", "full flow", "trace", "journey", "flow",
                      "what happened", "end to end", "pipeline", "lifecycle",
                      "from start", "walk me through", "show me the path"]
    BROKEN_KEYWORDS = ["broken", "data quality", "issues", "missing link",
                       "incomplete", "broken flow", "anomal", "gap", "problem",
                       "without", "no delivery", "no journal", "no payment",
                       "not billed", "not delivered", "not paid", "mismatch",
                       "discrepan", "blocked partner", "identify.*sales orders.*broken",
                       "identify.*incomplete"]
    PRODUCTS_KEYWORDS = ["product", "material", "item", "sku"]
    BILLING_KEYWORDS  = ["billing", "invoice", "bill"]

    def _lookup(entity_type: str, entity_id: str) -> dict:
        related_map = {
            "customer":         ["addresses", "sales_area_config", "company_config"],
            "sales_order":      ["items", "schedule_lines", "billing_documents"],
            "delivery":         ["billing_documents"],
            "billing_document": ["journal_entries", "payments", "cancellations"],
            "product":          ["product_descriptions", "storage_locations"],
            "plant":            ["storage_locations"],
        }
        return {
            "intent": "lookup_entity",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "include_related": related_map.get(entity_type, []),
        }

    def _trace(entity_type: str, entity_id: str, stages: list | None = None) -> dict:
        default_stages = {
            "sales_order":      ["sales_order", "schedule_lines", "delivery", "billing", "journal_entry", "payment"],
            "billing_document": ["billing", "journal_entry", "payment"],
            "delivery":         ["delivery", "billing", "journal_entry", "payment"],
            "customer":         ["sales_order", "delivery", "billing", "journal_entry", "payment"],
        }
        return {
            "intent": "trace_flow",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "stages": stages or default_stages.get(entity_type, ["sales_order", "delivery", "billing", "journal_entry", "payment"]),
            "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
        }

    def _broken(break_types: list | None = None) -> dict:
        return {
            "intent": "find_broken_flows",
            "break_types": break_types or ALL_BREAK_TYPES,
            "filters": {"date_from": None, "date_to": None, "company_code": None, "fiscal_year": None},
        }

    def _top_products(limit: int = 10, sort_by: str = "total_net_amount") -> dict:
        return {
            "intent": "top_products_by_billing",
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "filters": {"date_from": None, "date_to": None, "company_code": None,
                        "customer_id": None, "exclude_cancelled": False, "product_group": None},
        }

    # ── 1. Guardrails: out-of-scope ───────────────────────────────────────────
    # Reject creative / general knowledge questions before hitting LLM
    oos_phrases = ["capital of", "who is", "what is the weather", "write a poem",
                   "tell me a joke", "recipe", "stock price", "translate", "explain quantum"]
    if any(p in text for p in oos_phrases):
        return {
            "intent": "reject",
            "reason": "out_of_scope",
            "clarification_needed": "This system only answers questions about the SAP Order-to-Cash dataset.",
        }

    # ── 2. Trace flow — sales order ───────────────────────────────────────────
    so_match = re.search(r"(?:sales\s*order|order|so)\s*(?:#|id\s*)?(\d{6,})", text)
    if so_match:
        if any(k in text for k in TRACE_KEYWORDS):
            return _trace("sales_order", so_match.group(1))
        # bare "show order X" / "order X" without trace keyword → lookup
        if any(k in text for k in ["show", "get", "fetch", "what", "status", "look", "details", "info", "payments", "billing", "delivery", "invoice"]):
            # if asking about payments/billing on a sales order → lookup with related
            return _lookup("sales_order", so_match.group(1))

    # ── 3. Trace flow — billing document ─────────────────────────────────────
    bill_match = re.search(r"(?:billing\s*(?:doc(?:ument)?)?|invoice|bill)\s*(?:#|id\s*)?(\d{6,})", text)
    if bill_match:
        if any(k in text for k in TRACE_KEYWORDS):
            return _trace("billing_document", bill_match.group(1))
        if any(k in text for k in ["show", "get", "fetch", "what", "status", "look", "details", "info", "payment", "journal"]):
            return _lookup("billing_document", bill_match.group(1))

    # ── 4. Trace flow — delivery ──────────────────────────────────────────────
    del_match = re.search(r"(?:delivery|shipment|outbound)\s*(?:#|id\s*)?(\d{6,})", text)
    if del_match:
        if any(k in text for k in TRACE_KEYWORDS):
            return _trace("delivery", del_match.group(1))
        if any(k in text for k in ["show", "get", "status", "look", "details", "info", "billing"]):
            return _lookup("delivery", del_match.group(1))

    # ── 5. Lookup — customer ──────────────────────────────────────────────────
    cust_match = re.search(r"(?:customer|client|partner|bp)\s*(?:#|id\s*)?(\d{6,})", text)
    if cust_match:
        if any(k in text for k in TRACE_KEYWORDS):
            return _trace("customer", cust_match.group(1))
        return _lookup("customer", cust_match.group(1))

    # ── 6. Lookup — product / material ───────────────────────────────────────
    # Product IDs look like "S8907367039280" or similar alphanumeric
    prod_match = re.search(r"(?:product|material|sku|item)\s*(?:#|id\s*)?([A-Z0-9]{6,})", user_input)
    if prod_match:
        return _lookup("product", prod_match.group(1))

    # ── 7. Top products ───────────────────────────────────────────────────────
    top_match = re.search(r"top\s*(\d+)?\s*products?", text)
    has_products = any(k in text for k in PRODUCTS_KEYWORDS)
    has_billing  = any(k in text for k in BILLING_KEYWORDS)
    is_ranking   = any(k in text for k in ["most", "highest", "top", "best", "ranked", "rank", "associated with", "number of billing", "number of invoice"])

    if top_match:
        limit   = int(top_match.group(1)) if top_match.group(1) else 10
        sort_by = "invoice_count" if any(k in text for k in ["invoice", "count", "number", "frequency"]) else "total_net_amount"
        if any(k in text for k in ["quantity", "qty", "units"]):
            sort_by = "quantity"
        return _top_products(limit, sort_by)

    if has_products and has_billing and is_ranking:
        sort_by = "invoice_count" if any(k in text for k in ["count", "number", "most", "frequency", "associated"]) else "total_net_amount"
        return _top_products(10, sort_by)

    if has_products and any(k in text for k in ["revenue", "sales", "amount"]):
        return _top_products(10, "total_net_amount")

    # ── 8. Broken flows — specific variants ──────────────────────────────────
    if any(re.search(p, text) for p in [r"delivered.*not.*bill", r"delivery.*no.*bill", r"ship.*not.*invoice"]):
        return _broken(["billing_without_delivery"])

    if any(re.search(p, text) for p in [r"billed.*no.*deliver", r"invoice.*no.*deliver", r"billing.*without.*delivery"]):
        return _broken(["billing_without_delivery"])

    if any(re.search(p, text) for p in [r"delivery.*no.*sales\s*order", r"delivery.*without.*order", r"orphan.*deliver"]):
        return _broken(["delivery_without_sales_order"])

    if any(re.search(p, text) for p in [r"journal.*without.*clear", r"uncleared", r"not.*cleared", r"open.*account"]):
        return _broken(["journal_entry_without_clearing"])

    if any(re.search(p, text) for p in [r"billing.*journal", r"no.*journal", r"journal.*missing", r"not.*posted"]):
        return _broken(["billing_without_journal_entry"])

    if any(re.search(p, text) for p in [r"amount.*mismatch", r"mismatch.*amount", r"discrepan", r"amount.*differ"]):
        return _broken(["amount_mismatch_billing_vs_journal"])

    if any(re.search(p, text) for p in [r"cancel", r"cancell"]):
        if "without" in text or "no " in text or "missing" in text:
            return _broken(["cancelled_without_accounting_doc"])

    if any(re.search(p, text) for p in [r"blocked.*partner", r"blocked.*customer", r"transaction.*blocked"]):
        return _broken(["active_txn_on_blocked_partner"])

    # General broken/quality catch-all
    if any(k in text for k in BROKEN_KEYWORDS):
        # Refine which break types to check
        types = list(ALL_BREAK_TYPES)
        if "delivery" in text and "sales" not in text:
            types = ["delivery_without_sales_order", "billing_without_delivery"]
        elif "journal" in text:
            types = ["billing_without_journal_entry", "journal_entry_without_clearing"]
        return _broken(types)

    # ── 9. Lookup via verb patterns ───────────────────────────────────────────
    for pattern, entity_type in [
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+(?:customer|client)\s+(?:id\s*)?(\d+)", "customer"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+(?:sales\s*order|order)\s+(?:id\s*)?(\d+)", "sales_order"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+(?:delivery|shipment)\s+(?:id\s*)?(\d+)", "delivery"),
        (r"(?:look\s*up|show|fetch|get|find|details?\s+(?:for|of)|info(?:rmation)?\s+(?:for|on|about))\s+(?:billing\s*(?:doc(?:ument)?)?|invoice)\s+(?:id\s*)?(\d+)", "billing_document"),
        (r"(?:list|show)\s+(?:all\s+)?payments?\s+for\s+(?:billing|invoice)\s+(\d+)", "billing_document"),
        (r"(?:payments?|invoices?)\s+for\s+(?:order|so)\s+(\d+)", "sales_order"),
    ]:
        m = re.search(pattern, text)
        if m:
            return _lookup(entity_type, m.group(1))

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
            preferred_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
            fallback_models = [
                preferred_model,
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash-lite",
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
