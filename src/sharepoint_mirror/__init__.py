"""SharePoint Mirror - Mirror SharePoint documents locally for vector database ingestion."""

import configparser
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from sharepoint_mirror.db import close_db, init_db_command, migrate_db_command


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Application factory for SharePoint Mirror."""
    # Project root: use SHAREPOINT_MIRROR_ROOT env var, or CWD, or relative to __file__
    if "SHAREPOINT_MIRROR_ROOT" in os.environ:
        project_root = Path(os.environ["SHAREPOINT_MIRROR_ROOT"])
    else:
        # Check if running from source (src/sharepoint_mirror/__init__.py exists relative to __file__)
        source_root = Path(__file__).parent.parent.parent
        if (source_root / "src" / "sharepoint_mirror" / "__init__.py").exists():
            project_root = source_root
        else:
            # Installed as package, use current working directory
            project_root = Path.cwd()
    instance_path = project_root / "instance"

    app = Flask(
        __name__,
        instance_path=str(instance_path),
        instance_relative_config=True,
    )

    # Default configuration
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE_PATH=str(instance_path / "sharepoint_mirror.sqlite3"),
        BLOBS_DIRECTORY=str(instance_path / "blobs"),
        HOST="0.0.0.0",
        PORT=5001,
        DEV_HOST="127.0.0.1",
        DEV_PORT=5001,
        # SharePoint defaults
        SHAREPOINT_TENANT_ID="",
        SHAREPOINT_CLIENT_ID="",
        SHAREPOINT_CLIENT_SECRET="",
        SHAREPOINT_SITE_HOSTNAME="",
        SHAREPOINT_SITE_PATH="",
        SHAREPOINT_LIBRARY_NAME="",
        # Sync defaults
        SYNC_INTERVAL=300,
        SYNC_DOWNLOAD_TIMEOUT=300,
        SYNC_MAX_FILE_SIZE_MB=100,
        SYNC_INCLUDE_EXTENSIONS="",
        SYNC_EXCLUDE_EXTENSIONS="",
        SYNC_INCLUDE_PATHS="",
        SYNC_PATH_PATTERNS="",
        SYNC_METADATA_ONLY=False,
        SYNC_VERIFY_QUICKXOR_HASH=False,
    )

    if test_config is None:
        # Load config.ini if it exists
        config_path = instance_path / "config.ini"
        if not config_path.exists():
            config_path = project_root / "config.ini"

        if config_path.exists():
            config = configparser.ConfigParser()
            config.read(config_path)

            if config.has_section("server"):
                if config.has_option("server", "SECRET_KEY"):
                    app.config["SECRET_KEY"] = config.get("server", "SECRET_KEY")
                if config.has_option("server", "DEBUG"):
                    app.config["DEBUG"] = config.getboolean("server", "DEBUG")
                if config.has_option("server", "HOST"):
                    app.config["HOST"] = config.get("server", "HOST")
                if config.has_option("server", "PORT"):
                    app.config["PORT"] = config.getint("server", "PORT")
                if config.has_option("server", "DEV_HOST"):
                    app.config["DEV_HOST"] = config.get("server", "DEV_HOST")
                if config.has_option("server", "DEV_PORT"):
                    app.config["DEV_PORT"] = config.getint("server", "DEV_PORT")

            if config.has_section("database"):
                if config.has_option("database", "PATH"):
                    db_path = config.get("database", "PATH")
                    if not os.path.isabs(db_path):
                        db_path = str(project_root / db_path)
                    app.config["DATABASE_PATH"] = db_path

            if config.has_section("blobs"):
                if config.has_option("blobs", "DIRECTORY"):
                    blobs_dir = config.get("blobs", "DIRECTORY")
                    if not os.path.isabs(blobs_dir):
                        blobs_dir = str(project_root / blobs_dir)
                    app.config["BLOBS_DIRECTORY"] = blobs_dir

            if config.has_section("sharepoint"):
                app.config["SHAREPOINT_TENANT_ID"] = config.get(
                    "sharepoint", "TENANT_ID", fallback=""
                )
                app.config["SHAREPOINT_CLIENT_ID"] = config.get(
                    "sharepoint", "CLIENT_ID", fallback=""
                )
                app.config["SHAREPOINT_CLIENT_SECRET"] = config.get(
                    "sharepoint", "CLIENT_SECRET", fallback=""
                )
                app.config["SHAREPOINT_SITE_HOSTNAME"] = config.get(
                    "sharepoint", "SITE_HOSTNAME", fallback=""
                )
                app.config["SHAREPOINT_SITE_PATH"] = config.get(
                    "sharepoint", "SITE_PATH", fallback=""
                )
                app.config["SHAREPOINT_LIBRARY_NAME"] = config.get(
                    "sharepoint", "LIBRARY_NAME", fallback=""
                )

            if config.has_section("sync"):
                app.config["SYNC_INTERVAL"] = config.getint("sync", "INTERVAL", fallback=300)
                app.config["SYNC_DOWNLOAD_TIMEOUT"] = config.getint(
                    "sync", "DOWNLOAD_TIMEOUT", fallback=300
                )
                app.config["SYNC_MAX_FILE_SIZE_MB"] = config.getint(
                    "sync", "MAX_FILE_SIZE_MB", fallback=100
                )
                app.config["SYNC_INCLUDE_EXTENSIONS"] = config.get(
                    "sync", "INCLUDE_EXTENSIONS", fallback=""
                )
                app.config["SYNC_EXCLUDE_EXTENSIONS"] = config.get(
                    "sync", "EXCLUDE_EXTENSIONS", fallback=""
                )
                app.config["SYNC_INCLUDE_PATHS"] = config.get("sync", "INCLUDE_PATHS", fallback="")
                app.config["SYNC_PATH_PATTERNS"] = config.get("sync", "PATH_PATTERNS", fallback="")
                app.config["SYNC_METADATA_ONLY"] = config.getboolean(
                    "sync", "METADATA_ONLY", fallback=False
                )
                app.config["SYNC_VERIFY_QUICKXOR_HASH"] = config.getboolean(
                    "sync", "VERIFY_QUICKXOR_HASH", fallback=False
                )

            if config.has_section("gatekeeper"):
                app.config["GATEKEEPER_DB_PATH"] = config.get("gatekeeper", "DB_PATH", fallback="")
                app.config["GATEKEEPER_URL"] = config.get("gatekeeper", "URL", fallback="")
                app.config["GATEKEEPER_API_KEY"] = config.get("gatekeeper", "API_KEY", fallback="")

            if config.has_section("proxy"):
                app.config["PROXY_X_FOR"] = config.getint("proxy", "X_FORWARDED_FOR", fallback=1)
                app.config["PROXY_X_PROTO"] = config.getint(
                    "proxy", "X_FORWARDED_PROTO", fallback=1
                )
                app.config["PROXY_X_HOST"] = config.getint("proxy", "X_FORWARDED_HOST", fallback=1)
                app.config["PROXY_X_PREFIX"] = config.getint(
                    "proxy", "X_FORWARDED_PREFIX", fallback=1
                )

    else:
        app.config.from_mapping(test_config)

    # Always apply ProxyFix - harmless without forwarding headers, required when
    # behind Caddy/nginx for correct URL generation (especially X-Forwarded-Prefix).
    if test_config is None:
        app.wsgi_app = ProxyFix(  # type: ignore[assignment]
            app.wsgi_app,
            x_for=app.config.get("PROXY_X_FOR", 1),
            x_proto=app.config.get("PROXY_X_PROTO", 1),
            x_host=app.config.get("PROXY_X_HOST", 1),
            x_prefix=app.config.get("PROXY_X_PREFIX", 1),
        )

    # Validate configuration
    if app.config["SYNC_METADATA_ONLY"] and app.config["SYNC_VERIFY_QUICKXOR_HASH"]:
        raise ValueError(
            "Configuration error: METADATA_ONLY and VERIFY_QUICKXOR_HASH cannot both be enabled."
        )

    # Configure logging for the web app
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )

    # Ensure directories exist
    instance_path.mkdir(parents=True, exist_ok=True)
    Path(app.config["BLOBS_DIRECTORY"]).mkdir(parents=True, exist_ok=True)

    # Register database teardown and CLI command
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(migrate_db_command)

    # Timezone helper
    def get_user_timezone() -> ZoneInfo:
        """Get user timezone from X-Timezone header or tz cookie, default UTC."""
        tz_name = request.headers.get("X-Timezone") or request.cookies.get("tz")
        if tz_name:
            try:
                return ZoneInfo(tz_name)
            except (KeyError, ValueError):
                pass
        return ZoneInfo("UTC")

    # Jinja filters for date formatting
    @app.template_filter("localdate")
    def localdate_filter(iso_string: str | None) -> str:
        """Format ISO date string (date only) in browser timezone."""
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(get_user_timezone()).strftime("%Y-%m-%d")
        except Exception:
            return iso_string[:10] if iso_string else ""

    @app.template_filter("localdatetime")
    def localdatetime_filter(iso_string: str | None) -> str:
        """Format ISO datetime string (with time) in browser timezone."""
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(get_user_timezone()).strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            return iso_string[:16].replace("T", " ") if iso_string else ""

    @app.template_filter("filesize")
    def filesize_filter(size: int | None) -> str:
        """Format file size in human-readable format."""
        if size is None:
            return ""
        fsize = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if fsize < 1024:
                return f"{fsize:.1f} {unit}" if unit != "B" else f"{int(fsize)} {unit}"
            fsize /= 1024
        return f"{fsize:.1f} PB"

    # Register CLI commands
    from sharepoint_mirror.cli import register_cli_commands

    register_cli_commands(app)

    # Register blueprints
    from sharepoint_mirror.blueprints import auth, documents, sync, viewer

    app.register_blueprint(auth.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(sync.bp)
    app.register_blueprint(viewer.bp)

    # Initialize Gatekeeper client (if configured)
    gk_db_path = app.config.get("GATEKEEPER_DB_PATH", "")
    gk_url = app.config.get("GATEKEEPER_URL", "")
    gk_api_key = app.config.get("GATEKEEPER_API_KEY", "")

    if gk_db_path:
        from gatekeeper import GatekeeperClient

        gk = GatekeeperClient(db_path=gk_db_path)
        gk.init_app(app, cookie_name="gk_session")
        app.config["GATEKEEPER_CLIENT"] = gk
    elif gk_url and gk_api_key:
        from gatekeeper import GatekeeperClient

        gk = GatekeeperClient(server_url=gk_url, api_key=gk_api_key)
        gk.init_app(app, cookie_name="gk_session")
        app.config["GATEKEEPER_CLIENT"] = gk

    @app.route("/")
    @auth.login_required
    def index() -> str:
        from sharepoint_mirror.models import Document, SyncRun

        # Get stats for dashboard
        stats = {
            "total_documents": Document.count_all(),
            "total_size": Document.total_size(),
            "last_sync": SyncRun.get_latest(),
            "recent_syncs": SyncRun.get_recent(limit=5),
        }
        return render_template("index.html", stats=stats)

    # Ensure database schema exists (safe to run every startup — uses IF NOT EXISTS)
    with app.app_context():
        from sharepoint_mirror.db import (
            get_db,
            get_expected_schema_version,
            get_schema_version,
        )

        schema_path = project_root / "database" / "schema.sql"
        if schema_path.exists():
            db = get_db()
            with open(schema_path) as f:
                for _ in db.execute(f.read()):
                    pass

        # Check schema version matches expected (from migration files)
        migrations_dir = project_root / "database" / "migrations"
        expected = get_expected_schema_version(migrations_dir)
        current = get_schema_version()
        if expected and current < expected:
            raise RuntimeError(
                f"Database schema is at version {current} but version {expected} is required. "
                f"Back up your database and run: flask --app wsgi migrate-db"
            )

    return app
