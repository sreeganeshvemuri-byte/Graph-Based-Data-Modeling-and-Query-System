from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.query.handlers import (
    handle_find_broken_flows,
    handle_lookup_entity,
    handle_trace_flow,
    handle_top_products_by_billing,
)
from app.query.validation import validate_query_plan
from app.query.plans import (
    FindBrokenFlowsPlan,
    LookupEntityPlan,
    RejectPlan,
    TraceFlowPlan,
    TopProductsPlan,
    parse_query_plan_or_reject,
)

from app.query.validation import validate_query_plan


def execute_user_input(session: Session, user_input: str) -> dict[str, Any]:
    """
    Full pipeline:
    1. user input -> generate_query_plan()
    2. validate JSON (strict)
    3. route to query handlers

    Returns:
      { "query_plan": <validated plan dict>, "result": <handler output> }

    Notes:
    - No SQL is ever produced or accepted from the LLM.
    - The LLM output is treated as data only and must pass strict Pydantic validation.
    """
    from app.llm.planner import generate_query_plan

    raw_plan = generate_query_plan(user_input)
    validated_plan = validate_query_plan(raw_plan)
    result = execute_query_plan(session, validated_plan)
    return {"query_plan": validated_plan, "result": result}


def execute_query_plan(session: Session, query_plan_json: Any) -> dict[str, Any]:
    """
    Validate JSON query plan and execute the corresponding handler.
    Does not integrate any LLM. Pure backend execution.
    """
    # Validation layer: strict schema; returns reject plan on invalid input.
    validated = validate_query_plan(query_plan_json)
    parsed = parse_query_plan_or_reject(validated)

    if isinstance(parsed, RejectPlan):
        return parsed.model_dump()

    if isinstance(parsed, TraceFlowPlan):
        return handle_trace_flow(session, parsed)
    if isinstance(parsed, TopProductsPlan):
        return handle_top_products_by_billing(session, parsed)
    if isinstance(parsed, FindBrokenFlowsPlan):
        return handle_find_broken_flows(session, parsed)
    if isinstance(parsed, LookupEntityPlan):
        return handle_lookup_entity(session, parsed)

    # Fallback; should be unreachable.
    return {
        "intent": "reject",
        "reason": "unsupported_operation",
        "clarification_needed": "Unsupported query plan type.",
    }

