"""
core/api.py — HTTP and API communication layer for Aurora Android App
"""
import os
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
        r = requests.post(url, json=data, headers=headers, timeout=25)
        return r.json()
    except requests.exceptions.ConnectionError:
        return {
            "error": f"Cannot connect to: {SERVER_URL}\n"
                     f"Please ensure the backend is running with --host 0.0.0.0 and you entered the correct Wi-Fi IP."
        }
    except requests.exceptions.Timeout:
        return {"error": "Request timed out. The server is taking longer than expected."}
    except Exception as e:
        return {"error": str(e)}


def api_get(endpoint: str, token: Optional[str] = None) -> Dict[str, Any]:
    """Send JSON GET request to Aurora API."""
    url = f"{get_api_base()}{endpoint}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=25)
        return r.json()
    except requests.exceptions.Timeout:
        return {"error": "Request timed out."}
    except Exception as e:
        return {"error": str(e)}


def api_upload_document(filepath: str, token: str) -> Dict[str, Any]:
    """Upload a study PDF or text note to the Knowledge Graph with generous timeout."""
    filename = os.path.basename(filepath)
    url = f"{get_api_base()}/documents/upload"
    try:
        with open(filepath, "rb") as f:
            file_bytes = f.read()

        file_size_mb = len(file_bytes) / (1024 * 1024)
        if file_size_mb > 50:
            return {"detail": f"File is too large ({file_size_mb:.1f} MB). Maximum allowed size is 50 MB."}

        mime_type = "application/pdf" if filename.lower().endswith(".pdf") else "text/plain"
        files = {"file": (filename, file_bytes, mime_type)}
        headers = {"Authorization": f"Bearer {token}"}

        # 180s timeout allows deep LLM decomposition of large multi-page textbooks
        r = requests.post(url, files=files, headers=headers, timeout=180)
        return r.json()
    except requests.exceptions.Timeout:
        return {"detail": "Upload timed out. The document is large and took over 3 minutes to process."}
    except requests.exceptions.ConnectionError:
        return {"detail": "Cannot connect to server."}
    except Exception as e:
        return {"detail": str(e)}
