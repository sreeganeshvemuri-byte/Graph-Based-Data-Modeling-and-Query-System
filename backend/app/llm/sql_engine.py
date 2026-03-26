"""
Dynamic SQL Query Engine
========================
LLM generates SQL from natural language, we execute it safely,
LLM then answers in natural language grounded in the actual rows.

This replaces the intent-locked system for free-form queries.
The 3 task-required structured queries (trace_flow, top_products, broken_flows)
are still handled by the dedicated handlers for reliability.
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

# ─── Schema Context (RAG) ─────────────────────────────────────────────────────
# Complete schema injected into every SQL generation prompt.
# This is the "RAG" — the model knows exactly what columns exist.

SCHEMA_CONTEXT = """
DATABASE SCHEMA — SAP Order-to-Cash (O2C) System
All IDs are VARCHAR (stored as strings, sometimes zero-padded).

TABLE: sales_order_headers
  salesOrder       VARCHAR PK  — sales order number (e.g. '740506')
  soldToParty      VARCHAR     — customer/business partner ID (FK → business_partners)
  totalNetAmount   FLOAT       — total order value
  status           VARCHAR     — 'C' = completed, 'A' = open
  creationDate     DATETIME

TABLE: sales_order_items
  salesOrder       VARCHAR     — FK → sales_order_headers
  item             VARCHAR     — line item number ('10', '20', ...)
  material         VARCHAR     — product ID (FK → products)
  netAmount        FLOAT
  quantity         FLOAT
  productionPlant  VARCHAR     — FK → plants

TABLE: sales_order_schedule_lines
  salesOrder       VARCHAR     — FK → sales_order_headers
  item             VARCHAR
  scheduleLine     VARCHAR
  confirmedDeliveryDate DATETIME
  confdOrderQty    FLOAT

TABLE: outbound_delivery_headers
  deliveryDocument VARCHAR PK  — delivery document number (e.g. '80738040')
  pickingStatus    VARCHAR     — 'C' = completed
  goodsMovementStatus VARCHAR  — 'A' = pending, 'C' = completed
  shippingPoint    VARCHAR

TABLE: outbound_delivery_items
  deliveryDocument VARCHAR     — FK → outbound_delivery_headers
  item             VARCHAR
  referenceSdDocument VARCHAR  — links back to salesOrder
  referenceSdDocumentItem VARCHAR
  plant            VARCHAR     — FK → plants
  batch            VARCHAR

TABLE: billing_document_headers
  billingDocument  VARCHAR PK  — billing/invoice number (e.g. '90504274')
  soldToParty      VARCHAR     — FK → business_partners
  companyCode      VARCHAR
  billingDocumentDate DATETIME
  accountingDocument VARCHAR   — FK → journal_entry_items_ar
  fiscalYear       VARCHAR
  totalNetAmount   FLOAT
  isCancelled      BOOLEAN

TABLE: billing_document_items
  billingDocument  VARCHAR     — FK → billing_document_headers
  item             VARCHAR
  referenceSdDocument VARCHAR  — links back to salesOrder
  referenceSdDocumentItem VARCHAR
  material         VARCHAR     — FK → products
  netAmount        FLOAT

TABLE: billing_document_cancellations
  billingDocument  VARCHAR PK  — cancelled billing document number

TABLE: journal_entry_items_ar
  accountingDocument VARCHAR   — accounting doc number
  item             VARCHAR
  customer         VARCHAR     — FK → business_partners
  referenceDocument VARCHAR    — FK → billing_document_headers.billingDocument
  companyCode      VARCHAR
  fiscalYear       VARCHAR
  postingDate      DATETIME
  amountInCompanyCodeCurrency FLOAT
  glAccount        VARCHAR
  clearingAccountingDocument VARCHAR  — if set, this entry is cleared (paid)

TABLE: payments_accounts_receivable
  accountingDocument VARCHAR   — FK → journal_entry_items_ar
  item             VARCHAR
  customer         VARCHAR     — FK → business_partners
  clearingAccountingDocument VARCHAR
  postingDate      DATETIME

TABLE: business_partners
  businessPartner  VARCHAR PK  — customer/partner ID (e.g. '310000108')
  fullName         VARCHAR     — customer name
  category         VARCHAR
  isBlocked        BOOLEAN
  isMarkedForArchiving BOOLEAN
  region           VARCHAR
  grouping         VARCHAR

TABLE: business_partner_addresses
  businessPartner  VARCHAR     — FK → business_partners
  addressId        VARCHAR
  cityName         VARCHAR
  region           VARCHAR
  country          VARCHAR
  postalCode       VARCHAR
  validityStartDate DATETIME

