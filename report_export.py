from __future__ import annotations

import os
import tempfile
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = "071B2E"

def export_excel(path, title, headers, rows):
    wb = Workbook(); ws = wb.active; ws.title = title[:31]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    cell = ws.cell(1, 1, title); cell.font = Font(size=16, bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", fgColor=NAVY); cell.alignment = Alignment(horizontal="center")
    ws.cell(2, 1, f"Generated: {datetime.now():%d-%m-%Y %H:%M}")
    for c, header in enumerate(headers, 1):
        h = ws.cell(4, c, header); h.font = Font(bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor=NAVY); h.alignment = Alignment(horizontal="center")
    for r, values in enumerate(rows, 5):
        for c, value in enumerate(values, 1): ws.cell(r, c, value)
    for index, column in enumerate(ws.columns, 1):
        width = min(35, max(12, max(len(str(c.value or "")) for c in column) + 2))
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A5"; ws.auto_filter.ref = f"A4:{ws.cell(4, len(headers)).coordinate}"
    wb.save(path)

def export_pdf(path, title, headers, rows):
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Paragraph(f"Generated: {datetime.now():%d-%m-%Y %H:%M}", styles["Normal"]), Spacer(1, 6*mm)]
    data = [headers] + [["" if value is None else str(value) for value in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#071B2E")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7),
        ("GRID", (0,0), (-1,-1), .25, colors.grey), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F3F6F8")]),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,0), 7), ("TOPPADDING", (0,0), (-1,0), 7),
    ]))
    story.append(table); doc.build(story)

def print_rows(title, headers, rows):
    handle = tempfile.NamedTemporaryFile(prefix="SaberAccounting_", suffix=".pdf", delete=False)
    handle.close(); export_pdf(handle.name, title, headers, rows)
    if os.name != "nt": raise RuntimeError("Printing is available in the Windows application")
    os.startfile(handle.name, "print")
    return handle.name
