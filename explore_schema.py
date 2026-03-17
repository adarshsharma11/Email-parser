
import sys
import os
import asyncio

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from src.api.config import settings

async def explore_tables():
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        # Check booking_service columns
        print("Columns for booking_service:")
        res = await session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'booking_service'"))
        for row in res:
            print(f"  {row.column_name}: {row.data_type}")
            
        # Check cleaning_tasks columns
        print("\nColumns for cleaning_tasks:")
        res = await session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'cleaning_tasks'"))
        for row in res:
            print(f"  {row.column_name}: {row.data_type}")

        # Check service_category columns
        print("\nColumns for service_category:")
        res = await session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'service_category'"))
        for row in res:
            print(f"  {row.column_name}: {row.data_type}")

if __name__ == "__main__":
    asyncio.run(explore_tables())
