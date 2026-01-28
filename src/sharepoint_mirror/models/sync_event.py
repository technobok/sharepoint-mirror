"""Sync event model for tracking individual file changes."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sharepoint_mirror.db import get_db, transaction


@dataclass
class SyncEvent:
    """Represents an individual sync event (add/remove/modify)."""

    id: int
    sync_run_id: int
    document_id: int | None
    event_type: str  # add, remove, modify_add, modify_remove
    sharepoint_item_id: str
    name: str
    path: str
    file_size: int | None
    file_blob_id: int | None
    logged_at: str

    @classmethod
    def from_row(cls, row: tuple) -> SyncEvent:
        """Create a SyncEvent from a database row."""
        return cls(
            id=row[0],
            sync_run_id=row[1],
            document_id=row[2],
            event_type=row[3],
            sharepoint_item_id=row[4],
            name=row[5],
            path=row[6],
            file_size=row[7],
            file_blob_id=row[8],
            logged_at=row[9],
        )

    @classmethod
    def get_by_id(cls, event_id: int) -> SyncEvent | None:
        """Get a sync event by ID."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, sync_run_id, document_id, event_type, sharepoint_item_id,
                   name, path, file_size, file_blob_id, logged_at
            FROM sync_event WHERE id = ?
            """,
            (event_id,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def create(
        cls,
        sync_run_id: int,
        event_type: str,
        sharepoint_item_id: str,
        name: str,
        path: str,
        document_id: int | None = None,
        file_size: int | None = None,
        file_blob_id: int | None = None,
    ) -> SyncEvent:
        """Create a new sync event."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO sync_event (
                    sync_run_id, document_id, event_type, sharepoint_item_id,
                    name, path, file_size, file_blob_id, logged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sync_run_id,
                    document_id,
                    event_type,
                    sharepoint_item_id,
                    name,
                    path,
                    file_size,
                    file_blob_id,
                    now,
                ),
            )
            row = cursor.execute("SELECT last_insert_rowid()").fetchone()
            assert row is not None
            event_id = row[0]

        result = cls.get_by_id(event_id)
        assert result is not None
        return result

    @classmethod
    def get_by_sync_run(cls, sync_run_id: int, event_type: str | None = None) -> list[SyncEvent]:
        """Get all events for a sync run, optionally filtered by type."""
        db = get_db()
        cursor = db.cursor()

        if event_type:
            cursor.execute(
                """
                SELECT id, sync_run_id, document_id, event_type, sharepoint_item_id,
                       name, path, file_size, file_blob_id, logged_at
                FROM sync_event WHERE sync_run_id = ? AND event_type = ?
                ORDER BY logged_at
                """,
                (sync_run_id, event_type),
            )
        else:
            cursor.execute(
                """
                SELECT id, sync_run_id, document_id, event_type, sharepoint_item_id,
                       name, path, file_size, file_blob_id, logged_at
                FROM sync_event WHERE sync_run_id = ?
                ORDER BY logged_at
                """,
                (sync_run_id,),
            )

        return [cls.from_row(row) for row in cursor.fetchall()]

    @classmethod
    def get_recent(cls, limit: int = 50) -> list[SyncEvent]:
        """Get recent sync events across all runs."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, sync_run_id, document_id, event_type, sharepoint_item_id,
                   name, path, file_size, file_blob_id, logged_at
            FROM sync_event ORDER BY logged_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [cls.from_row(row) for row in cursor.fetchall()]

    @classmethod
    def count_by_type(cls, sync_run_id: int) -> dict[str, int]:
        """Get counts of events by type for a sync run."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT event_type, COUNT(*) FROM sync_event
            WHERE sync_run_id = ? GROUP BY event_type
            """,
            (sync_run_id,),
        )
        result: dict[str, int] = {}
        for row in cursor.fetchall():
            if row[0] is not None and row[1] is not None:
                result[str(row[0])] = int(row[1])
        return result
