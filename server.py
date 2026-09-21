from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from database import Database

class ApiHandler(BaseHTTPRequestHandler):
    db: Database = None

    def log_message(self, fmt, *args):
        print(f"[Saber API] {self.address_string()} {fmt % args}")

    def _json(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _user(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        return self.db.user_for_token(token)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            return self._json(200, {"status": "ok", "application": "Saber Accounting"})
        user = self._user()
        if not user:
            return self._json(401, {"error": "Unauthorized"})
        if path == "/api/invoices":
            return self._json(200, {"items": self.db.list_invoices()})
        if path == "/api/accounts":
            return self._json(200, {"items": self.db.list_accounts()})
        if path == "/api/parties":
            return self._json(200, {"items": self.db.list_parties()})
        if path == "/api/statement":
            query = parse_qs(parsed.query)
            try:
                party_id = int(query.get("party_id", [""])[0])
                result = self.db.statement_of_account(
                    party_id,
                    query.get("from_date", [None])[0],
                    query.get("to_date", [None])[0],
                    query.get("currency", [None])[0],
                )
            except KeyError:
                return self._json(404, {"error": "Party not found"})
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(200, result)
        if path == "/api/dashboard":
            return self._json(200, {"items": self.db.dashboard()})
        if path == "/api/trial-balance":
            query = parse_qs(parsed.query)
            from_date = query.get("from_date", [None])[0]
            to_date = query.get("to_date", [None])[0]
            return self._json(200, {"items": self.db.trial_balance(from_date, to_date)})
        return self._json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
        except Exception:
            return self._json(400, {"error": "Invalid JSON"})
        if path == "/api/login":
            session = self.db.login(body.get("username", ""), body.get("password", ""))
            return self._json(200, session) if session else self._json(401, {"error": "Invalid username or password"})
        user = self._user()
        if not user:
            return self._json(401, {"error": "Unauthorized"})
        if path.startswith("/api/invoices/") and path.endswith("/items"):
            try:
                invoice_id = int(path.split("/")[-2])
                result = self.db.add_invoice_item(invoice_id, body.get("item", {}), user["id"])
            except KeyError:
                return self._json(404, {"error": "Invoice not found"})
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(201, {"invoice": result})
        if path == "/api/invoices/manual":
            invoice = body.get("invoice", {})
            items = body.get("items", [])
            if not isinstance(invoice, dict) or not isinstance(items, list) or len(items) > 500:
                return self._json(400, {"error": "Invalid manual invoice"})
            required = ("invoice_number", "invoice_date", "party_name", "kind", "currency")
            missing = [field for field in required if not str(invoice.get(field) or "").strip()]
            if missing:
                return self._json(400, {"error": "Missing fields: " + ", ".join(missing)})
            try:
                invoice_id = self.db.create_manual_invoice(invoice, items, user["id"])
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(201, {"invoice_id": invoice_id})
        if path == "/api/invoices/import":
            items = body.get("items", [])
            if not isinstance(items, list) or len(items) > 5000:
                return self._json(400, {"error": "Invalid import batch"})
            replacement = self.db.clear_invoices(user["id"]) if body.get("replace_existing", False) else {"deleted": 0, "backup": None}
            ids, errors = [], []
            for index, item in enumerate(items):
                try:
                    ids.append(self.db.import_invoice(item, user["id"]))
                except Exception as exc:
                    errors.append({"index": index, "invoice_number": item.get("invoice_number"), "error": str(exc)})
            return self._json(200, {"imported": len(ids), "ids": ids, "errors": errors, "deleted": replacement["deleted"], "backup": replacement["backup"]})
        return self._json(404, {"error": "Not found"})

    def do_PUT(self):
        path = urlparse(self.path).path
        user = self._user()
        if not user:
            return self._json(401, {"error": "Unauthorized"})
        if path.startswith("/api/invoices/"):
            try:
                invoice_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                return self._json(400, {"error": "Invalid invoice ID"})
            try:
                body = self._body()
                invoice = body.get("invoice", {})
                if not isinstance(invoice, dict):
                    raise ValueError("Invalid invoice details")
                updated = self.db.update_invoice(invoice_id, invoice, user["id"])
            except KeyError:
                return self._json(404, {"error": "Invoice not found"})
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(200, {"invoice": updated})
        return self._json(404, {"error": "Not found"})

def run_server(host="0.0.0.0", port=8765, database="saber_accounting.db", admin_password="ChangeMe123!"):
    db = Database(database)
    db.initialize(admin_password)
    ApiHandler.db = db
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"Saber Accounting server running at http://{host}:{port}")
    server.serve_forever()

def main():
    parser = argparse.ArgumentParser(description="Saber Accounting shared server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", default=str(Path.home() / "SaberAccounting" / "saber_accounting_v0_7.db"))
    parser.add_argument("--admin-password", default="ChangeMe123!")
    args = parser.parse_args()
    Path(args.database).parent.mkdir(parents=True, exist_ok=True)
    run_server(args.host, args.port, args.database, args.admin_password)

if __name__ == "__main__":
    main()
