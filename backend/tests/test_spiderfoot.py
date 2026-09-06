"""Bridge policy checks do not launch a scan against a third-party target."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_bridge_requires_secret_and_forces_passive(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "deploy/spiderfoot_bridge.py"
    spec = importlib.util.spec_from_file_location("bridge_test", path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    monkeypatch.setenv("WATCH_SPIDERFOOT_TOKEN", "bridge-test-secret")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        kwargs["stdout"].write(b"[]")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    with TestClient(bridge.app) as client:
        body = {"target": "example.com", "asset_id": "test"}
        assert client.post("/scan", json=body).status_code == 401
        client.headers["Authorization"] = "Bearer bridge-test-secret"
        assert (
            client.post("/scan", json={"target": "--evil;id", "asset_id": "test"}).status_code
            == 422
        )
        response = client.post("/scan", json=body)
        assert response.status_code == 200 and response.json()["mode"] == "passive"
    assert commands == [
        [
            "python",
            "sf.py",
            "-s",
            "example.com",
            "-u",
            "passive",
            "-o",
            "json",
            "-q",
            "-max-threads",
            "2",
        ]
    ]
