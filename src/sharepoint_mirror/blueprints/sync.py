"""Sync management blueprint."""

from flask import Blueprint, redirect, render_template, request, url_for

from sharepoint_mirror.models import SyncEvent, SyncRun
from sharepoint_mirror.services import SyncService

bp = Blueprint("sync", __name__, url_prefix="/sync")


@bp.route("/")
def index():
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
def view(run_id: int):
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
def trigger():
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
            return redirect(url_for("sync.index"))

        # Start sync (this blocks until complete)
        # In production, you'd want to run this in a background task
        run = service.run_sync(full_sync=full_sync)

        if request.headers.get("HX-Request"):
            return render_template(
                "sync/_status.html",
                run=run,
                success=True,
            )

    except Exception as e:
        if request.headers.get("HX-Request"):
            return render_template(
                "sync/_status.html",
                error=str(e),
            )

    return redirect(url_for("sync.index"))


@bp.route("/status")
def status():
    """Get current sync status (HTMX endpoint)."""
    service = SyncService()
    status = service.get_status()

    return render_template(
        "sync/_status.html",
        status=status,
    )
