"""测试 Web API."""

import pytest
from fastapi.testclient import TestClient

from goalflow.api.app import app


client = TestClient(app)


class TestAPI:
    def test_create_session(self):
        response = client.post("/sessions", json={
            "repo_path": "/tmp/test-repo",
            "requirement": "Add a hello world function",
            "auto_mode": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["repo_path"] == "/tmp/test-repo"

    def test_get_session_not_found(self):
        response = client.get("/sessions/non-existent-id")
        assert response.status_code == 404

    def test_list_sessions(self):
        response = client.get("/sessions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_checkpoint_response(self):
        # First create a session
        create_resp = client.post("/sessions", json={
            "repo_path": "/tmp/test-repo",
            "requirement": "Test",
            "auto_mode": True,
        })
        session_id = create_resp.json()["id"]

        # Then respond to checkpoint
        response = client.post(f"/sessions/{session_id}/checkpoint/plan?action=continue")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
