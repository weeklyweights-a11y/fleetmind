import logging
from pathlib import Path

from neo4j import AsyncGraphDatabase, AsyncDriver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document import Document
from app.models.driver import Driver
from app.models.truck import Truck
from app.models.vendor import Vendor

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=settings.neo4j_max_connection_pool_size,
        )
    return _driver


async def close_neo4j_driver() -> None:
    global _driver
    if _driver is not None:
        try:
            await _driver.close()
        except (RuntimeError, AttributeError):
            logger.debug("Neo4j driver close skipped (event loop closed)")
        _driver = None


async def verify_connectivity() -> bool:
    driver = get_neo4j_driver()
    try:
        await driver.verify_connectivity()
        return True
    except Exception:
        logger.exception("Neo4j connectivity check failed")
        return False


async def apply_migrations() -> None:
    driver = get_neo4j_driver()
    migrations_dir = Path(__file__).resolve().parent.parent / "neo4j" / "migrations"
    for path in sorted(migrations_dir.glob("*.cypher")):
        statements = [
            s.strip()
            for s in path.read_text(encoding="utf-8").replace(";", "\n").splitlines()
            if s.strip() and not s.strip().startswith("//")
        ]
        async with driver.session() as session:
            for statement in statements:
                await session.run(statement)
        logger.info("Applied Neo4j migration %s", path.name)


async def check_graph_integrity(db: AsyncSession) -> None:
    """Log-only integrity check in Phase 1; no auto-resync."""
    driver = get_neo4j_driver()
    pg_counts = {
        "Truck": (await db.execute(select(func.count()).select_from(Truck))).scalar_one(),
        "Driver": (await db.execute(select(func.count()).select_from(Driver))).scalar_one(),
        "Vendor": (await db.execute(select(func.count()).select_from(Vendor))).scalar_one(),
        "Document": (await db.execute(select(func.count()).select_from(Document))).scalar_one(),
    }

    neo4j_labels = ["Truck", "Driver", "Vendor", "Document", "InsurancePolicy", "IFTAFiling"]
    async with driver.session() as session:
        for label in neo4j_labels:
            pg_count = pg_counts.get(label, 0)
            result = await session.run(f"MATCH (n:{label}) RETURN count(n) AS c")
            record = await result.single()
            neo4j_count = record["c"] if record else 0
            if label in pg_counts and neo4j_count != pg_count:
                logger.warning(
                    "Graph integrity: %s Postgres=%s Neo4j=%s",
                    label,
                    pg_count,
                    neo4j_count,
                )
            else:
                logger.info("Graph integrity: %s Neo4j count=%s", label, neo4j_count)
