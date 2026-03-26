"""
Query API — two-path architecture:

PATH A — Structured (fast, no SQL generation):
  Used for the 3 task-required query types detected by rule-based planner:
  trace_flow, top_products_by_billing, find_broken_flows
  → Pydantic-validated plan → dedicated SQL handler → NL answer

PATH B — Dynamic SQL (LLM generates SQL from schema context):
  Used for everything else — lookup_entity, free-form questions,
  follow-ups, product searches, customer analysis, etc.
  → LLM generates SQL → execute safely → LLM answers from rows

Both paths stream via SSE: plan → result → tokens → done
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.planner import generate_query_plan
from app.llm.sql_engine import (
    generate_sql,
    execute_safe_sql,
    generate_nl_answer,
    is_out_of_scope,
    _fallback_nl_answer,
)
from app.query.execute import execute_query_plan
from app.query.validation import validate_query_plan

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

router = APIRouter(tags=["query"])


# ─── Request / Response models ────────────────────────────────────────────────

class HistoryTurn(BaseModel):
    role: str
    content: str
    model_config = ConfigDict(extra="forbid")


class QueryRequest(BaseModel):
    query: str
    history: list[HistoryTurn] = []
    model_config = ConfigDict(extra="forbid")


class QueryResponse(BaseModel):
    plan: dict[str, Any]
    result: Any
    model_config = ConfigDict(extra="forbid")


# ─── Synchronous endpoint ────────────────────────────────────────────────────

@router.post("", response_model=QueryResponse)
def query_endpoint(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    raw_plan = generate_query_plan(payload.query, history=history)
    validated_plan = validate_query_plan(raw_plan)
    result = execute_query_plan(db, validated_plan)
    return QueryResponse(plan=validated_plan, result=result)


# ─── SSE helpers ─────────────────────────────────────────────────────────────

def _sse(event_type: str, payload: Any) -> str:
    return f"data: {json.dumps({'type': event_type, 'payload': payload})}\n\n"


def _stream_words(text: str) -> Iterator[str]:
    words = text.split(" ")
    for i, w in enumerate(words):
        yield w + (" " if i < len(words) - 1 else "")


# ─── Streaming endpoint ───────────────────────────────────────────────────────

@router.post("/stream")
def query_stream_endpoint(payload: QueryRequest, db: Session = Depends(get_db)):
    """
    SSE streaming endpoint. Emits:
      {type: "plan",   payload: {intent, ...}}
      {type: "result", payload: {rows/path/...}}
      {type: "token",  payload: "word "}   (repeated)
      {type: "done"}
    """
    history = [{"role": t.role, "content": t.content} for t in payload.history]

    def generate():
        query = payload.query.strip()

        # ── Guardrail ─────────────────────────────────────────────────────────
        if is_out_of_scope(query):
            plan = {"intent": "reject", "reason": "out_of_scope",
                    "clarification_needed": "This system only answers questions about the SAP Order-to-Cash dataset."}
            yield _sse("plan", plan)
            yield _sse("result", {})
            yield _sse("token", "This system is designed to answer questions about the SAP Order-to-Cash dataset only. Please ask about orders, deliveries, billing, payments, customers, or products.")
            yield _sse("done", None)
            return

        # ── Path A: Rule-based structured query ───────────────────────────────
        # Only for the 3 deterministic task examples where we have reliable handlers
        raw_plan = generate_query_plan(query, history=history)
        intent = raw_plan.get("intent", "")

        if intent in ("trace_flow", "top_products_by_billing", "find_broken_flows"):
            validated_plan = validate_query_plan(raw_plan)
            yield _sse("plan", validated_plan)

            result = execute_query_plan(db, validated_plan)
            yield _sse("result", result)

            # NL answer
            for token in _stream_nl_from_structured(query, validated_plan, result, history):
                yield _sse("token", token)

            yield _sse("done", None)
            return

        # ── Path B: Dynamic SQL generation ────────────────────────────────────
        # For everything else: lookups, free-form, product searches, follow-ups
        plan_meta = {"intent": "sql_query", "query": query}
        yield _sse("plan", plan_meta)

        # Check if LLM is available
        has_llm = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY"))
        if not has_llm:
            yield _sse("result", {"rows": [], "sql": None})
            yield _sse("token", "No LLM configured. Add GEMINI_API_KEY or GROQ_API_KEY to backend/.env to enable dynamic queries.")
            yield _sse("done", None)
            return

        # Generate SQL
        try:
            sql = generate_sql(query, history=history)
        except Exception as e:
            yield _sse("result", {"rows": [], "sql": None, "error": str(e)})
            # Fallback answer
            for token in _stream_words(f"Could not generate SQL: {str(e)[:100]}"):
                yield _sse("token", token)
            yield _sse("done", None)
            return

        if sql is None:
            yield _sse("result", {"rows": [], "sql": None})
            yield _sse("token", "This question appears to be outside the scope of the O2C dataset. Please ask about orders, deliveries, invoices, payments, customers, or products.")
            yield _sse("done", None)
            return

        # Execute SQL
        rows, error = execute_safe_sql(db, sql)

        result_payload = {
            "intent": "sql_query",
            "sql": sql,
            "rows": rows,
            "row_count": len(rows),
            "error": error,
        }
        yield _sse("result", result_payload)

        if error:
            for token in _stream_words(f"The query encountered an error: {error}. Please rephrase your question."):
                yield _sse("token", token)
            yield _sse("done", None)
            return

        # Generate NL answer from actual rows
        try:
            for token in generate_nl_answer(query, sql, rows, history=history):
                yield _sse("token", token)
        except Exception:
            # Fallback no-LLM answer
            for token in _fallback_nl_answer(query, rows):
                yield _sse("token", token)

        yield _sse("done", None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── NL answer for structured queries ────────────────────────────────────────

def _stream_nl_from_structured(
    user_query: str, plan: dict, result: dict, history: list
) -> Iterator[str]:
    """
    Generate NL answer for the 3 structured query types.
    Uses LLM if available, deterministic fallback otherwise.
    """
    intent = plan.get("intent", "")
    has_llm = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY"))

    if has_llm:
        try:
            from app.llm.sql_engine import _llm_call, NL_ANSWER_SYSTEM_PROMPT
            # Build a concise summary of the structured result
            summary = _summarise_structured_result(intent, plan, result)
            user_msg = f"User question: {user_query}\n\nData retrieved:\n{summary}\n\nAnswer:"

            # Build conversation context
            history_str = ""
            if history:
                lines = [f"{t['role'].title()}: {t['content']}" for t in history[-4:]]
                history_str = "\n".join(lines) + "\n\n"

            answer = _llm_call(NL_ANSWER_SYSTEM_PROMPT, history_str + user_msg, max_tokens=300, temperature=0.3)
            yield from _stream_words(answer)
            return
        except Exception:
            pass  # fall through to deterministic

    # Deterministic fallback
    yield from _deterministic_nl(intent, plan, result)


def _summarise_structured_result(intent: str, plan: dict, result: dict) -> str:
    """Compact text summary of structured query result for LLM context."""
    if intent == "trace_flow":
        nodes = result.get("path", {}).get("nodes", [])
        edges = result.get("path", {}).get("edges", [])
        node_types: dict[str, list] = {}
        for n in nodes:
            node_types.setdefault(n["type"], []).append(n["id"])
        lines = [f"Traced {plan.get('entity_type')} {plan.get('entity_id')}:"]
        for t, ids in node_types.items():
            lines.append(f"  {t}: {', '.join(ids[:5])}")
        lines.append(f"Total: {len(nodes)} nodes, {len(edges)} edges")
        return "\n".join(lines)

    if intent == "top_products_by_billing":
        results = result.get("results", [])
        lines = [f"Top {len(results)} products by {plan.get('sort_by')}:"]
        for r in results[:10]:
            lines.append(f"  {r['product_id']}: net_amount={r['total_net_amount']:.2f}, invoices={r['invoice_count']}")
        return "\n".join(lines)

    if intent == "find_broken_flows":
        issues = result.get("issues", [])
        by_type: dict[str, int] = {}
        for i in issues:
            by_type[i.get("break_type", "?")] = by_type.get(i.get("break_type", "?"), 0) + 1
        lines = [f"Found {len(issues)} total flow issues:"]
        for t, c in by_type.items():
            lines.append(f"  {t}: {c}")
        return "\n".join(lines)

    return json.dumps(result, default=str)[:500]


def _deterministic_nl(intent: str, plan: dict, result: dict) -> Iterator[str]:
    """No-LLM fallback for structured results."""
    if intent == "trace_flow":
        nodes = result.get("path", {}).get("nodes", [])
        edges = result.get("path", {}).get("edges", [])
        if not nodes:
            yield from _stream_words(f"No flow data found for {plan.get('entity_type')} {plan.get('entity_id')}.")
            return
        node_types: dict[str, int] = {}
        for n in nodes:
            node_types[n["type"]] = node_types.get(n["type"], 0) + 1
        parts = [f"{v} {k.replace('_',' ')}" for k, v in node_types.items()]
        yield from _stream_words(f"Traced {plan.get('entity_type','').replace('_',' ')} {plan.get('entity_id')}: found {', '.join(parts)} connected by {len(edges)} edge(s).")
        return

    if intent == "top_products_by_billing":
        results = result.get("results", [])
        if not results:
            yield from _stream_words("No products found.")
            return
        top = results[0]
        yield from _stream_words(
            f"Top product: {top['product_id']} with {top.get('invoice_count',0)} invoice(s) and net amount {top.get('total_net_amount',0):.2f}. "
            f"Retrieved {len(results)} products total."
        )
        return

    if intent == "find_broken_flows":
        issues = result.get("issues", [])
        if not issues:
            yield from _stream_words("No broken flows detected in the dataset.")
            return
        by_type: dict[str, int] = {}
        for i in issues:
            by_type[i.get("break_type","?")] = by_type.get(i.get("break_type","?"),0)+1
        summary = "; ".join(f"{c} {t.replace('_',' ')}" for t,c in list(by_type.items())[:3])
        yield from _stream_words(f"Found {len(issues)} total flow issues: {summary}.")
