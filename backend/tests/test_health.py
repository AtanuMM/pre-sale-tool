from unittest.mock import patch

from fastapi.testclient import TestClient

from app.health_checks import DependencyStatus
from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_all_ok() -> None:
    ready = DependencyStatus(database="ok", object_storage="ok")
    with patch("app.main.run_dependency_checks", return_value=ready):
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] == "ok"
    assert response.json()["checks"]["object_storage"] == "ok"


def test_health_ready_returns_503_when_database_down() -> None:
    not_ready = DependencyStatus(
        database="error: connection refused",
        object_storage="ok",
    )
    with patch("app.main.run_dependency_checks", return_value=not_ready):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
