"""XLSX export helper."""

import tempfile
from typing import Any

from openpyxl import Workbook


def write_xlsx(headers: list[str], rows: list[list[Any]], filename: str) -> str:
    """Write rows to a temp XLSX file, return the path."""
    wb = Workbook()
    ws = wb.active
    ws.title = filename.removesuffix(".xlsx")
    ws.append(headers)
    for row in rows:
        ws.append(row)
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    wb.save(tmp.name)
    return tmp.name
