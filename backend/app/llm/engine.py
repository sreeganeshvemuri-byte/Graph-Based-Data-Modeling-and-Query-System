"""
O2C Query Engine — Clean rewrite
=================================
Architecture:
  1. TRIAGE  — classify query (domain check, type detection)
  2. PLAN    — LLM decides which SQL queries to run
  3. EXECUTE — run SQL safely, collect rows
  4. ANSWER  — LLM writes grounded NL answer from real data

No intent locking. No hardcoded SQL. LLM drives everything with
the full schema as context. Two LLM calls per query max.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

# ─────────────────────────────────────────────────────────────────────────────
# 1. LLM CALL (single function, model resolved once)
# ─────────────────────────────────────────────────────────────────────────────

# Model cascade — tried in order, skips any that return 429
# Each model has its own independent rate-limit pool on Gemini's free tier
GEMINI_MODEL_CASCADE = [
    "gemini-2.5-flash-lite",   # fastest, highest RPM
    "gemini-2.0-flash-lite",   # separate pool
    "gemma-3-27b-it",          # Gemma pool, completely independent
    "gemma-3-4b-it",           # smaller Gemma, very high RPM
    "gemini-2.0-flash",        # fallback flash
]

import time as _time

class RateLimitError(Exception):
    pass

def _call_gemini_model(model: str, system: str, user: str, temperature: float, max_tokens: int, key: str) -> str:
    """Call one specific Gemini/Gemma model. Raises RateLimitError on 429.
    
    Gemma models (gemma-3-*) don't support systemInstruction — for those,
    we prepend the system prompt to the user message instead.
    """
    from urllib.error import HTTPError
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    
    is_gemma = model.startswith("gemma")
    if is_gemma:
        # Gemma: no systemInstruction, prepend to user turn
        combined_user = system + "\n\n" + user

        payload = {
            "contents": [{"role": "user", "parts": [{"text": combined_user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
    else:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"].strip()
    except HTTPError as e:
        if e.code == 429:
            raise RateLimitError(f"{model} rate limited")
        raise

def _call_llm(system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 1024) -> str:
    """
    LLM call with model cascade.
    Tries each Gemini/Gemma model in order — if one is 429, moves to the next.
    Falls back to Groq if all Gemini models are rate-limited.
    Raises RateLimitError only if ALL providers are exhausted.
    """
    from urllib.error import HTTPError
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key   = os.environ.get("GROQ_API_KEY")

    # Override cascade from env (e.g. GEMINI_MODEL=gemma-3-27b-it to pin a model)
    env_model = os.environ.get("GEMINI_MODEL")
    models = [env_model] + [m for m in GEMINI_MODEL_CASCADE if m != env_model] if env_model else GEMINI_MODEL_CASCADE

    if gemini_key:
        last_err = None
        for model in models:
            try:
                return _call_gemini_model(model, system, user, temperature, max_tokens, gemini_key)
            except RateLimitError as e:
                last_err = e
                continue  # try next model
            except Exception:
                raise
        # All Gemini models rate-limited — fall through to Groq or raise

    if groq_key:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": os.environ.get("GROQ_MODEL", "llama3-8b-8192"),
            "temperature": temperature, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bearer {groq_key}",
                                              "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except HTTPError as e:
            if e.code == 429:
                raise RateLimitError("All providers rate limited. Please wait a moment.")
            raise

    if not gemini_key and not groq_key:
        raise RuntimeError("No LLM provider. Set GEMINI_API_KEY or GROQ_API_KEY in backend/.env")

    raise RateLimitError("All models rate limited. Please wait a moment and try again.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. SCHEMA CONTEXT  (full schema as RAG — injected into every LLM call)
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
SAP Order-to-Cash (O2C) SQLite database. All IDs are VARCHAR strings.

TABLE sales_order_headers        — one row per sales order
  salesOrder VARCHAR PK          — e.g. '740506'
  soldToParty VARCHAR            — customer ID → business_partners.businessPartner
  totalNetAmount FLOAT           — total order value
  status VARCHAR                 — 'C'=complete 'A'=open
  creationDate DATETIME

TABLE sales_order_items          — line items within a sales order
  salesOrder VARCHAR             — → sales_order_headers
  item VARCHAR                   — '10','20'…
  material VARCHAR               — product ID → products.product
  netAmount FLOAT
  quantity FLOAT
  productionPlant VARCHAR        — → plants.plant

TABLE sales_order_schedule_lines — confirmed delivery dates per item
  salesOrder VARCHAR
  item VARCHAR
  scheduleLine VARCHAR
  confirmedDeliveryDate DATETIME
  confdOrderQty FLOAT

TABLE outbound_delivery_headers  — one row per delivery
  deliveryDocument VARCHAR PK    — e.g. '80738040'
  pickingStatus VARCHAR          — 'C'=picked
  goodsMovementStatus VARCHAR    — 'C'=shipped
  shippingPoint VARCHAR

TABLE outbound_delivery_items    — items in a delivery
  deliveryDocument VARCHAR       — → outbound_delivery_headers
  item VARCHAR
  referenceSdDocument VARCHAR    — links back to salesOrder
  referenceSdDocumentItem VARCHAR
  plant VARCHAR
  batch VARCHAR

TABLE billing_document_headers   — invoice / billing document
  billingDocument VARCHAR PK     — e.g. '90504274'
  soldToParty VARCHAR            — → business_partners
  companyCode VARCHAR
  billingDocumentDate DATETIME
  accountingDocument VARCHAR     — → journal_entry_items_ar
  fiscalYear VARCHAR
  totalNetAmount FLOAT
  isCancelled BOOLEAN            — 0=active 1=cancelled

TABLE billing_document_items     — line items on a billing doc
  billingDocument VARCHAR        — → billing_document_headers
  item VARCHAR
  referenceSdDocument VARCHAR    — links back to salesOrder
  material VARCHAR               — → products.product
  netAmount FLOAT

TABLE billing_document_cancellations  — cancelled docs
  billingDocument VARCHAR PK

TABLE journal_entry_items_ar     — AR accounting entries
  accountingDocument VARCHAR
  item VARCHAR
  customer VARCHAR               — → business_partners
  referenceDocument VARCHAR      — → billing_document_headers.billingDocument
  companyCode VARCHAR
  fiscalYear VARCHAR
  postingDate DATETIME
  amountInCompanyCodeCurrency FLOAT
  glAccount VARCHAR
  clearingAccountingDocument VARCHAR  — set = cleared/paid

TABLE payments_accounts_receivable   — payment records
  accountingDocument VARCHAR
  item VARCHAR
  customer VARCHAR
  clearingAccountingDocument VARCHAR
  postingDate DATETIME

TABLE business_partners          — customers / partners
  businessPartner VARCHAR PK     — e.g. '310000108'
  fullName VARCHAR               — e.g. 'Cardenas, Parker and Avila'
  category VARCHAR
  isBlocked BOOLEAN
  isMarkedForArchiving BOOLEAN
  region VARCHAR
  grouping VARCHAR

TABLE business_partner_addresses
  businessPartner VARCHAR        — → business_partners
  addressId VARCHAR
  cityName VARCHAR
  region VARCHAR
  country VARCHAR
  postalCode VARCHAR
  validityStartDate DATETIME

TABLE products
  product VARCHAR PK             — e.g. 'S8907367010814'
  productType VARCHAR
  productGroup VARCHAR
  division VARCHAR
  isMarkedForDeletion BOOLEAN

TABLE product_descriptions       — product names
  product VARCHAR                — → products
  language VARCHAR               — 'EN' for English
  productDescription VARCHAR

TABLE plants
  plant VARCHAR PK               — e.g. '1920' 'WB05'
  plantName VARCHAR
  salesOrganization VARCHAR
  valuationArea VARCHAR

TABLE product_plants             — product-plant assignments
  product VARCHAR
  plant VARCHAR
  mrpType VARCHAR
  profitCenter VARCHAR
  countryOfOrigin VARCHAR

TABLE product_storage_locations
  product VARCHAR
  plant VARCHAR
  storageLocation VARCHAR
  physicalInventoryBlockInd VARCHAR
  dateOfLastPostedCnt DATETIME

TABLE graph_edges                — precomputed relationships
  source_type VARCHAR            — 'sales_order','delivery','billing_document','customer','product'…
  source_id VARCHAR
  target_type VARCHAR
  target_id VARCHAR
  edge_type VARCHAR              — SOLD_TO, FULFILLED_BY, BILLED_AS, POSTS_TO, CLEARED_BY,
                                    CANCELLED_BY, CONTAINS_MATERIAL, SHIPS_FROM, STORED_AT, BILLED_TO

KEY JOIN PATHS:
  order → delivery:   outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
  order → billing:    billing_document_items.referenceSdDocument = sales_order_headers.salesOrder
  billing → journal:  journal_entry_items_ar.referenceDocument = billing_document_headers.billingDocument
  billing → paid?:    journal_entry_items_ar.clearingAccountingDocument IS NOT NULL
  product name:       JOIN product_descriptions pd ON pd.product=X AND pd.language='EN'
  customer name:      JOIN business_partners bp ON bp.businessPartner=X
"""


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRIAGE  — quick rule-based O2C domain check (no LLM needed)
# ─────────────────────────────────────────────────────────────────────────────

