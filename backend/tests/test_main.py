from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app import main
from app.graph import workflow


def test_app_starts_workflow_and_serves_graph_definition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
  monkeypatch.setattr(
      workflow,
      "settings",
      SimpleNamespace(checkpoint_db_path=lambda: tmp_path / "checkpoints.sqlite"),
  )

  with TestClient(main.app) as client:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    health_data = health_response.json()
    assert health_data["status"] == "ok"
    if "graph_ready" in health_data:
      assert health_data["graph_ready"] is True

    response = client.get("/graph/definition")

  assert response.status_code == 200
  assert response.json()["mermaid"]