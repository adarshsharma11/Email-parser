"""
PostgreSQL client using SQLAlchemy and asyncpg.
"""
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from src.api.config import settings

logger = structlog.get_logger(__name__)

# Base class for SQLAlchemy models
Base = declarative_base()

class PostgreSQLClient:
    """PostgreSQL client for database operations."""

    def __init__(self, database_url: str = settings.database_url):
        self.database_url = database_url
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        self.async_session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency for getting async session."""
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            finally:
                await session.close()

    async def close(self):
        """Close database engine."""
        await self.engine.dispose()

# Global instance
psql_client = PostgreSQLClient()
