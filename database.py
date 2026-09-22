from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from lebanese_accounts import DEFAULT_LEBANESE_ACCOUNTS, LEBANESE_ACCOUNTS

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','accountant','viewer')), language TEXT NOT NULL DEFAULT 'en', active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parties (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('customer','supplier','both')),
 name TEXT NOT NULL, tax_number TEXT, currency TEXT NOT NULL DEFAULT 'USD', UNIQUE(kind,name)
);
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name_en TEXT NOT NULL, name_ar TEXT, name_fr TEXT,
 type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')), parent_id INTEGER REFERENCES accounts(id), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY, invoice_number TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('sale','purchase')),
 invoice_date TEXT, party_id INTEGER REFERENCES parties(id), currency TEXT NOT NULL, exchange_rate TEXT NOT NULL DEFAULT '1',
 subtotal TEXT, vat TEXT, total TEXT, status TEXT NOT NULL DEFAULT 'posted', currency_issue TEXT NOT NULL DEFAULT '',
 supplier_account TEXT NOT NULL DEFAULT '4011', vat_account TEXT NOT NULL DEFAULT '4426.6', expense_account TEXT NOT NULL DEFAULT '6011',
 source_file TEXT, source_row INTEGER,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_items (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 description TEXT NOT NULL, quantity TEXT NOT NULL, unit_price TEXT NOT NULL,
 subtotal TEXT NOT NULL, vat_rate TEXT NOT NULL, vat TEXT NOT NULL, total TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal_entries (
 id INTEGER PRIMARY KEY, entry_number TEXT NOT NULL UNIQUE, entry_date TEXT, description TEXT, source_type TEXT,
 source_id INTEGER, currency TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal_lines (
 id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
 account_id INTEGER NOT NULL REFERENCES accounts(id), party_id INTEGER REFERENCES parties(id), debit TEXT NOT NULL DEFAULT '0', credit TEXT NOT NULL DEFAULT '0'
);
CREATE TABLE IF NOT EXISTS inventory_items (
 id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'unit', quantity TEXT NOT NULL DEFAULT '0', average_cost TEXT NOT NULL DEFAULT '0'
);
CREATE TABLE IF NOT EXISTS stock_movements (
 id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES inventory_items(id), movement_date TEXT NOT NULL,
 quantity TEXT NOT NULL, unit_cost TEXT NOT NULL, source_type TEXT, source_id INTEGER
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), action TEXT NOT NULL, entity TEXT NOT NULL,
 entity_id INTEGER, details TEXT, created_at TEXT NOT NULL
);
"""

LEGACY_ACCOUNT_MAP = {
    "1100": DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"],
    "2100": DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],
    "2200": DEFAULT_LEBANESE_ACCOUNTS["vat_payable"],
    "1300": DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"],
    "4100": DEFAULT_LEBANESE_ACCOUNTS["sales"],
    "5100": DEFAULT_LEBANESE_ACCOUNTS["purchases"],
    "9999": DEFAULT_LEBANESE_ACCOUNTS["import_variance"],
}
def utcnow():
    return datetime.now(timezone.utc).isoformat()

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"

def verify_password(password, encoded):
    salt_hex, digest_hex = encoded.split(":", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    return hmac.compare_digest(candidate, digest_hex)

class Database:
    def __init__(self, path):
        self.path = str(Path(path))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, admin_password="ChangeMe123!"):
        with self.connect() as db:
            db.executescript(SCHEMA)
            invoice_columns = {row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "currency_issue" not in invoice_columns:
                db.execute("ALTER TABLE invoices ADD COLUMN currency_issue TEXT NOT NULL DEFAULT ''")
            account_columns = {
                "supplier_account": DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],
                "vat_account": DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"],
                "expense_account": DEFAULT_LEBANESE_ACCOUNTS["purchases"],
            }
            for column, default_code in account_columns.items():
                if column not in invoice_columns:
                    db.execute(
                        f"ALTER TABLE invoices ADD COLUMN {column} "
                        f"TEXT NOT NULL DEFAULT '{default_code}'"
                    )
            db.execute("INSERT OR IGNORE INTO users(username,password_hash,role) VALUES(?,?,?)", ("admin", hash_password(admin_password), "admin"))
            db.executemany("""INSERT INTO accounts(code,name_en,name_ar,name_fr,type)
                VALUES(?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET
                name_en=excluded.name_en,name_ar=excluded.name_ar,name_fr=excluded.name_fr,type=excluded.type""",
                [row[:5] for row in LEBANESE_ACCOUNTS])
            for code, _name_en, _name_ar, _name_fr, _type, parent_code in LEBANESE_ACCOUNTS:
                if parent_code:
                    db.execute("UPDATE accounts SET parent_id=(SELECT id FROM accounts WHERE code=?) WHERE code=?",
                               (parent_code, code))
            for old_code, new_code in LEGACY_ACCOUNT_MAP.items():
                old = db.execute("SELECT id FROM accounts WHERE code=?", (old_code,)).fetchone()
                new = db.execute("SELECT id FROM accounts WHERE code=?", (new_code,)).fetchone()
                if old and new and old["id"] != new["id"]:
                    db.execute("UPDATE journal_lines SET account_id=? WHERE account_id=?", (new["id"], old["id"]))
                    db.execute("DELETE FROM accounts WHERE id=?", (old["id"],))
            db.execute("UPDATE invoices SET supplier_account=? WHERE supplier_account='2100'",
                       (DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],))
            db.execute("UPDATE invoices SET vat_account=? WHERE vat_account='1300'",
                       (DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"],))
            db.execute("UPDATE invoices SET expense_account=? WHERE expense_account='5100'",
                       (DEFAULT_LEBANESE_ACCOUNTS["purchases"],))

    def login(self, username, password):
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
            if not user or not verify_password(password, user["password_hash"]):
                return None
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)", (token, user["id"], utcnow()))
            return {"token": token, "username": user["username"], "role": user["role"], "language": user["language"]}

    def user_for_token(self, token):
        with self.connect() as db:
            return db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1", (token,)).fetchone()

    def _account_id(self, db, code):
        row = db.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()
        return row["id"]

    def backup(self):
        source = Path(self.path)
        if not source.exists(): return None
        folder = source.parent / "backups"; folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"saber_accounting_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
        shutil.copy2(source, target)
        return str(target)

    def clear_invoices(self, user_id):
        backup_path = self.backup()
        with self.connect() as db:
            entry_ids = [r["id"] for r in db.execute("SELECT id FROM journal_entries WHERE source_type='invoice'")]
            if entry_ids:
                marks = ",".join("?" for _ in entry_ids)
                db.execute(f"DELETE FROM journal_lines WHERE entry_id IN ({marks})", entry_ids)
                db.execute(f"DELETE FROM journal_entries WHERE id IN ({marks})", entry_ids)
            deleted = db.execute("SELECT COUNT(*) n FROM invoices").fetchone()["n"]
            db.execute("DELETE FROM invoices")
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)", (user_id,"replace","invoice_import",json.dumps({"deleted":deleted,"backup":backup_path}),utcnow()))
            return {"deleted": deleted, "backup": backup_path}

    def import_invoice(self, item, user_id):
        # No uniqueness constraint is applied to invoice numbers: duplicates are intentionally retained.
        with self.connect() as db:
            party_kind = "customer" if item["kind"] == "sale" else "supplier"
            db.execute("INSERT OR IGNORE INTO parties(kind,name,currency) VALUES(?,?,?)", (party_kind, item.get("party_name") or "Unspecified", item.get("currency", "USD")))
            party = db.execute("SELECT id FROM parties WHERE kind=? AND name=?", (party_kind, item.get("party_name") or "Unspecified")).fetchone()
            subtotal = Decimal(str(item.get("subtotal") or 0)); vat = Decimal(str(item.get("vat") or 0)); total = Decimal(str(item.get("total") or subtotal + vat))
            currency_issue = str(item.get("currency_issue") or "")
            status = "posted" if total == subtotal + vat and not currency_issue.startswith(("conflicting:", "unsupported:")) else "review"
            supplier_account = str(item.get("supplier_account") or DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]).strip()
            vat_account = str(item.get("vat_account") or DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"]).strip()
            expense_account = str(item.get("expense_account") or DEFAULT_LEBANESE_ACCOUNTS["purchases"]).strip()
            account_definitions = [
                (supplier_account, "Supplier Account", "liability"),
                (vat_account, "VAT Account", "asset"),
                (expense_account, "Expense Account", "expense"),
            ]
            for code, name, account_type in account_definitions:
                db.execute(
                    "INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",
                    (code, name, account_type),
                )
            cur = db.execute("""INSERT INTO invoices(invoice_number,kind,invoice_date,party_id,currency,exchange_rate,subtotal,vat,total,status,currency_issue,supplier_account,vat_account,expense_account,source_file,source_row,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                str(item["invoice_number"]), item["kind"], item.get("invoice_date"), party["id"], item.get("currency", "USD"),
                str(item.get("exchange_rate", 1)), str(item.get("subtotal") or 0), str(item.get("vat") or 0), str(item.get("total") or 0),
                status, currency_issue, supplier_account, vat_account, expense_account,
                item.get("source_file"), item.get("source_row"), user_id, utcnow()))
            invoice_id = cur.lastrowid
            entry_number = f"INV-{invoice_id}"
            entry = db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (entry_number, item.get("invoice_date"), f"{item['kind'].title()} invoice {item['invoice_number']}", "invoice", invoice_id, item.get("currency", "USD"), user_id, utcnow()))
            if item["kind"] == "sale":
                lines = [(DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"], total, 0), (DEFAULT_LEBANESE_ACCOUNTS["sales"], 0, subtotal), (DEFAULT_LEBANESE_ACCOUNTS["vat_payable"], 0, vat)]
            else:
                lines = [(expense_account, subtotal, 0), (vat_account, vat, 0), (supplier_account, 0, total)]
            difference = sum(x[1] for x in lines) - sum(x[2] for x in lines)
            if difference > 0:
                lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"], 0, difference))
            elif difference < 0:
                lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"], -difference, 0))
            for code, debit, credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)", (entry.lastrowid, self._account_id(db, code), party["id"], str(debit), str(credit)))
            debit_total = sum(x[1] for x in lines); credit_total = sum(x[2] for x in lines)
            if debit_total != credit_total:
                raise ValueError(f"Unbalanced journal entry for invoice {item['invoice_number']}")
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (user_id, "import", "invoice", invoice_id, json.dumps({"source_file": item.get("source_file"), "source_row": item.get("source_row")}), utcnow()))
            return invoice_id

    def create_manual_invoice(self, item, line_items, user_id):
        if not isinstance(line_items, list) or not line_items:
            raise ValueError("Add at least one invoice item")
        normalized = []
        subtotal_total = Decimal("0")
        vat_total = Decimal("0")
        for index, line in enumerate(line_items, start=1):
            description = str(line.get("description") or "").strip()
            if not description:
                raise ValueError(f"Item {index}: description is required")
            try:
                quantity = Decimal(str(line.get("quantity") or 0))
                unit_price = Decimal(str(line.get("unit_price") or 0))
                vat_rate = Decimal(str(line.get("vat_rate") if line.get("vat_rate") not in (None, "") else 11))
            except Exception as exc:
                raise ValueError(f"Item {index}: invalid quantity, price, or VAT rate") from exc
            if quantity <= 0 or unit_price < 0 or vat_rate < 0:
                raise ValueError(f"Item {index}: values cannot be negative and quantity must be above zero")
            calculated_subtotal = (quantity * unit_price).quantize(Decimal("0.01"))
            supplied_subtotal = line.get("subtotal")
            subtotal = calculated_subtotal if supplied_subtotal in (None, "") else Decimal(str(supplied_subtotal)).quantize(Decimal("0.01"))
            if subtotal < 0:
                raise ValueError(f"Item {index}: total before VAT cannot be negative")
            supplied_vat = line.get("vat")
            vat = (subtotal * vat_rate / Decimal("100")).quantize(Decimal("0.01")) if supplied_vat in (None, "") else Decimal(str(supplied_vat)).quantize(Decimal("0.01"))
            if vat < 0:
                raise ValueError(f"Item {index}: VAT cannot be negative")
            total = subtotal + vat
            normalized.append((description, quantity, unit_price, subtotal, vat_rate, vat, total))
            subtotal_total += subtotal
            vat_total += vat
        invoice = dict(item)
        invoice["subtotal"] = float(subtotal_total)
        invoice["vat"] = float(vat_total)
        invoice["total"] = float(subtotal_total + vat_total)
        invoice_id = self.import_invoice(invoice, user_id)
        with self.connect() as db:
            db.executemany("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,vat_rate,vat,total)
                VALUES(?,?,?,?,?,?,?,?)""", [
                (invoice_id, description, str(quantity), str(unit_price), str(subtotal), str(vat_rate), str(vat), str(total))
                for description, quantity, unit_price, subtotal, vat_rate, vat, total in normalized
            ])
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "manual_entry", "invoice", invoice_id, json.dumps({"items": len(normalized)}), utcnow()))
        return invoice_id

    def update_invoice(self, invoice_id, item, user_id):
        required = ("invoice_number", "invoice_date", "party_name", "kind", "currency")
        missing = [field for field in required if not str(item.get(field) or "").strip()]
        if missing:
            raise ValueError("Missing fields: " + ", ".join(missing))
        kind = str(item["kind"]).lower()
        currency = str(item["currency"]).upper()
        if kind not in ("sale", "purchase"):
            raise ValueError("Type must be sale or purchase")
        if currency not in ("USD", "EUR", "LBP", "AED"):
            raise ValueError("Currency must be USD, EUR, LBP, or AED")
        try:
            subtotal = Decimal(str(item.get("subtotal") or 0))
            vat = Decimal(str(item.get("vat") or 0))
            total = Decimal(str(item.get("total") or 0))
        except Exception as exc:
            raise ValueError("Before VAT, VAT, and Total must be valid numbers") from exc
        if min(subtotal, vat, total) < 0:
            raise ValueError("Amounts cannot be negative")
        if total != subtotal + vat:
            raise ValueError("Total must equal Before VAT plus VAT")
        supplier_account = str(item.get("supplier_account") or DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]).strip()
        vat_account = str(item.get("vat_account") or DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"]).strip()
        expense_account = str(item.get("expense_account") or DEFAULT_LEBANESE_ACCOUNTS["purchases"]).strip()
        status = str(item.get("status") or "posted").strip().lower()
        if status not in ("posted", "review"):
            raise ValueError("Status must be posted or review")
        with self.connect() as db:
            existing = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not existing:
                raise KeyError(invoice_id)
            party_kind = "customer" if kind == "sale" else "supplier"
            party_name = str(item["party_name"]).strip()
            db.execute("INSERT OR IGNORE INTO parties(kind,name,currency) VALUES(?,?,?)", (party_kind, party_name, currency))
            party = db.execute("SELECT id FROM parties WHERE kind=? AND name=?", (party_kind, party_name)).fetchone()
            for code, name, account_type in (
                (supplier_account, "Supplier Account", "liability"),
                (vat_account, "VAT Account", "asset"),
                (expense_account, "Expense Account", "expense"),
            ):
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)", (code, name, account_type))
            db.execute("""UPDATE invoices SET invoice_number=?,kind=?,invoice_date=?,party_id=?,currency=?,
                subtotal=?,vat=?,total=?,status=?,supplier_account=?,vat_account=?,expense_account=? WHERE id=?""",
                (str(item["invoice_number"]).strip(), kind, str(item["invoice_date"]).strip(), party["id"], currency,
                 str(subtotal), str(vat), str(total), status, supplier_account, vat_account, expense_account, invoice_id))
            entry = db.execute("SELECT id FROM journal_entries WHERE source_type='invoice' AND source_id=?", (invoice_id,)).fetchone()
            description = f"{kind.title()} invoice {str(item['invoice_number']).strip()}"
            if entry:
                entry_id = entry["id"]
                db.execute("DELETE FROM journal_lines WHERE entry_id=?", (entry_id,))
                db.execute("UPDATE journal_entries SET entry_date=?,description=?,currency=? WHERE id=?",
                           (str(item["invoice_date"]).strip(), description, currency, entry_id))
            else:
                created = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""", (f"INV-{invoice_id}", str(item["invoice_date"]).strip(), description,
                    "invoice", invoice_id, currency, user_id, utcnow()))
                entry_id = created.lastrowid
            if kind == "sale":
                lines = [(DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"], total, Decimal("0")), (DEFAULT_LEBANESE_ACCOUNTS["sales"], Decimal("0"), subtotal), (DEFAULT_LEBANESE_ACCOUNTS["vat_payable"], Decimal("0"), vat)]
            else:
                lines = [(expense_account, subtotal, Decimal("0")), (vat_account, vat, Decimal("0")), (supplier_account, Decimal("0"), total)]
            for code, debit, credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)",
                           (entry_id, self._account_id(db, code), party["id"], str(debit), str(credit)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id, "update", "invoice", invoice_id, json.dumps({"fields": sorted(item.keys())}), utcnow()))
            row = db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.kind,i.currency,
                i.subtotal,i.vat,i.total,i.status,i.currency_issue,i.supplier_account,i.vat_account,
                i.expense_account,i.source_row FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""",
                (invoice_id,)).fetchone()
            return dict(row)

    def add_invoice_item(self, invoice_id, line, user_id):
        description = str(line.get("description") or "").strip()
        if not description:
            raise ValueError("Description is required")
        try:
            quantity = Decimal(str(line.get("quantity") or 0))
            unit_price = Decimal(str(line.get("unit_price") or 0))
            subtotal = Decimal(str(line.get("subtotal") if line.get("subtotal") not in (None, "") else quantity * unit_price))
            vat_rate = Decimal(str(line.get("vat_rate") if line.get("vat_rate") not in (None, "") else 11))
            vat = Decimal(str(line.get("vat") if line.get("vat") not in (None, "") else subtotal * vat_rate / Decimal("100")))
        except Exception as exc:
            raise ValueError("Invalid item amount") from exc
        if quantity <= 0 or min(unit_price, subtotal, vat, vat_rate) < 0:
            raise ValueError("Item values cannot be negative and quantity must be above zero")
        subtotal = subtotal.quantize(Decimal("0.01")); vat = vat.quantize(Decimal("0.01"))
        total = subtotal + vat
        with self.connect() as db:
            row = db.execute("""SELECT i.*,p.name party_name FROM invoices i
                LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            invoice = dict(row)
        updated_values = {
            "invoice_number": invoice["invoice_number"], "invoice_date": invoice["invoice_date"],
            "party_name": invoice["party_name"], "kind": invoice["kind"], "currency": invoice["currency"],
            "subtotal": str(Decimal(str(invoice["subtotal"] or 0)) + subtotal),
            "vat": str(Decimal(str(invoice["vat"] or 0)) + vat),
            "total": str(Decimal(str(invoice["total"] or 0)) + total),
            "supplier_account": invoice["supplier_account"], "vat_account": invoice["vat_account"],
            "expense_account": invoice["expense_account"], "status": "posted",
        }
        updated = self.update_invoice(invoice_id, updated_values, user_id)
        with self.connect() as db:
            db.execute("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,vat_rate,vat,total)
                VALUES(?,?,?,?,?,?,?,?)""", (invoice_id, description, str(quantity), str(unit_price),
                str(subtotal), str(vat_rate), str(vat), str(total)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id, "add_item", "invoice", invoice_id, json.dumps({"description": description}), utcnow()))
        return updated

    def list_parties(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,kind,name,currency FROM parties ORDER BY name,kind")]

    def statement_of_account(self, party_id, from_date=None, to_date=None, currency=None):
        normalized_date = """CASE
            WHEN i.invoice_date GLOB '??-??-????'
                THEN substr(i.invoice_date,7,4)||'-'||substr(i.invoice_date,4,2)||'-'||substr(i.invoice_date,1,2)
            ELSE i.invoice_date END"""
        filters = ["i.party_id=?"]
        parameters = [party_id]
        if currency:
            filters.append("i.currency=?"); parameters.append(currency)
        if to_date:
            filters.append(f"{normalized_date} <= ?"); parameters.append(to_date)
        with self.connect() as db:
            party = db.execute("SELECT id,kind,name,currency FROM parties WHERE id=?", (party_id,)).fetchone()
            if not party:
                raise KeyError(party_id)
            rows = [dict(row) for row in db.execute(f"""SELECT i.id,i.invoice_number,i.invoice_date,i.kind,
                i.currency,i.total FROM invoices i WHERE {' AND '.join(filters)}
                ORDER BY {normalized_date},i.id""", parameters)]
        opening = {}
        items = []
        for row in rows:
            normalized = row["invoice_date"]
            try:
                normalized = datetime.strptime(normalized, "%d-%m-%Y").strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass
            amount = Decimal(str(row["total"] or 0))
            debit = amount if row["kind"] == "sale" else Decimal("0")
            credit = amount if row["kind"] == "purchase" else Decimal("0")
            if from_date and normalized < from_date:
                opening[row["currency"]] = opening.get(row["currency"], Decimal("0")) + debit - credit
                continue
            items.append({**row, "description": f"{row['kind'].title()} invoice {row['invoice_number']}",
                          "debit": float(debit), "credit": float(credit)})
        balances = dict(opening)
        for row in items:
            code = row["currency"]
            balances[code] = balances.get(code, Decimal("0")) + Decimal(str(row["debit"])) - Decimal(str(row["credit"]))
            row["balance"] = float(balances[code])
        return {"party": dict(party), "opening": {key: float(value) for key,value in opening.items()}, "items": items}

    def list_invoices(self, limit=500):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.kind,i.currency,i.subtotal,i.vat,i.total,
                CASE WHEN i.kind='sale' THEN CAST(i.total AS REAL) ELSE 0 END debit,
                CASE WHEN i.kind='purchase' THEN CAST(i.total AS REAL) ELSE 0 END credit,
                i.status,i.currency_issue,i.supplier_account,i.vat_account,i.expense_account,i.source_row
                FROM invoices i LEFT JOIN parties p ON p.id=i.party_id ORDER BY i.id DESC LIMIT ?""", (limit,))]

    def list_accounts(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT a.code,a.name_en,a.name_ar,a.name_fr,a.type,
                p.code parent_code FROM accounts a LEFT JOIN accounts p ON p.id=a.parent_id
                ORDER BY CASE WHEN instr(a.code,'.')>0 THEN replace(a.code,'.','') ELSE a.code END""")]

    def dashboard(self):
        with self.connect() as db:
            rows = db.execute("""SELECT kind,currency,SUM(CAST(subtotal AS REAL)) subtotal,
                SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total,COUNT(*) count,
                SUM(CASE WHEN kind='sale' THEN CAST(total AS REAL) ELSE 0 END) debit,
                SUM(CASE WHEN kind='purchase' THEN CAST(total AS REAL) ELSE 0 END) credit
                FROM invoices GROUP BY kind,currency""").fetchall()
            return [dict(r) for r in rows]

    def journal(self, from_date=None, to_date=None, currency=None, limit=5000):
        """Return journal lines with a running balance per account and currency."""
        conditions = []
        parameters = []
        normalized_date = """CASE
            WHEN e.entry_date GLOB '??-??-????'
                THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if from_date:
            conditions.append(f"{normalized_date} >= ?")
            parameters.append(from_date)
        if to_date:
            conditions.append(f"{normalized_date} <= ?")
            parameters.append(to_date)
        if currency:
            conditions.append("e.currency = ?")
            parameters.append(currency)
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        parameters.append(int(limit))
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(f"""SELECT e.id entry_id,e.entry_number,e.entry_date,
                e.description,e.source_type,e.source_id,e.currency,a.code account_code,a.name_en account_name,
                COALESCE(p.name,'') party_name,CAST(j.debit AS REAL) debit,CAST(j.credit AS REAL) credit,j.id line_id
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id
                JOIN accounts a ON a.id=j.account_id LEFT JOIN parties p ON p.id=j.party_id
                {where_clause}
                ORDER BY {normalized_date},e.id,j.id LIMIT ?""", parameters)]
        balances = {}
        for row in rows:
            key = (row["currency"], row["account_code"])
            balances[key] = balances.get(key, Decimal("0")) + Decimal(str(row["debit"] or 0)) - Decimal(str(row["credit"] or 0))
            row["balance"] = float(balances[key])
            row.pop("line_id", None)
        return rows

    def trial_balance(self, from_date=None, to_date=None):
        conditions = []
        parameters = []
        normalized_date = """CASE
            WHEN e.entry_date GLOB '??-??-????'
                THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if from_date:
            conditions.append(f"{normalized_date} >= ?")
            parameters.append(from_date)
        if to_date:
            conditions.append(f"{normalized_date} <= ?")
            parameters.append(to_date)
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            rows = db.execute(f"""SELECT a.code,a.name_en,e.currency,SUM(CAST(j.debit AS REAL)) debit,SUM(CAST(j.credit AS REAL)) credit,
                SUM(CAST(j.debit AS REAL)-CAST(j.credit AS REAL)) balance
                FROM journal_lines j JOIN accounts a ON a.id=j.account_id JOIN journal_entries e ON e.id=j.entry_id
                {where_clause}
                GROUP BY a.id,e.currency ORDER BY e.currency,a.code""", parameters).fetchall()
            return [dict(r) for r in rows]
