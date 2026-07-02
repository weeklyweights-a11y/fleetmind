"""Neo4j graph read queries with Postgres enrichment."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import FleetMindError
from app.models.insurance_coverage import InsuranceCoverage
from app.models.vendor import Vendor
from app.neo4j_client import get_neo4j_driver
from app.schemas.common import GraphEdge, GraphNode
from app.schemas.fleet import FleetGraphResponse
from app.schemas.graph import EntityConnectionsResponse
from app.schemas.trucks import TruckGraphResponse

ENTITY_LABEL_MAP = {
    "truck": "Truck",
    "driver": "Driver",
    "vendor": "Vendor",
    "document": "Document",
    "insurance_policy": "InsurancePolicy",
    "ifta_filing": "IFTAFiling",
    "jurisdiction": "Jurisdiction",
}


async def _enrich_vendor_names(db: AsyncSession, nodes: list[GraphNode], tenant_id: int = 1) -> None:
    vendor_ids = [n.id for n in nodes if n.type == "Vendor"]
    if not vendor_ids:
        return
    uuids = []
    for vid in vendor_ids:
        try:
            uuids.append(uuid.UUID(vid))
        except ValueError:
            continue
    if not uuids:
        return
    result = await db.execute(
        select(Vendor.id, Vendor.name, Vendor.address, Vendor.vendor_type).where(
            Vendor.id.in_(uuids), Vendor.tenant_id == tenant_id
        )
    )
    name_map = {str(row.id): row for row in result.all()}
    for node in nodes:
        if node.type == "Vendor" and node.id in name_map:
            v = name_map[node.id]
            node.label = v.name
            node.properties.update({"name": v.name, "address": v.address, "vendor_type": v.vendor_type})


async def _synthesize_issued_by(
    db: AsyncSession,
    truck_id: uuid.UUID,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    tenant_id: int = 1,
) -> None:
    if any(e.type == "ISSUED_BY" for e in edges):
        return
    coverage = (
        await db.execute(
            select(InsuranceCoverage)
            .where(InsuranceCoverage.truck_id == truck_id, InsuranceCoverage.tenant_id == tenant_id)
            .order_by(InsuranceCoverage.expiry_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not coverage:
        return

    policy_nodes = [n for n in nodes if n.type == "InsurancePolicy"]
    if not policy_nodes:
        policy_id = str(coverage.id)
        nodes.append(
            GraphNode(
                id=policy_id,
                label=coverage.policy_number,
                type="InsurancePolicy",
                properties={
                    "policy_number": coverage.policy_number,
                    "insurer_name": coverage.insurer_name,
                },
            )
        )
        policy_node_id = policy_id
    else:
        policy_node_id = policy_nodes[0].id

    vendor_id = str(coverage.insurer_vendor_id) if coverage.insurer_vendor_id else f"insurer-{coverage.insurer_name}"
    if not any(n.id == vendor_id for n in nodes):
        nodes.append(
            GraphNode(
                id=vendor_id,
                label=coverage.insurer_name,
                type="Vendor",
                properties={"name": coverage.insurer_name},
            )
        )
    edges.append(
        GraphEdge(
            source=policy_node_id,
            target=vendor_id,
            type="ISSUED_BY",
            properties={"insurer_name": coverage.insurer_name},
        )
    )


def _node_from_record(node: Any) -> GraphNode | None:
    if node is None:
        return None
    labels = list(node.labels)
    ntype = labels[0] if labels else "Unknown"
    props = dict(node)
    pg_id = props.get("pg_id", str(node.element_id))
    label = props.get("full_name") or props.get("name") or props.get("policy_number") or props.get("document_type") or ntype
    return GraphNode(id=str(pg_id), label=str(label), type=ntype, properties=props)


async def get_truck_graph(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
) -> TruckGraphResponse:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_nodes: set[str] = set()

    driver = get_neo4j_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (t:Truck {pg_id: $truck_id})
            OPTIONAL MATCH (t)-[r1]-(n1)
            OPTIONAL MATCH (n1)-[r2]-(n2)
            WHERE n2 IS NULL OR NOT n2:Truck OR n2 = t
            RETURN t, collect(DISTINCT n1) AS n1s, collect(DISTINCT r1) AS r1s,
                   collect(DISTINCT n2) AS n2s, collect(DISTINCT r2) AS r2s
            """,
            truck_id=str(truck_id),
        )
        record = await result.single()
        if not record or record["t"] is None:
            return TruckGraphResponse(nodes=[], edges=[], center_node=str(truck_id))

        for node in [record["t"]] + (record["n1s"] or []) + (record["n2s"] or []):
            if node is None:
                continue
            gn = _node_from_record(node)
            if gn and gn.id not in seen_nodes:
                seen_nodes.add(gn.id)
                nodes.append(gn)

        for rel in (record["r1s"] or []) + (record["r2s"] or []):
            if rel is None:
                continue
            edges.append(
                GraphEdge(
                    source=str(rel.start_node["pg_id"]),
                    target=str(rel.end_node["pg_id"]),
                    type=rel.type,
                    properties=dict(rel),
                )
            )

    await _enrich_vendor_names(db, nodes, tenant_id)
    await _synthesize_issued_by(db, truck_id, nodes, edges, tenant_id)

    return TruckGraphResponse(nodes=nodes, edges=edges, center_node=str(truck_id))


