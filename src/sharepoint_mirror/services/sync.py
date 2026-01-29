"""Sync service for orchestrating SharePoint synchronization."""

import logging
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePosixPath

import magic
from flask import current_app

from sharepoint_mirror.models import DeltaToken, Document, FileBlob, SyncEvent, SyncRun
from sharepoint_mirror.quickxorhash import quickxorhash
from sharepoint_mirror.services.sharepoint import DriveItem, SharePointClient
from sharepoint_mirror.services.storage import StorageService

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Statistics for a sync operation."""

    added: int = 0
    modified: int = 0
    removed: int = 0
    unchanged: int = 0
    skipped: int = 0
    bytes_downloaded: int = 0
    errors: list[str] = field(default_factory=list)


class SyncService:
    """Orchestrates SharePoint document synchronization."""

    def __init__(
        self,
        sharepoint_client: SharePointClient | None = None,
        storage_service: StorageService | None = None,
    ):
        """Initialize sync service."""
        self.sharepoint = sharepoint_client or SharePointClient()
        self.storage = storage_service or StorageService()

        # Configuration
        self.max_file_size = current_app.config.get("SYNC_MAX_FILE_SIZE_MB", 100) * 1024 * 1024
        self.include_extensions = self._parse_extensions(
            current_app.config.get("SYNC_INCLUDE_EXTENSIONS", "")
        )
        self.exclude_extensions = self._parse_extensions(
            current_app.config.get("SYNC_EXCLUDE_EXTENSIONS", "")
        )
        self.include_paths = self._parse_include_paths(
            current_app.config.get("SYNC_INCLUDE_PATHS", "")
        )
        self.path_patterns = self._parse_path_patterns(
            current_app.config.get("SYNC_PATH_PATTERNS", "")
        )
        self.metadata_only = current_app.config.get("SYNC_METADATA_ONLY", False)
        self.verify_quickxor = current_app.config.get("SYNC_VERIFY_QUICKXOR_HASH", False)

    def _parse_extensions(self, ext_string: str) -> set[str]:
        """Parse comma-separated extensions string."""
        if not ext_string:
            return set()
        return {ext.strip().lower() for ext in ext_string.split(",") if ext.strip()}

    def _parse_multiline(self, value: str) -> list[str]:
        """Split a multi-line config value into trimmed, non-empty lines."""
        return [line.strip() for line in value.splitlines() if line.strip()]

    def _parse_include_paths(self, value: str) -> list[str]:
        """Parse SYNC_INCLUDE_PATHS into normalized path prefixes."""
        paths = self._parse_multiline(value)
        # Normalize: strip trailing slashes, ensure leading slash
        result = []
        for p in paths:
            p = p.rstrip("/")
            if not p.startswith("/"):
                p = "/" + p
            result.append(p)
        return result

    def _parse_path_patterns(self, value: str) -> list[tuple[bool, str]]:
        """
        Parse SYNC_PATH_PATTERNS into (is_include, pattern) tuples.

        Patterns prefixed with ! are exclusions; others are inclusions.
        """
        lines = self._parse_multiline(value)
        result = []
        for line in lines:
            if line.startswith("!"):
                result.append((False, line[1:].strip()))
            else:
                result.append((True, line))
        return result

    def _matches_include_paths(self, item_path: str) -> bool:
        """
        Check if item_path falls under any configured include path prefix.

        Boundary-aware: /Projects/Active matches /Projects/Active/file.pdf
        but not /Projects/ActiveOld/file.pdf.

        Returns True if no include paths are configured (i.e. no filtering).
        """
        if not self.include_paths:
            return True
        for prefix in self.include_paths:
            if item_path == prefix or item_path.startswith(prefix + "/"):
                return True
        return False

    def _matches_path_patterns(self, item_path: str) -> tuple[bool, str]:
        """
        Evaluate item_path against configured glob patterns (first-match-wins).

        Returns (should_include, reason).
        If only exclude patterns exist, default is include.
        If any include patterns exist, default is exclude.
        """
        if not self.path_patterns:
            return True, ""

        name = PurePosixPath(item_path).name

        for is_include, pattern in self.path_patterns:
            # Support ** recursive globs via PurePosixPath.match
            if "**" in pattern or "/" in pattern:
                matched = PurePosixPath(item_path).match(pattern)
            else:
                # Simple filename pattern (e.g. *.pdf)
                matched = fnmatch(name, pattern)

            if matched:
                if is_include:
                    return True, ""
                return False, f"excluded by pattern !{pattern}"

        # Default: if any include patterns exist, items not matching anything are excluded
        has_includes = any(inc for inc, _ in self.path_patterns)
        if has_includes:
            return False, "no include pattern matched"
        return True, ""

    def _should_process_file(self, item: DriveItem) -> tuple[bool, str]:
        """Check if a file should be processed. Returns (should_process, reason)."""
        if item.is_folder:
            return False, "folder"

        # Check size
        if item.size and item.size > self.max_file_size:
            return False, f"size exceeds {self.max_file_size // (1024 * 1024)}MB"

        # Check include paths
        if not self._matches_include_paths(item.path):
            return False, "path not in include paths"

        # Check path patterns
        pattern_ok, pattern_reason = self._matches_path_patterns(item.path)
        if not pattern_ok:
            return False, pattern_reason

        # Check extension filters
        name_lower = item.name.lower()
        if self.include_extensions:
            if not any(name_lower.endswith(ext) for ext in self.include_extensions):
                return False, "extension not in include list"

        if self.exclude_extensions:
            if any(name_lower.endswith(ext) for ext in self.exclude_extensions):
                return False, "extension in exclude list"

        return True, ""

    def run_sync(
        self,
        full_sync: bool = False,
        dry_run: bool = False,
        library_name: str | None = None,
    ) -> SyncRun:
        """
        Run a sync operation.

        Args:
            full_sync: If True, ignore delta tokens and sync everything
            dry_run: If True, don't make any changes, just report what would happen
            library_name: Specific library to sync (None = all libraries)
        """
        # Check if sync is already in progress
        if SyncRun.is_sync_in_progress():
            raise RuntimeError("A sync is already in progress")

        # Create sync run record
        sync_run = SyncRun.create(is_full_sync=full_sync)

        try:
            stats = SyncStats()

            # Clear delta tokens if full sync
            if full_sync:
                DeltaToken.delete_all()
                logger.info("Full sync requested, cleared all delta tokens")

            # Get drives to sync
            library_name = library_name or current_app.config.get("SHAREPOINT_LIBRARY_NAME", "")
            if library_name:
                drive = self.sharepoint.get_drive_by_name(library_name)
                if not drive:
                    raise ValueError(f"Document library not found: {library_name}")
                drives = [drive]
            else:
                drives = self.sharepoint.get_drives()

            logger.info(f"Syncing {len(drives)} drive(s)")

            # Process each drive
            for drive in drives:
                drive_stats = self._sync_drive(
                    drive_id=drive.id,
                    drive_name=drive.name,
                    sync_run=sync_run,
                    dry_run=dry_run,
                )
                stats.added += drive_stats.added
                stats.modified += drive_stats.modified
                stats.removed += drive_stats.removed
                stats.unchanged += drive_stats.unchanged
                stats.skipped += drive_stats.skipped
                stats.bytes_downloaded += drive_stats.bytes_downloaded
                stats.errors.extend(drive_stats.errors)

            # Complete sync run
            if not dry_run:
                sync_run = sync_run.complete(
                    files_added=stats.added,
                    files_modified=stats.modified,
                    files_removed=stats.removed,
                    files_unchanged=stats.unchanged,
                    files_skipped=stats.skipped,
                    bytes_downloaded=stats.bytes_downloaded,
                )

            logger.info(
                f"Sync completed: added={stats.added}, modified={stats.modified}, "
                f"removed={stats.removed}, unchanged={stats.unchanged}, skipped={stats.skipped}"
            )

            return sync_run

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            if not dry_run:
                sync_run.fail(str(e))
            raise

    def _sync_drive(
        self,
        drive_id: str,
        drive_name: str,
        sync_run: SyncRun,
        dry_run: bool = False,
    ) -> SyncStats:
        """Sync a single drive."""
        stats = SyncStats()

        logger.info(f"Syncing drive: {drive_name} ({drive_id})")

        # Get delta token
        delta_token = DeltaToken.get_by_drive_id(drive_id)
        delta_link = delta_token.delta_link if delta_token else None

        # Get changes from SharePoint
        items, new_delta_link = self.sharepoint.get_drive_items_delta(drive_id, delta_link)

        logger.info(f"Received {len(items)} items from delta query")

        for item in items:
            try:
                self._process_item(
                    item=item,
                    drive_id=drive_id,
                    sync_run=sync_run,
                    stats=stats,
                    dry_run=dry_run,
                )
            except Exception as e:
                error_msg = f"Error processing {item.path}: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

        # Save new delta token
        if not dry_run and new_delta_link:
            DeltaToken.upsert(drive_id, new_delta_link)

        return stats

    def _process_item(
        self,
        item: DriveItem,
        drive_id: str,
        sync_run: SyncRun,
        stats: SyncStats,
        dry_run: bool = False,
    ) -> None:
        """Process a single drive item."""
        # Get existing document (composite key lookup)
        existing = Document.get_by_item_id(item.id, drive_id)

        # Handle deletion
        if item.is_deleted:
            if existing and not existing.is_deleted:
                logger.info(f"Removing: {existing.path}")
                if not dry_run:
                    existing.soft_delete()
                    SyncEvent.create(
                        sync_run_id=sync_run.id,
                        event_type="remove",
                        sharepoint_item_id=item.id,
                        name=existing.name,
                        path=existing.path,
                        document_id=existing.id,
                        file_size=existing.file_size,
                        file_blob_id=existing.file_blob_id,
                    )
                stats.removed += 1
            return

        # Skip folders
        if item.is_folder:
            return

        # Determine if the item is within configured paths
        item_in_scope = self._matches_include_paths(item.path)
        if item_in_scope:
            pattern_ok, _ = self._matches_path_patterns(item.path)
            item_in_scope = pattern_ok

        # Handle existing document that moved out of scope
        if existing and not existing.is_deleted and not item_in_scope:
            logger.info(f"Removing (moved out of scope): {existing.path}")
            if not dry_run:
                existing.soft_delete()
                SyncEvent.create(
                    sync_run_id=sync_run.id,
                    event_type="remove",
                    sharepoint_item_id=item.id,
                    name=existing.name,
                    path=existing.path,
                    document_id=existing.id,
                    file_size=existing.file_size,
                    file_blob_id=existing.file_blob_id,
                )
            stats.removed += 1
            return

        # Check full eligibility (size, extensions, etc.) for in-scope items
        should_process, skip_reason = self._should_process_file(item)
        if not should_process:
            logger.debug(f"Skipping {item.path}: {skip_reason}")
            stats.skipped += 1
            return

        # Handle new file (or previously deleted doc now back in scope)
        if not existing or existing.is_deleted:
            logger.info(f"Adding: {item.path}")
            if not dry_run:
                self._add_document(item, drive_id, sync_run, stats)
            else:
                stats.added += 1
            return

        # Detect path change (rename or move)
        if existing.path != item.path:
            logger.info(f"Path changed: {existing.path} -> {item.path}")
            if not dry_run:
                # Emit remove for old path, add for new path
                SyncEvent.create(
                    sync_run_id=sync_run.id,
                    event_type="modify_remove",
                    sharepoint_item_id=item.id,
                    name=existing.name,
                    path=existing.path,
                    document_id=existing.id,
                    file_size=existing.file_size,
                    file_blob_id=existing.file_blob_id,
                )
                SyncEvent.create(
                    sync_run_id=sync_run.id,
                    event_type="modify_add",
                    sharepoint_item_id=item.id,
                    name=item.name,
                    path=item.path,
                    document_id=existing.id,
                    file_size=existing.file_size,
                    file_blob_id=existing.file_blob_id,
                )
                existing.update(
                    name=item.name,
                    path=item.path,
                    web_url=item.web_url,
                    last_modified_by=item.last_modified_by,
                    sharepoint_modified_at=item.modified_at,
                )
            stats.modified += 1
            # If content also changed, fall through to the modification check
            if existing.sharepoint_modified_at == item.modified_at:
                return

        # Handle existing file - check if modified
        if existing.sharepoint_modified_at != item.modified_at:
            logger.info(f"Modifying: {item.path}")
            if not dry_run:
                self._update_document(existing, item, sync_run, stats)
            else:
                stats.modified += 1
            return

        # No changes
        stats.unchanged += 1

    def _add_document(
        self,
        item: DriveItem,
        drive_id: str,
        sync_run: SyncRun,
        stats: SyncStats,
    ) -> None:
        """Add a new document."""
        if self.metadata_only:
            doc = Document.create(
                sharepoint_item_id=item.id,
                sharepoint_drive_id=drive_id,
                name=item.name,
                path=item.path,
                mime_type=item.mime_type,
                file_size=item.size,
                web_url=item.web_url,
                created_by=item.created_by,
                last_modified_by=item.last_modified_by,
                sharepoint_created_at=item.created_at,
                sharepoint_modified_at=item.modified_at,
                quickxor_hash=item.quickxor_hash,
                file_blob_id=None,
            )
            SyncEvent.create(
                sync_run_id=sync_run.id,
                event_type="add",
                sharepoint_item_id=item.id,
                name=item.name,
                path=item.path,
                document_id=doc.id,
                file_size=item.size,
                file_blob_id=None,
            )
            stats.added += 1
            return

        # Download content
        if item.download_url:
            content = self.sharepoint.download_file_by_url(item.download_url)
        else:
            content = self.sharepoint.download_file(drive_id, item.id)

        stats.bytes_downloaded += len(content)

        # Detect MIME type
        mime_type = item.mime_type or magic.from_buffer(content, mime=True)

        # Verify quickXorHash if enabled
        if self.verify_quickxor and item.quickxor_hash:
            computed = quickxorhash(content)
            if computed != item.quickxor_hash:
                logger.warning(
                    "QuickXorHash mismatch for %s: expected %s, got %s",
                    item.path,
                    item.quickxor_hash,
                    computed,
                )

        # Store blob
        blob = self.storage.store_content(content, mime_type)

        # Create document record
        doc = Document.create(
            sharepoint_item_id=item.id,
            sharepoint_drive_id=drive_id,
            name=item.name,
            path=item.path,
            mime_type=mime_type,
            file_size=len(content),
            web_url=item.web_url,
            created_by=item.created_by,
            last_modified_by=item.last_modified_by,
            sharepoint_created_at=item.created_at,
            sharepoint_modified_at=item.modified_at,
            quickxor_hash=item.quickxor_hash,
            file_blob_id=blob.id,
        )

        # Log event
        SyncEvent.create(
            sync_run_id=sync_run.id,
            event_type="add",
            sharepoint_item_id=item.id,
            name=item.name,
            path=item.path,
            document_id=doc.id,
            file_size=len(content),
            file_blob_id=blob.id,
        )

        stats.added += 1

    def _update_document(
        self,
        existing: Document,
        item: DriveItem,
        sync_run: SyncRun,
        stats: SyncStats,
    ) -> None:
        """Update an existing document."""
        if self.metadata_only:
            existing.update(
                name=item.name,
                path=item.path,
                mime_type=item.mime_type,
                file_size=item.size,
                web_url=item.web_url,
                last_modified_by=item.last_modified_by,
                sharepoint_modified_at=item.modified_at,
                quickxor_hash=item.quickxor_hash,
            )
            stats.modified += 1
            return

        # Download new content
        if item.download_url:
            content = self.sharepoint.download_file_by_url(item.download_url)
        else:
            content = self.sharepoint.download_file(existing.sharepoint_drive_id, item.id)

        stats.bytes_downloaded += len(content)

        # Verify quickXorHash if enabled
        if self.verify_quickxor and item.quickxor_hash:
            computed = quickxorhash(content)
            if computed != item.quickxor_hash:
                logger.warning(
                    "QuickXorHash mismatch for %s: expected %s, got %s",
                    item.path,
                    item.quickxor_hash,
                    computed,
                )

        # Calculate hash to check if content actually changed
        new_hash = self.storage.calculate_hash(content)
        old_blob = existing.get_blob()

        if old_blob and old_blob.sha256_hash == new_hash:
            # Content unchanged, just update metadata
            existing.update(
                name=item.name,
                path=item.path,
                web_url=item.web_url,
                last_modified_by=item.last_modified_by,
                sharepoint_modified_at=item.modified_at,
                quickxor_hash=item.quickxor_hash,
            )
            stats.unchanged += 1
            stats.modified -= 1  # Adjust since we thought it was modified
            return

        # Log the removal of old version
        SyncEvent.create(
            sync_run_id=sync_run.id,
            event_type="modify_remove",
            sharepoint_item_id=item.id,
            name=existing.name,
            path=existing.path,
            document_id=existing.id,
            file_size=existing.file_size,
            file_blob_id=existing.file_blob_id,
        )

        # Detect MIME type
        mime_type = item.mime_type or magic.from_buffer(content, mime=True)

        # Store new blob (old blob kept for reference tracking)
        new_blob = self.storage.store_content(content, mime_type)

        # Update document
        existing.update(
            name=item.name,
            path=item.path,
            mime_type=mime_type,
            file_size=len(content),
            web_url=item.web_url,
            last_modified_by=item.last_modified_by,
            sharepoint_modified_at=item.modified_at,
            quickxor_hash=item.quickxor_hash,
            file_blob_id=new_blob.id,
        )

        # Log the addition of new version
        SyncEvent.create(
            sync_run_id=sync_run.id,
            event_type="modify_add",
            sharepoint_item_id=item.id,
            name=item.name,
            path=item.path,
            document_id=existing.id,
            file_size=len(content),
            file_blob_id=new_blob.id,
        )

        stats.modified += 1

    def get_status(self) -> dict:
        """Get current sync status."""
        latest_run = SyncRun.get_latest()
        running = SyncRun.get_running()

        return {
            "is_running": running is not None,
            "current_run": running,
            "last_completed_run": latest_run
            if latest_run and latest_run.status != "running"
            else None,
            "total_documents": Document.count_all(),
            "total_size": Document.total_size(),
            "total_blobs": FileBlob.count_all(),
            "blobs_size": FileBlob.total_size(),
        }
