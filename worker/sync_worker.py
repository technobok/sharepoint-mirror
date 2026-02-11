"""Background sync worker — runs SharePoint sync on a periodic schedule."""

import logging
import signal
import time
from datetime import UTC, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sharepoint_mirror.worker")

_running = True


def _handle_signal(signum: int, frame: object) -> None:
    global _running
    log.info("Received signal %s, shutting down...", signum)
    _running = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def _recover_stuck_runs() -> None:
    """Mark any running sync_run records as failed (from a previous crash)."""
    from sharepoint_mirror.db import get_db, transaction

    cursor = get_db().cursor()
    cursor.execute("SELECT COUNT(*) FROM sync_run WHERE status = 'running'")
    row = cursor.fetchone()
    stuck = int(row[0]) if row else 0
    if stuck:
        with transaction() as cur:
            cur.execute(
                "UPDATE sync_run SET status = 'failed', "
                "completed_at = ?, error_message = 'Interrupted (recovered on worker startup)' "
                "WHERE status = 'running'",
                (datetime.now(UTC).isoformat(),),
            )
        log.info("Recovered %d stuck sync run(s)", stuck)


def run() -> None:
    """Main worker loop."""
    from sharepoint_mirror import create_app

    app = create_app()

    interval: int = app.config["SYNC_INTERVAL"]

    # Clean up any sync runs left running by a previous crash/kill
    with app.app_context():
        _recover_stuck_runs()

    log.info("Sync worker started (interval=%ds)", interval)

    while _running:
        with app.app_context():
            try:
                from sharepoint_mirror.models import SyncRun
                from sharepoint_mirror.services.sync import SyncService

                if SyncRun.is_sync_in_progress():
                    log.info("Sync already in progress, skipping")
                else:
                    log.info("Starting sync")
                    service = SyncService()
                    run_result = service.run_sync()
                    log.info(
                        "Sync completed: added=%d, modified=%d, removed=%d",
                        run_result.files_added,
                        run_result.files_modified,
                        run_result.files_removed,
                    )
            except Exception:
                log.exception("Error in sync worker loop")

        # Sleep in small increments so we can respond to signals
        for _ in range(interval * 10):
            if not _running:
                break
            time.sleep(0.1)

    log.info("Sync worker stopped.")


if __name__ == "__main__":
    run()
