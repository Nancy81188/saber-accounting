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
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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

def export_invoice_pdf(path, invoice, items, logo_path=None):
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet(); story=[]
    if logo_path and os.path.exists(str(logo_path)):
        story.append(Image(str(logo_path),width=38*mm,height=38*mm))
    story.extend([
        Paragraph("SABER FOR AUDIT",styles["Title"]),
        Paragraph("Accounting & Management Consulting",styles["Heading3"]),
        Paragraph("Zouk Mosbeh, Keserwan, Lebanon | +961 70 636729 | bassam.saber@saberforaudit.com | saberforaudit.com",styles["Normal"]),
        Spacer(1,6*mm),
        Paragraph(f'{invoice["kind"].title()} Invoice {invoice["invoice_number"]}',styles["Heading1"]),
        Paragraph(f'Date: {invoice["invoice_date"]} &nbsp;&nbsp; Due: {invoice.get("due_date") or "-"} &nbsp;&nbsp; Currency: {invoice["currency"]}',styles["Normal"]),
        Paragraph(f'Customer / Supplier: {invoice["party_name"]} &nbsp;&nbsp; Payment: {invoice.get("payment_status","unpaid").title()}',styles["Normal"]),
        Spacer(1,6*mm),
    ])
    headers=["Description","Qty","Unit Price","Before VAT","VAT %","VAT","Total"]
    rows=[[x["description"],x["quantity"],x["unit_price"],x["subtotal"],x["vat_rate"],x["vat"],x["total"]] for x in items]
    if not rows: rows=[["Invoice total","1",invoice["subtotal"],invoice["subtotal"],"",invoice["vat"],invoice["total"]]]
    table=Table([headers]+rows,repeatRows=1,colWidths=[65*mm,14*mm,23*mm,25*mm,16*mm,22*mm,24*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#071B2E")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),.4,colors.grey),("FONTSIZE",(0,0),(-1,-1),8),
        ("ALIGN",(1,1),(-1,-1),"RIGHT"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F6F8")])]))
    story.extend([table,Spacer(1,7*mm),Paragraph(f'Before VAT: {invoice["subtotal"]} &nbsp;&nbsp; VAT: {invoice["vat"]} &nbsp;&nbsp; Total: {invoice["total"]} {invoice["currency"]}',styles["Heading2"]),
        Paragraph(f'Amount Paid: {invoice.get("amount_paid",0)} &nbsp;&nbsp; Outstanding: {invoice.get("outstanding",invoice["total"])}',styles["Normal"]),Spacer(1,10*mm),
        Paragraph("Thank you for your business.",styles["Normal"])])
    doc.build(story)
