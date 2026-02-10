"""Document viewer blueprint."""

from flask import Blueprint, abort, render_template

from sharepoint_mirror.blueprints.auth import login_required
from sharepoint_mirror.models import Document

bp = Blueprint("viewer", __name__, url_prefix="/viewer")


@bp.route("/pdf/<int:doc_id>")
@login_required
def pdf(doc_id: int) -> str:
    """PDF viewer page."""
    doc = Document.get_by_id(doc_id)
    if doc is None:
        abort(404)
    assert doc is not None

    # Check if it's a PDF
    if doc.mime_type != "application/pdf":
        abort(400, "Document is not a PDF")

    blob = doc.get_blob()
    if blob is None:
        abort(404, "File content not available")

    return render_template(
        "viewer/pdf.html",
        document=doc,
    )


@bp.route("/text/<int:doc_id>")
@login_required
def text(doc_id: int) -> str:
    """Text file viewer."""
    doc = Document.get_by_id(doc_id)
    if doc is None:
        abort(404)
    assert doc is not None

    # Check if it's a text file
    if not doc.mime_type or not doc.mime_type.startswith("text/"):
        abort(400, "Document is not a text file")

    blob = doc.get_blob()
    if blob is None:
        abort(404, "File content not available")
    assert blob is not None

    from sharepoint_mirror.services import StorageService

    storage = StorageService()
    content = storage.get_content(blob)
    if content is None:
        abort(404, "File not found in storage")
    assert content is not None

    # Try to decode as UTF-8
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    return render_template(
        "viewer/text.html",
        document=doc,
        content=text_content,
    )
