from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.planner import generate_query_plan
from app.query.execute import execute_query_plan
from app.query.validation import validate_query_plan
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    query: str

    model_config = ConfigDict(extra="forbid")


class QueryResponse(BaseModel):
    plan: dict[str, Any]
    result: Any

    model_config = ConfigDict(extra="forbid")


@router.post("", response_model=QueryResponse)
def query_endpoint(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    raw_plan = generate_query_plan(payload.query)
    validated_plan = validate_query_plan(raw_plan)
    result = execute_query_plan(db, validated_plan)
    return QueryResponse(plan=validated_plan, result=result)


# ─────────────────────────────────────────────
# Streaming endpoint: POST /api/query/stream
# Sends Server-Sent Events (SSE):
#   data: {"type":"plan",  "payload": {...}}
#   data: {"type":"result","payload": {...}}
#   data: {"type":"token", "payload": "word "}   ← streamed NL answer tokens
#   data: {"type":"done"}
# ─────────────────────────────────────────────

_NL_SYSTEM_PROMPT = (
    "You are a helpful analyst for an SAP Order-to-Cash (O2C) system. "
    "Given a user query and the structured result data, write a concise natural language answer "
    "(2–5 sentences). Be data-specific: mention IDs, counts, amounts, statuses. "
    "Do NOT invent data. If the result is empty, say so clearly. "
    "Do NOT start with 'Based on the data' or 'Sure'. Get straight to the answer."
)


def _build_nl_prompt(user_query: str, plan: dict, result: dict) -> str:
    # Summarize result concisely so we don't blow the context window
    intent = plan.get("intent", "")

    if intent == "reject":
        return f"Query: {user_query}\nSystem response: {plan.get('clarification_needed', '')}\nWrite one sentence explaining this to the user."

    if intent == "trace_flow":
        nodes = result.get("path", {}).get("nodes", [])
        edges = result.get("path", {}).get("edges", [])
        node_types = {}
        for n in nodes:
            node_types[n["type"]] = node_types.get(n["type"], 0) + 1
        summary = f"Found {len(nodes)} nodes ({node_types}) and {len(edges)} edges tracing {plan.get('entity_type')} {plan.get('entity_id')}."
        return f"User query: {user_query}\nResult summary: {summary}\nAnswer:"

    if intent == "top_products_by_billing":
        top3 = result.get("results", [])[:3]
        return (
            f"User query: {user_query}\n"
            f"Top products (first 3 of {len(result.get('results',[]))}): {json.dumps(top3)}\n"
            f"Sort by: {plan.get('sort_by')}\nAnswer:"
        )

    if intent == "find_broken_flows":
        issues = result.get("issues", [])
        by_type: dict[str, int] = {}
        for i in issues:
            bt = i.get("break_type", "unknown")
            by_type[bt] = by_type.get(bt, 0) + 1
        return (
            f"User query: {user_query}\n"
            f"Found {len(issues)} total issues: {by_type}\n"
            f"Answer:"
        )

    if intent == "lookup_entity":
        entity = result.get("entity", {})
        related_keys = list(result.get("related", {}).keys())
        return (
            f"User query: {user_query}\n"
            f"Entity type: {plan.get('entity_type')} | ID: {plan.get('entity_id')}\n"
            f"Entity data: {json.dumps(entity)}\n"
            f"Related: {related_keys}\n"
            f"Answer:"
        )

    return f"User query: {user_query}\nResult: {json.dumps(result)[:500]}\nAnswer:"


def _gemini_stream(prompt: str) -> Iterator[str]:
    """Stream tokens from Gemini generateContent (non-streaming REST, chunk the response)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return  # caller falls back

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "systemInstruction": {"role": "system", "parts": [{"text": _NL_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        # Simulate streaming by yielding word-by-word
        words = text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
    except Exception:
        return  # caller falls back


def _groq_stream(prompt: str):
    """Stream tokens from Groq streaming API."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        yield "No GROQ key."
        return

    model = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.3,
        "max_tokens": 300,
        "stream": True,
        "messages": [
            {"role": "system", "content": _NL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    token = chunk["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                except Exception:
                    pass
    except Exception as e:
        yield f"(stream error: {e})"


# Need Iterator import
from typing import Iterator


def _stream_nl_answer(user_query: str, plan: dict, result: dict):
    prompt = _build_nl_prompt(user_query, plan, result)
    provider = "groq" if os.environ.get("GROQ_API_KEY") else "gemini" if os.environ.get("GEMINI_API_KEY") else None

    tokens_yielded = 0
    if provider == "groq":
        for token in _groq_stream(prompt):
            tokens_yielded += 1
            yield token
    elif provider == "gemini":
        for token in _gemini_stream(prompt):
            tokens_yielded += 1
            yield token

    # If LLM yielded nothing (rate limit / error), use rule-based fallback
    if tokens_yielded == 0:
        yield from _fallback_nl(plan, result)


def _fallback_nl(plan: dict, result: dict):
    """Rule-based NL answer when no LLM is available."""
    intent = plan.get("intent", "")
    if intent == "reject":
        yield plan.get("clarification_needed", "This query is out of scope.")
        return
    if intent == "trace_flow":
        nodes = result.get("path", {}).get("nodes", [])
        edges = result.get("path", {}).get("edges", [])
        if not nodes:
            yield f"No flow data found for {plan.get('entity_type')} {plan.get('entity_id')}."
            return
        node_types: dict[str, int] = {}
        for n in nodes:
            node_types[n["type"]] = node_types.get(n["type"], 0) + 1
        parts = [f"{v} {k.replace('_', ' ')}(s)" for k, v in node_types.items()]
        yield f"Traced {plan.get('entity_type', '').replace('_',' ')} {plan.get('entity_id')}: found {', '.join(parts)} connected by {len(edges)} edge(s) across the O2C pipeline."
        return
    if intent == "top_products_by_billing":
        results = result.get("results", [])
        if not results:
            yield "No products found matching your criteria."
            return
        top = results[0]
        yield (
            f"Top product is {top['product_id']} with "
            f"{top.get('invoice_count', 0)} invoice(s) and "
            f"total net amount of {top.get('total_net_amount', 0):.2f}. "
            f"Retrieved {len(results)} products total."
        )
        return
    if intent == "find_broken_flows":
        issues = result.get("issues", [])
        by_type: dict[str, int] = {}
        for i in issues:
            bt = i.get("break_type", "unknown")
            by_type[bt] = by_type.get(bt, 0) + 1
        if not issues:
            yield "No broken flows detected in the dataset."
            return
        summary = "; ".join(f"{v} {k.replace('_',' ')}" for k, v in list(by_type.items())[:3])
        yield f"Found {len(issues)} total flow issues: {summary}."
        return
    if intent == "lookup_entity":
        entity = result.get("entity", {})
        if result.get("error") == "not_found":
            yield f"{plan.get('entity_type', 'Entity')} {plan.get('entity_id')} was not found in the dataset."
            return
        name = entity.get("fullName") or entity.get("productDescription") or entity.get("plantName") or ""
        amount = entity.get("totalNetAmount") or entity.get("total_net_amount")
        out = f"Found {plan.get('entity_type','entity').replace('_',' ')} {plan.get('entity_id')}."
        if name:
            out += f" Name: {name}."
        if amount:
            out += f" Net amount: {float(amount):.2f}."
        yield out
        return
    yield "Query executed successfully."


def _sse(event_type: str, payload: Any) -> str:
    return f"data: {json.dumps({'type': event_type, 'payload': payload})}\n\n"


@router.post("/stream")
def query_stream_endpoint(payload: QueryRequest, db: Session = Depends(get_db)):
    """
    Streaming endpoint. Returns SSE with:
      {type: 'plan',   payload: {...}}
      {type: 'result', payload: {...}}
      {type: 'token',  payload: "word "}  (streamed NL answer)
      {type: 'done'}
    """

    def generate():
        # Step 1 – query plan
        raw_plan = generate_query_plan(payload.query)
        validated_plan = validate_query_plan(raw_plan)
        yield _sse("plan", validated_plan)

        # Step 2 – execute
        result = execute_query_plan(db, validated_plan)
        yield _sse("result", result)

        # Step 3 – stream NL answer token-by-token
        for token in _stream_nl_answer(payload.query, validated_plan, result):
            yield _sse("token", token)

        yield _sse("done", None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
