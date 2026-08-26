from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.models import Base


def make_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        db_path = database_url.rsplit("/", 1)[-1]
        if db_path and db_path != ":memory:":
            Path("data").mkdir(parents=True, exist_ok=True)
    return create_async_engine(database_url, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


def _ensure_compatible_schema(sync_conn) -> None:
    """Small additive migrations for databases created by earlier playtest builds."""
    columns = {column["name"] for column in inspect(sync_conn).get_columns("games")}
    if "live_zone" not in columns:
        sync_conn.execute(
            text("ALTER TABLE games ADD COLUMN live_zone BOOLEAN NOT NULL DEFAULT FALSE")
        )


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_compatible_schema)
