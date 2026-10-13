from unittest.mock import MagicMock

import psycopg
import pytest

from image_studio import create_app


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    application = create_app()
    application.config["TESTING"] = True
    return application


def test_health_without_database(app):
    response = app.test_client().get("/api/health")
    assert response.status_code == 503
    assert response.json == {"postgres": "unavailable"}


def test_health_database_failure(app, monkeypatch):
    app.config["DATABASE_URL"] = "postgresql://synthetic.invalid/studio"

    def fail(*args, **kwargs):
        raise psycopg.OperationalError("synthetic database failure")

    monkeypatch.setattr("image_studio.psycopg.connect", fail)
    response = app.test_client().get("/api/health")
    assert response.status_code == 503
    assert response.json == {"postgres": "unavailable"}


def test_health_database_reachable(app, monkeypatch):
    app.config["DATABASE_URL"] = "postgresql://synthetic.invalid/studio"
    connect = MagicMock()
    monkeypatch.setattr("image_studio.psycopg.connect", connect)
    response = app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.json == {"postgres": "ok"}
    connect.assert_called_once_with(app.config["DATABASE_URL"], connect_timeout=3)
    connect.return_value.__enter__.return_value.execute.assert_called_once_with(
        "SELECT 1"
    )
    connect.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "path", ["/api", "/api/", "/api/unknown", "/api/nested/unknown"]
)
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_unknown_api_is_json(app, path, method):
    response = app.test_client().open(path, method=method)
    assert response.status_code == 404
    assert response.json == {"error": "Unknown API route"}


def test_built_page_and_files(app, tmp_path):
    page = "<!doctype html><title>image studio</title><div>No assets yet</div>"
    (tmp_path / "index.html").write_text(page)
    (tmp_path / "app.js").write_text("// synthetic build")
    app.config["FRONTEND_DIST"] = tmp_path
    client = app.test_client()
    for path in ["/", "/projects/future"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == page
    assert client.get("/app.js").text == "// synthetic build"
    assert client.get("/api/unknown").status_code == 404


def test_frontend_setting_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    assert create_app().config["FRONTEND_DIST"] == tmp_path
