import pytest
import sys
import os
import tempfile
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ["GEMINI_API_KEY"]        = "dummy-key-for-tests"
os.environ["SECRET_KEY"]            = "test-secret-key-for-tests-32bytes-secure-key"
os.environ["MLFLOW_TRACKING_URI"]   = "sqlite:///test_mlflow.db"
os.environ["TELEGRAM_TOKEN"]        = "dummy-telegram-token"

# Mock heavy external deps so tests are fast and offline
sys.modules["mlflow"]               = unittest.mock.MagicMock()
sys.modules["mlflow.tracking"]      = unittest.mock.MagicMock()
sys.modules["google.generativeai"]  = unittest.mock.MagicMock()
sys.modules["langgraph"]            = unittest.mock.MagicMock()
sys.modules["langgraph.graph"]      = unittest.mock.MagicMock()
sys.modules["langgraph.checkpoint"] = unittest.mock.MagicMock()
sys.modules["langgraph.checkpoint.sqlite"] = unittest.mock.MagicMock()
sys.modules["duckduckgo_search"]    = unittest.mock.MagicMock()

# Mock the CRAG agent so chat tests don't call Gemini
_MOCK_AGENT = unittest.mock.MagicMock()
_MOCK_AGENT.return_value = {
    "answer": "Mock Aurora response",
    "strategy": "direct",
    "kg_nodes_used": 0,
    "context_relevant": False,
    "latency_ms": 10.0,
}
sys.modules["services.crag_agent"] = unittest.mock.MagicMock(run_agent=_MOCK_AGENT)

from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["DB_PATH"] = tmp.name

    import importlib
    import models.database as dbmod
    importlib.reload(dbmod)

    from app import app
    from models.database import init_db
    init_db()

    with TestClient(app) as c:
        yield c

    try:
        os.unlink(tmp.name)
    except Exception:
        pass


@pytest.fixture
def auth_client(client):
    """Client with a registered and logged-in user. Returns (client, token)."""
    r = client.post("/api/auth/register",
                    json={"username": "testuser", "password": "testpass123"})
    token = r.json()["access_token"]
    return client, token


def H(token):
    return {"Authorization": f"Bearer {token}"}


# ── Health ────────────────────────────────────────────────────────────────────
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["version"] == "3.0.0"


# ── Auth ──────────────────────────────────────────────────────────────────────
def test_register(client):
    r = client.post("/api/auth/register",
                    json={"username": "parth", "password": "secret123"})
    assert r.status_code == 201
    assert "access_token" in r.json()
    assert r.json()["username"] == "parth"

def test_register_duplicate(client):
    client.post("/api/auth/register", json={"username": "parth", "password": "secret123"})
    r = client.post("/api/auth/register", json={"username": "parth", "password": "other"})
    assert r.status_code == 400

def test_login_success(client):
    client.post("/api/auth/register", json={"username": "parth", "password": "secret123"})
    r = client.post("/api/auth/login",    json={"username": "parth", "password": "secret123"})
    assert r.status_code == 200
    assert "access_token" in r.json()

def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "parth", "password": "secret123"})
    r = client.post("/api/auth/login",    json={"username": "parth", "password": "wrong"})
    assert r.status_code == 401

def test_get_me(auth_client):
    client, token = auth_client
    r = client.get("/api/auth/me", headers=H(token))
    assert r.status_code == 200
    assert r.json()["username"] == "testuser"

def test_no_token_forbidden(client):
    r = client.get("/api/stats/")
    assert r.status_code in (401, 403)


# ── Tasks ─────────────────────────────────────────────────────────────────────
def test_create_task(auth_client):
    client, token = auth_client
    r = client.post("/api/tasks/",
                    json={"title": "Study DSA", "priority": "high"},
                    headers=H(token))
    assert r.status_code == 201
    assert "id" in r.json()

def test_get_tasks(auth_client):
    client, token = auth_client
    client.post("/api/tasks/", json={"title": "Test task"}, headers=H(token))
    r = client.get("/api/tasks/", headers=H(token))
    assert r.status_code == 200
    assert len(r.json()["tasks"]) >= 1

def test_update_task_done(auth_client):
    client, token = auth_client
    task_id = client.post("/api/tasks/", json={"title": "Finish Docker"},
                          headers=H(token)).json()["id"]
    r = client.patch(f"/api/tasks/{task_id}", json={"status": "done"}, headers=H(token))
    assert r.status_code == 200

def test_delete_task(auth_client):
    client, token = auth_client
    task_id = client.post("/api/tasks/", json={"title": "Delete me"},
                          headers=H(token)).json()["id"]
    r = client.delete(f"/api/tasks/{task_id}", headers=H(token))
    assert r.status_code == 200

def test_task_missing_title(auth_client):
    client, token = auth_client
    r = client.post("/api/tasks/", json={"description": "no title"}, headers=H(token))
    assert r.status_code == 422


# ── Goals (new) ───────────────────────────────────────────────────────────────
def test_create_goal(auth_client):
    client, token = auth_client
    r = client.post("/api/goals/",
                    json={"label": "Placement Prep", "priority": "urgent",
                          "target": "ML/AI role", "deadline": "Dec 2026"},
                    headers=H(token))
    assert r.status_code == 201
    assert r.json()["label"] == "Placement Prep"
    assert r.json()["source"] == "api"