_OOS_PATTERNS = [
    r"capital\s+of\b", r"weather\s+(in|today|forecast)",
    r"write\s+a\s+(poem|story|essay|song|code for)",
    r"(recipe|ingredients)\s+(for|to)",
    r"stock\s+price\s+of\b",
    r"who\s+(won|is)\s+the\s+(president|prime|ceo\s+of\s+(?!sap))",
    r"translate\s+(this|to|from)",
    r"(explain|what\s+is)\s+quantum",
    r"(generate|create|draw)\s+an?\s+(image|picture|video)",
]

# Mutation verbs — always reject, never generate SQL for these
_MUTATION_PATTERNS = re.compile(
    r"\b(delete|drop|remove|truncate|update|modify|change|alter|create|insert|"
    r"add\s+new|cancel\s+all|clear\s+all|wipe|reset\s+the)\b",
    re.IGNORECASE
)

_O2C_SIGNALS = [
    "order", "delivery", "billing", "invoice", "payment", "customer",
    "product", "material", "shipment", "journal", "accounting", "plant",
    "sales", "flow", "trace", "billed", "shipped", "cleared", "partner",
    "dataset", "data", "summary", "highest", "lowest", "total", "count",
    "list", "show", "find", "get", "which", "how many", "average",
]

def is_out_of_scope(query: str) -> bool:
    t = query.lower()
    # Explicit general-knowledge patterns
    if any(re.search(p, t) for p in _OOS_PATTERNS):
        return True
    # Mutation verbs are always out of scope (read-only system)
    if _MUTATION_PATTERNS.search(t):
        return True
    # If no O2C signals AND no numbers (entity IDs), likely off-topic
    has_signal = any(s in t for s in _O2C_SIGNALS)
    has_number = bool(re.search(r"\d{4,}", t))
    return not (has_signal or has_number)


