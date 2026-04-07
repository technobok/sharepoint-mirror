"""Sync management blueprint."""

import logging
import threading

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from sharepoint_mirror.blueprints.auth import login_required
from sharepoint_mirror.models import Document, SyncEvent, SyncRun
from sharepoint_mirror.services import SyncService

logger = logging.getLogger(__name__)

bp = Blueprint("sync", __name__, url_prefix="/sync")


@bp.route("/")
@login_required
def index() -> str:
    """Show sync history."""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    runs = SyncRun.get_recent(limit=per_page, offset=(page - 1) * per_page)
    total = SyncRun.count_all()

    # Check if sync is in progress
    current_run = SyncRun.get_running()

    # Check if HTMX request
    if request.headers.get("HX-Request"):
        return render_template(
            "sync/_history.html",
            runs=runs,
            current_run=current_run,
            page=page,
            per_page=per_page,
            total=total,
        )

    return render_template(
        "sync/index.html",
        runs=runs,
        current_run=current_run,
        page=page,
        per_page=per_page,
        total=total,
    )


@bp.route("/<int:run_id>")
@login_required
def view(run_id: int) -> str | Response:
    """View sync run details."""
    run = SyncRun.get_by_id(run_id)
    if not run:
        return redirect(url_for("sync.index"))

    events = SyncEvent.get_by_sync_run(run_id)

    return render_template(
        "sync/view.html",
        run=run,
        events=events,
    )


@bp.route("/trigger", methods=["POST"])
@login_required
def trigger() -> str | Response:
    """Trigger a new sync."""
    full_sync = request.form.get("full", "0") == "1"

    try:
        service = SyncService()

        # Check if already running
        if SyncRun.is_sync_in_progress():
            if request.headers.get("HX-Request"):
                return render_template(
                    "sync/_status.html",
                    error="A sync is already in progress",
                )
            flash("A sync is already in progress.", "warning")
            return redirect(url_for("sync.index"))

        # Start sync (this blocks until complete)
        # In production, you'd want to run this in a background task
        logger.info("Sync triggered via web UI (full=%s)", full_sync)
        run = service.run_sync(full_sync=full_sync)

        if request.headers.get("HX-Request"):
            return render_template(
                "sync/_status.html",
                run=run,
                success=True,
            )

        flash(
            f"Sync completed: +{run.files_added} added, ~{run.files_modified} modified, "
            f"-{run.files_removed} removed.",
            "success",
        )

    except Exception as e:
        logger.exception("Sync trigger failed")
        if request.headers.get("HX-Request"):
            return render_template(
                "sync/_status.html",
                error=str(e),
            )
        flash(f"Sync failed: {e}", "error")

    return redirect(url_for("sync.index"))


def _get_running_metadata_refresh() -> SyncRun | None:
    """Get the currently running metadata refresh SyncRun, if any."""
    run = SyncRun.get_running()
    if run and run.sync_type == "metadata":
        return run
    return None


@bp.route("/refresh-metadata", methods=["POST"])
@login_required
def refresh_metadata() -> str | Response:
    """Start a background metadata refresh for all synced documents."""
    existing = _get_running_metadata_refresh()
    if existing:
        if request.headers.get("HX-Request"):
            return render_template("sync/_refresh_metadata.html", run=existing)
        flash("Metadata refresh is already running.", "warning")
        return redirect(url_for("sync.index"))

    docs = Document.get_all(include_deleted=False)
    if not docs:
        if request.headers.get("HX-Request"):
            return render_template("sync/_refresh_metadata.html", error="No documents to process.")
        flash("No documents to process.", "warning")
        return redirect(url_for("sync.index"))

    app = current_app._get_current_object()

    def run_refresh() -> None:
        with app.app_context():
            service = SyncService()
            service.run_metadata_refresh()

    logger.info("Metadata refresh triggered via web UI (%d documents)", len(docs))
    threading.Thread(target=run_refresh, daemon=True).start()

    import time

    time.sleep(0.2)  # Brief pause to let the SyncRun record be created

    if request.headers.get("HX-Request"):
        run = _get_running_metadata_refresh()
        return render_template("sync/_refresh_metadata.html", run=run)

    flash(f"Metadata refresh started for {len(docs)} document(s).", "info")
    return redirect(url_for("sync.index"))


@bp.route("/refresh-metadata/status")
@login_required
def refresh_metadata_status() -> str:
    """Poll metadata refresh progress (HTMX endpoint)."""
    run = _get_running_metadata_refresh()
    if run:
        return render_template("sync/_refresh_metadata.html", run=run)

    # Check the most recent completed metadata run
    latest = SyncRun.get_latest()
    if latest and latest.sync_type == "metadata":
        return render_template("sync/_refresh_metadata.html", run=latest)

    return render_template("sync/_refresh_metadata.html")


@bp.route("/status")
@login_required
def status() -> str:
    """Get current sync status (HTMX endpoint)."""
    service = SyncService()
    status = service.get_status()

    return render_template(
        "sync/_status.html",
        status=status,
    )
