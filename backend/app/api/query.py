from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.planner import generate_query_plan
from app.query.execute import execute_query_plan
from app.query.validation import validate_query_plan


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
    # 1) user input -> generate_query_plan()
    raw_plan = generate_query_plan(payload.query)

    # 2) validate JSON (strict)
    validated_plan = validate_query_plan(raw_plan)

    # 3) route to query handlers
    result = execute_query_plan(db, validated_plan)

    return QueryResponse(plan=validated_plan, result=result)

