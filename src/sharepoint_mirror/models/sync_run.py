"""Sync run model for tracking sync operations."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sharepoint_mirror.db import get_db, transaction


@dataclass
class SyncRun:
    """Represents a sync operation run."""

    id: int
    status: str
    started_at: str
    completed_at: str | None
    is_full_sync: bool
    files_added: int
    files_modified: int
    files_removed: int
    files_unchanged: int
    files_skipped: int
    bytes_downloaded: int
    error_message: str | None

    @classmethod
    def from_row(cls, row: tuple) -> SyncRun:
        """Create a SyncRun from a database row."""
        return cls(
            id=row[0],
            status=row[1],
            started_at=row[2],
            completed_at=row[3],
            is_full_sync=bool(row[4]),
            files_added=row[5],
            files_modified=row[6],
            files_removed=row[7],
            files_unchanged=row[8],
            files_skipped=row[9],
            bytes_downloaded=row[10],
            error_message=row[11],
        )

    @classmethod
    def get_by_id(cls, run_id: int) -> SyncRun | None:
        """Get a sync run by ID."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, status, started_at, completed_at, is_full_sync,
                   files_added, files_modified, files_removed, files_unchanged,
                   files_skipped, bytes_downloaded, error_message
            FROM sync_run WHERE id = ?
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def create(cls, is_full_sync: bool = False) -> SyncRun:
        """Create a new sync run."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO sync_run (status, started_at, is_full_sync)
                VALUES ('running', ?, ?)
                """,
                (now, 1 if is_full_sync else 0),
            )
            row = cursor.execute("SELECT last_insert_rowid()").fetchone()
            assert row is not None
            run_id = row[0]

        result = cls.get_by_id(run_id)
        assert result is not None
        return result

    def complete(
        self,
        files_added: int = 0,
        files_modified: int = 0,
        files_removed: int = 0,
        files_unchanged: int = 0,
        files_skipped: int = 0,
        bytes_downloaded: int = 0,
    ) -> SyncRun:
        """Mark sync run as completed."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                UPDATE sync_run SET
                    status = 'completed',
                    completed_at = ?,
                    files_added = ?,
                    files_modified = ?,
                    files_removed = ?,
                    files_unchanged = ?,
                    files_skipped = ?,
                    bytes_downloaded = ?
                WHERE id = ?
                """,
                (
                    now,
                    files_added,
                    files_modified,
                    files_removed,
                    files_unchanged,
                    files_skipped,
                    bytes_downloaded,
                    self.id,
                ),
            )

        result = self.get_by_id(self.id)
        assert result is not None
        return result

    def fail(self, error_message: str) -> SyncRun:
        """Mark sync run as failed."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                UPDATE sync_run SET
                    status = 'failed',
                    completed_at = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (now, error_message, self.id),
            )

        result = self.get_by_id(self.id)
        assert result is not None
        return result

    def increment_counts(
        self,
        added: int = 0,
        modified: int = 0,
        removed: int = 0,
        unchanged: int = 0,
        skipped: int = 0,
        bytes_downloaded: int = 0,
    ) -> None:
        """Increment counters during sync."""
        with transaction() as cursor:
            cursor.execute(
                """
                UPDATE sync_run SET
                    files_added = files_added + ?,
                    files_modified = files_modified + ?,
                    files_removed = files_removed + ?,
                    files_unchanged = files_unchanged + ?,
                    files_skipped = files_skipped + ?,
                    bytes_downloaded = bytes_downloaded + ?
                WHERE id = ?
                """,
                (added, modified, removed, unchanged, skipped, bytes_downloaded, self.id),
            )

    @classmethod
    def get_latest(cls) -> SyncRun | None:
        """Get the most recent sync run."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, status, started_at, completed_at, is_full_sync,
                   files_added, files_modified, files_removed, files_unchanged,
                   files_skipped, bytes_downloaded, error_message
            FROM sync_run ORDER BY started_at DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def get_running(cls) -> SyncRun | None:
        """Get currently running sync run if any."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, status, started_at, completed_at, is_full_sync,
                   files_added, files_modified, files_removed, files_unchanged,
                   files_skipped, bytes_downloaded, error_message
            FROM sync_run WHERE status = 'running' ORDER BY started_at DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def get_recent(cls, limit: int = 10) -> list[SyncRun]:
        """Get recent sync runs."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, status, started_at, completed_at, is_full_sync,
                   files_added, files_modified, files_removed, files_unchanged,
                   files_skipped, bytes_downloaded, error_message
            FROM sync_run ORDER BY started_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [cls.from_row(row) for row in cursor.fetchall()]

    @classmethod
    def is_sync_in_progress(cls) -> bool:
        """Check if a sync is currently in progress."""
        return cls.get_running() is not None