def test_list_goals_empty(auth_client):
    client, token = auth_client
    r = client.get("/api/goals/", headers=H(token))
    assert r.status_code == 200
    assert r.json()["goals"] == []

def test_list_goals_after_create(auth_client):
    client, token = auth_client
    client.post("/api/goals/", json={"label": "Learn Guitar", "priority": "low"},
                headers=H(token))
    r = client.get("/api/goals/", headers=H(token))
    assert r.status_code == 200
    assert len(r.json()["goals"]) == 1

def test_update_goal(auth_client):
    client, token = auth_client
    goal_id = client.post("/api/goals/",
                          json={"label": "Lose Weight", "priority": "medium"},
                          headers=H(token)).json()["id"]
    r = client.patch(f"/api/goals/{goal_id}",
                     json={"priority": "high", "status": "active"},
                     headers=H(token))
    assert r.status_code == 200

def test_archive_goal(auth_client):
    client, token = auth_client
    goal_id = client.post("/api/goals/",
                          json={"label": "Old goal", "priority": "low"},
                          headers=H(token)).json()["id"]
    r = client.delete(f"/api/goals/{goal_id}", headers=H(token))
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

def test_invalid_priority(auth_client):
    client, token = auth_client
    r = client.post("/api/goals/",
                    json={"label": "Bad goal", "priority": "extreme"},
                    headers=H(token))
    assert r.status_code == 400


# ── KG endpoints (new) ───────────────────────────────────────────────────────
def test_kg_nodes_empty(auth_client):
    client, token = auth_client
    r = client.get("/api/kg/nodes", headers=H(token))
    assert r.status_code == 200
    assert "nodes" in r.json()

def test_kg_edges_empty(auth_client):
    client, token = auth_client
    r = client.get("/api/kg/edges", headers=H(token))
    assert r.status_code == 200
    assert "edges" in r.json()

def test_kg_obsidian_export(auth_client):
    client, token = auth_client
    # Add a goal first so export has content
    client.post("/api/goals/", json={"label": "Test KG Goal", "priority": "high"},
                headers=H(token))
    r = client.get("/api/kg/export/obsidian", headers=H(token))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "aurora_kg" in r.headers.get("content-disposition", "")


# ── Stats ─────────────────────────────────────────────────────────────────────
def test_stats_endpoint(auth_client):
    client, token = auth_client
    r = client.get("/api/stats/", headers=H(token))
    assert r.status_code == 200
    data = r.json()
    assert "tasks"           in data
    assert "llm"             in data
    assert "knowledge_graph" in data   # new field
    assert "strategies"      in data["llm"]   # new field


# ── Reminders ─────────────────────────────────────────────────────────────────
def test_create_reminder(auth_client):
    client, token = auth_client
    r = client.post("/api/reminders/",
                    json={"title": "Morning DSA", "remind_at": "2025-12-01T07:00:00"},
                    headers=H(token))
    assert r.status_code == 201


# ── Documents (Hybrid GraphRAG) ───────────────────────────────────────────────
def test_list_documents_empty(auth_client):
    client, token = auth_client
    r = client.get("/api/documents/", headers=H(token))
    assert r.status_code == 200
    assert r.json()["documents"] == []

def test_upload_document_text(auth_client):
    client, token = auth_client
    content = b"# Dynamic Programming\nDynamic programming solves subproblems and caches them."
    files = {"file": ("dsa_notes.txt", content, "text/plain")}
    r = client.post("/api/documents/upload", files=files, headers=H(token))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert "document" in data
    assert data["document"]["filename"] == "dsa_notes.txt"

def test_get_document_details(auth_client):
    client, token = auth_client
    content = b"Binary Search is an O(log N) algorithm."
    files = {"file": ("binary_search.txt", content, "text/plain")}
    upload_res = client.post("/api/documents/upload", files=files, headers=H(token))
    doc_id = upload_res.json()["document"]["id"]

    r = client.get(f"/api/documents/{doc_id}", headers=H(token))
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == doc_id
    assert len(data["topics"]) >= 1

def test_delete_document(auth_client):
    client, token = auth_client
    content = b"Graph BFS and DFS traversals."
    files = {"file": ("graphs.txt", content, "text/plain")}
    upload_res = client.post("/api/documents/upload", files=files, headers=H(token))
    doc_id = upload_res.json()["document"]["id"]

    del_res = client.delete(f"/api/documents/{doc_id}", headers=H(token))
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Confirm 404 after deletion
    r = client.get(f"/api/documents/{doc_id}", headers=H(token))
    assert r.status_code == 404

def test_upload_invalid_file_type(auth_client):
    client, token = auth_client
    files = {"file": ("script.py", b"print('hello')", "text/x-python")}
    r = client.post("/api/documents/upload", files=files, headers=H(token))
    assert r.status_code == 400


def test_get_llm_status(auth_client):
    client, token = auth_client
    r = client.get("/api/llm/", headers=H(token))
    assert r.status_code == 200
    data = r.json()
    assert "current" in data
    assert len(data["options"]) >= 1
    assert all(opt["configured"] is True for opt in data["options"])


def test_switch_llm_provider(auth_client):
    client, token = auth_client
    r = client.post(
        "/api/llm/switch",
        json={"provider": "gemini", "model": "gemini-3.1-flash-lite"},
        headers=H(token)
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["current"]["provider"] == "gemini"