TABLE: products
  product          VARCHAR PK  — product/material code (e.g. 'S8907367010814')
  productType      VARCHAR
  productGroup     VARCHAR
  division         VARCHAR
  isMarkedForDeletion BOOLEAN

TABLE: product_descriptions
  product          VARCHAR     — FK → products
  language         VARCHAR
  productDescription VARCHAR   — human-readable product name

TABLE: product_plants
  product          VARCHAR     — FK → products
  plant            VARCHAR     — FK → plants
  mrpType          VARCHAR
  profitCenter     VARCHAR
  countryOfOrigin  VARCHAR

TABLE: plants
  plant            VARCHAR PK  — plant code (e.g. '1920', 'WB05')
  plantName        VARCHAR
  salesOrganization VARCHAR
  valuationArea    VARCHAR

TABLE: graph_edges
  source_type      VARCHAR     — node type (sales_order, delivery, billing_document, etc.)
  source_id        VARCHAR     — entity ID
  target_type      VARCHAR     — node type
  target_id        VARCHAR     — entity ID
  edge_type        VARCHAR     — SOLD_TO, FULFILLED_BY, BILLED_AS, POSTS_TO, CLEARED_BY,
                                  CANCELLED_BY, CONTAINS_MATERIAL, SHIPS_FROM, STORED_AT, BILLED_TO

KEY RELATIONSHIPS (for JOINs):
- Sales order → items:       sales_order_headers.salesOrder = sales_order_items.salesOrder
- Sales order → delivery:    outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
- Sales order → billing:     billing_document_items.referenceSdDocument = sales_order_headers.salesOrder
- Billing → journal:         journal_entry_items_ar.referenceDocument = billing_document_headers.billingDocument
- Billing → accounting:      billing_document_headers.accountingDocument = journal_entry_items_ar.accountingDocument
- Journal → payment cleared: journal_entry_items_ar.clearingAccountingDocument IS NOT NULL
- Product in order:          sales_order_items.material = products.product
- Product in billing:        billing_document_items.material = products.product
- Customer name:             sales_order_headers.soldToParty = business_partners.businessPartner
"""

# ─── SQL Generation Prompt ───────────────────────────────────────────────────

SQL_SYSTEM_PROMPT = """You are a SQL expert for an SAP Order-to-Cash database.
Your job: convert a natural language question into a single valid SQLite SELECT query.

