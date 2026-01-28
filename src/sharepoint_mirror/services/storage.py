"""Storage service for content-addressed blob storage."""

import hashlib
from pathlib import Path

from flask import current_app

from sharepoint_mirror.models import FileBlob


class StorageService:
    """Manages content-addressed blob storage."""

    def __init__(self, blobs_directory: str | None = None):
        """Initialize storage service."""
        self.blobs_directory = Path(blobs_directory or current_app.config["BLOBS_DIRECTORY"])

    def store_content(self, content: bytes, mime_type: str) -> FileBlob:
        """
        Store content and return the FileBlob record.
        Content is deduplicated by SHA256 hash.
        """
        # Calculate hash
        sha256_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        # Check if blob already exists
        existing = FileBlob.get_by_hash(sha256_hash)
        if existing:
            # File already stored, just increment reference
            return FileBlob.create(sha256_hash, file_size, mime_type)

        # Store the file
        blob_path = self._get_blob_path(sha256_hash)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(content)

        # Create database record
        return FileBlob.create(sha256_hash, file_size, mime_type)

    def get_content(self, blob: FileBlob) -> bytes | None:
        """Get content for a blob."""
        blob_path = self._get_blob_path(blob.sha256_hash)
        if blob_path.exists():
            return blob_path.read_bytes()
        return None

    def get_content_by_hash(self, sha256_hash: str) -> bytes | None:
        """Get content by hash directly."""
        blob_path = self._get_blob_path(sha256_hash)
        if blob_path.exists():
            return blob_path.read_bytes()
        return None

    def delete_blob(self, blob: FileBlob) -> bool:
        """
        Delete a blob if reference count reaches zero.
        Returns True if file was deleted.
        """
        should_delete = blob.decrement_reference()
        if should_delete:
            blob_path = self._get_blob_path(blob.sha256_hash)
            if blob_path.exists():
                blob_path.unlink()
            blob.delete()
            # Clean up empty directories
            self._cleanup_empty_dirs(blob_path.parent)
            return True
        return False

    def blob_exists(self, sha256_hash: str) -> bool:
        """Check if a blob exists on disk."""
        return self._get_blob_path(sha256_hash).exists()

    def get_blob_path(self, blob: FileBlob) -> Path:
        """Get the filesystem path for a blob."""
        return self._get_blob_path(blob.sha256_hash)

    def _get_blob_path(self, sha256_hash: str) -> Path:
        """Get the filesystem path for a given hash."""
        # Use 2-level directory structure: {hash[:2]}/{hash[2:4]}/{hash}
        return self.blobs_directory / sha256_hash[:2] / sha256_hash[2:4] / sha256_hash

    def _cleanup_empty_dirs(self, path: Path) -> None:
        """Remove empty directories up to blobs_directory."""
        while path != self.blobs_directory and path.is_dir():
            try:
                path.rmdir()  # Only removes if empty
                path = path.parent
            except OSError:
                break  # Directory not empty

    def calculate_hash(self, content: bytes) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    def get_total_size(self) -> int:
        """Get total size of all stored blobs."""
        total = 0
        for blob_file in self.blobs_directory.rglob("*"):
            if blob_file.is_file():
                total += blob_file.stat().st_size
        return total

    def verify_integrity(self) -> list[dict]:
        """
        Verify integrity of stored blobs.
        Returns list of issues found.
        """
        issues = []

        # Check database records have matching files
        db_blobs = self._get_all_blob_hashes()
        for sha256_hash in db_blobs:
            path = self._get_blob_path(sha256_hash)
            if not path.exists():
                issues.append(
                    {
                        "type": "missing_file",
                        "hash": sha256_hash,
                        "message": f"Database record exists but file missing: {sha256_hash}",
                    }
                )
            else:
                # Verify hash matches content
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_hash != sha256_hash:
                    issues.append(
                        {
                            "type": "hash_mismatch",
                            "hash": sha256_hash,
                            "actual_hash": actual_hash,
                            "message": f"Hash mismatch for {sha256_hash}",
                        }
                    )

        # Check for orphaned files (files without database records)
        for blob_file in self.blobs_directory.rglob("*"):
            if blob_file.is_file():
                file_hash = blob_file.name
                if file_hash not in db_blobs:
                    issues.append(
                        {
                            "type": "orphaned_file",
                            "hash": file_hash,
                            "path": str(blob_file),
                            "message": f"File exists but no database record: {file_hash}",
                        }
                    )

        return issues

    def _get_all_blob_hashes(self) -> set[str]:
        """Get all blob hashes from database."""
        from sharepoint_mirror.db import get_db

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT sha256_hash FROM file_blob")
        return {str(row[0]) for row in cursor.fetchall()}
