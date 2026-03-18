import asyncio
from sqlalchemy import text
import sys
import os

# Add the project root to sys.path to allow imports from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.api.dependencies import get_db_session
from src.api.config import settings
from config.settings import app_config

async def update_ical_urls():
    """Update existing properties with correct iCal feed URLs including the version prefix."""
    # Use the generator directly
    async for session in get_db_session():
        try:
            # Fetch all properties
            query = text(f"SELECT id, ical_feed_url FROM {app_config.properties_collection}")
            result = await session.execute(query)
            properties = result.fetchall()
            
            base_url = settings.api_base_url or "http://127.0.0.1:8001"
            api_prefix = settings.api_prefix or ""
            api_version = settings.api_version or "v1"
            prefix_part = f"{api_prefix}/{api_version}" if api_prefix else f"/{api_version}"

            updated_count = 0
            for prop in properties:
                prop_id = prop.id
                # New URL format using /ical instead of .ics to avoid proxy static file interception
                new_url = f"{base_url}{prefix_part}/property/{prop_id}/ical"
                
                # Only update if the URL has changed
                if prop.ical_feed_url != new_url:
                    print(f"Updating property {prop_id}: {prop.ical_feed_url} -> {new_url}")
                    update_query = text(f"UPDATE {app_config.properties_collection} SET ical_feed_url = :url WHERE id = :id")
                    await session.execute(update_query, {"url": new_url, "id": prop_id})
                    updated_count += 1
            
            await session.commit()
            print(f"Successfully updated {updated_count} property iCal URLs.")
            break # Exit after one session
        except Exception as e:
            print(f"Error updating iCal URLs: {e}")
            await session.rollback()
            break

if __name__ == "__main__":
    asyncio.run(update_ical_urls())
