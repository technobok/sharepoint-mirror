"""File blob model for content-addressed storage."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from flask import current_app

from sharepoint_mirror.db import get_db, transaction


@dataclass
class FileBlob:
    """Represents a deduplicated file blob stored by content hash."""

    id: int
    sha256_hash: str
    file_size: int
    mime_type: str
    reference_count: int
    created_at: str

    @classmethod
    def from_row(cls, row: tuple) -> FileBlob:
        """Create a FileBlob from a database row."""
        return cls(
            id=row[0],
            sha256_hash=row[1],
            file_size=row[2],
            mime_type=row[3],
            reference_count=row[4],
            created_at=row[5],
        )

    @classmethod
    def get_by_id(cls, blob_id: int) -> FileBlob | None:
        """Get a blob by ID."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, sha256_hash, file_size, mime_type, reference_count, created_at
            FROM file_blob WHERE id = ?
            """,
            (blob_id,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def get_by_hash(cls, sha256_hash: str) -> FileBlob | None:
        """Get a blob by its SHA256 hash."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, sha256_hash, file_size, mime_type, reference_count, created_at
            FROM file_blob WHERE sha256_hash = ?
            """,
            (sha256_hash,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def create(cls, sha256_hash: str, file_size: int, mime_type: str) -> FileBlob:
        """Create a new blob record or increment reference count if exists."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            # Try to find existing blob
            cursor.execute(
                "SELECT id FROM file_blob WHERE sha256_hash = ?",
                (sha256_hash,),
            )
            existing = cursor.fetchone()

            if existing:
                # Increment reference count
                cursor.execute(
                    "UPDATE file_blob SET reference_count = reference_count + 1 WHERE id = ?",
                    (existing[0],),
                )
                blob_id = existing[0]
            else:
                # Create new blob
                cursor.execute(
                    """
                    INSERT INTO file_blob (sha256_hash, file_size, mime_type, reference_count, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (sha256_hash, file_size, mime_type, now),
                )
                row = cursor.execute("SELECT last_insert_rowid()").fetchone()
                assert row is not None
                blob_id = row[0]

        result = cls.get_by_id(blob_id)
        assert result is not None
        return result

    def decrement_reference(self) -> bool:
        """
        Decrement reference count. Returns True if blob should be deleted
        (reference count reached 0).
        """
        with transaction() as cursor:
            cursor.execute(
                "UPDATE file_blob SET reference_count = reference_count - 1 WHERE id = ?",
                (self.id,),
            )
            cursor.execute("SELECT reference_count FROM file_blob WHERE id = ?", (self.id,))
            row = cursor.fetchone()
            return row is not None and row[0] <= 0

    def delete(self) -> None:
        """Delete the blob record from the database."""
        with transaction() as cursor:
            cursor.execute("DELETE FROM file_blob WHERE id = ?", (self.id,))

    def get_path(self) -> Path:
        """Get the filesystem path for this blob."""
        blobs_dir = Path(current_app.config["BLOBS_DIRECTORY"])
        # Use 2-level directory structure: {hash[:2]}/{hash[2:4]}/{hash}
        return blobs_dir / self.sha256_hash[:2] / self.sha256_hash[2:4] / self.sha256_hash

    @classmethod
    def get_path_for_hash(cls, sha256_hash: str) -> Path:
        """Get the filesystem path for a given hash (static method)."""
        blobs_dir = Path(current_app.config["BLOBS_DIRECTORY"])
        return blobs_dir / sha256_hash[:2] / sha256_hash[2:4] / sha256_hash

    @classmethod
    def count_all(cls) -> int:
        """Count total number of blobs."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM file_blob")
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])

    @classmethod
    def total_size(cls) -> int:
        """Get total size of all blobs."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COALESCE(SUM(file_size), 0) FROM file_blob")
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])
