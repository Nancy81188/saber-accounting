from __future__ import annotations

import json
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from database import Database, utcnow


class CompanyManager:
    """Keeps every company/fiscal year in its own SQLite file."""

    def __init__(self, master_database):
        self.master_path=Path(master_database).resolve()
        self.root=self.master_path.parent/"companies"; self.root.mkdir(parents=True,exist_ok=True)
        self.registry_path=self.root/"companies.json"; self._cache={}
        if not self.registry_path.exists():
            year=datetime.now().year
            self._write({"companies":[{"id":"saber-for-audit","name":"Saber for Audit","active":True,
                "years":[{"year":year,"database":str(self.master_path),"status":"open"}]}]})

    def _read(self):
        try: return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception: return {"companies":[]}

    def _write(self,data):
        temporary=self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); temporary.replace(self.registry_path)

    def list_companies(self,include_inactive=False):
        companies=self._read()["companies"]
        return companies if include_inactive else [c for c in companies if c.get("active",True)]

    def _company(self,company_id):
        company=next((c for c in self._read()["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        return company

    def database(self,company_id=None,year=None):
        companies=self.list_companies(True)
        company=next((c for c in companies if c["id"]==(company_id or "saber-for-audit")),None) or companies[0]
        years=company.get("years",[])
        selected=next((y for y in years if int(y["year"])==int(year)),None) if year else (max(years,key=lambda y:int(y["year"])) if years else None)
        if not selected: raise KeyError("Fiscal year not found")
        path=str(Path(selected["database"]).resolve())
        if path not in self._cache: self._cache[path]=Database(path)
        return self._cache[path]

    def year_status(self,company_id,year):
        company=self._company(company_id or "saber-for-audit")
        selected=next((item for item in company.get("years",[]) if int(item["year"])==int(year)),None)
        return selected.get("status","open") if selected else "open"

    def create_company(self,item,master_db):
        name=str(item.get("name") or "").strip(); year=int(item.get("year") or datetime.now().year)
        if not name or year<2000 or year>2100: raise ValueError("Enter a valid company name and fiscal year")
        data=self._read(); company_id=re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-") or uuid.uuid4().hex[:10]
        if any(c["id"]==company_id or c["name"].casefold()==name.casefold() for c in data["companies"]): raise ValueError("Company already exists")
        company_id=f"{company_id}-{uuid.uuid4().hex[:6]}"; folder=self.root/company_id; folder.mkdir(parents=True,exist_ok=True)
        path=folder/f"{year}.db"; target=Database(path); target.initialize(secrets.token_urlsafe(24))
        self._copy_master_data(master_db,target)
        settings={"company_name":name,"company_address":item.get("address","").strip(),"company_phone":item.get("phone","").strip(),
            "company_mof":item.get("mof_number","").strip(),"company_email":item.get("email","").strip(),"company_website":item.get("website","").strip()}
        with target.connect() as db:
            for key,value in settings.items(): db.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
        company={"id":company_id,"name":name,"active":True,"years":[{"year":year,"database":str(path.resolve()),"status":"open"}]}
        data["companies"].append(company); self._write(data); return company

    def update_company(self,company_id,item):
        data=self._read(); company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        if str(item.get("name") or "").strip(): company["name"]=str(item["name"]).strip()
        if "active" in item: company["active"]=bool(item["active"])
        self._write(data)
        for year in company.get("years",[]):
            db=Database(year["database"])
            with db.connect() as connection:
                connection.execute("INSERT INTO app_settings(key,value) VALUES('company_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(company["name"],))
        return company

    def create_year(self,company_id,year,user_id):
        year=int(year); data=self._read(); company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        if any(int(y["year"])==year for y in company["years"]): raise ValueError("Fiscal year already exists")
        previous=max((y for y in company["years"] if int(y["year"])<year),key=lambda y:int(y["year"]),default=None)
        if not previous: raise ValueError("Create fiscal years in chronological order")
        source=Database(previous["database"])
        if previous.get("status")!="closed": source.close_fiscal_year(int(previous["year"]),user_id); previous["status"]="closed"
        path=self.root/company_id/f"{year}.db"; target=Database(path); target.initialize(secrets.token_urlsafe(24)); self._copy_master_data(source,target)
        self._opening_balances(source,target,year,user_id)
        company["years"].append({"year":year,"database":str(path.resolve()),"status":"open"}); company["years"].sort(key=lambda y:int(y["year"]))
        self._write(data); return company

    def _copy_master_data(self,source,target):
        with source.connect() as src, target.connect() as dst:
            for table in ("users","accounts","parties","app_settings"):
                rows=src.execute(f"SELECT * FROM {table}").fetchall()
                if not rows: continue
                columns=list(rows[0].keys())
                if table=="accounts": dst.execute("UPDATE accounts SET parent_id=NULL")
                dst.execute(f"DELETE FROM {table}")
                placeholders=",".join("?" for _ in columns)
                dst.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",[tuple(row[col] for col in columns) for row in rows])

    def _opening_balances(self,source,target,year,user_id):
        rows=source.trial_balance(to_date=f"{year-1}-12-31")
        by_currency={}
        for row in rows:
            balance=float(row.get("balance") or 0)
            if abs(balance)>=0.005: by_currency.setdefault(row["currency"],[]).append((row["code"],balance))
        with target.connect() as db:
            for currency,lines in by_currency.items():
                entry=db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,currency,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                    (f"OPEN-{year}-{currency}",f"01-01-{year}",f"Opening balances {year}","opening",currency,user_id,utcnow()))
                for code,balance in lines:
                    account=db.execute("SELECT id FROM accounts WHERE code=?",(code,)).fetchone()
                    if account: db.execute("INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,?,?,?)",(entry.lastrowid,account["id"],str(max(balance,0)),str(max(-balance,0))))
