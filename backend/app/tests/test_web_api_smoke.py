from __future__ import annotations

import json


def test_health_and_scene_import_smoke(monkeypatch, tmp_path):
    db_path = tmp_path / "web_api_smoke.sqlite3"
    monkeypatch.setenv("GRAPHWORLD_DATABASE_URL", f"sqlite:///{db_path}")

    from backend.app.core.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from backend.app.core.security import hash_password
    from backend.app.db.models import Base, User
    from backend.app.db.session import SessionLocal, engine
    from backend.app.main import app

    Base.metadata.create_all(bind=engine)

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    with SessionLocal() as db:
        db.add(User(id="admin", username="admin", display_name="Admin", role="admin", password_hash=hash_password("admin123"), is_active=True))
        db.commit()
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    with open("backend/data/sg_output/simple_graph/simple_home_1f.json", encoding="utf-8") as file:
        source_json = json.load(file)

    imported = client.post("/api/scenes/import", json={"source_json": source_json, "description": "smoke"})
    assert imported.status_code == 201
    scene_version_id = imported.json()["id"]
    assert imported.json()["graph_summary"]["node_count"] == 75
    assert imported.json()["graph_summary"]["edge_count"] == 92
    assert imported.json()["graph_summary"]["floor_count"] == 1
    assert imported.json()["graph_summary"]["room_count"] == 7

    scenes = client.get("/api/scenes")
    assert scenes.status_code == 200
    assert scenes.json()[0]["id"] == "simple_home_1f"

    graph = client.get(f"/api/scene-versions/{scene_version_id}/graph")
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) == 75
    assert len(graph.json()["edges"]) == 92
    assert len(graph.json()["source_json"]["layout"]["rooms"]) == 7

    validated = client.post(
        f"/api/scene-versions/{scene_version_id}/layout/validate",
        json={"source_json": graph.json()["source_json"]},
    )
    assert validated.status_code == 200
    assert validated.json() == {"valid": True, "issues": []}

    published = client.post(
        f"/api/scene-versions/{scene_version_id}/layout/publish",
        json={"source_json": graph.json()["source_json"], "description": "editor smoke"},
    )
    assert published.status_code == 201
    assert published.json()["version"] == 2

    human_run = client.post(
        "/api/runs",
        json={
            "scene_version_id": scene_version_id,
            "control_mode": "human",
            "visibility_mode": "fog_of_war",
            "max_steps": 3,
        },
    )
    assert human_run.status_code == 201
    human_state = human_run.json()
    assert human_state["run"]["status"] == "waiting_for_human"
    assert human_state["observation"]["visible_nodes"]
    assert human_state["candidate_actions"]

    run_id = human_state["run"]["id"]
    action_id = human_state["candidate_actions"][0]["action_id"]
    stepped = client.post(f"/api/runs/{run_id}/actions", json={"action_id": action_id})
    assert stepped.status_code == 200
    assert stepped.json()["run"]["current_step"] == 1
    assert stepped.json()["latest_action_result"]["ok"] is True

    steps = client.get(f"/api/runs/{run_id}/steps")
    assert steps.status_code == 200
    assert len(steps.json()) == 1
    replay = client.get(f"/api/runs/{run_id}/replay")
    assert replay.status_code == 200
    assert replay.json()["steps"][0]["step_index"] == 0
    metrics = client.get(f"/api/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["metrics"]

    agent_run = client.post(
        "/api/runs",
        json={
            "scene_version_id": scene_version_id,
            "control_mode": "agent",
            "visibility_mode": "room",
            "max_steps": 1,
        },
    )
    assert agent_run.status_code == 201
    agent_run_id = agent_run.json()["run"]["id"]
    advanced = client.post(f"/api/runs/{agent_run_id}/advance")
    assert advanced.status_code == 200
    assert advanced.json()["run"]["status"] == "completed"
    assert advanced.json()["run"]["current_step"] == 1
