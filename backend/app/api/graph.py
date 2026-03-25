from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import GraphEdge, SalesOrderHeader, BillingDocumentHeader, OutboundDeliveryHeader, BusinessPartner
from app.db.session import get_db

router = APIRouter(tags=["graph"])


class GraphNode(BaseModel):
    type: str
    id: str
    metadata: dict = {}

    model_config = ConfigDict(extra="forbid")


class GraphEdgeDTO(BaseModel):
    edge_type: str
    source: dict[str, str]
    target: dict[str, str]

    model_config = ConfigDict(extra="forbid")


class GraphOverviewResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdgeDTO]

    model_config = ConfigDict(extra="forbid")


class GraphStatsResponse(BaseModel):
    node_counts: dict[str, int]
    edge_counts: dict[str, int]
    total_nodes: int
    total_edges: int

    model_config = ConfigDict(extra="forbid")


def _quick_metadata(db: Session, node_type: str, node_id: str) -> dict:
    """Fetch minimal metadata for graph overview nodes."""
    try:
        if node_type == "sales_order":
            row = db.get(SalesOrderHeader, node_id)
            if row:
                return {
                    "sold_to_party": row.soldToParty,
                    "total_net_amount": row.totalNetAmount,
                    "status": row.status,
                }
        elif node_type == "billing_document":
            row = db.get(BillingDocumentHeader, node_id)
            if row:
                return {
                    "sold_to_party": row.soldToParty,
                    "total_net_amount": row.totalNetAmount,
                    "is_cancelled": row.isCancelled,
                }
        elif node_type == "delivery":
            row = db.get(OutboundDeliveryHeader, node_id)
            if row:
                return {
                    "picking_status": row.pickingStatus,
                    "goods_movement_status": row.goodsMovementStatus,
                }
        elif node_type == "customer":
            row = db.get(BusinessPartner, node_id)
            if row:
                return {
                    "full_name": row.fullName,
                    "is_blocked": row.isBlocked,
                }
    except Exception:
        pass
    return {}


@router.get("/overview", response_model=GraphOverviewResponse)
def graph_overview(
    max_edges: int = Query(default=800, ge=1, le=5000),
    node_types: str = Query(default="", description="Comma-separated node types to filter, e.g. sales_order,billing_document"),
    db: Session = Depends(get_db),
) -> GraphOverviewResponse:
    stmt = select(GraphEdge).limit(max_edges)

    # Optionally filter by node type
    allowed_types = [t.strip() for t in node_types.split(",") if t.strip()] if node_types else []
    if allowed_types:
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(
                GraphEdge.source_type.in_(allowed_types),
                GraphEdge.target_type.in_(allowed_types),
            )
        )

    rows = db.execute(stmt).scalars().all()

    node_map: dict[tuple[str, str], GraphNode] = {}
    edges: list[GraphEdgeDTO] = []

    for e in rows:
        src_key = (e.source_type, e.source_id)
        tgt_key = (e.target_type, e.target_id)

        if src_key not in node_map:
            node_map[src_key] = GraphNode(
                type=e.source_type,
                id=e.source_id,
                metadata=_quick_metadata(db, e.source_type, e.source_id),
            )
        if tgt_key not in node_map:
            node_map[tgt_key] = GraphNode(
                type=e.target_type,
                id=e.target_id,
                metadata=_quick_metadata(db, e.target_type, e.target_id),
            )

        edges.append(
            GraphEdgeDTO(
                edge_type=e.edge_type,
                source={"type": e.source_type, "id": e.source_id},
                target={"type": e.target_type, "id": e.target_id},
            )
        )

    return GraphOverviewResponse(nodes=list(node_map.values()), edges=edges)


@router.get("/stats", response_model=GraphStatsResponse)
def graph_stats(db: Session = Depends(get_db)) -> GraphStatsResponse:
    """Return node and edge type counts for the overview stats panel."""
    node_type_rows = db.execute(
        select(GraphEdge.source_type, func.count().label("cnt"))
        .group_by(GraphEdge.source_type)
    ).all()

    edge_type_rows = db.execute(
        select(GraphEdge.edge_type, func.count().label("cnt"))
        .group_by(GraphEdge.edge_type)
    ).all()

    node_counts = {t: c for t, c in node_type_rows}
    edge_counts = {t: c for t, c in edge_type_rows}

    return GraphStatsResponse(
        node_counts=node_counts,
        edge_counts=edge_counts,
        total_nodes=sum(node_counts.values()),
        total_edges=sum(edge_counts.values()),
    )
