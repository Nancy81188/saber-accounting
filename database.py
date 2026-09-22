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

EXPENSE_ACCOUNT_9 = "601100000"
VAT_ACCOUNT_9 = "442660000"

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','accountant','viewer')), language TEXT NOT NULL DEFAULT 'en', active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parties (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('customer','supplier','both')),
 name TEXT NOT NULL, tax_number TEXT, currency TEXT NOT NULL DEFAULT 'USD', account_number TEXT, UNIQUE(kind,name)
);
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name_en TEXT NOT NULL, name_ar TEXT, name_fr TEXT,
 type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')), parent_id INTEGER REFERENCES accounts(id), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY, invoice_number TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('sale','purchase')),
 invoice_date TEXT, party_id INTEGER REFERENCES parties(id), currency TEXT NOT NULL, exchange_rate TEXT NOT NULL DEFAULT '1',
 subtotal TEXT, vat TEXT, total TEXT, status TEXT NOT NULL DEFAULT 'posted', currency_issue TEXT NOT NULL DEFAULT '',
 supplier_account TEXT NOT NULL DEFAULT '4011', vat_account TEXT NOT NULL DEFAULT '442660000', expense_account TEXT NOT NULL DEFAULT '601100000',
 entry_type TEXT NOT NULL DEFAULT 'purchase', debit_override TEXT, credit_override TEXT,
 source_file TEXT, source_row INTEGER, due_date TEXT, payment_status TEXT NOT NULL DEFAULT 'unpaid',
 amount_paid TEXT NOT NULL DEFAULT '0', cancelled_at TEXT, cancellation_reason TEXT,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_items (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 description TEXT NOT NULL, quantity TEXT NOT NULL, unit_price TEXT NOT NULL,
 subtotal TEXT NOT NULL, vat_rate TEXT NOT NULL, vat TEXT NOT NULL, total TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_attachments (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 file_name TEXT NOT NULL, mime_type TEXT NOT NULL, content BLOB NOT NULL,
 uploaded_by INTEGER REFERENCES users(id), uploaded_at TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS fiscal_years (
 id INTEGER PRIMARY KEY, year INTEGER NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'open',
 opened_at TEXT NOT NULL, closed_at TEXT, closed_by INTEGER REFERENCES users(id), details TEXT
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('customer_receipt','supplier_payment')),
 party_id INTEGER NOT NULL REFERENCES parties(id), payment_date TEXT NOT NULL, currency TEXT NOT NULL,
 amount TEXT NOT NULL, cash_account TEXT NOT NULL, party_account TEXT NOT NULL,
 reference TEXT, description TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY, expense_date TEXT NOT NULL, description TEXT NOT NULL, category TEXT,
 currency TEXT NOT NULL, subtotal TEXT NOT NULL, vat TEXT NOT NULL, total TEXT NOT NULL,
 expense_account TEXT NOT NULL, vat_account TEXT NOT NULL, payment_account TEXT NOT NULL,
 reference TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exchange_rates (
 id INTEGER PRIMARY KEY, rate_date TEXT NOT NULL, from_currency TEXT NOT NULL, to_currency TEXT NOT NULL,
 rate TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(rate_date,from_currency,to_currency)
);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
            lifecycle_columns = {
                "due_date": "TEXT",
                "payment_status": "TEXT NOT NULL DEFAULT 'unpaid'",
                "amount_paid": "TEXT NOT NULL DEFAULT '0'",
                "cancelled_at": "TEXT",
                "cancellation_reason": "TEXT",
                "entry_type": "TEXT NOT NULL DEFAULT 'purchase'",
                "debit_override": "TEXT",
                "credit_override": "TEXT",
            }
            for column, definition in lifecycle_columns.items():
                if column not in invoice_columns:
                    db.execute(f"ALTER TABLE invoices ADD COLUMN {column} {definition}")
            party_columns={row["name"] for row in db.execute("PRAGMA table_info(parties)")}
            if "account_number" not in party_columns:
                db.execute("ALTER TABLE parties ADD COLUMN account_number TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_parties_account_number ON parties(account_number) WHERE account_number IS NOT NULL")
            db.execute("INSERT OR IGNORE INTO users(username,password_hash,role) VALUES(?,?,?)", ("admin", hash_password(admin_password), "admin"))
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('base_currency','USD')")
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('backup_interval_hours','24')")
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('last_scheduled_backup','')")
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
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='6011'))",
                       (EXPENSE_ACCOUNT_9,"General Expenses - 9 Digit","expense"))
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='4426.6'))",
                       (VAT_ACCOUNT_9,"VAT Receivable - 9 Digit","asset"))
            db.execute("UPDATE invoices SET expense_account=? WHERE expense_account='6011'",(EXPENSE_ACCOUNT_9,))
            db.execute("UPDATE invoices SET vat_account=? WHERE vat_account='4426.6'",(VAT_ACCOUNT_9,))
            db.execute("UPDATE invoices SET entry_type=kind WHERE entry_type IS NULL OR entry_type='' OR (entry_type='purchase' AND kind='sale')")
            suppliers=db.execute("SELECT id,name,account_number FROM parties WHERE kind IN ('supplier','both') ORDER BY id").fetchall()
            for supplier in suppliers:
                account_number=supplier["account_number"] or f"4011{supplier['id']:05d}"
                db.execute("UPDATE parties SET account_number=? WHERE id=?",(account_number,supplier["id"]))
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='4011'))",
                    (account_number,f"Supplier - {supplier['name']}","liability"))
                db.execute("UPDATE invoices SET supplier_account=? WHERE party_id=? AND kind='purchase' AND supplier_account='4011'",
                    (account_number,supplier["id"]))

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

    def list_users(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,username,role,language,active FROM users ORDER BY username")]

    def save_user(self, item, acting_user_id):
        username=str(item.get("username") or "").strip(); role=str(item.get("role") or "viewer").strip()
        language=str(item.get("language") or "en").strip(); password=str(item.get("password") or "")
        active=1 if item.get("active",True) else 0; user_id=item.get("id")
        if not username or role not in ("admin","accountant","viewer") or language not in ("en","ar","fr"):
            raise ValueError("Enter a valid username, role, and language")
        with self.connect() as db:
            if user_id:
                if password:
                    db.execute("UPDATE users SET username=?,role=?,language=?,active=?,password_hash=? WHERE id=?",
                        (username,role,language,active,hash_password(password),int(user_id)))
                else:
                    db.execute("UPDATE users SET username=?,role=?,language=?,active=? WHERE id=?",
                        (username,role,language,active,int(user_id)))
                saved_id=int(user_id)
            else:
                if not password: raise ValueError("Password is required for a new user")
                saved_id=db.execute("INSERT INTO users(username,password_hash,role,language,active) VALUES(?,?,?,?,?)",
                    (username,hash_password(password),role,language,active)).lastrowid
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (acting_user_id,"save","user",saved_id,json.dumps({"username":username,"role":role,"active":active}),utcnow()))
        return next(row for row in self.list_users() if row["id"]==saved_id)

    def _account_id(self, db, code):
        row = db.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()
        return row["id"]

    def _ensure_party_account(self, db, party):
        if party["kind"] not in ("supplier","both"): return None
        account_number=party["account_number"] or f"4011{party['id']:05d}"
        db.execute("UPDATE parties SET account_number=? WHERE id=?",(account_number,party["id"]))
        db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='4011'))",
            (account_number,f"Supplier - {party['name']}","liability"))
        return account_number

    def _date_year(self, value):
        text = str(value or "").strip()
        for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
            try: return datetime.strptime(text, pattern).year
            except ValueError: pass
        raise ValueError("Date must use DD-MM-YYYY")

    def _assert_period_open(self, value):
        year = self._date_year(value)
        with self.connect() as db:
            row = db.execute("SELECT status FROM fiscal_years WHERE year=?", (year,)).fetchone()
        if row and row["status"] == "closed":
            raise ValueError(f"Fiscal year {year} is closed; entries cannot be added or changed")

    def next_invoice_number(self, kind="sale", invoice_date=None):
        prefix = "SAL" if kind == "sale" else "PUR"
        year = str(invoice_date or datetime.now().year)
        if "-" in year:
            year = year[-4:] if year[:4].isdigit() is False else year[:4]
        if not year.isdigit() or len(year) != 4:
            year = str(datetime.now().year)
        pattern = f"{prefix}-{year}-%"
        with self.connect() as db:
            values = [row["invoice_number"] for row in db.execute(
                "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?", (pattern,))]
        sequence = 1
        for value in values:
            try: sequence = max(sequence, int(value.rsplit("-", 1)[-1]) + 1)
            except (TypeError, ValueError): pass
        return f"{prefix}-{year}-{sequence:06d}"

    def backup(self):
        source = Path(self.path)
        if not source.exists(): return None
        folder = source.parent / "backups"; folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"saber_accounting_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
        shutil.copy2(source, target)
        return str(target)

    def list_backups(self):
        folder=Path(self.path).parent/"backups"
        if not folder.exists(): return []
        return [{"name":path.name,"size":path.stat().st_size,"modified":datetime.fromtimestamp(path.stat().st_mtime).isoformat()}
                for path in sorted(folder.glob("saber_accounting_*.db"),reverse=True)]

    def restore_backup(self, name, user_id):
        folder=(Path(self.path).parent/"backups").resolve(); source=(folder/Path(str(name)).name).resolve()
        if source.parent!=folder or not source.exists(): raise ValueError("Backup was not found")
        safety=self.backup(); shutil.copy2(source,self.path)
        with self.connect() as db:
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"restore","database",json.dumps({"backup":source.name,"safety_backup":safety}),utcnow()))
        return {"restored":source.name,"safety_backup":safety}

    def settings(self):
        with self.connect() as db: return {row["key"]:row["value"] for row in db.execute("SELECT key,value FROM app_settings")}

    def save_settings(self, values, user_id):
        allowed={"base_currency","backup_interval_hours"}
        if str(values.get("base_currency") or "USD") not in ("USD","EUR","LBP","AED"): raise ValueError("Invalid base currency")
        try: hours=int(values.get("backup_interval_hours",24))
        except Exception as exc: raise ValueError("Backup interval must be a number") from exc
        if hours<1 or hours>720: raise ValueError("Backup interval must be between 1 and 720 hours")
        with self.connect() as db:
            for key in allowed:
                if key in values: db.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(values[key])))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"update","settings",json.dumps({key:values[key] for key in allowed if key in values}),utcnow()))
        return self.settings()

    def maybe_scheduled_backup(self):
        settings=self.settings(); hours=int(settings.get("backup_interval_hours","24")); last=settings.get("last_scheduled_backup","")
        try: due=(datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()>=hours*3600
        except Exception: due=True
        if due:
            path=self.backup()
            with self.connect() as db:
                db.execute("INSERT INTO app_settings(key,value) VALUES('last_scheduled_backup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(utcnow(),))
            return path
        return None

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
        self._assert_period_open(item.get("invoice_date"))
        with self.connect() as db:
            entry_type=str(item.get("entry_type") or item.get("kind") or "purchase").strip().lower().replace(" ","_")
            if entry_type not in ("sale","purchase","assets","expenses","expense_without_vat"): entry_type="purchase"
            kind="sale" if entry_type=="sale" else "purchase"
            party_kind = "customer" if kind == "sale" else "supplier"
            db.execute("INSERT OR IGNORE INTO parties(kind,name,currency) VALUES(?,?,?)", (party_kind, item.get("party_name") or "Unspecified", item.get("currency", "USD")))
            party = db.execute("SELECT * FROM parties WHERE kind=? AND name=?", (party_kind, item.get("party_name") or "Unspecified")).fetchone()
            subtotal = Decimal(str(item.get("subtotal") or 0)); vat = Decimal(str(item.get("vat") or 0)); total = Decimal(str(item.get("total") or subtotal + vat))
            currency_issue = str(item.get("currency_issue") or "")
            status = "posted" if total == subtotal + vat and not currency_issue.startswith(("conflicting:", "unsupported:")) else "review"
            supplier_account = str(item.get("supplier_account") or DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]).strip()
            party_account=self._ensure_party_account(db,party)
            if kind=="purchase" and (not item.get("supplier_account") or supplier_account==DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]):
                supplier_account=party_account
            vat_account = str(item.get("vat_account") or VAT_ACCOUNT_9).strip()
            expense_account = str(item.get("expense_account") or EXPENSE_ACCOUNT_9).strip()
            if entry_type=="expense_without_vat": vat=Decimal("0"); total=subtotal
            account_definitions = [
                (supplier_account, "Supplier Account", "liability"),
                (vat_account, "VAT Account", "asset"),
                (expense_account, "Asset Account" if entry_type=="assets" else "Expense Account", "asset" if entry_type=="assets" else "expense"),
            ]
            for code, name, account_type in account_definitions:
                db.execute(
                    "INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",
                    (code, name, account_type),
                )
            due_date = str(item.get("due_date") or "").strip() or None
            amount_paid = Decimal(str(item.get("amount_paid") or 0))
            if amount_paid < 0 or amount_paid > total:
                raise ValueError("Amount paid must be between zero and invoice total")
            payment_status = "paid" if amount_paid == total and total > 0 else "partial" if amount_paid > 0 else "unpaid"
            debit_override=item.get("debit"); credit_override=item.get("credit")
            cur = db.execute("""INSERT INTO invoices(invoice_number,kind,invoice_date,party_id,currency,exchange_rate,subtotal,vat,total,status,currency_issue,supplier_account,vat_account,expense_account,entry_type,debit_override,credit_override,source_file,source_row,due_date,payment_status,amount_paid,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                str(item["invoice_number"]), kind, item.get("invoice_date"), party["id"], item.get("currency", "USD"),
                str(item.get("exchange_rate", 1)), str(subtotal), str(vat), str(total),
                status, currency_issue, supplier_account, vat_account, expense_account,entry_type,
                None if debit_override in (None,"") else str(Decimal(str(debit_override))),None if credit_override in (None,"") else str(Decimal(str(credit_override))),
                item.get("source_file"), item.get("source_row"), due_date, payment_status, str(amount_paid), user_id, utcnow()))
            invoice_id = cur.lastrowid
            entry_number = f"INV-{invoice_id}"
            entry = db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (entry_number, item.get("invoice_date"), f"{entry_type.replace('_',' ').title()} {item['invoice_number']}", "invoice", invoice_id, item.get("currency", "USD"), user_id, utcnow()))
            if kind == "sale":
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
        if not str(invoice.get("invoice_number") or "").strip():
            invoice["invoice_number"] = self.next_invoice_number(invoice.get("kind", "sale"), invoice.get("invoice_date"))
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
        self._assert_period_open(item.get("invoice_date"))
        entry_type=str(item.get("entry_type") or item["kind"]).lower().replace(" ","_")
        if entry_type not in ("sale","purchase","assets","expenses","expense_without_vat"):
            raise ValueError("Type must be Sale, Purchase, Assets, Expenses, or Expense without VAT")
        kind = "sale" if entry_type=="sale" else "purchase"
        currency = str(item["currency"]).upper()
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
        if entry_type=="expense_without_vat": vat=Decimal("0"); total=subtotal
        supplier_account = str(item.get("supplier_account") or DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]).strip()
        vat_account = str(item.get("vat_account") or VAT_ACCOUNT_9).strip()
        expense_account = str(item.get("expense_account") or EXPENSE_ACCOUNT_9).strip()
        debit_override=Decimal(str(item.get("debit") or 0)); credit_override=Decimal(str(item.get("credit") or 0))
        if debit_override<0 or credit_override<0: raise ValueError("D and C cannot be negative")
        status = str(item.get("status") or "posted").strip().lower()
        if status not in ("posted", "review"):
            raise ValueError("Status must be posted or review")
        due_date = str(item.get("due_date") or "").strip() or None
        amount_paid = Decimal(str(item.get("amount_paid") or 0))
        if amount_paid < 0 or amount_paid > total:
            raise ValueError("Amount paid must be between zero and invoice total")
        payment_status = "paid" if amount_paid == total and total > 0 else "partial" if amount_paid > 0 else "unpaid"
        with self.connect() as db:
            existing = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not existing:
                raise KeyError(invoice_id)
            if existing["status"] == "cancelled":
                raise ValueError("Cancelled invoices cannot be edited")
            party_kind = "customer" if kind == "sale" else "supplier"
            party_name = str(item["party_name"]).strip()
            db.execute("INSERT OR IGNORE INTO parties(kind,name,currency) VALUES(?,?,?)", (party_kind, party_name, currency))
            party = db.execute("SELECT * FROM parties WHERE kind=? AND name=?", (party_kind, party_name)).fetchone()
            party_account = self._ensure_party_account(db, party)
            if kind == "purchase" and supplier_account == DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"] and party_account:
                supplier_account = party_account
            for code, name, account_type in (
                (supplier_account, "Supplier Account", "liability"),
                (vat_account, "VAT Account", "asset"),
                (expense_account, "Asset Account" if entry_type=="assets" else "Expense Account", "asset" if entry_type=="assets" else "expense"),
            ):
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)", (code, name, account_type))
            db.execute("""UPDATE invoices SET invoice_number=?,kind=?,invoice_date=?,party_id=?,currency=?,
                subtotal=?,vat=?,total=?,status=?,supplier_account=?,vat_account=?,expense_account=?,entry_type=?,
                debit_override=?,credit_override=?,due_date=?,payment_status=?,amount_paid=? WHERE id=?""",
                (str(item["invoice_number"]).strip(), kind, str(item["invoice_date"]).strip(), party["id"], currency,
                 str(subtotal), str(vat), str(total), status, supplier_account, vat_account, expense_account,
                 entry_type,str(debit_override),str(credit_override),due_date, payment_status, str(amount_paid), invoice_id))
            entry = db.execute("SELECT id FROM journal_entries WHERE source_type='invoice' AND source_id=?", (invoice_id,)).fetchone()
            description = f"{entry_type.replace('_',' ').title()} {str(item['invoice_number']).strip()}"
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
                i.expense_account,i.entry_type,i.debit_override,i.credit_override,i.source_row,i.due_date,i.payment_status,i.amount_paid,
                CAST(i.total AS REAL)-CAST(i.amount_paid AS REAL) outstanding
                FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""",
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
            "party_name": invoice["party_name"], "kind": invoice["kind"], "entry_type":invoice.get("entry_type") or invoice["kind"], "currency": invoice["currency"],
            "subtotal": str(Decimal(str(invoice["subtotal"] or 0)) + subtotal),
            "vat": str(Decimal(str(invoice["vat"] or 0)) + vat),
            "total": str(Decimal(str(invoice["total"] or 0)) + total),
            "supplier_account": invoice["supplier_account"], "vat_account": invoice["vat_account"],
            "expense_account": invoice["expense_account"], "status": "posted",
            "due_date": invoice.get("due_date"), "amount_paid": invoice.get("amount_paid", 0),"debit":invoice.get("debit",0),"credit":invoice.get("credit",0),
        }
        updated = self.update_invoice(invoice_id, updated_values, user_id)
        with self.connect() as db:
            db.execute("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,vat_rate,vat,total)
                VALUES(?,?,?,?,?,?,?,?)""", (invoice_id, description, str(quantity), str(unit_price),
                str(subtotal), str(vat_rate), str(vat), str(total)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id, "add_item", "invoice", invoice_id, json.dumps({"description": description}), utcnow()))
        return updated

    def cancel_invoice(self, invoice_id, reason, user_id):
        reason = str(reason or "").strip()
        if not reason:
            raise ValueError("Cancellation reason is required")
        with self.connect() as db:
            invoice = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not invoice:
                raise KeyError(invoice_id)
            if invoice["status"] == "cancelled":
                raise ValueError("Invoice is already cancelled")
            self._assert_period_open(invoice["invoice_date"])
            original = db.execute("SELECT * FROM journal_entries WHERE source_type='invoice' AND source_id=?", (invoice_id,)).fetchone()
            if not original:
                raise ValueError("Invoice journal entry was not found")
            reverse = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""", (f"REV-{invoice_id}", invoice["invoice_date"],
                f"Cancellation of invoice {invoice['invoice_number']}", "invoice_reversal", invoice_id,
                invoice["currency"], user_id, utcnow()))
            lines = db.execute("SELECT account_id,party_id,debit,credit FROM journal_lines WHERE entry_id=?", (original["id"],)).fetchall()
            for line in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)",
                    (reverse.lastrowid, line["account_id"], line["party_id"], line["credit"], line["debit"]))
            db.execute("UPDATE invoices SET status='cancelled',cancelled_at=?,cancellation_reason=? WHERE id=?",
                       (utcnow(), reason, invoice_id))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id,"cancel","invoice",invoice_id,json.dumps({"reason":reason}),utcnow()))
        return self.get_invoice(invoice_id)

    def duplicate_invoice(self, invoice_id, user_id):
        with self.connect() as db:
            row = db.execute("""SELECT i.*,p.name party_name FROM invoices i
                LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            source = dict(row)
            items = [dict(item) for item in db.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id", (invoice_id,))]
        new_number = self.next_invoice_number(source["kind"], source["invoice_date"])
        payload = {key:source.get(key) for key in ("invoice_date","party_name","kind","entry_type","currency","exchange_rate",
            "subtotal","vat","total","supplier_account","vat_account","expense_account","due_date")}
        payload.update({"debit":source.get("debit_override"),"credit":source.get("credit_override")})
        payload.update({"invoice_number":new_number,"amount_paid":0,"source_file":"Duplicated invoice","source_row":None})
        new_id = self.import_invoice(payload, user_id)
        if items:
            with self.connect() as db:
                db.executemany("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,vat_rate,vat,total)
                    VALUES(?,?,?,?,?,?,?,?)""", [(new_id,item["description"],item["quantity"],item["unit_price"],
                    item["subtotal"],item["vat_rate"],item["vat"],item["total"]) for item in items])
                db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                    (user_id,"duplicate","invoice",new_id,json.dumps({"source_invoice_id":invoice_id}),utcnow()))
        return self.get_invoice(new_id)

    def get_invoice(self, invoice_id):
        rows = self.list_invoices(limit=100000)
        row = next((item for item in rows if item["id"] == invoice_id), None)
        if not row:
            raise KeyError(invoice_id)
        return row

    def invoice_detail(self, invoice_id):
        invoice=self.get_invoice(invoice_id)
        with self.connect() as db:
            items=[dict(row) for row in db.execute("SELECT description,quantity,unit_price,subtotal,vat_rate,vat,total FROM invoice_items WHERE invoice_id=? ORDER BY id",(invoice_id,))]
        return {"invoice":invoice,"items":items}

    def add_attachment(self, invoice_id, file_name, mime_type, content, user_id):
        if not file_name or not content:
            raise ValueError("Attachment file is required")
        if len(content) > 15 * 1024 * 1024:
            raise ValueError("Attachment cannot exceed 15 MB")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM invoices WHERE id=?", (invoice_id,)).fetchone():
                raise KeyError(invoice_id)
            result = db.execute("""INSERT INTO invoice_attachments(invoice_id,file_name,mime_type,content,uploaded_by,uploaded_at)
                VALUES(?,?,?,?,?,?)""", (invoice_id,file_name,mime_type or "application/octet-stream",content,user_id,utcnow()))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"attach","invoice",invoice_id,json.dumps({"file_name":file_name}),utcnow()))
            return result.lastrowid

    def list_attachments(self, invoice_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,file_name,mime_type,length(content) size,uploaded_at
                FROM invoice_attachments WHERE invoice_id=? ORDER BY id DESC""", (invoice_id,))]

    def get_attachment(self, attachment_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM invoice_attachments WHERE id=?", (attachment_id,)).fetchone()
            if not row: raise KeyError(attachment_id)
            return dict(row)

    def invoice_history(self, invoice_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT l.id,l.action,l.details,l.created_at,u.username
                FROM audit_log l LEFT JOIN users u ON u.id=l.user_id
                WHERE l.entity='invoice' AND l.entity_id=? ORDER BY l.id DESC""", (invoice_id,))]

    def profit_and_loss(self, from_date=None, to_date=None, currency=None):
        conditions = ["a.type IN ('income','expense')"]
        parameters = []
        normalized_date = """CASE WHEN e.entry_date GLOB '??-??-????'
            THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if from_date: conditions.append(f"{normalized_date}>=?"); parameters.append(from_date)
        if to_date: conditions.append(f"{normalized_date}<=?"); parameters.append(to_date)
        if currency: conditions.append("e.currency=?"); parameters.append(currency)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(f"""SELECT e.currency,a.code,a.name_en,a.type,
                SUM(CAST(j.debit AS REAL)) debit,SUM(CAST(j.credit AS REAL)) credit
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
                WHERE {' AND '.join(conditions)} GROUP BY e.currency,a.id ORDER BY e.currency,a.code""", parameters)]
        for row in rows:
            row["amount"] = (row["credit"] - row["debit"]) if row["type"] == "income" else (row["debit"] - row["credit"])
        return rows

    def close_fiscal_year(self, year, user_id):
        year = int(year)
        start, end = f"{year}-01-01", f"{year}-12-31"
        with self.connect() as db:
            existing = db.execute("SELECT * FROM fiscal_years WHERE year=?", (year,)).fetchone()
            if existing and existing["status"] == "closed":
                raise ValueError(f"Fiscal year {year} is already closed")
            pnl_rows = self.profit_and_loss(start, end)
            by_currency = {}
            for row in pnl_rows:
                balance = Decimal(str(row["debit"] or 0)) - Decimal(str(row["credit"] or 0))
                if balance:
                    by_currency.setdefault(row["currency"], []).append((row["code"], balance))
            results = {}
            for currency, balances in by_currency.items():
                entry = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""", (f"CLOSE-{year}-{currency}", end, f"Fiscal year {year} closing",
                    "year_close", year, currency, user_id, utcnow()))
                close_difference = Decimal("0")
                for code, balance in balances:
                    debit = -balance if balance < 0 else Decimal("0")
                    credit = balance if balance > 0 else Decimal("0")
                    close_difference += debit - credit
                    db.execute("INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,?,?,?)",
                        (entry.lastrowid,self._account_id(db,code),str(debit),str(credit)))
                if close_difference > 0:
                    result_code, debit, credit = "121", Decimal("0"), close_difference
                else:
                    result_code, debit, credit = "125", -close_difference, Decimal("0")
                db.execute("INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,?,?,?)",
                    (entry.lastrowid,self._account_id(db,result_code),str(debit),str(credit)))
                results[currency] = float(credit - debit)
            db.execute("""INSERT INTO fiscal_years(year,status,opened_at,closed_at,closed_by,details)
                VALUES(?,'closed',?,?,?,?) ON CONFLICT(year) DO UPDATE SET status='closed',closed_at=excluded.closed_at,
                closed_by=excluded.closed_by,details=excluded.details""",
                (year,f"{year}-01-01T00:00:00",utcnow(),user_id,json.dumps({"net_results":results})))
            db.execute("INSERT OR IGNORE INTO fiscal_years(year,status,opened_at) VALUES(?,'open',?)", (year+1,utcnow()))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"close","fiscal_year",year,json.dumps({"next_year":year+1,"net_results":results}),utcnow()))
        return {"closed_year":year,"opened_year":year+1,"net_results":results}

    def list_fiscal_years(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM fiscal_years ORDER BY year DESC")]

    def list_parties(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,kind,name,tax_number,currency,account_number FROM parties ORDER BY name,kind")]

    def save_party(self, item, user_id):
        name=str(item.get("name") or "").strip(); kind=str(item.get("kind") or "").strip().lower()
        currency=str(item.get("currency") or "USD").upper(); tax_number=str(item.get("tax_number") or "").strip() or None
        if not name or kind not in ("customer","supplier","both") or currency not in ("USD","EUR","LBP","AED"):
            raise ValueError("Enter a valid name, type, and currency")
        with self.connect() as db:
            db.execute("""INSERT INTO parties(kind,name,tax_number,currency) VALUES(?,?,?,?)
                ON CONFLICT(kind,name) DO UPDATE SET tax_number=excluded.tax_number,currency=excluded.currency""",
                (kind,name,tax_number,currency))
            row=db.execute("SELECT * FROM parties WHERE kind=? AND name=?",(kind,name)).fetchone()
            account_number=self._ensure_party_account(db,row)
            if account_number: row=db.execute("SELECT * FROM parties WHERE id=?",(row["id"],)).fetchone()
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"save","party",row["id"],json.dumps({"name":name,"kind":kind}),utcnow()))
            return dict(row)

    def add_payment(self, item, user_id):
        kind=str(item.get("kind") or "").strip(); date=str(item.get("payment_date") or "").strip()
        self._assert_period_open(date)
        if kind not in ("customer_receipt","supplier_payment"): raise ValueError("Invalid payment type")
        try: amount=Decimal(str(item.get("amount") or 0))
        except Exception as exc: raise ValueError("Invalid payment amount") from exc
        if amount<=0: raise ValueError("Payment amount must be above zero")
        currency=str(item.get("currency") or "USD").upper()
        cash_account=str(item.get("cash_account") or "531").strip()
        party_account=str(item.get("party_account") or (DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"] if kind=="customer_receipt" else DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"])).strip()
        party_id=int(item.get("party_id"))
        with self.connect() as db:
            party=db.execute("SELECT * FROM parties WHERE id=?",(party_id,)).fetchone()
            if not party: raise KeyError(party_id)
            supplier_account=self._ensure_party_account(db,party)
            if kind=="supplier_payment" and party_account==DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"] and supplier_account:
                party_account=supplier_account
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(cash_account,"Cash / Bank Account","asset"))
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(party_account,"Party Control Account","asset" if kind=="customer_receipt" else "liability"))
            result=db.execute("""INSERT INTO payments(kind,party_id,payment_date,currency,amount,cash_account,party_account,reference,description,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(kind,party_id,date,currency,str(amount),cash_account,party_account,
                str(item.get("reference") or "").strip(),str(item.get("description") or "").strip(),user_id,utcnow()))
            payment_id=result.lastrowid
            entry=db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",(f"PAY-{payment_id}",date,str(item.get("description") or kind.replace("_"," ")).strip(),"payment",payment_id,currency,user_id,utcnow()))
            if kind=="customer_receipt": lines=[(cash_account,amount,0),(party_account,0,amount)]
            else: lines=[(party_account,amount,0),(cash_account,0,amount)]
            for code,debit,credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)",
                    (entry.lastrowid,self._account_id(db,code),party_id,str(debit),str(credit)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"create","payment",payment_id,json.dumps({"kind":kind,"amount":str(amount),"currency":currency}),utcnow()))
            return payment_id

    def list_payments(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT x.id,x.kind,x.payment_date,p.name party_name,x.currency,
                CAST(x.amount AS REAL) amount,x.cash_account,x.party_account,x.reference,x.description
                FROM payments x JOIN parties p ON p.id=x.party_id ORDER BY x.id DESC""")]

    def add_expense(self, item, user_id):
        date=str(item.get("expense_date") or "").strip(); self._assert_period_open(date)
        description=str(item.get("description") or "").strip()
        if not description: raise ValueError("Expense description is required")
        subtotal=Decimal(str(item.get("subtotal") or 0)); vat=Decimal(str(item.get("vat") or 0)); total=subtotal+vat
        if subtotal<0 or vat<0 or total<=0: raise ValueError("Expense amounts must be valid")
        currency=str(item.get("currency") or "USD").upper(); expense_account=str(item.get("expense_account") or EXPENSE_ACCOUNT_9).strip()
        vat_account=str(item.get("vat_account") or VAT_ACCOUNT_9).strip(); payment_account=str(item.get("payment_account") or "531").strip()
        with self.connect() as db:
            for code,name,typ in ((expense_account,"Expense Account","expense"),(vat_account,"VAT Receivable","asset"),(payment_account,"Cash / Bank Account","asset")):
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(code,name,typ))
            result=db.execute("""INSERT INTO expenses(expense_date,description,category,currency,subtotal,vat,total,expense_account,vat_account,payment_account,reference,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(date,description,str(item.get("category") or "").strip(),currency,str(subtotal),str(vat),str(total),expense_account,vat_account,payment_account,str(item.get("reference") or "").strip(),user_id,utcnow()))
            expense_id=result.lastrowid
            entry=db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",(f"EXP-{expense_id}",date,description,"expense",expense_id,currency,user_id,utcnow()))
            for code,debit,credit in ((expense_account,subtotal,0),(vat_account,vat,0),(payment_account,0,total)):
                if Decimal(str(debit or credit)):
                    db.execute("INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,?,?,?)",(entry.lastrowid,self._account_id(db,code),str(debit),str(credit)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"create","expense",expense_id,json.dumps({"total":str(total),"currency":currency}),utcnow()))
            return expense_id

    def list_expenses(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,expense_date,description,category,currency,
                CAST(subtotal AS REAL) subtotal,CAST(vat AS REAL) vat,CAST(total AS REAL) total,
                expense_account,vat_account,payment_account,reference FROM expenses ORDER BY id DESC""")]

    def save_exchange_rate(self, item, user_id):
        date=str(item.get("rate_date") or "").strip(); self._date_year(date)
        source=str(item.get("from_currency") or "").upper(); target=str(item.get("to_currency") or "").upper()
        rate=Decimal(str(item.get("rate") or 0))
        if source not in ("USD","EUR","LBP","AED") or target not in ("USD","EUR","LBP","AED") or source==target or rate<=0:
            raise ValueError("Enter two different currencies and a positive rate")
        with self.connect() as db:
            db.execute("""INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_by,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(rate_date,from_currency,to_currency) DO UPDATE SET rate=excluded.rate,
                created_by=excluded.created_by,created_at=excluded.created_at""",(date,source,target,str(rate),user_id,utcnow()))
        return True

    def list_exchange_rates(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,rate_date,from_currency,to_currency,CAST(rate AS REAL) rate,created_at
                FROM exchange_rates ORDER BY id DESC""")]

    def professional_dashboard(self):
        invoice_rows=self.dashboard(); expenses=self.list_expenses()
        metrics={}
        for row in invoice_rows:
            code=row["currency"]; metrics.setdefault(code,{"currency":code,"sales":0.0,"purchases":0.0,"expenses":0.0,"profit":0.0,"receivables":0.0,"payables":0.0,"overdue":0})
            amount=float(row["subtotal"] or 0)
            if row["kind"]=="sale": metrics[code]["sales"]+=amount
            else: metrics[code]["purchases"]+=amount
        for row in expenses:
            code=row["currency"]; metrics.setdefault(code,{"currency":code,"sales":0.0,"purchases":0.0,"expenses":0.0,"profit":0.0,"receivables":0.0,"payables":0.0,"overdue":0})
            metrics[code]["expenses"]+=float(row["subtotal"] or 0)
        today=datetime.now().date()
        with self.connect() as db:
            invoices=[dict(row) for row in db.execute("SELECT kind,currency,total,amount_paid,due_date,status FROM invoices WHERE status!='cancelled'")]
            monthly=[dict(row) for row in db.execute("""SELECT substr(CASE WHEN invoice_date GLOB '??-??-????' THEN substr(invoice_date,7,4)||'-'||substr(invoice_date,4,2)||'-'||substr(invoice_date,1,2) ELSE invoice_date END,1,7) month,
                currency,kind,SUM(CAST(subtotal AS REAL)) amount FROM invoices WHERE status!='cancelled' GROUP BY month,currency,kind ORDER BY month""")]
        for row in invoices:
            code=row["currency"]; metrics.setdefault(code,{"currency":code,"sales":0.0,"purchases":0.0,"expenses":0.0,"profit":0.0,"receivables":0.0,"payables":0.0,"overdue":0})
            outstanding=float(row["total"] or 0)-float(row["amount_paid"] or 0)
            if row["kind"]=="sale": metrics[code]["receivables"]+=outstanding
            else: metrics[code]["payables"]+=outstanding
            if outstanding>0 and row.get("due_date"):
                try:
                    due=datetime.strptime(row["due_date"],"%d-%m-%Y").date()
                    if due<today: metrics[code]["overdue"]+=1
                except ValueError: pass
        for value in metrics.values(): value["profit"]=value["sales"]-value["purchases"]-value["expenses"]
        return {"metrics":list(metrics.values()),"monthly":monthly}

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
            return [dict(r) for r in db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.kind,i.entry_type,i.currency,i.subtotal,i.vat,i.total,
                COALESCE(CAST(i.debit_override AS REAL),CASE WHEN i.kind='sale' THEN CAST(i.total AS REAL) ELSE 0 END) debit,
                COALESCE(CAST(i.credit_override AS REAL),CASE WHEN i.kind='purchase' THEN CAST(i.total AS REAL) ELSE 0 END) credit,
                i.status,i.currency_issue,i.supplier_account,i.vat_account,i.expense_account,i.source_row,
                i.due_date,i.payment_status,CAST(i.amount_paid AS REAL) amount_paid,
                CAST(i.total AS REAL)-CAST(i.amount_paid AS REAL) outstanding,i.cancelled_at,i.cancellation_reason,
                (SELECT COUNT(*) FROM invoice_attachments x WHERE x.invoice_id=i.id) attachment_count
                FROM invoices i LEFT JOIN parties p ON p.id=i.party_id ORDER BY i.id DESC LIMIT ?""", (limit,))]

    def list_accounts(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT a.code,a.name_en,a.name_ar,a.name_fr,a.type,
                p.code parent_code FROM accounts a LEFT JOIN accounts p ON p.id=a.parent_id
                ORDER BY CASE WHEN instr(a.code,'.')>0 THEN replace(a.code,'.','') ELSE a.code END""")]

    def save_account(self,item,user_id):
        code=str(item.get("code") or "").strip(); name=str(item.get("name_en") or "").strip()
        account_type=str(item.get("type") or "expense").strip().lower(); parent=str(item.get("parent_code") or "").strip() or None
        if len(code)!=9 or not code.isdigit(): raise ValueError("Account number must contain exactly 9 digits")
        if not name or account_type not in ("asset","liability","equity","income","expense"): raise ValueError("Enter a valid account name and type")
        with self.connect() as db:
            parent_id=None
            if parent:
                row=db.execute("SELECT id FROM accounts WHERE code=?",(parent,)).fetchone()
                if not row: raise ValueError("Parent account was not found")
                parent_id=row["id"]
            db.execute("""INSERT INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET name_en=excluded.name_en,type=excluded.type,parent_id=excluded.parent_id""",
                (code,name,account_type,parent_id))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"save","account",json.dumps({"code":code,"name":name}),utcnow()))
        return True

    def dashboard(self):
        with self.connect() as db:
            rows = db.execute("""SELECT kind,currency,SUM(CAST(subtotal AS REAL)) subtotal,
                SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total,COUNT(*) count,
                SUM(CASE WHEN kind='sale' THEN CAST(total AS REAL) ELSE 0 END) debit,
                SUM(CASE WHEN kind='purchase' THEN CAST(total AS REAL) ELSE 0 END) credit
                FROM invoices WHERE status!='cancelled' GROUP BY kind,currency""").fetchall()
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

    def general_ledger(self, account_code=None, from_date=None, to_date=None, currency=None):
        rows=self.journal(None,to_date,currency,limit=20000)
        if account_code: rows=[row for row in rows if row["account_code"]==str(account_code)]
        opening={}; items=[]; balances={}
        for row in rows:
            normalized=str(row["entry_date"] or "")
            try: normalized=datetime.strptime(normalized,"%d-%m-%Y").strftime("%Y-%m-%d")
            except ValueError: pass
            key=(row["currency"],row["account_code"])
            movement=Decimal(str(row["debit"] or 0))-Decimal(str(row["credit"] or 0))
            if from_date and normalized<from_date:
                opening[key]=opening.get(key,Decimal("0"))+movement; continue
            balances[key]=balances.get(key,opening.get(key,Decimal("0")))+movement
            row["balance"]=float(balances[key]); items.append(row)
        return {"opening":[{"currency":k[0],"account_code":k[1],"amount":float(v)} for k,v in opening.items()],"items":items}

    def balance_sheet(self, to_date=None, currency=None):
        conditions=["a.type IN ('asset','liability','equity')"]
        parameters=[]
        normalized_date="""CASE WHEN e.entry_date GLOB '??-??-????'
            THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if to_date: conditions.append(f"{normalized_date}<=?"); parameters.append(to_date)
        if currency: conditions.append("e.currency=?"); parameters.append(currency)
        with self.connect() as db:
            rows=[dict(row) for row in db.execute(f"""SELECT e.currency,a.code,a.name_en,a.type,
                SUM(CAST(j.debit AS REAL)) debit,SUM(CAST(j.credit AS REAL)) credit,
                SUM(CAST(j.debit AS REAL)-CAST(j.credit AS REAL)) balance
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
                WHERE {' AND '.join(conditions)} GROUP BY e.currency,a.id ORDER BY e.currency,a.type,a.code""",parameters)]
        pnl=self.profit_and_loss(None,to_date,currency)
        current_results={}
        for row in pnl:
            current_results.setdefault(row["currency"],Decimal("0"))
            amount=Decimal(str(row["amount"] or 0))
            current_results[row["currency"]]+=amount if row["type"]=="income" else -amount
        for code,result in current_results.items():
            if result:
                rows.append({"currency":code,"code":"13","name_en":"Current Year Net Result","type":"equity",
                    "debit":float(-result) if result<0 else 0.0,"credit":float(result) if result>0 else 0.0,"balance":float(-result)})
        return rows

    def vat_report(self, from_date=None, to_date=None, currency=None):
        normalized="""CASE WHEN invoice_date GLOB '??-??-????'
            THEN substr(invoice_date,7,4)||'-'||substr(invoice_date,4,2)||'-'||substr(invoice_date,1,2)
            ELSE invoice_date END"""
        conditions=["status!='cancelled'"]; parameters=[]
        if from_date: conditions.append(f"{normalized}>=?"); parameters.append(from_date)
        if to_date: conditions.append(f"{normalized}<=?"); parameters.append(to_date)
        if currency: conditions.append("currency=?"); parameters.append(currency)
        with self.connect() as db:
            invoice_rows=[dict(row) for row in db.execute(f"""SELECT currency,kind,COUNT(*) invoices,
                SUM(CAST(subtotal AS REAL)) subtotal,SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total
                FROM invoices WHERE {' AND '.join(conditions)} GROUP BY currency,kind ORDER BY currency,kind""",parameters)]
            expense_conditions=[]; expense_parameters=[]
            expense_date="""CASE WHEN expense_date GLOB '??-??-????'
                THEN substr(expense_date,7,4)||'-'||substr(expense_date,4,2)||'-'||substr(expense_date,1,2)
                ELSE expense_date END"""
            if from_date: expense_conditions.append(f"{expense_date}>=?"); expense_parameters.append(from_date)
            if to_date: expense_conditions.append(f"{expense_date}<=?"); expense_parameters.append(to_date)
            if currency: expense_conditions.append("currency=?"); expense_parameters.append(currency)
            where=" WHERE "+" AND ".join(expense_conditions) if expense_conditions else ""
            expenses=[dict(row) for row in db.execute(f"""SELECT currency,COUNT(*) invoices,SUM(CAST(subtotal AS REAL)) subtotal,
                SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total FROM expenses{where} GROUP BY currency""",expense_parameters)]
        for row in expenses: invoice_rows.append({**row,"kind":"expense"})
        totals={}
        for row in invoice_rows:
            totals.setdefault(row["currency"],{"sales_vat":0.0,"purchase_vat":0.0,"expense_vat":0.0})
            key="sales_vat" if row["kind"]=="sale" else "purchase_vat" if row["kind"]=="purchase" else "expense_vat"
            totals[row["currency"]][key]+=float(row["vat"] or 0)
        summary=[]
        for code,value in totals.items():
            recoverable=value["purchase_vat"]+value["expense_vat"]
            summary.append({"currency":code,**value,"recoverable_vat":recoverable,"vat_payable":value["sales_vat"]-recoverable})
        return {"items":invoice_rows,"summary":summary}
