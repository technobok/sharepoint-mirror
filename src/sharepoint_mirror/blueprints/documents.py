"""Document browsing blueprint."""

from flask import Blueprint, abort, render_template, request, send_file

from sharepoint_mirror.models import Document, Drive
from sharepoint_mirror.services import StorageService

bp = Blueprint("documents", __name__, url_prefix="/documents")


@bp.route("/")
def index():
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
def view(doc_id: int):
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
def download(doc_id: int):
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
def content(doc_id: int):
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


@bp.route("/search")
def search():
    """Search documents (HTMX endpoint)."""
    query = request.args.get("q", "").strip()

    if not query:
        docs = Document.get_all(limit=50)
    else:
        docs = Document.get_all(search=query, limit=50)

    drives = {d.id: d for d in Drive.get_all()}

    return render_template(
        "documents/_list.html",
        documents=docs,
        drives=drives,
        search=query,
    )
