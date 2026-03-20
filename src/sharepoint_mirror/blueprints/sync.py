"""Sync management blueprint."""

import logging
import threading
from dataclasses import dataclass, field

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from sharepoint_mirror.blueprints.auth import login_required
from sharepoint_mirror.models import Document, SyncEvent, SyncRun
from sharepoint_mirror.services import SyncService

logger = logging.getLogger(__name__)

bp = Blueprint("sync", __name__, url_prefix="/sync")


@dataclass
class MetadataRefreshState:
    """Tracks progress of a background metadata refresh."""

    running: bool = False
    total: int = 0
    processed: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    done: bool = False

    def reset(self, total: int) -> None:
        self.running = True
        self.total = total
        self.processed = 0
        self.errors = 0
        self.error_messages = []
        self.done = False


_refresh_state = MetadataRefreshState()


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


@bp.route("/refresh-metadata", methods=["POST"])
@login_required
def refresh_metadata() -> str | Response:
    """Start a background metadata refresh for all synced documents."""
    if _refresh_state.running:
        if request.headers.get("HX-Request"):
            return render_template("sync/_refresh_metadata.html", state=_refresh_state)
        flash("Metadata refresh is already running.", "warning")
        return redirect(url_for("sync.index"))

    docs = Document.get_all(include_deleted=False)
    if not docs:
        if request.headers.get("HX-Request"):
            return render_template("sync/_refresh_metadata.html", error="No documents to process.")
        flash("No documents to process.", "warning")
        return redirect(url_for("sync.index"))

    # Capture document info before spawning thread (avoid passing ORM objects)
    doc_refs = [(doc.id, doc.sharepoint_drive_id, doc.sharepoint_item_id, doc.name) for doc in docs]
    _refresh_state.reset(len(doc_refs))

    app = current_app._get_current_object()

    def run_refresh() -> None:
        with app.app_context():
            sync_run = SyncRun.create(sync_type="metadata")
            try:
                service = SyncService()
                for doc_id, drive_id, item_id, name in doc_refs:
                    try:
                        service._sync_metadata(doc_id, drive_id, item_id)
                    except Exception as e:
                        _refresh_state.errors += 1
                        _refresh_state.error_messages.append(f"{name}: {e}")
                        logger.warning("Metadata refresh failed for %s: %s", name, e)
                    _refresh_state.processed += 1
                sync_run.complete(
                    files_modified=_refresh_state.processed - _refresh_state.errors,
                    files_skipped=_refresh_state.errors,
                )
            except Exception as e:
                logger.exception("Metadata refresh failed")
                _refresh_state.error_messages.append(str(e))
                sync_run.fail(str(e))
            finally:
                _refresh_state.running = False
                _refresh_state.done = True

    logger.info("Metadata refresh triggered via web UI (%d documents)", len(doc_refs))
    threading.Thread(target=run_refresh, daemon=True).start()

    if request.headers.get("HX-Request"):
        return render_template("sync/_refresh_metadata.html", state=_refresh_state)

    flash(f"Metadata refresh started for {len(doc_refs)} document(s).", "info")
    return redirect(url_for("sync.index"))


@bp.route("/refresh-metadata/status")
@login_required
def refresh_metadata_status() -> str:
    """Poll metadata refresh progress (HTMX endpoint)."""
    return render_template("sync/_refresh_metadata.html", state=_refresh_state)


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
