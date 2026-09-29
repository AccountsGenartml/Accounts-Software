import requests
from pathlib import Path
from db import get_supabase_credentials, get_headers
import os

def upload_file_to_bucket(bucket_name, file_path, object_name=None):
    url, key = get_supabase_credentials()
    if not url: return  # local mode
    if not object_name: object_name = Path(file_path).name
    
    with open(file_path, "rb") as f:
        requests.post(
            f"{url}/storage/v1/object/{bucket_name}/{object_name}",
            headers=get_headers(key),
            data=f
        )

def download_file_from_bucket(bucket_name, object_name, dest_path):
    url, key = get_supabase_credentials()
    if not url: return False
    
    res = requests.get(
        f"{url}/storage/v1/object/public/{bucket_name}/{object_name}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}
    )
    if res.status_code == 200:
        with open(dest_path, "wb") as f:
            f.write(res.content)
        return True
    return False
