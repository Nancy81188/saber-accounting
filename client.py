from __future__ import annotations

import json
import base64
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

class ApiClient:
    def __init__(self, base_url="http://127.0.0.1:8765"):
        self.base_url = base_url.rstrip("/")
        self.token = None

    def request(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try: message = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except Exception: message = str(exc)
            raise RuntimeError(message) from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot connect to {self.base_url}") from exc

    def login(self, username, password):
        result = self.request("POST", "/api/login", {"username": username, "password": password})
        self.token = result["token"]
        return result

    def dashboard(self): return self.request("GET", "/api/dashboard")["items"]
    def professional_dashboard(self): return self.request("GET","/api/dashboard/professional")
    def invoices(self): return self.request("GET", "/api/invoices")["items"]
    def accounts(self): return self.request("GET", "/api/accounts")["items"]
    def parties(self): return self.request("GET", "/api/parties")["items"]
    def statement(self, party_id, from_date=None, to_date=None, currency=None):
        query = urlencode({key:value for key,value in {
            "party_id":party_id,"from_date":from_date,"to_date":to_date,"currency":currency
        }.items() if value})
        return self.request("GET", f"/api/statement?{query}")
    def add_invoice_item(self, invoice_id, item):
        return self.request("POST", f"/api/invoices/{invoice_id}/items", {"item":item})["invoice"]
    def trial_balance(self, from_date=None, to_date=None):
        query = urlencode({key: value for key, value in {
            "from_date": from_date, "to_date": to_date
        }.items() if value})
        path = "/api/trial-balance" + (f"?{query}" if query else "")
        return self.request("GET", path)["items"]
    def journal(self, from_date=None, to_date=None, currency=None):
        query = urlencode({key: value for key, value in {
            "from_date": from_date, "to_date": to_date, "currency": currency
        }.items() if value})
        path = "/api/journal" + (f"?{query}" if query else "")
        return self.request("GET", path)["items"]
    def import_invoices(self, items, replace_existing=True): return self.request("POST", "/api/invoices/import", {"items": items, "replace_existing": replace_existing})
    def create_manual_invoice(self, invoice, items): return self.request("POST", "/api/invoices/manual", {"invoice": invoice, "items": items})
    def update_invoice(self, invoice_id, invoice): return self.request("PUT", f"/api/invoices/{invoice_id}", {"invoice": invoice})
    def invoice_detail(self, invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/detail")
    def cancel_invoice(self, invoice_id, reason): return self.request("POST",f"/api/invoices/{invoice_id}/cancel",{"reason":reason})["invoice"]
    def duplicate_invoice(self, invoice_id): return self.request("POST",f"/api/invoices/{invoice_id}/duplicate",{})["invoice"]
    def invoice_history(self, invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/history")["items"]
    def attachments(self, invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/attachments")["items"]
    def upload_attachment(self, invoice_id, file_name, mime_type, content):
        return self.request("POST",f"/api/invoices/{invoice_id}/attachments",{
            "file_name":file_name,"mime_type":mime_type,"content":base64.b64encode(content).decode("ascii")})
    def download_attachment(self, attachment_id):
        result=self.request("GET",f"/api/attachments/{attachment_id}"); result["content"]=base64.b64decode(result["content"]); return result
    def profit_loss(self, from_date=None, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/profit-loss"+(f"?{query}" if query else ""))["items"]
    def fiscal_years(self): return self.request("GET","/api/fiscal-years")["items"]
    def close_fiscal_year(self, year): return self.request("POST","/api/fiscal-years/close",{"year":year})
    def save_party(self, item): return self.request("POST","/api/parties",item)["party"]
    def payments(self): return self.request("GET","/api/payments")["items"]
    def add_payment(self, item): return self.request("POST","/api/payments",item)
    def expenses(self): return self.request("GET","/api/expenses")["items"]
    def add_expense(self, item): return self.request("POST","/api/expenses",item)
    def general_ledger(self, account=None, from_date=None, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"account":account,"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/general-ledger"+(f"?{query}" if query else ""))
    def balance_sheet(self, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/balance-sheet"+(f"?{query}" if query else ""))["items"]
    def vat_report(self, from_date=None, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/vat-report"+(f"?{query}" if query else ""))
    def users(self): return self.request("GET","/api/users")["items"]
    def save_user(self,item): return self.request("POST","/api/users",item)["user"]
    def backups(self): return self.request("GET","/api/backups")["items"]
    def create_backup(self): return self.request("POST","/api/backups/create",{})
    def restore_backup(self,name): return self.request("POST","/api/backups/restore",{"name":name})
    def settings(self): return self.request("GET","/api/settings")
    def save_settings(self,item): return self.request("POST","/api/settings",item)
    def exchange_rates(self): return self.request("GET","/api/exchange-rates")["items"]
    def save_exchange_rate(self,item): return self.request("POST","/api/exchange-rates",item)
