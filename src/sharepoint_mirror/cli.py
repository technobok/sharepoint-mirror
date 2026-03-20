"""CLI commands for SharePoint Mirror."""

import json
import logging
import sys

import click
from flask import Flask, current_app


def register_cli_commands(app: Flask) -> None:
    """Register CLI commands with the Flask app."""

    @app.cli.command("sync")
    @click.option("--full", is_flag=True, help="Force full sync (ignore delta tokens)")
    @click.option("--dry-run", is_flag=True, help="Preview changes without making them")
    @click.option("--library", "-l", help="Specific library to sync")
    @click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
    def sync_command(full: bool, dry_run: bool, library: str | None, verbose: bool) -> None:
        """Synchronize documents from SharePoint."""
        if verbose:
            logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        else:
            logging.basicConfig(level=logging.INFO, stream=sys.stdout)

        from sharepoint_mirror.services import SyncService

        try:
            service = SyncService()

            if dry_run:
                click.echo("DRY RUN - No changes will be made")
                click.echo()

            sync_run = service.run_sync(
                full_sync=full,
                dry_run=dry_run,
                library_name=library,
            )

            click.echo()
            click.echo("Sync completed:")
            click.echo(f"  Added:     {sync_run.files_added}")
            click.echo(f"  Modified:  {sync_run.files_modified}")
            click.echo(f"  Removed:   {sync_run.files_removed}")
            click.echo(f"  Unchanged: {sync_run.files_unchanged}")
            click.echo(f"  Skipped:   {sync_run.files_skipped}")
            click.echo(f"  Downloaded: {_format_size(sync_run.bytes_downloaded)}")

        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Sync failed: {e}", err=True)
            sys.exit(1)

    @app.cli.command("status")
    def status_command() -> None:
        """Show sync status and statistics."""
        from sharepoint_mirror.services import SyncService

        service = SyncService()
        status = service.get_status()

        click.echo("SharePoint Mirror Status")
        click.echo("=" * 40)

        if status["is_running"]:
            run = status["current_run"]
            click.echo(f"Status: SYNC IN PROGRESS (started {run.started_at})")
        else:
            click.echo("Status: Idle")

        click.echo()
        click.echo("Documents:")
        click.echo(f"  Total files:  {status['total_documents']}")
        click.echo(f"  Total size:   {_format_size(status['total_size'])}")

        click.echo()
        click.echo("Storage:")
        click.echo(f"  Unique blobs: {status['total_blobs']}")
        click.echo(f"  Blobs size:   {_format_size(status['blobs_size'])}")

        if status["last_completed_run"]:
            run = status["last_completed_run"]
            click.echo()
            click.echo("Last Sync:")
            click.echo(f"  Status:     {run.status}")
            click.echo(f"  Started:    {run.started_at}")
            click.echo(f"  Completed:  {run.completed_at}")
            click.echo(f"  Added:      {run.files_added}")
            click.echo(f"  Modified:   {run.files_modified}")
            click.echo(f"  Removed:    {run.files_removed}")
            if run.error_message:
                click.echo(f"  Error:      {run.error_message}")

    @app.cli.command("list")
    @click.option("--search", "-s", help="Search by name or path")
    @click.option("--limit", "-n", default=50, help="Maximum number of results")
    @click.option("--deleted", is_flag=True, help="Include deleted documents")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON")
    def list_command(search: str | None, limit: int, deleted: bool, as_json: bool) -> None:
        """List synchronized documents."""
        from sharepoint_mirror.models import Document

        docs = Document.get_all(
            include_deleted=deleted,
            search=search,
            limit=limit,
        )

        if as_json:
            output = [
                {
                    "id": doc.id,
                    "name": doc.name,
                    "path": doc.path,
                    "size": doc.file_size,
                    "mime_type": doc.mime_type,
                    "synced_at": doc.synced_at,
                    "is_deleted": doc.is_deleted,
                }
                for doc in docs
            ]
            click.echo(json.dumps(output, indent=2))
        else:
            if not docs:
                click.echo("No documents found.")
                return

            click.echo(f"{'Path':<60} {'Size':>10} {'Synced'}")
            click.echo("-" * 90)
            for doc in docs:
                size_str = _format_size(doc.file_size) if doc.file_size else "-"
                synced = doc.synced_at[:10] if doc.synced_at else "-"
                path = doc.path
                if len(path) > 58:
                    path = "..." + path[-55:]
                if doc.is_deleted:
                    path = f"[DEL] {path}"
                click.echo(f"{path:<60} {size_str:>10} {synced}")

            click.echo()
            click.echo(f"Total: {len(docs)} document(s)")

    @app.cli.command("export-metadata")
    @click.option("--output", "-o", help="Output file (default: stdout)")
    @click.option("--format", "-f", "fmt", default="json", type=click.Choice(["json", "jsonl"]))
    @click.option("--include-blob-path", is_flag=True, help="Include local blob file path")
    def export_metadata_command(output: str | None, fmt: str, include_blob_path: bool) -> None:
        """Export document metadata for vector database ingestion."""
        from sharepoint_mirror.models import Document, DocumentMetadata

        docs = Document.get_all(include_deleted=False)

        records = []
        for doc in docs:
            record = {
                "id": doc.id,
                "sharepoint_item_id": doc.sharepoint_item_id,
                "name": doc.name,
                "path": doc.path,
                "mime_type": doc.mime_type,
                "file_size": doc.file_size,
                "web_url": doc.web_url,
                "created_by": doc.created_by,
                "last_modified_by": doc.last_modified_by,
                "sharepoint_created_at": doc.sharepoint_created_at,
                "sharepoint_modified_at": doc.sharepoint_modified_at,
                "synced_at": doc.synced_at,
            }

            if include_blob_path:
                blob = doc.get_blob()
                if blob:
                    record["blob_path"] = str(blob.get_path())
                    record["blob_hash"] = blob.sha256_hash

            custom = DocumentMetadata.get_for_document(doc.id)
            if custom:
                record["custom_metadata"] = custom

            records.append(record)

        if fmt == "json":
            content = json.dumps(records, indent=2)
        else:  # jsonl
            content = "\n".join(json.dumps(r) for r in records)

        if output:
            with open(output, "w") as f:
                f.write(content)
            click.echo(f"Exported {len(records)} document(s) to {output}")
        else:
            click.echo(content)

    @app.cli.command("export-catalog")
    @click.option("--output", "-o", default="catalog.xlsx", help="Output file path")
    def export_catalog_command(output: str) -> None:
        """Export full document catalog as XLSX spreadsheet."""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        from sharepoint_mirror.models import Document, DocumentMetadata, Drive

        docs = Document.get_all(include_deleted=False)
        drives = {d.id: d for d in Drive.get_all()}

        # Collect custom metadata for all documents and discover field names
        doc_metadata: dict[int, dict[str, list[str]]] = {}
        for doc in docs:
            meta = DocumentMetadata.get_for_document(doc.id)
            if meta:
                doc_metadata[doc.id] = meta

        # Get all distinct custom field names in sorted order
        custom_fields = sorted({name for meta in doc_metadata.values() for name in meta})

        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Documents"

        headers = [
            "Library",
            "Name",
            "Path",
            "MIME Type",
            "File Size",
            "Web URL",
            "Created By",
            "Last Modified By",
            "SP Created",
            "SP Modified",
            "Synced At",
            "QuickXor Hash",
            "SharePoint Item ID",
            "SharePoint Drive ID",
        ] + custom_fields
        ws.append(headers)

        bold = Font(bold=True)
        for cell in ws[1]:
            cell.font = bold

        for doc in docs:
            drive = drives.get(doc.sharepoint_drive_id)
            row = [
                drive.name if drive else doc.sharepoint_drive_id,
                doc.name,
                doc.path,
                doc.mime_type,
                doc.file_size,
                doc.web_url,
                doc.created_by,
                doc.last_modified_by,
                doc.sharepoint_created_at,
                doc.sharepoint_modified_at,
                doc.synced_at,
                doc.quickxor_hash,
                doc.sharepoint_item_id,
                doc.sharepoint_drive_id,
            ]
            meta = doc_metadata.get(doc.id, {})
            for field_name in custom_fields:
                values = meta.get(field_name, [])
                row.append("; ".join(v for v in values if v is not None) if values else "")
            ws.append(row)

        ws.auto_filter.ref = ws.dimensions
        wb.save(output)
        click.echo(f"Exported {len(docs)} document(s) to {output}")

    @app.cli.command("list-fields")
    @click.option("--library", "-l", help="Specific library (default: all)")
    @click.option("--include-hidden", is_flag=True, help="Include hidden columns")
    def list_fields_command(library: str | None, include_hidden: bool) -> None:
        """List custom metadata fields defined on SharePoint document libraries."""
        from sharepoint_mirror.services import SharePointClient

        try:
            client = SharePointClient()
            library_name = library or current_app.config.get("SHAREPOINT_LIBRARY_NAME", "")

            if library_name:
                drive = client.get_drive_by_name(library_name)
                if not drive:
                    click.echo(f"Library not found: {library_name}", err=True)
                    sys.exit(1)
                drives = [drive]
            else:
                drives = client.get_drives()

            for drv in drives:
                columns = client.get_library_columns(drv.id)

                click.echo(f"Library: {drv.name}")
                click.echo()
                click.echo(
                    f"  {'Name':<30} {'Type':<12} {'Read-Only':<11} {'Hidden':<8} Description"
                )
                click.echo(f"  {'─' * 90}")

                for col in columns:
                    hidden = col.get("hidden", False)
                    if hidden and not include_hidden:
                        continue
                    name = col.get("displayName") or col.get("name", "?")
                    col_type = col.get("type", "?")
                    read_only = "yes" if col.get("readOnly", False) else "no"
                    hidden_str = "yes" if hidden else "no"
                    description = col.get("description", "") or ""
                    click.echo(
                        f"  {name:<30} {col_type:<12} {read_only:<11} {hidden_str:<8} {description}"
                    )

                click.echo()

        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    @app.cli.command("refresh-metadata")
    @click.option("--library", "-l", help="Limit to a specific library")
    @click.option("--verbose", "-v", is_flag=True, help="Show each document being processed")
    def refresh_metadata_command(library: str | None, verbose: bool) -> None:
        """Re-fetch custom metadata (listItem.fields) for all synced documents."""
        if verbose:
            logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        else:
            logging.basicConfig(level=logging.INFO, stream=sys.stdout)

        from sharepoint_mirror.models import Document, Drive
        from sharepoint_mirror.services import SyncService

        try:
            service = SyncService()

            docs = Document.get_all(include_deleted=False)

            # Filter by library if specified
            if library:
                drives = {d.name: d for d in Drive.get_all()}
                drive = drives.get(library)
                if not drive:
                    click.echo(f"Library not found: {library}", err=True)
                    sys.exit(1)
                docs = [d for d in docs if d.sharepoint_drive_id == drive.id]

            if not docs:
                click.echo("No documents to process.")
                return

            click.echo(f"Refreshing metadata for {len(docs)} document(s)...")

            errors = 0
            for i, doc in enumerate(docs, 1):
                if verbose:
                    click.echo(f"  [{i}/{len(docs)}] {doc.name}")
                try:
                    service._sync_metadata(doc.id, doc.sharepoint_drive_id, doc.sharepoint_item_id)
                except Exception as e:
                    errors += 1
                    click.echo(f"  Warning: {doc.name}: {e}", err=True)

            click.echo(f"Done. Processed {len(docs)} document(s), {errors} error(s).")

        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    @app.cli.command("test-connection")
    def test_connection_command() -> None:
        """Test SharePoint connection."""
        from sharepoint_mirror.services import SharePointClient

        click.echo("Testing SharePoint connection...")
        try:
            client = SharePointClient()
            info = client.test_connection()

            click.echo()
            click.echo("Connection successful!")
            click.echo(f"  Site: {info['site_name']}")
            click.echo(f"  URL:  {info['site_url']}")
            click.echo()
            click.echo("Document Libraries:")
            for drive in info["drives"]:
                click.echo(f"  - {drive['name']} ({drive['id']})")

        except Exception as e:
            click.echo(f"Connection failed: {e}", err=True)
            sys.exit(1)

    @app.cli.command("clear-delta-tokens")
    @click.confirmation_option(prompt="This will force a full sync on next run. Continue?")
    def clear_delta_tokens_command() -> None:
        """Clear all delta tokens to force a full sync."""
        from sharepoint_mirror.models import DeltaToken

        DeltaToken.delete_all()
        click.echo("Delta tokens cleared. Next sync will be a full sync.")

    @app.cli.command("verify-storage")
    def verify_storage_command() -> None:
        """Verify integrity of blob storage."""
        from sharepoint_mirror.services import StorageService

        click.echo("Verifying storage integrity...")
        service = StorageService()
        issues = service.verify_integrity()

        if not issues:
            click.echo("No issues found. Storage is healthy.")
        else:
            click.echo(f"Found {len(issues)} issue(s):")
            for issue in issues:
                click.echo(f"  [{issue['type']}] {issue['message']}")


def _format_size(size: int | None) -> str:
    """Format file size in human-readable format."""
    if size is None:
        return "-"
    fsize = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if fsize < 1024:
            return f"{fsize:.1f} {unit}" if unit != "B" else f"{int(fsize)} {unit}"
        fsize /= 1024
    return f"{fsize:.1f} PB"
