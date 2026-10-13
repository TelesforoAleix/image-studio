"""Single-origin studio skeleton: a JSON API and a built React application."""

import os
from pathlib import Path

import psycopg
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        DATABASE_URL=os.environ.get("DATABASE_URL", ""),
        FRONTEND_DIST=Path(os.environ.get("FRONTEND_DIST", "frontend/dist")).resolve(),
    )

    @app.get("/api/health")
    def health():
        database_url = app.config["DATABASE_URL"]
        if not database_url:
            return jsonify(postgres="unavailable"), 503
        try:
            with psycopg.connect(database_url, connect_timeout=3) as connection:
                connection.execute("SELECT 1")
        except psycopg.Error:
            return jsonify(postgres="unavailable"), 503
        return jsonify(postgres="ok")

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path == "/api" or request.path.startswith("/api/"):
            message = "Unknown API route" if error.code == 404 else error.name
            return jsonify(error=message), error.code
        return error

    api_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

    @app.route(
        "/api",
        strict_slashes=False,
        defaults={"path": ""},
        methods=api_methods,
        provide_automatic_options=False,
    )
    @app.route("/api/<path:path>", methods=api_methods, provide_automatic_options=False)
    def unknown_api(path):
        return jsonify(error="Unknown API route"), 404

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path):
        root = app.config["FRONTEND_DIST"]
        if path and (root / path).is_file():
            return send_from_directory(root, path)
        return send_from_directory(root, "index.html")

    return app