RULES:
1. Output ONLY the SQL query — no markdown, no explanation, no ```sql fences.
2. Always use LIMIT 50 unless user asks for more or the query is an aggregation.
3. Use table aliases for readability.
4. Never use UPDATE, DELETE, INSERT, DROP, CREATE, ALTER.
5. All IDs are strings — use string comparison, not integer.
6. For product names: JOIN product_descriptions pd ON pd.product = products.product AND pd.language = 'EN'
7. For customer names: JOIN business_partners bp ON bp.businessPartner = sales_order_headers.soldToParty
8. isCancelled is stored as 0/1 in SQLite (0=false, 1=true).
9. If the question is completely out of scope (not about O2C data), output exactly: OUT_OF_SCOPE
10. If you cannot write a valid SQL for the question, output exactly: CANNOT_GENERATE

The database schema is provided in the context.
"""

# ─── NL Answer Prompt ────────────────────────────────────────────────────────

NL_ANSWER_SYSTEM_PROMPT = """You are a helpful SAP Order-to-Cash analyst.
You are given:
1. A user question
2. The SQL query that was executed  
3. The actual results (rows) from the database

Your job: Write a clear, concise, data-backed answer in 2-5 sentences.
- Reference specific IDs, counts, amounts, names from the data
- If the result is empty, say clearly that nothing was found and suggest why
- Do NOT say "Based on the data" or "Sure" — get straight to the answer
- Do NOT invent information not in the results
- If there are many rows, summarise the key findings
"""


def _call_gemini(system_prompt: str, user_message: str, history: list | None = None, max_tokens: int = 512, temperature: float = 0.0) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("No GEMINI_API_KEY")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    contents: list[dict] = []
    for turn in (history or [])[-6:]:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": turn["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = {
        "systemInstruction": {"role": "system", "parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_groq(system_prompt: str, user_message: str, history: list | None = None, max_tokens: int = 512) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("No GROQ_API_KEY")

    model = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
    url = "https://api.groq.com/openai/v1/chat/completions"

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for turn in (history or [])[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    payload = {"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": messages}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def _llm_call(system_prompt: str, user_message: str, history: list | None = None, max_tokens: int = 512) -> str:
    """Single LLM call — tries Gemini first, falls back to Groq."""
    if os.environ.get("GEMINI_API_KEY"):
        return _call_gemini(system_prompt, user_message, history=history, max_tokens=max_tokens)
    elif os.environ.get("GROQ_API_KEY"):
        return _call_groq(system_prompt, user_message, history=history, max_tokens=max_tokens)
    else:
        raise RuntimeError("No LLM provider configured")


def generate_sql(user_query: str, history: list | None = None) -> str | None:
    """
    Use LLM to generate a SQL query for the user's question.
    Returns the SQL string, None if out-of-scope, or raises on error.
    """
    # Build the user message: schema + question
    user_message = f"{SCHEMA_CONTEXT}\n\nUser question: {user_query}"

    # Add history context for follow-up questions
    if history:
        recent = history[-4:]
        history_str = "\n".join(f"{t['role'].title()}: {t['content']}" for t in recent)
        user_message = f"Conversation so far:\n{history_str}\n\n{SCHEMA_CONTEXT}\n\nCurrent question: {user_query}"

    raw = _llm_call(SQL_SYSTEM_PROMPT, user_message, max_tokens=600)

    # Strip any accidental markdown
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    if raw.upper().startswith("OUT_OF_SCOPE") or raw.upper().startswith("CANNOT_GENERATE"):
        return None

    return raw


def execute_safe_sql(db_session, sql: str) -> tuple[list[dict], str | None]:
    """
    Execute a SQL query safely (read-only enforced).
    Returns (rows_as_dicts, error_message_or_None).
    """
    from sqlalchemy import text

    # Hard block on write operations
    sql_upper = sql.upper().strip()
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "REPLACE"]
    for word in forbidden:
        if re.search(rf"\b{word}\b", sql_upper):
            return [], f"Write operation '{word}' is not allowed."

    try:
        result = db_session.execute(text(sql))
        columns = list(result.keys())
        rows = []
        for row in result.fetchmany(100):  # cap at 100 rows
            rows.append(dict(zip(columns, row)))
        return rows, None
    except Exception as e:
        return [], str(e)


def generate_nl_answer(user_query: str, sql: str, rows: list[dict], history: list | None = None) -> Iterator[str]:
    """
    Generate a natural language answer grounded in the actual SQL results.
    Yields word-by-word for streaming.
    """
    # Build compact result representation
    if not rows:
        result_str = "The query returned 0 rows (no matching data found)."
    elif len(rows) <= 10:
        result_str = json.dumps(rows, default=str, indent=2)
    else:
        # Summarise: first 5 rows + count
        result_str = f"Total rows: {len(rows)}\nFirst 5 rows:\n{json.dumps(rows[:5], default=str, indent=2)}"

    user_message = (
        f"User question: {user_query}\n\n"
        f"SQL executed:\n{sql}\n\n"
        f"Database results:\n{result_str}\n\n"
        f"Write a clear, data-backed answer:"
    )

    try:
        answer = _llm_call(NL_ANSWER_SYSTEM_PROMPT, user_message, history=history, max_tokens=400, temperature=0.3)
        words = answer.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
    except Exception as e:
        # Fallback: generate answer from rows directly without LLM
        yield from _fallback_nl_answer(user_query, rows)


def _fallback_nl_answer(user_query: str, rows: list[dict]) -> Iterator[str]:
    """No-LLM answer when rate limited."""
    if not rows:
        answer = "No matching records were found in the dataset for your query."
    else:
        count = len(rows)
        # Pick the most useful fields from first row to mention
        first = rows[0]
        fields = [f"{k}: {v}" for k, v in list(first.items())[:4] if v is not None]
        fields_str = ", ".join(fields)
        answer = f"Found {count} result(s). First record — {fields_str}."
        if count > 1:
            answer += f" {count} total records returned."

    words = answer.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")


def is_out_of_scope(user_query: str) -> bool:
    """
    Quick rule-based check before hitting the LLM.
    Returns True if clearly out of scope.
    """
    text = user_query.strip().lower()
    oos_patterns = [
        r"capital of", r"what is the weather", r"write a (?:poem|story|essay|song)",
        r"tell me a joke", r"recipe for", r"translate this", r"explain quantum",
        r"who (?:is|was) (?:the )?(?:president|prime minister|ceo of (?!sap))",
        r"what (?:is|are) (?:the )?(?:latest|current|today'?s?) (?:news|weather|stocks?)",
        r"play (?:a song|music)",
        r"(?:generate|create|write|draw|make) (?:an? )?(?:image|picture|video|audio)",
    ]
    return any(re.search(p, text) for p in oos_patterns)
