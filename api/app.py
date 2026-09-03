import os
import sys
from pathlib import Path
from werkzeug.wrappers import Response

# -----------------------------------------------------------------
# Make the project root importable (so we can import the original code)
# -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]   # …/genartml-payroll-4
sys.path.append(str(PROJECT_ROOT))

# -----------------------------------------------------------------
# Import the *real* Flask application – we keep it unchanged except
# for the static folder path (now it must point to ../public)
# -----------------------------------------------------------------
from app import app as flask_app  # <-- this pulls in the original app.py

# -----------------------------------------------------------------
# Adjust the Flask app to use the public folder for static assets.
# (Only needed if the original app used `static_folder='static'`.)
# -----------------------------------------------------------------
flask_app.static_folder = str(PROJECT_ROOT / "public")

# -----------------------------------------------------------------
# Vercel calls `handler(event, context)` → we translate it to a WSGI
# request using Werkzeug and return the proper dict Vercel expects.
# -----------------------------------------------------------------
def handler(event, context):
    """
    Vercel entry point.
    `event` contains the HTTP request data.
    We build a WSGI environ dict, call the Flask app and return a Vercel‑compatible
    response dict: {statusCode, headers, body, isBase64Encoded}
    """
    # Build the WSGI environ from the event (Vercel provides a subset that Werkzeug understands)
    environ = {
        "REQUEST_METHOD": event["httpMethod"],
        "PATH_INFO": event["path"],
        "SERVER_NAME": event["headers"].get("host", "vercel"),
        "SERVER_PORT": event["headers"].get("x-forwarded-port", "443"),
        "QUERY_STRING": "",
        "wsgi.input": sys.stdin,
        "wsgi.errors": sys.stderr,
        "wsgi.version": (1, 0),
        "wsgi.run_once": False,
        "wsgi.url_scheme": "https",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
    }

    # Add all incoming HTTP headers (case‑insensitive) to environ
    for k, v in event.get("headers", {}).items():
        environ[f"HTTP_{k.upper().replace('-', '_')}"] = v

    response_body = []
    status_headers = {}

    def start_response(status, response_headers, exc_info=None):
        status_headers["status"] = status
        status_headers["headers"] = dict(response_headers)

    result = flask_app.wsgi_app(environ, start_response)
    for data in result:
        response_body.append(data)
    if hasattr(result, "close"):
        result.close()

    body_bytes = b"".join(response_body)
    body = body_bytes.decode("utf-8")

    return {
        "statusCode": int(status_headers["status"].split()[0]),
        "headers": status_headers["headers"],
        "body": body,
        "isBase64Encoded": False,
    }
