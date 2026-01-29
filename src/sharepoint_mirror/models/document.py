"""Document model for SharePoint documents."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sharepoint_mirror.db import get_db, transaction
from sharepoint_mirror.models.file_blob import FileBlob


@dataclass
class Document:
    """Represents a SharePoint document."""

    id: int
    sharepoint_item_id: str
    sharepoint_drive_id: str
    name: str
    path: str
    mime_type: str | None
    file_size: int | None
    web_url: str | None
    created_by: str | None
    last_modified_by: str | None
    sharepoint_created_at: str | None
    sharepoint_modified_at: str | None
    quickxor_hash: str | None
    file_blob_id: int | None
    is_deleted: bool
    synced_at: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: tuple) -> Document:
        """Create a Document from a database row."""
        return cls(
            id=row[0],
            sharepoint_item_id=row[1],
            sharepoint_drive_id=row[2],
            name=row[3],
            path=row[4],
            mime_type=row[5],
            file_size=row[6],
            web_url=row[7],
            created_by=row[8],
            last_modified_by=row[9],
            sharepoint_created_at=row[10],
            sharepoint_modified_at=row[11],
            quickxor_hash=row[12],
            file_blob_id=row[13],
            is_deleted=bool(row[14]),
            synced_at=row[15],
            created_at=row[16],
            updated_at=row[17],
        )

    @classmethod
    def get_by_id(cls, doc_id: int) -> Document | None:
        """Get a document by ID."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, sharepoint_item_id, sharepoint_drive_id, name, path,
                   mime_type, file_size, web_url, created_by, last_modified_by,
                   sharepoint_created_at, sharepoint_modified_at, quickxor_hash,
                   file_blob_id, is_deleted, synced_at, created_at, updated_at
            FROM document WHERE id = ?
            """,
            (doc_id,),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def get_by_item_id(cls, sharepoint_item_id: str, sharepoint_drive_id: str) -> Document | None:
        """Get a document by SharePoint item ID and drive ID."""
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, sharepoint_item_id, sharepoint_drive_id, name, path,
                   mime_type, file_size, web_url, created_by, last_modified_by,
                   sharepoint_created_at, sharepoint_modified_at, quickxor_hash,
                   file_blob_id, is_deleted, synced_at, created_at, updated_at
            FROM document WHERE sharepoint_item_id = ? AND sharepoint_drive_id = ?
            """,
            (sharepoint_item_id, sharepoint_drive_id),
        )
        row = cursor.fetchone()
        return cls.from_row(row) if row else None

    @classmethod
    def create(
        cls,
        sharepoint_item_id: str,
        sharepoint_drive_id: str,
        name: str,
        path: str,
        mime_type: str | None = None,
        file_size: int | None = None,
        web_url: str | None = None,
        created_by: str | None = None,
        last_modified_by: str | None = None,
        sharepoint_created_at: str | None = None,
        sharepoint_modified_at: str | None = None,
        quickxor_hash: str | None = None,
        file_blob_id: int | None = None,
    ) -> Document:
        """Create a new document."""
        now = datetime.now(UTC).isoformat()

        with transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO document (
                    sharepoint_item_id, sharepoint_drive_id, name, path,
                    mime_type, file_size, web_url, created_by, last_modified_by,
                    sharepoint_created_at, sharepoint_modified_at, quickxor_hash,
                    file_blob_id, is_deleted, synced_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    sharepoint_item_id,
                    sharepoint_drive_id,
                    name,
                    path,
                    mime_type,
                    file_size,
                    web_url,
                    created_by,
                    last_modified_by,
                    sharepoint_created_at,
                    sharepoint_modified_at,
                    quickxor_hash,
                    file_blob_id,
                    now,
                    now,
                    now,
                ),
            )
            row = cursor.execute("SELECT last_insert_rowid()").fetchone()
            assert row is not None
            doc_id = row[0]

        result = cls.get_by_id(doc_id)
        assert result is not None
        return result

    def update(
        self,
        name: str | None = None,
        path: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        web_url: str | None = None,
        created_by: str | None = None,
        last_modified_by: str | None = None,
        sharepoint_created_at: str | None = None,
        sharepoint_modified_at: str | None = None,
        quickxor_hash: str | None = None,
        file_blob_id: int | None = None,
        is_deleted: bool | None = None,
    ) -> Document:
        """Update document fields."""
        now = datetime.now(UTC).isoformat()

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if path is not None:
            updates.append("path = ?")
            params.append(path)
        if mime_type is not None:
            updates.append("mime_type = ?")
            params.append(mime_type)
        if file_size is not None:
            updates.append("file_size = ?")
            params.append(file_size)
        if web_url is not None:
            updates.append("web_url = ?")
            params.append(web_url)
        if created_by is not None:
            updates.append("created_by = ?")
            params.append(created_by)
        if last_modified_by is not None:
            updates.append("last_modified_by = ?")
            params.append(last_modified_by)
        if sharepoint_created_at is not None:
            updates.append("sharepoint_created_at = ?")
            params.append(sharepoint_created_at)
        if sharepoint_modified_at is not None:
            updates.append("sharepoint_modified_at = ?")
            params.append(sharepoint_modified_at)
        if quickxor_hash is not None:
            updates.append("quickxor_hash = ?")
            params.append(quickxor_hash)
        if file_blob_id is not None:
            updates.append("file_blob_id = ?")
            params.append(file_blob_id)
        if is_deleted is not None:
            updates.append("is_deleted = ?")
            params.append(1 if is_deleted else 0)

        updates.append("synced_at = ?")
        params.append(now)
        updates.append("updated_at = ?")
        params.append(now)

        params.append(self.id)

        with transaction() as cursor:
            cursor.execute(
                f"UPDATE document SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        return self.get_by_id(self.id)  # type: ignore

    def soft_delete(self) -> Document:
        """Mark document as deleted."""
        return self.update(is_deleted=True)

    def get_blob(self) -> FileBlob | None:
        """Get the associated file blob."""
        if self.file_blob_id is None:
            return None
        return FileBlob.get_by_id(self.file_blob_id)

    @classmethod
    def get_all(
        cls,
        include_deleted: bool = False,
        search: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Document]:
        """Get all documents with optional filtering."""
        db = get_db()
        cursor = db.cursor()

        if search:
            # Use FTS search
            query = """
                SELECT d.id, d.sharepoint_item_id, d.sharepoint_drive_id, d.name, d.path,
                       d.mime_type, d.file_size, d.web_url, d.created_by, d.last_modified_by,
                       d.sharepoint_created_at, d.sharepoint_modified_at, d.quickxor_hash,
                       d.file_blob_id, d.is_deleted, d.synced_at, d.created_at, d.updated_at
                FROM document d
                JOIN document_fts fts ON d.id = fts.rowid
                WHERE document_fts MATCH ?
            """
            params: list = [search]
            if not include_deleted:
                query += " AND d.is_deleted = 0"
            query += " ORDER BY d.path"
        else:
            query = """
                SELECT id, sharepoint_item_id, sharepoint_drive_id, name, path,
                       mime_type, file_size, web_url, created_by, last_modified_by,
                       sharepoint_created_at, sharepoint_modified_at, quickxor_hash,
                       file_blob_id, is_deleted, synced_at, created_at, updated_at
                FROM document
            """
            params = []
            if not include_deleted:
                query += " WHERE is_deleted = 0"
            query += " ORDER BY path"

        if limit:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor.execute(query, params)
        return [cls.from_row(row) for row in cursor.fetchall()]

    @classmethod
    def count_all(cls, include_deleted: bool = False) -> int:
        """Count total number of documents."""
        db = get_db()
        cursor = db.cursor()
        if include_deleted:
            cursor.execute("SELECT COUNT(*) FROM document")
        else:
            cursor.execute("SELECT COUNT(*) FROM document WHERE is_deleted = 0")
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])

    @classmethod
    def total_size(cls, include_deleted: bool = False) -> int:
        """Get total size of all documents."""
        db = get_db()
        cursor = db.cursor()
        if include_deleted:
            cursor.execute("SELECT COALESCE(SUM(file_size), 0) FROM document")
        else:
            cursor.execute("SELECT COALESCE(SUM(file_size), 0) FROM document WHERE is_deleted = 0")
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])

    @classmethod
    def get_by_drive(cls, drive_id: str, include_deleted: bool = False) -> list[Document]:
        """Get all documents for a specific drive."""
        db = get_db()
        cursor = db.cursor()
        query = """
            SELECT id, sharepoint_item_id, sharepoint_drive_id, name, path,
                   mime_type, file_size, web_url, created_by, last_modified_by,
                   sharepoint_created_at, sharepoint_modified_at, quickxor_hash,
                   file_blob_id, is_deleted, synced_at, created_at, updated_at
            FROM document WHERE sharepoint_drive_id = ?
        """
        if not include_deleted:
            query += " AND is_deleted = 0"
        query += " ORDER BY path"
        cursor.execute(query, (drive_id,))
        return [cls.from_row(row) for row in cursor.fetchall()]
