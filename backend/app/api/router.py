from fastapi import APIRouter

from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.query import router as query_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(query_router, prefix="/query")
api_router.include_router(graph_router, prefix="/graph")
