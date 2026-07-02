import asyncio

from app.neo4j_client import apply_migrations, close_neo4j_driver, get_neo4j_driver, verify_connectivity


def test_neo4j_constraints_exist():
    async def _check():
        await close_neo4j_driver()
        assert await verify_connectivity()
        await apply_migrations()
        driver = get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run("SHOW CONSTRAINTS")
            records = [record async for record in result]
            names = [str(r.get("name", "")) for r in records]
            assert any("truck" in name.lower() for name in names)

    asyncio.run(_check())
