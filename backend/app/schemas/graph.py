from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import GraphEdge, GraphNode


class EntityConnectionsResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    paths: list[list[str]] = Field(default_factory=list)
