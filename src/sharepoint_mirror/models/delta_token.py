"""Delta token model for Graph API delta queries."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sharepoint_mirror.db import get_db, transaction


@dataclass
class DeltaToken:
    """Stores delta link for Graph API delta queries per drive."""

    id: int
    drive_id: str
    delta_link: str
    updated_at: str

    @classmethod
    def from_row(cls, row: tuple) -> DeltaToken:
        """Create a DeltaToken from a database row."""
        return cls(
            id=row[0],
            drive_id=row[1],
            delta_link=row[2],
            updated_at=row[3],
        )

    @classmethod
    def get_by_drive_id(cls, drive_id: str) -> DeltaToken | None:
        """Get delta token for a drive."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, drive_id, delta_link, updated_at
            FROM delta_token WHERE drive_id = ?
            """,
            (drive_id,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def upsert(cls, drive_id: str, delta_link: str) -> DeltaToken:
        """Create or update delta token for a drive."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO delta_token (drive_id, delta_link, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(drive_id) DO UPDATE SET
                    delta_link = excluded.delta_link,
                    updated_at = excluded.updated_at
                """,
                (drive_id, delta_link, now),
            )

        result = cls.get_by_drive_id(drive_id)
        assert result is not None
        return result

    @classmethod
    def delete_by_drive_id(cls, drive_id: str) -> None:
        """Delete delta token for a drive (forces full sync)."""
        with transaction() as cursor:
            cursor.execute("DELETE FROM delta_token WHERE drive_id = ?", (drive_id,))

    @classmethod
    def delete_all(cls) -> None:
        """Delete all delta tokens (forces full sync on all drives)."""
        with transaction() as cursor:
            cursor.execute("DELETE FROM delta_token")

    @classmethod
    def get_all(cls) -> list[DeltaToken]:
        """Get all delta tokens."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, drive_id, delta_link, updated_at
            FROM delta_token ORDER BY updated_at DESC
            """
        )
        return [cls.from_row(row) for row in cursor.fetchall()]
