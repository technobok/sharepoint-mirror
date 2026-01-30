"""Drive model for SharePoint document library lookup."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sharepoint_mirror.db import get_db, transaction


@dataclass
class Drive:
    """Stores drive ID to library name mapping."""

    id: str
    name: str
    web_url: str | None
    updated_at: str

    @classmethod
    def from_row(cls, row: tuple) -> Drive:
        """Create a Drive from a database row."""
        return cls(
            id=row[0],
            name=row[1],
            web_url=row[2],
            updated_at=row[3],
        )

    @classmethod
    def get_by_id(cls, drive_id: str) -> Drive | None:
        """Get drive by ID."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, name, web_url, updated_at
            FROM drive WHERE id = ?
            """,
            (drive_id,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def upsert(cls, drive_id: str, name: str, web_url: str | None = None) -> Drive:
        """Create or update drive record."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO drive (id, name, web_url, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    web_url = excluded.web_url,
                    updated_at = excluded.updated_at
                """,
                (drive_id, name, web_url, now),
            )

        result = cls.get_by_id(drive_id)
        assert result is not None
        return result

    @classmethod
    def get_all(cls) -> list[Drive]:
        """Get all drives."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, name, web_url, updated_at
            FROM drive ORDER BY name
            """
        )
        return [cls.from_row(row) for row in cursor.fetchall()]
