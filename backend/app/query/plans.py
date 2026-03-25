from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class RejectPlan(BaseModel):
    intent: Literal["reject"]
    reason: Literal[
        "out_of_scope",
        "ambiguous_entity",
        "unsupported_operation",
        "missing_required_parameter",
        "multiple_intents_detected",
    ]
    clarification_needed: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("clarification_needed")
    @classmethod
    def _check_clarification_len(cls, v: str) -> str:
        if len(v) < 10 or len(v) > 400:
            raise ValueError("clarification_needed must be 10-400 chars")
        return v


class TraceFlowFilters(BaseModel):
    company_code: str | None = None
    fiscal_year: str | None = None
    include_cancelled: bool = False

    model_config = ConfigDict(extra="forbid")


class TraceFlowPlan(BaseModel):
    intent: Literal["trace_flow"]
    entity_type: Literal["sales_order", "billing_document", "delivery", "customer"]
    entity_id: str
    stages: list[
        Literal[
            "sales_order",
            "schedule_lines",
            "delivery",
            "billing",
            "journal_entry",
            "payment",
            "cancellation",
        ]
    ]
    filters: TraceFlowFilters

    model_config = ConfigDict(extra="forbid")

    @field_validator("entity_id")
    @classmethod
    def _non_empty_entity_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("entity_id must be non-empty")
        return v.strip()

    @field_validator("stages")
    @classmethod
    def _unique_stages(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("stages must be unique")
        if not v:
            raise ValueError("stages must have at least 1 element")
        return v


class TopProductsFilters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    company_code: str | None = None
    customer_id: str | None = None
    exclude_cancelled: bool = False
    product_group: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("date_to")
    @classmethod
    def _validate_dates(cls, v: date | None, info) -> date | None:  # type: ignore[override]
        # pydantic supplies other fields via info.data in v2.
        data = info.data
        date_from = data.get("date_from")
        if v is not None and date_from is not None and v < date_from:
            raise ValueError("date_to must be >= date_from")
        return v


class TopProductsPlan(BaseModel):
    intent: Literal["top_products_by_billing"]
    limit: Annotated[int, Field(ge=1, le=100)]
    sort_by: Literal["total_net_amount", "invoice_count", "quantity"]
    filters: TopProductsFilters

    model_config = ConfigDict(extra="forbid")


class FindBrokenFlowsFilters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    company_code: str | None = None
    fiscal_year: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("date_to")
    @classmethod
    def _validate_dates(cls, v: date | None, info) -> date | None:  # type: ignore[override]
        data = info.data
        date_from = data.get("date_from")
        if v is not None and date_from is not None and v < date_from:
            raise ValueError("date_to must be >= date_from")
        return v


class FindBrokenFlowsPlan(BaseModel):
    intent: Literal["find_broken_flows"]
    break_types: list[
        Literal[
            "billing_without_delivery",
            "delivery_without_sales_order",
            "billing_without_journal_entry",
            "journal_entry_without_clearing",
            "cancelled_without_accounting_doc",
            "active_txn_on_blocked_partner",
            "amount_mismatch_billing_vs_journal",
        ]
    ]
    filters: FindBrokenFlowsFilters

    model_config = ConfigDict(extra="forbid")

    @field_validator("break_types")
    @classmethod
    def _unique_break_types(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("break_types must be unique")
        if not v:
            raise ValueError("break_types must have at least 1 element")
        return v


class LookupEntityPlan(BaseModel):
    intent: Literal["lookup_entity"]
    entity_type: Literal[
        "customer",
        "product",
        "plant",
        "sales_order",
        "delivery",
        "billing_document",
    ]
    entity_id: str
    include_related: list[
        Literal[
            "addresses",
            "sales_area_config",
            "company_config",
            "items",
            "schedule_lines",
            "billing_documents",
            "journal_entries",
            "payments",
            "cancellations",
            "product_descriptions",
            "storage_locations",
        ]
    ]

    model_config = ConfigDict(extra="forbid")

    @field_validator("entity_id")
    @classmethod
    def _non_empty_entity_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("entity_id must be non-empty")
        return v.strip()

    @field_validator("include_related")
    @classmethod
    def _unique_include_related(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("include_related must be uniqueItems")
        return v


QueryPlan = Annotated[
    TraceFlowPlan | TopProductsPlan | FindBrokenFlowsPlan | LookupEntityPlan | RejectPlan,
    Field(discriminator="intent"),  # type: ignore[arg-type]
]


def parse_query_plan_or_reject(raw: object) -> TraceFlowPlan | TopProductsPlan | FindBrokenFlowsPlan | LookupEntityPlan | RejectPlan:
    """
    Parse raw JSON into one of the allowed plans.
    On validation failure, returns a RejectPlan.
    """
    def _normalize_clarification(v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            v = (v + " (details)").strip()
        if len(v) > 400:
            v = v[:397] + "..."
        return v

    if not isinstance(raw, dict):
        return RejectPlan(
            intent="reject",
            reason="missing_required_parameter",
            clarification_needed=_normalize_clarification("Query plan must be a JSON object."),
        )

    intent = raw.get("intent")
    allowed_intents = {
        "trace_flow",
        "top_products_by_billing",
        "find_broken_flows",
        "lookup_entity",
        "reject",
    }

    if intent not in allowed_intents:
        return RejectPlan(
            intent="reject",
            reason="out_of_scope",
            clarification_needed=_normalize_clarification(
                "Invalid intent. Expected one of: trace_flow, top_products_by_billing, find_broken_flows, lookup_entity, reject."
            ),
        )

    try:
        if intent == "trace_flow":
            return TraceFlowPlan.model_validate(raw)
        if intent == "top_products_by_billing":
            return TopProductsPlan.model_validate(raw)
        if intent == "find_broken_flows":
            return FindBrokenFlowsPlan.model_validate(raw)
        if intent == "lookup_entity":
            return LookupEntityPlan.model_validate(raw)
        if intent == "reject":
            return RejectPlan.model_validate(raw)
    except ValidationError as e:
        # This covers missing required fields and extra/unexpected keys (because extra="forbid").
        # Reason enum allows "missing_required_parameter" and "out_of_scope"; we map to missing_required_parameter.
        err0 = e.errors()[0] if e.errors() else {"msg": "validation_error"}
        details = str(err0.get("msg") or err0)
        return RejectPlan(
            intent="reject",
            reason="missing_required_parameter",
            clarification_needed=_normalize_clarification(f"Query plan validation failed: {details}"),
        )

    # Defensive fallback
    return RejectPlan(
        intent="reject",
        reason="out_of_scope",
        clarification_needed=_normalize_clarification("Unsupported or invalid query plan payload."),
    )

