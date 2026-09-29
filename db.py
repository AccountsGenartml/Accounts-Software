import requests
import json
import os
from pathlib import Path

HERE = Path(__file__).parent
SECRETS = HERE / "config" / "secrets.json"

def get_supabase_credentials():
    if SECRETS.exists():
        try:
            secrets = json.loads(SECRETS.read_text())
            url = secrets.get("supabase_url")
            key = secrets.get("supabase_key")
            if url and key:
                return url.rstrip("/"), key
        except Exception:
            pass
    
    # Fallback to env vars (for Vercel)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return url.rstrip("/"), key
        
    return None, None

def get_headers(key):
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

def get_json(config_name):
    """Fetch a config JSON from Supabase configs table. Fallback to local file if not found/no DB."""
    url, key = get_supabase_credentials()
    if not url:
        # Fallback local
        local_path = HERE / "config" / f"{config_name}.json"
        if local_path.exists():
            return json.loads(local_path.read_text())
        return [] if config_name == "chat_history" else {}
        
    res = requests.get(
        f"{url}/rest/v1/configs?key=eq.{config_name}&select=value",
        headers=get_headers(key)
    )
    if res.status_code == 200 and res.json():
        return res.json()[0]["value"]
    
    local_path = HERE / "config" / f"{config_name}.json"
    if local_path.exists():
        local_data = json.loads(local_path.read_text())
    else:
        local_data = [] if config_name == "chat_history" else {}
    save_json(config_name, local_data)
    return local_data

def save_json(config_name, data):
    """Save a config JSON to Supabase configs table."""
    url, key = get_supabase_credentials()
    if not url:
        # Fallback local
        p = HERE / "config" / f"{config_name}.json"
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return

    # Upsert to Supabase
    payload = {"key": config_name, "value": data}
    headers = get_headers(key)
    headers["Prefer"] = "resolution=merge-duplicates"
    
    res = requests.post(
        f"{url}/rest/v1/configs",
        headers=headers,
        json=payload
    )
    res.raise_for_status()

