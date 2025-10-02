"""
Main entry point for the FastAPI application.
"""
import os
import sys
from pathlib import Path
from src.api.app import create_app, settings

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Expose FastAPI app for Vercel
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",  # point to the app, not create_app
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
        access_log=True
    )
