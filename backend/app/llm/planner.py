from __future__ import annotations

import json
import os
import re
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Load environment variables from `backend/.env` if present.
# This keeps local development simple and avoids needing to export GEMINI_API_KEY manually.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def _load_system_prompt() -> str:
    # IMPORTANT: this must be byte-for-byte the exact prompt provided by the spec.
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
        "FIELD RULES\n"
        "────────────────────────────────────────────\n"
        "  entity_id:  output exactly as given. If user gives a name not an ID → reject(ambiguous_entity).\n"
        "  dates:      ISO-8601 (YYYY-MM-DD). Resolve relative dates. If year unknown → reject.\n"
        "  null:       only for optional filter fields not specified by the user.\n"
        "  filters:    always include the filters object even if all values are null.\n"
        "  include_cancelled / exclude_cancelled: default false; set true only if user says so.\n"
        "\n"
        "────────────────────────────────────────────\n"
        "DECISION RULES\n"
        "────────────────────────────────────────────\n"
        "  Two questions in one message → reject(multiple_intents_detected).\n"
        "  Vague request with no ID or scope → reject(missing_required_parameter).\n"
        "  Mutation verb (delete/update/create/cancel/reverse/post) → reject(unsupported_operation).\n"
        "  Schema or system design question → reject(out_of_scope).\n"
        "  Customer name instead of ID → reject(ambiguous_entity).\n"
        "\n"
        "────────────────────────────────────────────\n"
        "NEVER\n"
        "────────────────────────────────────────────\n"
        "  Write SQL, SOQL, OData, or any query language fragment.\n"
        "  Include prose, chain-of-thought, or commentary in your response.\n"
        "  Invent entity IDs, product names, or dates not in the user message.\n"
        "  Add keys not in the schema for the chosen intent.\n"
        "  Return a partial JSON object.\n"
        "\n"
        "────────────────────────────────────────────\n"
        "EXAMPLES (user → JSON, no explanation)\n"
        "────────────────────────────────────────────\n"
        "\"Show order 740506\"\n"
        "→ {\"intent\":\"lookup_entity\",\"entity_type\":\"sales_order\",\"entity_id\":\"740506\",\"include_related\":[\"items\",\"schedule_lines\",\"billing_documents\"]}\n"
        "\n"
        "\"Delete invoices for customer X\"\n"
        "→ {\"intent\":\"reject\",\"reason\":\"unsupported_operation\",\"clarification_needed\":\"This system is read-only. Mutations must be made in the source ERP system.\"}\n"
        "\n"
        "\"Show me the orders\"\n"
        "→ {\"intent\":\"reject\",\"reason\":\"missing_required_parameter\",\"clarification_needed\":\"Please provide a sales order ID, customer ID, or date range.\"}\n"
    )


def _safe_extract_json(raw_text: str) -> dict[str, Any]:
    """
    Parse model output as JSON safely.
    - Tries direct json.loads first.
    - If that fails, tries to extract the substring between the first '{' and last '}'.
    - Returns a dict or raises ValueError.
    """
    candidate = raw_text.strip()

    # Remove common markdown fences if they exist.
    # (Spec requests raw JSON, but models may still wrap in ```json ... ```.)
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
    # OpenAI compatible shape: { choices: [ { message: { content: "..." } } ] }
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
    # Expected shape:
    # { candidates: [ { content: { parts: [ { text: "..." }, ... ] } } ] }
    return data["candidates"][0]["content"]["parts"][0]["text"]




def _rule_based_plan(user_input: str) -> dict[str, Any] | None:
    """
    Lightweight fallback for high-frequency prompts so users don't get false rejects.
    """
    text = user_input.strip().lower()

    sales_order_match = re.search(r"sales\s*order\s*(?:id\s*)?(\d+)", text)
    if sales_order_match and any(k in text for k in ["full journey", "full flow", "trace", "journey", "flow"]):
        so_id = sales_order_match.group(1)
        return {
            "intent": "trace_flow",
            "entity_type": "sales_order",
            "entity_id": so_id,
            "stages": ["sales_order", "schedule_lines", "delivery", "billing", "journal_entry", "payment"],
            "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
        }

    billing_match = re.search(r"billing\s*(?:doc(?:ument)?|invoice)?\s*(\d+)", text)
    if billing_match and any(k in text for k in ["full journey", "full flow", "trace", "journey", "flow"]):
        billing_id = billing_match.group(1)
        return {
            "intent": "trace_flow",
            "entity_type": "billing_document",
            "entity_id": billing_id,
            "stages": ["billing", "journal_entry", "payment"],
            "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False},
        }

    return None


def generate_query_plan(user_input: str) -> dict[str, Any]:
    """
    Generate a structured query plan by calling an LLM.

    Provider selection:
    - If GROQ_API_KEY is set, uses Groq.
    - Else if GEMINI_API_KEY is set, uses Gemini.
    - Else returns a reject plan describing the missing config.
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
            "clarification_needed": "LLM provider not configured. Set GROQ_API_KEY or GEMINI_API_KEY.",
        }

    try:
        if provider == "groq":
            model = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
            raw = _groq_chat_completion(system_prompt, user_input, model=model)
        else:
            preferred_model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
            # Some model aliases have shifted over time; try a fallback list if the first model 404s.
            fallback_models = [
                preferred_model,
                "gemini-flash-latest",
                "gemini-1.5-flash-latest",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
            ]
            last_err: Exception | None = None
            raw = None
            for m_name in fallback_models:
                try:
                    raw = _gemini_generate_content(system_prompt, user_input, model=m_name)
                    break
                except HTTPError as e:
                    last_err = e
                    # Retry only on "model not found" style errors.
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
            "clarification_needed": f"LLM request failed: {type(e).__name__}: {str(e)}",
        }

    try:
        parsed = _safe_extract_json(raw)


        if parsed.get("intent") == "trace_flow":
            if "stages" not in parsed:
                parsed["stages"] = [
                    "sales_order",
                    "delivery",
                    "billing",
                    "journal_entry",
                    "payment"
                ]
            if "filters" not in parsed:
                parsed["filters"] = {
                    "company_code": None,
                    "fiscal_year": None,
                    "include_cancelled": False
                }

        if parsed.get("intent") == "top_products_by_billing":
            parsed.setdefault("filters", {})

        if parsed.get("intent") == "find_broken_flows":
            parsed.setdefault("filters", {})

        return parsed
    except Exception as e:
        return {
            "intent": "reject",
            "reason": "out_of_scope",
            "clarification_needed": f"LLM returned invalid JSON: {type(e).__name__}: {str(e)}",
        }

