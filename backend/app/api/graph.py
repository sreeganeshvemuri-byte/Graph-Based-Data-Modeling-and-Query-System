from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GraphEdge
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


@router.get("/overview", response_model=GraphOverviewResponse)
def graph_overview(
    max_edges: int = Query(default=800, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> GraphOverviewResponse:
    rows = db.execute(select(GraphEdge).limit(max_edges)).scalars().all()

    node_map: dict[tuple[str, str], GraphNode] = {}
    edges: list[GraphEdgeDTO] = []

    for e in rows:
        src_key = (e.source_type, e.source_id)
        tgt_key = (e.target_type, e.target_id)

        if src_key not in node_map:
            node_map[src_key] = GraphNode(type=e.source_type, id=e.source_id, metadata={})
        if tgt_key not in node_map:
            node_map[tgt_key] = GraphNode(type=e.target_type, id=e.target_id, metadata={})

        edges.append(
            GraphEdgeDTO(
                edge_type=e.edge_type,
                source={"type": e.source_type, "id": e.source_id},
                target={"type": e.target_type, "id": e.target_id},
            )
        )

    return GraphOverviewResponse(nodes=list(node_map.values()), edges=edges)
