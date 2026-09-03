import os
import sys
from pathlib import Path

# Make the project root importable so we can import the original Flask app
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

# Import the existing Flask application (defined in app.py at the repo root)
from app import app as flask_app  # original Flask app

# Ensure static assets are served from the `public` folder (Vercel serves files from the repo root)
flask_app.static_folder = str(PROJECT_ROOT / "public")

# Export the Flask app as the entrypoint Vercel expects
app = flask_app
