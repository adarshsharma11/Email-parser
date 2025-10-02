import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.app import create_app

# Create app instance for Vercel
app = create_app()