async def get_fleet_graph(
    db: AsyncSession,
    tenant_id: int = 1,
) -> FleetGraphResponse:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen: set[str] = set()

    driver = get_neo4j_driver()
    async with driver.session() as session:
        n_result = await session.run(
            "MATCH (n) WHERE n:Truck OR n:Driver OR n:Vendor RETURN n"
        )
        async for rec in n_result:
            gn = _node_from_record(rec["n"])
            if gn and gn.id not in seen:
                seen.add(gn.id)
                nodes.append(gn)

        e_result = await session.run(
            """
            MATCH (a)-[r]->(b)
            WHERE (a:Truck OR a:Driver OR a:Vendor) AND (b:Truck OR b:Driver OR b:Vendor)
            RETURN a, r, b
            """
        )
        async for rec in e_result:
            edges.append(
                GraphEdge(
                    source=str(rec["a"]["pg_id"]),
                    target=str(rec["b"]["pg_id"]),
                    type=rec["r"].type,
                    properties=dict(rec["r"]),
                )
            )

    await _enrich_vendor_names(db, nodes, tenant_id)

    return FleetGraphResponse(
        nodes=nodes,
        edges=edges,
        stats={
            "truck_count": sum(1 for n in nodes if n.type == "Truck"),
            "driver_count": sum(1 for n in nodes if n.type == "Driver"),
            "vendor_count": sum(1 for n in nodes if n.type == "Vendor"),
            "relationship_count": len(edges),
        },
    )


async def get_entity_connections(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    max_hops: int = 2,
    tenant_id: int = 1,
) -> EntityConnectionsResponse:
    label = ENTITY_LABEL_MAP.get(entity_type.lower())
    if not label:
        raise FleetMindError(
            f"Unsupported entity type: {entity_type}",
            error_code="VALIDATION_ERROR",
            details={"supported": list(ENTITY_LABEL_MAP.keys())},
        )

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    paths: list[list[str]] = []
    seen: set[str] = set()

    driver = get_neo4j_driver()
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (start:{label} {{pg_id: $entity_id}})
            MATCH p = (start)-[*1..{max_hops}]-(connected)
            RETURN p
            LIMIT 100
            """,
            entity_id=entity_id,
        )
        async for rec in result:
            path = rec["p"]
            path_ids: list[str] = []
            for node in path.nodes:
                gn = _node_from_record(node)
                if gn and gn.id not in seen:
                    seen.add(gn.id)
                    nodes.append(gn)
                if gn:
                    path_ids.append(gn.id)
            for rel in path.relationships:
                edges.append(
                    GraphEdge(
                        source=str(rel.start_node["pg_id"]),
                        target=str(rel.end_node["pg_id"]),
                        type=rel.type,
                        properties=dict(rel),
                    )
                )
            if path_ids:
                paths.append(path_ids)

    await _enrich_vendor_names(db, nodes, tenant_id)

    return EntityConnectionsResponse(nodes=nodes, edges=edges, paths=paths)
