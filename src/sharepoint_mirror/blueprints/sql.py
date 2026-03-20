"""SQL query blueprint."""

import apsw
from flask import (
    Blueprint,
    flash,
    render_template,
    request,
    send_file,
)
from werkzeug.wrappers import Response

from sharepoint_mirror.blueprints.auth import login_required
from sharepoint_mirror.db import get_db
from sharepoint_mirror.services.export import write_xlsx

bp = Blueprint("sql", __name__, url_prefix="/sql")


def _get_schema() -> list[dict[str, object]]:
    """Get database schema: table names with their column names."""
    db = get_db()
    tables: list[dict[str, object]] = []
    for (name,) in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall():
        cols = [row[1] for row in db.execute(f"PRAGMA table_info({name})").fetchall()]
        tables.append({"name": name, "columns": cols})
    return tables


@bp.route("/", methods=["GET"])
@login_required
def index() -> str:
    """Show the SQL query page."""
    schema = _get_schema()
    return render_template("sql.html", schema=schema, query="", columns=[], rows=[])


@bp.route("/", methods=["POST"])
@login_required
def execute() -> str:
    """Execute a SQL query and display results."""
    sql = request.form.get("sql", "").strip()
    schema = _get_schema()
    columns: list[str] = []
    rows = []

    if not sql:
        flash("No SQL query provided.", "error")
        return render_template("sql.html", schema=schema, query=sql, columns=columns, rows=rows)

    try:
        cursor = get_db().cursor()
        cursor.execute(sql)
        try:
            desc = cursor.getdescription()
            columns = [d[0] for d in desc]
            rows = cursor.fetchall()
        except apsw.ExecutionCompleteError:
            flash("Statement executed successfully.", "success")
    except Exception as exc:
        flash(str(exc), "error")

    return render_template("sql.html", schema=schema, query=sql, columns=columns, rows=rows)


@bp.route("/export", methods=["POST"])
@login_required
def export() -> str | Response:
    """Export SQL query results as XLSX."""
    sql = request.form.get("sql", "").strip()
    if not sql:
        flash("No SQL query provided.", "error")
        return render_template("sql.html", schema=_get_schema(), query=sql, columns=[], rows=[])

    try:
        cursor = get_db().cursor()
        cursor.execute(sql)
        desc = cursor.getdescription()
        headers = [d[0] for d in desc]
        rows = cursor.fetchall()
    except Exception as exc:
        flash(str(exc), "error")
        return render_template("sql.html", schema=_get_schema(), query=sql, columns=[], rows=[])

    data = [list(row) for row in rows]
    path = write_xlsx(headers, data, "query.xlsx")
    return send_file(path, as_attachment=True, download_name="query.xlsx")
