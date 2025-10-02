"""
Main entry point for the FastAPI application.
"""
import os
import sys
from pathlib import Path

# Add the project root to Python path before imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api.app import create_app, settings

# Expose FastAPI app for Vercel
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",  # Vercel needs this to point to `app`
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
        access_log=True
    )
