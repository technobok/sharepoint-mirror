"""Model for custom SharePoint metadata fields (listItem.fields)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sharepoint_mirror.db import get_db, transaction


@dataclass
class DocumentMetadata:
    """A single metadata field value for a document."""

    id: int
    document_id: int
    field_name: str
    field_value: str | None

    @staticmethod
    def from_row(row: tuple) -> DocumentMetadata:
        return DocumentMetadata(
            id=row[0],
            document_id=row[1],
            field_name=row[2],
            field_value=row[3],
        )

    @staticmethod
    def replace_for_document(document_id: int, fields: dict[str, Any]) -> None:
        """Replace all metadata for a document with new fields.

        Handles multi-value fields (lists) by inserting one row per value.
        Non-string scalar values are converted to strings.
        """
        with transaction() as cursor:
            cursor.execute("DELETE FROM document_metadata WHERE document_id = ?", (document_id,))
            for name, value in fields.items():
                if isinstance(value, list):
                    for v in value:
                        cursor.execute(
                            "INSERT OR IGNORE INTO document_metadata "
                            "(document_id, field_name, field_value) VALUES (?, ?, ?)",
                            (document_id, name, str(v) if v is not None else None),
                        )
                else:
                    cursor.execute(
                        "INSERT OR IGNORE INTO document_metadata "
                        "(document_id, field_name, field_value) VALUES (?, ?, ?)",
                        (document_id, name, str(value) if value is not None else None),
                    )

    @staticmethod
    def get_for_document(document_id: int) -> dict[str, list[str]]:
        """Get all metadata for a document as field_name -> list of values."""
        db = get_db()
        rows = db.execute(
            "SELECT field_name, field_value FROM document_metadata "
            "WHERE document_id = ? ORDER BY field_name, field_value",
            (document_id,),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for name, value in rows:
            result.setdefault(name, []).append(value)
        return result

    @staticmethod
    def delete_for_document(document_id: int) -> None:
        """Delete all metadata for a document."""
        with transaction() as cursor:
            cursor.execute("DELETE FROM document_metadata WHERE document_id = ?", (document_id,))

    @staticmethod
    def get_all_field_names() -> list[str]:
        """Get all distinct field names across all documents."""
        db = get_db()
        rows = db.execute(
            "SELECT DISTINCT field_name FROM document_metadata ORDER BY field_name"
        ).fetchall()
        return [row[0] for row in rows]
