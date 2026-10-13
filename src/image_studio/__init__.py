"""Single-origin studio: project and asset API and a built React application."""

import os
from pathlib import Path

import psycopg
from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from image_studio.api import api
from image_studio.database import database_engine
from image_studio.files import REQUEST_LIMIT
from image_studio.generation_api import generation_api as generation_blueprint
from image_studio.image_client import ImageClient
from image_studio.portability import portability_api


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        DATABASE_URL=os.environ.get("DATABASE_URL", ""),
        STUDIO_FILES=Path(os.environ.get("STUDIO_FILES", "data/files")).resolve(),
        MAX_CONTENT_LENGTH=REQUEST_LIMIT,
        MAX_FORM_MEMORY_SIZE=REQUEST_LIMIT,
        FRONTEND_DIST=Path(os.environ.get("FRONTEND_DIST", "frontend/dist")).resolve(),
    )

    app.extensions["database"] = (
        database_engine(app.config["DATABASE_URL"])
        if app.config["DATABASE_URL"]
        else None
    )
    app.extensions["image_client"] = ImageClient(
        os.environ.get("IMAGE_API_BASE_URL", ""), os.environ.get("IMAGE_API_KEY", "")
    )
    app.register_blueprint(api)
    app.register_blueprint(portability_api)
    app.register_blueprint(generation_blueprint)

    @app.before_request
    def enforce_request_limit():
        if request.content_length and request.content_length > REQUEST_LIMIT:
            raise RequestEntityTooLarge("Maximum request size is 90 MB")

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        app.logger.error("Database operation failed")
        return jsonify(error="Database temporarily unavailable"), 503

    @app.errorhandler(500)
    def internal_error(error):
        if request.path == "/api" or request.path.startswith("/api/"):
            return jsonify(error="Internal server error"), 500
        return error

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
            message = error.description
            if error.code == 413 and message == error.__class__().description:
                message = "Maximum request size is 90 MB"
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
