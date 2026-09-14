from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
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
    def invoices(self): return self.request("GET", "/api/invoices")["items"]
    def trial_balance(self): return self.request("GET", "/api/trial-balance")["items"]
    def import_invoices(self, items, replace_existing=True): return self.request("POST", "/api/invoices/import", {"items": items, "replace_existing": replace_existing})
