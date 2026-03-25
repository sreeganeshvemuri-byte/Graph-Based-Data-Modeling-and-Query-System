from __future__ import annotations

from typing import Any

from app.query.plans import (
    RejectPlan,
    TraceFlowPlan,
    TopProductsPlan,
    FindBrokenFlowsPlan,
    LookupEntityPlan,
    parse_query_plan_or_reject,
)


def validate_query_plan(query_plan_json: Any) -> dict[str, Any]:
    """
    Validation layer for the query plan.

    - Uses Pydantic models with strict schema (no extra fields).
    - Rejects invalid intent, missing required fields, and extra fields.
    - On any invalid input, returns a `reject` response.
    """
    parsed = parse_query_plan_or_reject(query_plan_json)

    if isinstance(
        parsed,
        (
            TraceFlowPlan,
            TopProductsPlan,
            FindBrokenFlowsPlan,
            LookupEntityPlan,
            RejectPlan,
        ),
    ):
        return parsed.model_dump()

    # Should not happen; keep defensive behavior.
    return RejectPlan(
        intent="reject",
        reason="out_of_scope",
        clarification_needed="Invalid query plan payload.",
    ).model_dump()

