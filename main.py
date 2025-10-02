"""
Main entry point for the FastAPI application (Vercel expects `app` here).
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api.app import create_app, settings

# This is what Vercel looks for
app = create_app()

# Local dev only
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
        access_log=True
    )