# ─────────────────────────────────────────────────────────────────────────────
# 4. PLAN PHASE  — LLM decides what SQL queries to run
# ─────────────────────────────────────────────────────────────────────────────

PLAN_SYSTEM = f"""You are a SQL planner for an SAP Order-to-Cash (O2C) database.

Given a user question and conversation history, decide what SQLite queries to run.

OUTPUT: Return a JSON object with this exact shape:
{{
  "queries": [
    {{"id": "q1", "purpose": "one line description", "sql": "SELECT ..."}},
    {{"id": "q2", "purpose": "one line description", "sql": "SELECT ..."}}
  ]
}}

RULES:
- Write 1–3 queries (use multiple only when genuinely needed)
- SELECT only — never INSERT/UPDATE/DELETE/DROP
- Always LIMIT 50 (or less for aggregations)
- All ID values are strings — use string comparison
- isCancelled is stored as 0/1
- For product names: JOIN product_descriptions pd ON pd.product=p.product AND pd.language='EN'
- For customer names: JOIN business_partners bp ON bp.businessPartner=soh.soldToParty
- Use table aliases
- If question is about the overall dataset/summary: write queries to count rows per key table
- Output ONLY the JSON object — no markdown, no explanation

{SCHEMA}
"""

def plan_queries(question: str, history: list[dict]) -> list[dict]:
    """
    Ask LLM to plan what SQL queries to run.
    Returns list of {id, purpose, sql} dicts.
    """
    # Build context from history
    ctx = ""
    if history:
        lines = [f"{t['role'].title()}: {t['content']}" for t in history[-4:]]
        ctx = "Conversation context:\n" + "\n".join(lines) + "\n\n"

    user_msg = f"{ctx}User question: {question}\n\nPlan the SQL queries:"

    try:
        raw = _call_llm(PLAN_SYSTEM, user_msg, temperature=0.0, max_tokens=800)
    except RateLimitError:
        raise RateLimitError("Rate limit reached — please wait a moment and try again")

    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    # Extract JSON
    try:
        parsed = json.loads(raw)
        queries = parsed.get("queries", [])
        if not queries and isinstance(parsed, list):
            queries = parsed
        return [q for q in queries if q.get("sql")]
    except Exception:
        # Try to find JSON substring
        m = re.search(r'\{.*"queries".*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0)).get("queries", [])
            except Exception:
                pass
        # Last resort: try to extract any SELECT statements
        selects = re.findall(r'SELECT\s+.+?(?=SELECT\s|\Z)', raw, re.DOTALL | re.IGNORECASE)
        return [{"id": f"q{i+1}", "purpose": "auto-extracted", "sql": s.strip()} for i, s in enumerate(selects[:3])]


# ─────────────────────────────────────────────────────────────────────────────
# 5. EXECUTE  — safe SQL runner
# ─────────────────────────────────────────────────────────────────────────────

_FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|ATTACH|DETACH)\b", re.IGNORECASE)

