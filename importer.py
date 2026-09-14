from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re

from openpyxl import load_workbook

VAT_RATE = Decimal("0.11")

ALIASES = {
    "invoice_number": {"invoice number", "invoice no", "invoice no.", "invoice #", "inv no", "رقم الفاتورة", "numero facture", "n facture"},
    "date": {"date", "invoice date", "تاريخ", "التاريخ", "date facture"},
    "party": {"supplier name", "customer name", "client name", "supplier", "customer", "client", "المورد", "العميل", "fournisseur"},
    "subtotal": {"total before vat", "before vat", "subtotal", "amount before vat", "قبل الضريبة", "hors tva", "ht"},
    "vat": {"vat", "tva", "ضريبة", "الضريبة"},
    "total": {"total after vat", "total", "grand total", "بعد الضريبة", "ttc"},
    "currency": {"currency", "curr", "العملة", "devise"},
    "kind": {"type", "invoice type", "نوع", "nature"},
}

def _norm(value):
    return re.sub(r"[^\w#]+", " ", str(value or "").strip().lower()).strip()

def _columns(header):
    result = {}
    for index, value in enumerate(header):
        normalized = _norm(value)
        for field, aliases in ALIASES.items():
            if normalized in aliases:
                result[field] = index
                break
    return result

def _decimal(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("$", "").strip()
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None

def _date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text

def read_invoices(path: str | Path, sheet_name: str | None = None, default_currency="USD", default_kind="purchase"):
    """Read invoices without deleting duplicates. Blank rows are ignored.

    Invoice number priority: source Invoice Number column, then original Excel row.
    """
    workbook_values = load_workbook(path, read_only=True, data_only=True)
    workbook_formulas = load_workbook(path, read_only=True, data_only=False)
    try:
        sheet = workbook_values[sheet_name] if sheet_name else workbook_values.worksheets[0]
        formula_sheet = workbook_formulas[sheet.title]
        value_rows = sheet.iter_rows(values_only=True)
        formula_rows = formula_sheet.iter_rows(values_only=True)
        header = next(value_rows)
        next(formula_rows)
        columns = _columns(header)
        required = {"date", "party", "subtotal", "vat", "total"}
        if not required.issubset(columns):
            missing = ", ".join(sorted(required - set(columns)))
            raise ValueError(f"Missing required columns: {missing}")
        invoices = []
        for row_number, (values, formulas) in enumerate(zip(value_rows, formula_rows), start=2):
            if not any(v not in (None, "") for v in formulas):
                continue
            def get(field, default=None):
                idx = columns.get(field)
                return values[idx] if idx is not None and idx < len(values) else default
            subtotal, vat, total = _decimal(get("subtotal")), _decimal(get("vat")), _decimal(get("total"))
            if subtotal is not None and vat is None:
                vat = (subtotal * VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if total is None and subtotal is not None and vat is not None:
                total = subtotal + vat
            invoice_number = str(get("invoice_number") or row_number).strip()
            kind = str(get("kind") or default_kind).strip().lower()
            invoices.append({
                "invoice_number": invoice_number,
                "invoice_date": _date(get("date")),
                "party_name": str(get("party") or "").strip(),
                "subtotal": float(subtotal) if subtotal is not None else None,
                "vat": float(vat) if vat is not None else None,
                "total": float(total) if total is not None else None,
                "currency": str(get("currency") or default_currency).upper(),
                "kind": "sale" if kind in {"sale", "sales", "customer"} else "purchase",
                "source_file": Path(path).name,
                "source_row": row_number,
            })
        return invoices
    finally:
        workbook_values.close()
        workbook_formulas.close()

