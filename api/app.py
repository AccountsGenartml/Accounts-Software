import os
import sys
from pathlib import Path

# Make the project root importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import the Flask application from the root app.py
from app import app as flask_app

# Export as `app` — the name Vercel looks for
app = flask_app
