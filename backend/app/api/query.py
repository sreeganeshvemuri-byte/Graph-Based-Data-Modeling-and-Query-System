"""
Query API — two-path streaming

PATH A: Structural queries detected by rule-based patterns
  → trace_flow / top_products / find_broken_flows
  → dedicated handlers (fast, no SQL gen needed)

PATH B: Everything else
  → LLM plans SQL queries using full schema context
  → Execute safely
  → LLM answers from real rows

Both paths: SSE stream  plan → result → tokens → done
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
from app.llm.engine import process_query, answer_from_results, is_out_of_scope, _fallback_answer
from app.llm.rule_planner import rule_based_plan
from app.query.execute import execute_query_plan
from app.query.validation import validate_query_plan

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

router = APIRouter(tags=["query"])


# ── Models ─────────────────────────────────────────────────────────────────

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


# ── Sync endpoint (kept for testing) ───────────────────────────────────────

@router.post("", response_model=QueryResponse)
def query_endpoint(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    plan = rule_based_plan(payload.query, history)
    if plan and plan.get("intent") in ("trace_flow", "top_products_by_billing", "find_broken_flows"):
        validated = validate_query_plan(plan)
        result = execute_query_plan(db, validated)
        return QueryResponse(plan=validated, result=result)
    # Dynamic path
    result = process_query(db, payload.query, history)
    return QueryResponse(plan={"intent": "sql_query"}, result=result)


# ── SSE helper ─────────────────────────────────────────────────────────────

def sse(event_type: str, payload: Any) -> str:
    return f"data: {json.dumps({'type': event_type, 'payload': payload})}\n\n"

def stream_words(text: str) -> Iterator[str]:
    words = text.split(" ")
    for i, w in enumerate(words):
        yield w + (" " if i < len(words) - 1 else "")


# ── Streaming endpoint ─────────────────────────────────────────────────────

@router.post("/stream")
def query_stream(payload: QueryRequest, db: Session = Depends(get_db)):
    """
    SSE events:
      {type: "plan",   payload: {intent|sql, ...}}
      {type: "result", payload: {...}}
      {type: "token",  payload: "word "}
      {type: "done"}
    """
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    query = payload.query.strip()

    def generate():

        # ── Guardrail ────────────────────────────────────────────────────────
        if is_out_of_scope(query):
            yield sse("plan", {"intent": "reject"})
            yield sse("result", {})
            yield sse("token", "This system only answers questions about the SAP Order-to-Cash dataset — orders, deliveries, billing, payments, customers, and products.")
            yield sse("done", None)
            return

        has_llm = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY"))

        # ── Path A: Rule-based structural queries ────────────────────────────
        plan = rule_based_plan(query, history)
        intent = plan.get("intent") if plan else None

        if intent in ("trace_flow", "top_products_by_billing", "find_broken_flows"):
            validated = validate_query_plan(plan)
            yield sse("plan", validated)
            result = execute_query_plan(db, validated)
            yield sse("result", result)
            # NL answer
            if has_llm:
                try:
                    summary = _structured_summary(intent, validated, result)
                    from app.llm.engine import _call_llm, ANSWER_SYSTEM
                    ctx = "\n".join(f"{t['role'].title()}: {t['content']}" for t in history[-3:])
                    prompt = f"{ctx}\n\nUser: {query}\n\nData:\n{summary}\n\nAnswer:"
                    answer = _call_llm(ANSWER_SYSTEM, prompt, temperature=0.3, max_tokens=350)
                    for tok in stream_words(answer):
                        yield sse("token", tok)
                except Exception:
                    for tok in _structured_fallback(intent, validated, result):
                        yield sse("token", tok)
            else:
                for tok in _structured_fallback(intent, validated, result):
                    yield sse("token", tok)
            yield sse("done", None)
            return

        # ── Path B: Dynamic SQL ───────────────────────────────────────────────
        yield sse("plan", {"intent": "sql_query", "query": query})

        if not has_llm:
            yield sse("result", {"queries": [], "total_rows": 0})
            yield sse("token", "No LLM provider configured. Add GEMINI_API_KEY or GROQ_API_KEY to backend/.env.")
            yield sse("done", None)
            return

        try:
            result = process_query(db, query, history)
        except Exception as e:
            yield sse("result", {"queries": [], "total_rows": 0, "error": str(e)})
            for tok in stream_words(f"Query planning failed: {str(e)[:150]}"):
                yield sse("token", tok)
            yield sse("done", None)
            return

        yield sse("result", result)

        # NL answer from actual rows
        try:
            for tok in answer_from_results(query, result["queries"], history):
                yield sse("token", tok)
        except Exception:
            for tok in _fallback_answer(query, result["queries"]):
                yield sse("token", tok)

        yield sse("done", None)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Structured result helpers ───────────────────────────────────────────────

def _structured_summary(intent: str, plan: dict, result: dict) -> str:
    if intent == "trace_flow":
        nodes = result.get("path", {}).get("nodes", [])
        edges = result.get("path", {}).get("edges", [])
        by_type: dict[str, list] = {}
        for n in nodes:
            by_type.setdefault(n["type"], []).append(n["id"])
        lines = [f"Traced {plan.get('entity_type')} {plan.get('entity_id')} — {len(nodes)} nodes, {len(edges)} edges:"]
        for t, ids in by_type.items():
            meta_strs = []
            for n in nodes:
                if n["type"] == t:
                    m = n.get("metadata", {})
                    if m:
                        meta_strs.append(f"{n['id']}: {json.dumps(m, default=str)}")
            lines.append(f"  {t}: {', '.join(meta_strs[:3] or ids[:3])}")
        return "\n".join(lines)

    if intent == "top_products_by_billing":
        rows = result.get("results", [])
        lines = [f"Top {len(rows)} products by {plan.get('sort_by')}:"]
        for r in rows[:10]:
            lines.append(f"  {r['product_id']}: net={r['total_net_amount']:.2f} invoices={r['invoice_count']} qty={r['quantity']}")
        return "\n".join(lines)

    if intent == "find_broken_flows":
        issues = result.get("issues", [])
        counts: dict[str, int] = {}
        for i in issues:
            counts[i["break_type"]] = counts.get(i["break_type"], 0) + 1
        lines = [f"Found {len(issues)} total issues:"]
        for t, c in counts.items():
            lines.append(f"  {t}: {c}")
        return "\n".join(lines)

    return json.dumps(result, default=str)[:600]


def _structured_fallback(intent: str, plan: dict, result: dict) -> Iterator[str]:
    if intent == "trace_flow":
        nodes = result.get("path", {}).get("nodes", [])
        edges = result.get("path", {}).get("edges", [])
        if not nodes:
            text = f"No flow data found for {plan.get('entity_type')} {plan.get('entity_id')}."
        else:
            counts: dict[str, int] = {}
            for n in nodes: counts[n["type"]] = counts.get(n["type"], 0) + 1
            parts = [f"{v} {k.replace('_',' ')}" for k, v in counts.items()]
            text = f"Traced {plan.get('entity_type','').replace('_',' ')} {plan.get('entity_id')}: found {', '.join(parts)} connected by {len(edges)} edge(s) across the O2C pipeline."
        return stream_words(text)

    if intent == "top_products_by_billing":
        rows = result.get("results", [])
        if not rows:
            return stream_words("No product billing data found.")
        top = rows[0]
        text = (f"Top product: {top['product_id']} with {top['invoice_count']} invoice(s) "
                f"and net amount {top['total_net_amount']:.2f}. {len(rows)} products retrieved.")
        return stream_words(text)

    if intent == "find_broken_flows":
        issues = result.get("issues", [])
        if not issues:
            return stream_words("No broken flows detected in the dataset.")
        counts: dict[str, int] = {}
        for i in issues: counts[i["break_type"]] = counts.get(i["break_type"], 0) + 1
        summary = "; ".join(f"{c} {t.replace('_',' ')}" for t, c in list(counts.items())[:3])
        return stream_words(f"Found {len(issues)} flow issues: {summary}.")

    return stream_words("Query executed.")
