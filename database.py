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
 subtotal TEXT, vat TEXT, total TEXT, status TEXT NOT NULL DEFAULT 'posted', source_file TEXT, source_row INTEGER,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
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

DEFAULT_ACCOUNTS = [
    ("1100", "Accounts Receivable", "ذمم العملاء", "Clients", "asset"),
    ("1200", "Inventory", "المخزون", "Stock", "asset"),
    ("2100", "Accounts Payable", "ذمم الموردين", "Fournisseurs", "liability"),
    ("2200", "VAT Payable", "ضريبة مستحقة", "TVA à payer", "liability"),
    ("1300", "VAT Receivable", "ضريبة قابلة للاسترداد", "TVA déductible", "asset"),
    ("4100", "Sales Revenue", "إيرادات المبيعات", "Ventes", "income"),
    ("5100", "Purchases", "المشتريات", "Achats", "expense"),
    ("9999", "Import Variance", "فروقات الاستيراد", "Écart d'importation", "expense"),
]

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
            db.execute("INSERT OR IGNORE INTO users(username,password_hash,role) VALUES(?,?,?)", ("admin", hash_password(admin_password), "admin"))
            db.executemany("INSERT OR IGNORE INTO accounts(code,name_en,name_ar,name_fr,type) VALUES(?,?,?,?,?)", DEFAULT_ACCOUNTS)

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
            status = "posted" if total == subtotal + vat else "review"
            cur = db.execute("""INSERT INTO invoices(invoice_number,kind,invoice_date,party_id,currency,exchange_rate,subtotal,vat,total,status,source_file,source_row,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                str(item["invoice_number"]), item["kind"], item.get("invoice_date"), party["id"], item.get("currency", "USD"),
                str(item.get("exchange_rate", 1)), str(item.get("subtotal") or 0), str(item.get("vat") or 0), str(item.get("total") or 0),
                status, item.get("source_file"), item.get("source_row"), user_id, utcnow()))
            invoice_id = cur.lastrowid
            entry_number = f"INV-{invoice_id}"
            entry = db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (entry_number, item.get("invoice_date"), f"{item['kind'].title()} invoice {item['invoice_number']}", "invoice", invoice_id, item.get("currency", "USD"), user_id, utcnow()))
            if item["kind"] == "sale":
                lines = [("1100", total, 0), ("4100", 0, subtotal), ("2200", 0, vat)]
            else:
                lines = [("5100", subtotal, 0), ("1300", vat, 0), ("2100", 0, total)]
            difference = sum(x[1] for x in lines) - sum(x[2] for x in lines)
            if difference > 0:
                lines.append(("9999", 0, difference))
            elif difference < 0:
                lines.append(("9999", -difference, 0))
            for code, debit, credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)", (entry.lastrowid, self._account_id(db, code), party["id"], str(debit), str(credit)))
            debit_total = sum(x[1] for x in lines); credit_total = sum(x[2] for x in lines)
            if debit_total != credit_total:
                raise ValueError(f"Unbalanced journal entry for invoice {item['invoice_number']}")
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (user_id, "import", "invoice", invoice_id, json.dumps({"source_file": item.get("source_file"), "source_row": item.get("source_row")}), utcnow()))
            return invoice_id

    def list_invoices(self, limit=500):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.kind,i.currency,i.subtotal,i.vat,i.total,i.source_row
                FROM invoices i LEFT JOIN parties p ON p.id=i.party_id ORDER BY i.id DESC LIMIT ?""", (limit,))]

    def dashboard(self):
        with self.connect() as db:
            rows = db.execute("SELECT kind,currency,SUM(CAST(subtotal AS REAL)) subtotal,SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total,COUNT(*) count FROM invoices GROUP BY kind,currency").fetchall()
            return [dict(r) for r in rows]

    def trial_balance(self):
        with self.connect() as db:
            rows = db.execute("""SELECT a.code,a.name_en,SUM(CAST(j.debit AS REAL)) debit,SUM(CAST(j.credit AS REAL)) credit,
                SUM(CAST(j.debit AS REAL)-CAST(j.credit AS REAL)) balance FROM accounts a LEFT JOIN journal_lines j ON j.account_id=a.id
                GROUP BY a.id ORDER BY a.code""").fetchall()
            return [dict(r) for r in rows]
