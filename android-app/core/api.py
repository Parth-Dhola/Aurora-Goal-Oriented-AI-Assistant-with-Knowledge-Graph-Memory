"""
core/api.py — HTTP and API communication layer for Aurora Android App
"""
import requests
from typing import Dict, Any, Optional
from core.config import get_api_base, SERVER_URL


def api_post(endpoint: str, data: dict, token: Optional[str] = None) -> Dict[str, Any]:
    """Send JSON POST request to Aurora API."""
    url = f"{get_api_base()}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(url, json=data, headers=headers, timeout=15)
        return r.json()
    except requests.exceptions.ConnectionError:
        return {
            "error": f"Cannot connect to: {SERVER_URL}\n"
                     f"Please ensure the backend is running with --host 0.0.0.0 and you entered the correct Wi-Fi IP."
        }
    except Exception as e:
        return {"error": str(e)}


def api_get(endpoint: str, token: Optional[str] = None) -> Dict[str, Any]:
    """Send JSON GET request to Aurora API."""
    url = f"{get_api_base()}{endpoint}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def api_upload_document(filepath: str, token: str) -> Dict[str, Any]:
    """Upload a study PDF or text note to the Knowledge Graph."""
    import os
    filename = os.path.basename(filepath)
    url = f"{get_api_base()}/documents/upload"
    try:
        with open(filepath, "rb") as f:
            file_bytes = f.read()
        
        mime_type = "application/pdf" if filename.lower().endswith(".pdf") else "text/plain"
        files = {"file": (filename, file_bytes, mime_type)}
        headers = {"Authorization": f"Bearer {token}"}
        
        r = requests.post(url, files=files, headers=headers, timeout=60)
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"detail": "Cannot connect to server."}
    except Exception as e:
        return {"detail": str(e)}

