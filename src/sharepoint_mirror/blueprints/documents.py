"""Document browsing blueprint."""

from io import BytesIO

from flask import Blueprint, abort, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Font
from werkzeug.wrappers import Response

from sharepoint_mirror.blueprints.auth import login_required
from sharepoint_mirror.models import Document, Drive
from sharepoint_mirror.services import StorageService

bp = Blueprint("documents", __name__, url_prefix="/documents")


@bp.route("/")
@login_required
def index() -> str:
    """List all documents with search."""
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    docs = Document.get_all(
        search=search if search else None,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    total = Document.count_all()
    drives = {d.id: d for d in Drive.get_all()}

    # Check if HTMX request
    if request.headers.get("HX-Request"):
        return render_template(
            "documents/_list.html",
            documents=docs,
            drives=drives,
            search=search,
            page=page,
            per_page=per_page,
            total=total,
        )

    return render_template(
        "documents/index.html",
        documents=docs,
        drives=drives,
        search=search,
        page=page,
        per_page=per_page,
        total=total,
    )


@bp.route("/<int:doc_id>")
@login_required
def view(doc_id: int) -> str:
    """View document details."""
    doc = Document.get_by_id(doc_id)
    if doc is None:
        abort(404)
    assert doc is not None

    blob = doc.get_blob()
    drive = Drive.get_by_id(doc.sharepoint_drive_id)

    return render_template(
        "documents/view.html",
        document=doc,
        blob=blob,
        drive=drive,
    )


@bp.route("/<int:doc_id>/download")
@login_required
def download(doc_id: int) -> Response:
    """Download document file."""
    doc = Document.get_by_id(doc_id)
    if doc is None:
        abort(404)
    assert doc is not None

    blob = doc.get_blob()
    if blob is None:
        abort(404, "File content not available")
    assert blob is not None

    storage = StorageService()
    blob_path = storage.get_blob_path(blob)

    if not blob_path.exists():
        abort(404, "File not found in storage")

    return send_file(
        blob_path,
        mimetype=doc.mime_type or "application/octet-stream",
        as_attachment=True,
        download_name=doc.name,
    )


@bp.route("/<int:doc_id>/content")
@login_required
def content(doc_id: int) -> Response:
    """Serve document content (for inline viewing)."""
    doc = Document.get_by_id(doc_id)
    if doc is None:
        abort(404)
    assert doc is not None

    blob = doc.get_blob()
    if blob is None:
        abort(404, "File content not available")
    assert blob is not None

    storage = StorageService()
    blob_path = storage.get_blob_path(blob)

    if not blob_path.exists():
        abort(404, "File not found in storage")

    return send_file(
        blob_path,
        mimetype=doc.mime_type or "application/octet-stream",
    )


@bp.route("/catalog.xlsx")
@login_required
def catalog_xlsx() -> Response:
    """Export full document catalog as XLSX."""
    docs = Document.get_all(include_deleted=False)
    drives = {d.id: d for d in Drive.get_all()}

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
    ]
    ws.append(headers)

    bold = Font(bold=True)
    for cell in ws[1]:
        cell.font = bold

    for doc in docs:
        drive = drives.get(doc.sharepoint_drive_id)
        ws.append(
            [
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
        )

    ws.auto_filter.ref = ws.dimensions

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="catalog.xlsx",
    )


@bp.route("/search")
@login_required
def search() -> str:
    """Search documents (HTMX endpoint)."""
    query = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    docs = Document.get_all(
        search=query if query else None,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    total = Document.count_all()
    drives = {d.id: d for d in Drive.get_all()}

    return render_template(
        "documents/_list.html",
        documents=docs,
        drives=drives,
        search=query,
        page=page,
        per_page=per_page,
        total=total,
    )