def run_query(db_session, sql: str) -> tuple[list[dict], str | None]:
    """Execute SQL safely. Returns (rows, error)."""
    from sqlalchemy import text

    if _FORBIDDEN.search(sql):
        return [], "Write operations are not permitted."
    try:
        result = db_session.execute(text(sql))
        cols = list(result.keys())
        rows = [dict(zip(cols, row)) for row in result.fetchmany(100)]
        return rows, None
    except Exception as e:
        return [], str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 6. ANSWER PHASE  — LLM writes grounded NL answer
# ─────────────────────────────────────────────────────────────────────────────

ANSWER_SYSTEM = """You are a helpful SAP Order-to-Cash analyst.
You are given a user question and the actual database results.

Write a clear, direct, data-backed answer (2-6 sentences).
- Mention specific IDs, names, amounts, counts from the data
- If results are empty, say clearly nothing was found and briefly suggest why
- Do NOT say "Based on the data" or "Sure" — answer directly
- Do NOT invent anything not in the results
- For large result sets, highlight the key findings and mention the total count
- Reference what the data shows, not what you assume
"""

def answer_from_results(question: str, query_results: list[dict], history: list[dict]) -> Iterator[str]:
    """
    Stream NL answer grounded in actual query results.
    query_results: list of {id, purpose, sql, rows, error}
    """
    # Build data summary for LLM
    data_parts = []
    total_rows = 0
    for qr in query_results:
        if qr.get("error"):
            data_parts.append(f"Query '{qr['purpose']}': ERROR — {qr['error']}")
            continue
        rows = qr.get("rows", [])
        total_rows += len(rows)
        if not rows:
            data_parts.append(f"Query '{qr['purpose']}': 0 rows returned")
        elif len(rows) <= 8:
            data_parts.append(f"Query '{qr['purpose']}' ({len(rows)} rows):\n{json.dumps(rows, default=str)}")
        else:
            data_parts.append(
                f"Query '{qr['purpose']}' ({len(rows)} rows, showing first 5):\n"
                f"{json.dumps(rows[:5], default=str)}"
                f"\n... and {len(rows)-5} more rows"
            )

    # History context
    ctx = ""
    if history:
        lines = [f"{t['role'].title()}: {t['content']}" for t in history[-3:]]
        ctx = "Recent conversation:\n" + "\n".join(lines) + "\n\n"

    user_msg = (
        f"{ctx}User question: {question}\n\n"
        f"Database results:\n" + "\n\n".join(data_parts) +
        "\n\nAnswer:"
    )

    try:
        answer = _call_llm(ANSWER_SYSTEM, user_msg, temperature=0.3, max_tokens=400)
        words = answer.split(" ")
        for i, w in enumerate(words):
            yield w + (" " if i < len(words) - 1 else "")
    except RateLimitError:
        # Rate limited on answer generation — use deterministic fallback
        yield from _fallback_answer(question, query_results)
    except Exception:
        yield from _fallback_answer(question, query_results)


def _fallback_answer(question: str, query_results: list[dict]) -> Iterator[str]:
    """No-LLM answer when rate-limited."""
    all_rows = []
    errors = []
    for qr in query_results:
        if qr.get("error"):
            errors.append(qr["error"])
        else:
            all_rows.extend(qr.get("rows", []))

    if errors and not all_rows:
        text = f"Query error: {errors[0]}"
    elif not all_rows:
        text = "No matching records found in the dataset for your query."
    else:
        n = len(all_rows)
        first = all_rows[0]
        sample = ", ".join(f"{k}: {v}" for k, v in list(first.items())[:4] if v is not None)
        text = f"Found {n} record{'s' if n!=1 else ''}. First: {sample}."
        if n > 1:
            text += f" {n} total results."

    for i, w in enumerate(text.split(" ")):
        yield w + (" " if i < len(text.split(" ")) - 1 else "")


# ─────────────────────────────────────────────────────────────────────────────
# 7. MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def process_query(db_session, question: str, history: list[dict]) -> dict:
    """
    Full pipeline. Returns:
    {
      "queries": [{id, purpose, sql, rows, row_count, error}],
      "total_rows": int,
    }
    """
    planned = plan_queries(question, history)

    results = []
    for q in planned:
        rows, error = run_query(db_session, q["sql"])
        results.append({
            "id": q.get("id", "q"),
            "purpose": q.get("purpose", ""),
            "sql": q["sql"],
            "rows": rows,
            "row_count": len(rows),
            "error": error,
        })

    return {
        "queries": results,
        "total_rows": sum(r["row_count"] for r in results),
    }
