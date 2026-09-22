from __future__ import annotations

import tkinter as tk
import sys
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from client import ApiClient
from i18n import tr
from importer import read_invoices
from report_export import export_excel, export_pdf, print_rows

NAVY, GOLD, LIGHT = "#071b2e", "#c9a96a", "#f3f6f8"

def resource_path(relative_path):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path

def row_matches_search(values, query):
    """Return True when every search term appears somewhere in the row."""
    terms = str(query or "").casefold().split()
    if not terms:
        return True
    searchable = " ".join("" if value is None else str(value) for value in values).casefold()
    return all(term in searchable for term in terms)

class SaberApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Saber Accounting")
        self.geometry("1180x720")
        self.minsize(940, 600)
        self.configure(bg=LIGHT)
        self.language = tk.StringVar(value="en")
        self.client = None
        self.import_rows = []
        self.manual_items = []
        self.view_currency = tk.StringVar(value="All Currencies")
        self.import_view_currency = tk.StringVar(value="All Currencies")
        self.trial_from_date = tk.StringVar()
        self.trial_to_date = tk.StringVar()
        self.statement_party = tk.StringVar()
        self.statement_from_date = tk.StringVar()
        self.statement_to_date = tk.StringVar()
        self.statement_currency = tk.StringVar(value="All Currencies")
        self.journal_from_date = tk.StringVar()
        self.journal_to_date = tk.StringVar()
        self._style()
        self.login_screen()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=NAVY, foreground="white", font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", NAVY)])

    def clear(self):
        for child in self.winfo_children(): child.destroy()

    def login_screen(self):
        self.clear()
        card = tk.Frame(self, bg="white", padx=42, pady=36)
        card.place(relx=.5, rely=.5, anchor="center")
        try:
            self.login_logo = tk.PhotoImage(file=str(resource_path("assets/Saber_for_Audit_logo.png"))).subsample(6, 6)
            tk.Label(card, image=self.login_logo, bg="white").grid(row=0, column=0, columnspan=2, pady=(0, 14))
        except Exception:
            tk.Label(card, text="SABER FOR AUDIT", font=("Segoe UI", 24, "bold"), fg=NAVY, bg="white").grid(row=0, column=0, columnspan=2)
        tk.Label(card, text="PROFESSIONAL ACCOUNTING", font=("Segoe UI", 11, "bold"), fg=GOLD, bg="white").grid(row=1, column=0, columnspan=2, pady=(0,25))
        self.server = tk.StringVar(value="http://127.0.0.1:8765")
        self.username = tk.StringVar(value="admin")
        self.password = tk.StringVar()
        fields = [("server", self.server, False), ("username", self.username, False), ("password", self.password, True)]
        for row,(key,var,secret) in enumerate(fields, 2):
            tk.Label(card, text=tr("en",key), bg="white", anchor="w").grid(row=row,column=0,sticky="w",pady=7,padx=(0,14))
            tk.Entry(card,textvariable=var,width=34,show="*" if secret else "").grid(row=row,column=1,pady=7)
        tk.Label(card,text="Language",bg="white").grid(row=5,column=0,sticky="w",pady=7)
        ttk.Combobox(card,textvariable=self.language,values=["en","ar","fr"],state="readonly",width=31).grid(row=5,column=1,pady=7)
        tk.Button(card,text="Sign in",command=self.login,bg=NAVY,fg="white",activebackground=GOLD,width=29,pady=8,border=0).grid(row=6,column=0,columnspan=2,pady=(22,0))

    def login(self):
        try:
            self.client = ApiClient(self.server.get())
            self.client.login(self.username.get(), self.password.get())
            self.main_screen()
        except Exception as exc: messagebox.showerror("Saber Accounting", str(exc))

    def main_screen(self):
        self.clear(); lang=self.language.get()
        top=tk.Frame(self,bg=NAVY,height=76); top.pack(fill="x"); top.pack_propagate(False)
        try:
            self.header_logo = tk.PhotoImage(file=str(resource_path("assets/Saber_for_Audit_logo.png"))).subsample(18, 18)
            tk.Label(top,image=self.header_logo,bg=NAVY).pack(side="left",padx=(18,8),pady=2)
        except Exception:
            pass
        tk.Label(top,text=tr(lang,"title"),bg=NAVY,fg="white",font=("Segoe UI",20,"bold")).pack(side="left",padx=8,pady=19)
        tk.Label(top,text="11% VAT  |  USD · LBP · EUR · AED",bg=NAVY,fg=GOLD,font=("Segoe UI",10,"bold")).pack(side="right",padx=28)
        notebook=ttk.Notebook(self); notebook.pack(fill="both",expand=True,padx=18,pady=16)
        self.dashboard_tab=tk.Frame(notebook,bg=LIGHT); self.invoices_tab=tk.Frame(notebook,bg=LIGHT); self.manual_tab=tk.Frame(notebook,bg=LIGHT); self.import_tab=tk.Frame(notebook,bg=LIGHT); self.journal_tab=tk.Frame(notebook,bg=LIGHT); self.trial_tab=tk.Frame(notebook,bg=LIGHT); self.accounts_tab=tk.Frame(notebook,bg=LIGHT); self.statement_tab=tk.Frame(notebook,bg=LIGHT)
        notebook.add(self.dashboard_tab,text=tr(lang,"dashboard")); notebook.add(self.invoices_tab,text=tr(lang,"invoices")); notebook.add(self.manual_tab,text="Manual Entry"); notebook.add(self.import_tab,text=tr(lang,"import")); notebook.add(self.journal_tab,text="General Journal"); notebook.add(self.trial_tab,text="Trial Balance"); notebook.add(self.statement_tab,text="Statement of Account"); notebook.add(self.accounts_tab,text="Lebanese Chart of Accounts")
        filter_bar=tk.Frame(self,bg=LIGHT); filter_bar.pack(fill="x",padx=28)
        tk.Label(filter_bar,text="Show currency:",bg=LIGHT,font=("Segoe UI",10,"bold")).pack(side="left")
        currency_filter=ttk.Combobox(filter_bar,textvariable=self.view_currency,values=["All Currencies","USD","EUR","LBP","AED"],state="readonly",width=16)
        currency_filter.pack(side="left",padx=8); currency_filter.bind("<<ComboboxSelected>>",lambda _event:self.currency_changed())
        self.build_dashboard(); self.build_invoices(); self.build_manual(); self.build_import(); self.build_journal(); self.build_trial(); self.build_statement(); self.build_accounts()

    def currency_changed(self):
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial()

    def table(self,parent,columns):
        search_bar=tk.Frame(parent,bg=LIGHT); search_bar.pack(fill="x",padx=10,pady=(10,0))
        search_var=tk.StringVar()
        tk.Label(search_bar,text="Search:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        search_entry=tk.Entry(search_bar,textvariable=search_var,width=36)
        search_entry.pack(side="left",padx=8)
        tk.Button(search_bar,text="Clear",command=lambda:search_var.set(""),bg=NAVY,fg="white",
                  border=0,padx=12,pady=3).pack(side="left")

        frame=tk.Frame(parent,bg=LIGHT); frame.pack(fill="both",expand=True,padx=10,pady=10)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show="headings")
        for key,label,width in columns: tree.heading(key,text=label); tree.column(key,width=width,anchor="w")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")

        real_insert,real_delete=tree.insert,tree.delete
        tree._search_rows=[]
        tree._search_counter=0
        def tracked_insert(parent_id,index,*args,**kwargs):
            tree._search_counter+=1
            saved_kwargs=dict(kwargs)
            saved_kwargs.setdefault("iid",f"search-{id(tree)}-{tree._search_counter}")
            record=(parent_id,index,args,saved_kwargs)
            tree._search_rows.append(record)
            if row_matches_search(saved_kwargs.get("values",()),search_var.get()):
                real_insert(parent_id,index,*args,**saved_kwargs)
            return saved_kwargs["iid"]
        def tracked_delete(*item_ids):
            visible=set(tree.get_children(""))
            requested=set(item_ids)
            if requested==visible:
                tree._search_rows.clear()
            else:
                tree._search_rows=[
                    record for record in tree._search_rows
                    if str(record[3].get("iid")) not in requested
                ]
            if item_ids:
                real_delete(*item_ids)
        def apply_search(*_args):
            visible=tree.get_children("")
            if visible:
                real_delete(*visible)
            for parent_id,index,args,saved_kwargs in tree._search_rows:
                if row_matches_search(saved_kwargs.get("values",()),search_var.get()):
                    real_insert(parent_id,index,*args,**saved_kwargs)
        tree.insert=tracked_insert
        tree.delete=tracked_delete
        tree.search_var=search_var
        search_var.trace_add("write",apply_search)
        search_entry.bind("<Escape>",lambda _event:search_var.set(""))
        return tree

    def build_dashboard(self):
        self.dashboard_tree=self.table(self.dashboard_tab,[("kind","Type",110),("currency","Currency",85),("count","Invoices",85),("subtotal","Before VAT",125),("vat","VAT",105),("total","Total",125),("debit","Debit",125),("credit","Credit",125)])
        actions=tk.Frame(self.dashboard_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_dashboard).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("dashboard","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("dashboard","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("dashboard","print")).pack(side="left",padx=4)
        self.load_dashboard()

    def load_dashboard(self):
        try: rows=self.client.dashboard()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.dashboard_rows=rows; self.dashboard_tree.delete(*self.dashboard_tree.get_children())
        for r in rows: self.dashboard_tree.insert("", "end", values=(r["kind"],r["currency"],r["count"],f'{r["subtotal"]:,.2f}',f'{r["vat"]:,.2f}',f'{r["total"]:,.2f}',f'{r["debit"]:,.2f}',f'{r["credit"]:,.2f}'))

    def build_invoices(self):
        l=self.language.get(); self.invoice_tree=self.table(self.invoices_tab,[("no",tr(l,"invoice_no"),105),("date",tr(l,"date"),100),("party",tr(l,"party"),200),("kind","Type",75),("currency",tr(l,"currency"),70),("subtotal",tr(l,"before_vat"),100),("vat",tr(l,"vat"),85),("total",tr(l,"total"),100),("debit","Debit",100),("credit","Credit",100),("supplier_account","Supplier A/C",90),("vat_account","VAT A/C",80),("expense_account","Expense A/C",90),("status","Status",80),("row",tr(l,"source_row"),70)])
        invoice_actions=tk.Frame(self.invoices_tab,bg=LIGHT); invoice_actions.pack(pady=(0,10))
        tk.Button(invoice_actions,text=tr(l,"refresh"),command=self.load_invoices,bg=NAVY,fg="white",border=0,padx=20,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Save Data",command=self.confirm_invoice_data_saved,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Export Excel",command=self.export_invoices_excel,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Add Invoice Row",command=self.add_invoice_row,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Add Item",command=self.add_item_to_selected_invoice,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Edit Selected",command=self.edit_selected_invoice,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=20,pady=7).pack(side="left",padx=4)
        self.invoice_tree.bind("<Double-1>",lambda _event:self.edit_selected_invoice())
        self.load_invoices()

    def load_invoices(self):
        try: rows=self.client.invoices()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.invoice_rows={str(r["id"]):r for r in rows}
        self.invoice_tree.delete(*self.invoice_tree.get_children())
        for r in rows: self.invoice_tree.insert("","end",iid=str(r["id"]),values=(r["invoice_number"],r["invoice_date"],r["party_name"],r["kind"],r["currency"],r["subtotal"],r["vat"],r["total"],r["debit"],r["credit"],r["supplier_account"],r["vat_account"],r["expense_account"],r["status"],r["source_row"]))

    def edit_selected_invoice(self):
        selected=self.invoice_tree.selection()
        if not selected:
            return messagebox.showwarning("Invoices","Select one invoice row to edit")
        invoice_id=selected[0]
        row=self.invoice_rows.get(invoice_id)
        if not row:
            return messagebox.showerror("Invoices","The selected invoice could not be found")
        window=tk.Toplevel(self); window.title(f'Edit Invoice {row["invoice_number"]}')
        window.configure(bg=LIGHT); window.transient(self); window.grab_set(); window.resizable(False,False)
        variables={
            "invoice_number":tk.StringVar(value=row["invoice_number"]),
            "invoice_date":tk.StringVar(value=row["invoice_date"]),
            "party_name":tk.StringVar(value=row["party_name"]),
            "kind":tk.StringVar(value=row["kind"]),
            "currency":tk.StringVar(value=row["currency"]),
            "subtotal":tk.StringVar(value=row["subtotal"]),
            "vat":tk.StringVar(value=row["vat"]),
            "total":tk.StringVar(value=row["total"]),
            "supplier_account":tk.StringVar(value=row["supplier_account"]),
            "vat_account":tk.StringVar(value=row["vat_account"]),
            "expense_account":tk.StringVar(value=row["expense_account"]),
            "status":tk.StringVar(value=row["status"]),
        }
        fields=[
            ("Invoice Number","invoice_number"),("Date (DD-MM-YYYY)","invoice_date"),
            ("Customer / Supplier","party_name"),("Type","kind"),("Currency","currency"),
            ("Before VAT","subtotal"),("VAT","vat"),("Total","total"),
            ("Supplier Account","supplier_account"),("VAT Account","vat_account"),
            ("Expense Account","expense_account"),("Status","status"),
        ]
        for index,(label,key) in enumerate(fields):
            grid_row=index//2; grid_column=(index%2)*2
            tk.Label(window,text=label,bg=LIGHT,anchor="w").grid(row=grid_row,column=grid_column,sticky="w",padx=(14,5),pady=8)
            if key=="kind":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["purchase","sale"],state="readonly",width=24)
            elif key=="currency":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["USD","EUR","LBP","AED"],state="readonly",width=24)
            elif key=="status":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["posted","review"],state="readonly",width=24)
            else:
                widget=tk.Entry(window,textvariable=variables[key],width=27)
            widget.grid(row=grid_row,column=grid_column+1,padx=(5,14),pady=8)

        def save_update():
            values={key:variable.get().strip() for key,variable in variables.items()}
            if not all(values[key] for key in ("invoice_number","invoice_date","party_name")):
                return messagebox.showwarning("Invoices","Invoice number, date, and customer/supplier are required",parent=window)
            try:
                datetime.strptime(values["invoice_date"],"%d-%m-%Y")
            except ValueError:
                try:
                    datetime.strptime(values["invoice_date"],"%Y-%m-%d")
                except ValueError:
                    return messagebox.showwarning("Invoices","Date must use DD-MM-YYYY",parent=window)
            try:
                subtotal=float(values["subtotal"]); vat=float(values["vat"]); total=float(values["total"])
            except ValueError:
                return messagebox.showwarning("Invoices","Before VAT, VAT, and Total must be valid numbers",parent=window)
            if abs((subtotal+vat)-total)>0.005:
                return messagebox.showwarning("Invoices","Total must equal Before VAT plus VAT",parent=window)
            try:
                self.client.update_invoice(int(invoice_id),values)
            except Exception as exc:
                return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy()
            self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Invoices","Invoice updated successfully")

        buttons=tk.Frame(window,bg=LIGHT); buttons.grid(row=(len(fields)+1)//2,column=0,columnspan=4,pady=16)
        tk.Button(buttons,text="Save Update",command=save_update,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),
                  border=0,padx=24,pady=8).pack(side="left",padx=5)
        tk.Button(buttons,text="Cancel",command=window.destroy,bg=NAVY,fg="white",border=0,padx=20,pady=8).pack(side="left",padx=5)

    def confirm_invoice_data_saved(self):
        try:
            rows=self.client.invoices()
        except Exception as exc:
            return messagebox.showerror("Invoices",str(exc))
        self.load_invoices()
        messagebox.showinfo("Invoices",f"{len(rows)} invoice rows are saved in the shared database")

    def export_invoices_excel(self):
        rows=list(getattr(self,"invoice_rows",{}).values())
        if not rows: return messagebox.showwarning("Invoices","No invoice data to export")
        headers=["Invoice Number","Date","Customer / Supplier","Type","Currency","Before VAT","VAT","Total","Debit","Credit",
                 "Supplier Account","VAT Account","Expense Account","Status","Source Row"]
        values=[[r["invoice_number"],r["invoice_date"],r["party_name"],r["kind"],r["currency"],r["subtotal"],
                 r["vat"],r["total"],r["debit"],r["credit"],r["supplier_account"],r["vat_account"],r["expense_account"],r["status"],r["source_row"]] for r in rows]
        path=filedialog.asksaveasfilename(defaultextension=".xlsx",filetypes=[("Excel workbook","*.xlsx")],
                                          initialfile="Saber_Accounting_Invoices.xlsx")
        if not path: return
        try:
            export_excel(path,"Saber Accounting - Invoices",headers,values)
            messagebox.showinfo("Invoices",f"Saved successfully:\n{path}")
        except Exception as exc:
            messagebox.showerror("Invoices",str(exc))

    def add_invoice_row(self):
        window=tk.Toplevel(self); window.title("Add Invoice Row"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        defaults={"invoice_number":"","invoice_date":datetime.now().strftime("%d-%m-%Y"),"party_name":"",
                  "kind":"purchase","currency":"USD","subtotal":"0","vat":"0","total":"0",
                  "supplier_account":"4011","vat_account":"4426.6","expense_account":"6011"}
        variables={key:tk.StringVar(value=value) for key,value in defaults.items()}
        fields=[("Invoice Number","invoice_number"),("Date (DD-MM-YYYY)","invoice_date"),("Customer / Supplier","party_name"),
                ("Type","kind"),("Currency","currency"),("Before VAT","subtotal"),("VAT","vat"),("Total","total"),
                ("Supplier Account","supplier_account"),("VAT Account","vat_account"),("Expense Account","expense_account")]
        for index,(label,key) in enumerate(fields):
            rr=index//2; cc=(index%2)*2
            tk.Label(window,text=label,bg=LIGHT).grid(row=rr,column=cc,sticky="w",padx=(14,5),pady=7)
            if key=="kind": widget=ttk.Combobox(window,textvariable=variables[key],values=["purchase","sale"],state="readonly",width=24)
            elif key=="currency": widget=ttk.Combobox(window,textvariable=variables[key],values=["USD","EUR","LBP","AED"],state="readonly",width=24)
            else: widget=tk.Entry(window,textvariable=variables[key],width=27)
            widget.grid(row=rr,column=cc+1,padx=(5,14),pady=7)
        def save():
            values={key:var.get().strip() for key,var in variables.items()}
            try:
                datetime.strptime(values["invoice_date"],"%d-%m-%Y")
                subtotal=float(values["subtotal"]); vat=float(values["vat"]); total=float(values["total"])
            except ValueError:
                return messagebox.showwarning("Invoices","Check the date and amounts",parent=window)
            if not values["invoice_number"] or not values["party_name"] or abs(subtotal+vat-total)>0.005:
                return messagebox.showwarning("Invoices","Complete required fields; Total must equal Before VAT plus VAT",parent=window)
            item={"description":"Manual invoice row","quantity":1,"unit_price":subtotal,"subtotal":subtotal,
                  "vat_rate":0 if subtotal==0 else vat*100/subtotal,"vat":vat,"total":total}
            try: self.client.create_manual_invoice(values,[item])
            except Exception as exc: return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial(); self.load_statement_parties()
            messagebox.showinfo("Invoices","Invoice row added successfully")
        tk.Button(window,text="Save Invoice",command=save,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=24,pady=8).grid(row=6,column=0,columnspan=4,pady=16)

    def add_item_to_selected_invoice(self):
        selected=self.invoice_tree.selection()
        if not selected: return messagebox.showwarning("Invoices","Select one invoice row")
        invoice_id=int(selected[0]); window=tk.Toplevel(self); window.title("Add Item to Invoice"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        defaults={"description":"","quantity":"1","unit_price":"0","subtotal":"0","vat_rate":"11","vat":"0"}
        variables={key:tk.StringVar(value=value) for key,value in defaults.items()}
        fields=[("Description","description"),("Quantity","quantity"),("Unit Price","unit_price"),
                ("Before VAT","subtotal"),("VAT %","vat_rate"),("VAT Amount","vat")]
        for index,(label,key) in enumerate(fields):
            tk.Label(window,text=label,bg=LIGHT).grid(row=index,column=0,sticky="w",padx=14,pady=6)
            tk.Entry(window,textvariable=variables[key],width=30).grid(row=index,column=1,padx=14,pady=6)
        def save():
            item={key:var.get().strip() for key,var in variables.items()}
            try:
                if not item["description"]: raise ValueError
                for key in ("quantity","unit_price","subtotal","vat_rate","vat"): float(item[key])
            except ValueError:
                return messagebox.showwarning("Invoices","Enter a description and valid amounts",parent=window)
            try: self.client.add_invoice_item(invoice_id,item)
            except Exception as exc: return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Invoices","Item added and invoice totals updated")
        tk.Button(window,text="Add Item",command=save,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=24,pady=8).grid(row=6,column=0,columnspan=2,pady=14)

    def build_manual(self):
        header=tk.LabelFrame(self.manual_tab,text="Invoice Details",bg=LIGHT,padx=10,pady=8)
        header.pack(fill="x",padx=10,pady=(10,4))
        self.manual_no=tk.StringVar(); self.manual_date=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y"))
        self.manual_party=tk.StringVar(); self.manual_kind=tk.StringVar(value="purchase"); self.manual_currency=tk.StringVar(value="USD")
        self.manual_supplier_account=tk.StringVar(value="4011")
        self.manual_vat_account=tk.StringVar(value="4426.6")
        self.manual_expense_account=tk.StringVar(value="6011")
        fields=[("Invoice Number",self.manual_no,16),("Date",self.manual_date,14),("Customer / Supplier",self.manual_party,28)]
        for col,(label,var,width) in enumerate(fields):
            tk.Label(header,text=label,bg=LIGHT).grid(row=0,column=col*2,sticky="w",padx=4)
            tk.Entry(header,textvariable=var,width=width).grid(row=0,column=col*2+1,padx=4)
        ttk.Combobox(header,textvariable=self.manual_kind,values=["purchase","sale"],state="readonly",width=10).grid(row=0,column=6,padx=5)
        ttk.Combobox(header,textvariable=self.manual_currency,values=["USD","EUR","LBP","AED"],state="readonly",width=8).grid(row=0,column=7,padx=5)
        account_fields=[
            ("Supplier Account",self.manual_supplier_account),
            ("VAT Account",self.manual_vat_account),
            ("Expense Account",self.manual_expense_account),
        ]
        for col,(label,var) in enumerate(account_fields):
            tk.Label(header,text=label,bg=LIGHT).grid(row=1,column=col*2,sticky="w",padx=4,pady=(10,2))
            tk.Entry(header,textvariable=var,width=16).grid(row=1,column=col*2+1,padx=4,pady=(10,2))

        editor=tk.LabelFrame(self.manual_tab,text="Add Invoice Item",bg=LIGHT,padx=10,pady=8)
        editor.pack(fill="x",padx=10,pady=4)
        self.item_description=tk.StringVar(); self.item_quantity=tk.StringVar(value="1"); self.item_price=tk.StringVar(value="0")
        self.item_subtotal=tk.StringVar(value="0.00"); self.item_vat_rate=tk.StringVar(value="11")
        self.item_vat=tk.StringVar(value="0.00"); self.item_total=tk.StringVar(value="0.00")
        self.subtotal_override=tk.BooleanVar(value=False); self.vat_override=tk.BooleanVar(value=False)
        item_fields=[("Description",self.item_description,22),("Quantity",self.item_quantity,8),("Unit Price",self.item_price,11),
                     ("Before VAT",self.item_subtotal,11),("VAT %",self.item_vat_rate,7),("VAT Amount",self.item_vat,11),("After VAT",self.item_total,11)]
        for col,(label,var,width) in enumerate(item_fields):
            tk.Label(editor,text=label,bg=LIGHT).grid(row=0,column=col,sticky="w",padx=3)
            entry=tk.Entry(editor,textvariable=var,width=width)
            entry.grid(row=1,column=col,padx=3,pady=3)
            entry.bind("<FocusOut>",lambda _event:self.calculate_manual_line())
        tk.Checkbutton(editor,text="Edit Before VAT",variable=self.subtotal_override,command=self.calculate_manual_line,bg=LIGHT).grid(row=2,column=3)
        tk.Checkbutton(editor,text="Edit VAT amount",variable=self.vat_override,command=self.calculate_manual_line,bg=LIGHT).grid(row=2,column=5)
        tk.Button(editor,text="Add Item",command=self.add_manual_item,bg=NAVY,fg="white",border=0,padx=16,pady=6).grid(row=1,column=7,padx=8)

        self.manual_tree=self.table(self.manual_tab,[("description","Description",220),("quantity","Qty",60),("price","Unit Price",90),
            ("subtotal","Before VAT",100),("rate","VAT %",70),("vat","VAT",90),("total","After VAT",100),("debit","Debit",100),("credit","Credit",100)])
        actions=tk.Frame(self.manual_tab,bg=LIGHT); actions.pack(pady=(0,10))
        tk.Button(actions,text="Remove Selected Item",command=self.remove_manual_item,bg="#8B1E1E",fg="white",border=0,padx=14,pady=7).pack(side="left",padx=5)
        tk.Button(actions,text="Save Invoice",command=self.save_manual_invoice,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=22,pady=7).pack(side="left",padx=5)
        tk.Button(actions,text="Excel",command=lambda:self.manual_entry_report("xlsx"),bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=3)
        tk.Button(actions,text="PDF",command=lambda:self.manual_entry_report("pdf"),bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=3)
        tk.Button(actions,text="Print",command=lambda:self.manual_entry_report("print"),bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=3)
        self.manual_totals=tk.Label(actions,text="Before VAT: 0.00   VAT: 0.00   Total: 0.00",bg=LIGHT,font=("Segoe UI",10,"bold"))
        self.manual_totals.pack(side="left",padx=18)

    def calculate_manual_line(self):
        try:
            quantity=float(self.item_quantity.get() or 0); price=float(self.item_price.get() or 0)
            subtotal=float(self.item_subtotal.get() or 0) if self.subtotal_override.get() else quantity*price
            if not self.subtotal_override.get(): self.item_subtotal.set(f"{subtotal:.2f}")
            rate=float(self.item_vat_rate.get() or 0)
            vat=float(self.item_vat.get() or 0) if self.vat_override.get() else subtotal*rate/100
            if not self.vat_override.get(): self.item_vat.set(f"{vat:.2f}")
            self.item_total.set(f"{subtotal+vat:.2f}")
            return subtotal,vat,subtotal+vat
        except ValueError:
            return None

    def add_manual_item(self):
        calculated=self.calculate_manual_line()
        if not self.item_description.get().strip(): return messagebox.showwarning("Manual Entry","Enter an item description")
        if calculated is None: return messagebox.showwarning("Manual Entry","Enter valid item amounts")
        try:
            quantity=float(self.item_quantity.get()); price=float(self.item_price.get()); rate=float(self.item_vat_rate.get())
            if quantity<=0 or price<0 or rate<0: raise ValueError
        except ValueError:
            return messagebox.showwarning("Manual Entry","Quantity must be above zero; price and VAT cannot be negative")
        subtotal,vat,total=calculated
        item={"description":self.item_description.get().strip(),"quantity":quantity,"unit_price":price,
              "subtotal":subtotal,"vat_rate":rate,"vat":vat,"total":total}
        self.manual_items.append(item)
        debit=total if self.manual_kind.get()=="sale" else 0
        credit=total if self.manual_kind.get()=="purchase" else 0
        self.manual_tree.insert("","end",values=(item["description"],item["quantity"],f'{price:,.2f}',f'{subtotal:,.2f}',f'{rate:g}',f'{vat:,.2f}',f'{total:,.2f}',f'{debit:,.2f}',f'{credit:,.2f}'))
        self.item_description.set(""); self.item_quantity.set("1"); self.item_price.set("0"); self.item_subtotal.set("0.00")
        self.item_vat_rate.set("11"); self.item_vat.set("0.00"); self.item_total.set("0.00")
        self.subtotal_override.set(False); self.vat_override.set(False); self.update_manual_totals()

    def remove_manual_item(self):
        selected=self.manual_tree.selection()
        if not selected: return
        index=self.manual_tree.index(selected[0]); self.manual_tree.delete(selected[0]); self.manual_items.pop(index); self.update_manual_totals()

    def update_manual_totals(self):
        subtotal=sum(float(item["subtotal"]) for item in self.manual_items)
        vat=sum(float(item["vat"]) for item in self.manual_items)
        self.manual_totals.config(text=f"Before VAT: {subtotal:,.2f}   VAT: {vat:,.2f}   Total: {subtotal+vat:,.2f}")

    def manual_entry_report(self, format_name):
        if not self.manual_items:
            return messagebox.showwarning("Manual Entry","Add at least one invoice item")
        invoice_no=self.manual_no.get().strip() or "Draft"
        party=self.manual_party.get().strip() or "Unspecified"
        currency=self.manual_currency.get()
        title=f"Invoice {invoice_no} - {party} - {currency}"
        headers=["Description","Quantity","Unit Price","Before VAT","VAT %","VAT Amount","After VAT","Debit","Credit"]
        rows=[[item["description"],item["quantity"],item["unit_price"],item["subtotal"],item["vat_rate"],item["vat"],item["total"],
               item["total"] if self.manual_kind.get()=="sale" else 0,item["total"] if self.manual_kind.get()=="purchase" else 0] for item in self.manual_items]
        total_amount=sum(float(item["total"]) for item in self.manual_items)
        rows.append(["","",f"TOTAL {currency}",sum(float(item["subtotal"]) for item in self.manual_items),
                     "",sum(float(item["vat"]) for item in self.manual_items),total_amount,
                     total_amount if self.manual_kind.get()=="sale" else 0,total_amount if self.manual_kind.get()=="purchase" else 0])
        try:
            if format_name=="print":
                print_rows(title,headers,rows); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,
                filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],
                initialfile=f"Invoice_{invoice_no}_{currency}{extension}")
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows)
            messagebox.showinfo("Manual Entry",f"Saved successfully:\\n{path}")
        except Exception as exc:
            messagebox.showerror("Manual Entry",str(exc))

    def save_manual_invoice(self):
        invoice={"invoice_number":self.manual_no.get().strip(),"invoice_date":self.manual_date.get().strip(),
                 "party_name":self.manual_party.get().strip(),"kind":self.manual_kind.get(),"currency":self.manual_currency.get(),
                 "supplier_account":self.manual_supplier_account.get().strip() or "4011",
                 "vat_account":self.manual_vat_account.get().strip() or "4426.6",
                 "expense_account":self.manual_expense_account.get().strip() or "6011",
                 "source_file":"Manual Entry","source_row":None}
        if not all((invoice["invoice_number"],invoice["invoice_date"],invoice["party_name"])):
            return messagebox.showwarning("Manual Entry","Enter invoice number, date, and customer/supplier")
        if not self.manual_items: return messagebox.showwarning("Manual Entry","Add at least one invoice item")
        try: self.client.create_manual_invoice(invoice,self.manual_items)
        except Exception as exc: return messagebox.showerror("Manual Entry",str(exc))
        messagebox.showinfo("Manual Entry","Invoice saved successfully")
        self.manual_items=[]; self.manual_tree.delete(*self.manual_tree.get_children())
        self.manual_no.set(""); self.manual_party.set(""); self.update_manual_totals()
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial()

    def build_import(self):
        l=self.language.get(); controls=tk.Frame(self.import_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        self.file_label=tk.Label(controls,text="No file selected",bg=LIGHT,anchor="w"); self.file_label.pack(side="left",fill="x",expand=True)
        self.currency=tk.StringVar(value="USD")
        ttk.Combobox(controls,textvariable=self.currency,values=["USD","LBP","EUR","AED"],state="readonly",width=8).pack(side="right",padx=6)
        import_filter=ttk.Combobox(controls,textvariable=self.import_view_currency,values=["All Currencies","USD","EUR","LBP","AED"],state="readonly",width=15)
        import_filter.pack(side="right",padx=(4,2))
        tk.Button(controls,text="Apply",command=self.populate_import_preview,bg=GOLD,fg=NAVY,font=("Segoe UI",9,"bold"),border=0,padx=12,pady=5).pack(side="right",padx=4)
        tk.Label(controls,text="Show:",bg=LIGHT).pack(side="right")
        self.kind=tk.StringVar(value="purchase"); ttk.Combobox(controls,textvariable=self.kind,values=["purchase","sale"],state="readonly",width=10).pack(side="right",padx=6)
        tk.Button(controls,text=tr(l,"choose_file"),command=self.choose_import,bg=NAVY,fg="white",border=0,padx=16,pady=7).pack(side="right")
        self.import_tree=self.table(self.import_tab,[("no",tr(l,"invoice_no"),90),("row",tr(l,"source_row"),65),("date",tr(l,"date"),95),("party",tr(l,"party"),190),("currency",tr(l,"currency"),70),("subtotal",tr(l,"before_vat"),95),("vat",tr(l,"vat"),80),("total",tr(l,"total"),95),("debit","Debit",95),("credit","Credit",95),("supplier_account","Supplier A/C",90),("vat_account","VAT A/C",80),("expense_account","Expense A/C",90)])
        self.import_status=tk.Label(self.import_tab,text="",bg=LIGHT); self.import_status.pack()
        tk.Button(self.import_tab,text=tr(l,"send"),command=self.send_import,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=22,pady=8).pack(pady=10)

    def choose_import(self):
        path=filedialog.askopenfilename(filetypes=[("Excel files","*.xlsx")])
        if not path: return
        try: self.import_rows=read_invoices(path,default_currency=self.currency.get(),default_kind=self.kind.get())
        except Exception as exc: return messagebox.showerror("Import",str(exc))
        self.file_label.config(text=path); self.populate_import_preview()

    def populate_import_preview(self):
        self.import_tree.delete(*self.import_tree.get_children())
        selected=self.import_view_currency.get()
        rows=[r for r in self.import_rows if selected=="All Currencies" or r["currency"]==selected]
        for r in rows[:1000]:
            debit=r["total"] if r["kind"]=="sale" else 0
            credit=r["total"] if r["kind"]=="purchase" else 0
            self.import_tree.insert("","end",values=(r["invoice_number"],r["source_row"],r["invoice_date"],r["party_name"],r["currency"],r["subtotal"],r["vat"],r["total"],debit,credit,r["supplier_account"],r["vat_account"],r["expense_account"]))
        self.import_status.config(text=f'{len(rows)} {tr(self.language.get(),"rows_ready")} ({selected})')

    def send_import(self):
        if not self.import_rows: return messagebox.showwarning("Import","Choose a file first")
        if not messagebox.askyesno("Replace previous data","This import will remove all previous invoices and replace them with the selected Excel file. A safety backup will be created. Continue?"):
            return
        try: result=self.client.import_invoices(self.import_rows,replace_existing=True)
        except Exception as exc: return messagebox.showerror("Import",str(exc))
        messagebox.showinfo("Import",f'Previous invoices removed: {result["deleted"]}\n{result["imported"]} {tr(self.language.get(),"imported")}\nErrors: {len(result["errors"])}')
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial()

    def build_journal(self):
        filters=tk.Frame(self.journal_tab,bg=LIGHT); filters.pack(fill="x",padx=10,pady=(10,0))
        tk.Label(filters,text="From Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Entry(filters,textvariable=self.journal_from_date,width=13).pack(side="left",padx=(5,14))
        tk.Label(filters,text="To Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Entry(filters,textvariable=self.journal_to_date,width=13).pack(side="left",padx=(5,10))
        tk.Label(filters,text="DD-MM-YYYY",bg=LIGHT,fg="#5f6b76").pack(side="left",padx=(0,10))
        tk.Button(filters,text="Apply",command=self.load_journal,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=16,pady=6).pack(side="left")
        self.journal_tree=self.table(self.journal_tab,[
            ("entry","Entry No.",95),("date","Date",95),("description","Description",190),
            ("source","Source",75),("reference","Reference",75),("currency","Currency",70),
            ("account","Account",85),("account_name","Account Name",190),("party","Customer / Supplier",165),
            ("debit","Debit",105),("credit","Credit",105),("balance","Balance",110)])
        actions=tk.Frame(self.journal_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,"Refresh",self.load_journal).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.journal_report("xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.journal_report("pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.journal_report("print")).pack(side="left",padx=4)
        self.journal_totals=tk.Label(actions,text="Debit: 0.00   Credit: 0.00",bg=LIGHT,font=("Segoe UI",10,"bold"))
        self.journal_totals.pack(side="left",padx=15)
        self.load_journal()

    def journal_date_range(self):
        values=[]
        for label,raw in (("From Date",self.journal_from_date.get()),("To Date",self.journal_to_date.get())):
            value=raw.strip()
            if not value:
                values.append(None); continue
            try: values.append(datetime.strptime(value,"%d-%m-%Y").strftime("%Y-%m-%d"))
            except ValueError:
                messagebox.showwarning("General Journal",f"{label} must use DD-MM-YYYY"); return None
        if values[0] and values[1] and values[0]>values[1]:
            messagebox.showwarning("General Journal","From Date cannot be after To Date"); return None
        return values

    def load_journal(self):
        if not hasattr(self,"journal_tree"): return
        dates=self.journal_date_range()
        if dates is None: return
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try: rows=self.client.journal(dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("General Journal",str(exc))
        self.journal_rows=rows; self.journal_tree.delete(*self.journal_tree.get_children())
        for row in rows:
            self.journal_tree.insert("","end",values=(row["entry_number"],row["entry_date"],row["description"],
                row["source_type"],row["source_id"],row["currency"],row["account_code"],row["account_name"],
                row["party_name"],f'{row["debit"]:,.2f}',f'{row["credit"]:,.2f}',f'{row["balance"]:,.2f}'))
        debit=sum(float(row["debit"] or 0) for row in rows); credit=sum(float(row["credit"] or 0) for row in rows)
        state="Balanced" if abs(debit-credit)<0.005 else "UNBALANCED"
        self.journal_totals.config(text=f"Debit: {debit:,.2f}   Credit: {credit:,.2f}   {state}")

    def journal_report(self,format_name):
        rows=getattr(self,"journal_rows",[])
        if not rows: return messagebox.showwarning("General Journal","No journal data to export")
        title="Saber Accounting - General Journal"
        headers=["Entry No.","Date","Description","Source","Reference","Currency","Account","Account Name","Customer / Supplier","Debit","Credit","Balance"]
        values=[[r["entry_number"],r["entry_date"],r["description"],r["source_type"],r["source_id"],r["currency"],
                 r["account_code"],r["account_name"],r["party_name"],r["debit"],r["credit"],r["balance"]] for r in rows]
        values.append(["","","","","","","","","TOTAL",sum(float(r["debit"] or 0) for r in rows),sum(float(r["credit"] or 0) for r in rows),""])
        try:
            if format_name=="print": print_rows(title,headers,values); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],initialfile="Saber_Accounting_General_Journal"+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,values)
            messagebox.showinfo("General Journal",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("General Journal",str(exc))

    def build_statement(self):
        controls=tk.Frame(self.statement_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        tk.Label(controls,text="Client / Supplier:",bg=LIGHT).pack(side="left")
        self.statement_party_combo=ttk.Combobox(controls,textvariable=self.statement_party,state="readonly",width=28)
        self.statement_party_combo.pack(side="left",padx=5)
        tk.Button(controls,text="Refresh Parties",command=self.refresh_statement_parties,bg=NAVY,fg="white",border=0,padx=10,pady=5).pack(side="left",padx=3)
        tk.Label(controls,text="From:",bg=LIGHT).pack(side="left",padx=(8,2))
        tk.Entry(controls,textvariable=self.statement_from_date,width=12).pack(side="left")
        tk.Label(controls,text="To:",bg=LIGHT).pack(side="left",padx=(8,2))
        tk.Entry(controls,textvariable=self.statement_to_date,width=12).pack(side="left")
        ttk.Combobox(controls,textvariable=self.statement_currency,values=["All Currencies","USD","EUR","LBP","AED"],state="readonly",width=14).pack(side="left",padx=8)
        tk.Button(controls,text="Apply",command=self.load_statement,bg=GOLD,fg=NAVY,font=("Segoe UI",9,"bold"),border=0,padx=15,pady=6).pack(side="left")
        self.statement_tree=self.table(self.statement_tab,[("date","Date",100),("invoice","Invoice",110),("description","Description",230),
            ("currency","Currency",80),("debit","Debit",120),("credit","Credit",120),("balance","Balance",130)])
        actions=tk.Frame(self.statement_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,"Export Excel",lambda:self.statement_report("xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.statement_report("pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.statement_report("print")).pack(side="left",padx=4)
        self.statement_total=tk.Label(actions,text="",bg=LIGHT,font=("Segoe UI",10,"bold")); self.statement_total.pack(side="left",padx=15)
        self.load_statement_parties()

    def refresh_statement_parties(self):
        self.load_statement_parties()
        if self.statement_party.get():
            self.load_statement()

    def load_statement_parties(self):
        try: parties=self.client.parties()
        except Exception as exc: return messagebox.showerror("Statement",str(exc))
        self.statement_parties={f'{p["name"]} ({p["kind"]})':p for p in parties}
        values=list(self.statement_parties)
        self.statement_party_combo["values"]=values
        if values and self.statement_party.get() not in self.statement_parties: self.statement_party.set(values[0])

    def statement_date_range(self):
        result=[]
        for label,value in (("From Date",self.statement_from_date.get().strip()),("To Date",self.statement_to_date.get().strip())):
            if not value: result.append(None); continue
            try: result.append(datetime.strptime(value,"%d-%m-%Y").strftime("%Y-%m-%d"))
            except ValueError:
                messagebox.showwarning("Statement",f"{label} must use DD-MM-YYYY"); return None
        if result[0] and result[1] and result[0]>result[1]:
            messagebox.showwarning("Statement","From Date cannot be after To Date"); return None
        return result

    def load_statement(self):
        party=self.statement_parties.get(self.statement_party.get()) if hasattr(self,"statement_parties") else None
        if not party: return
        dates=self.statement_date_range()
        if dates is None: return
        currency=None if self.statement_currency.get()=="All Currencies" else self.statement_currency.get()
        try: data=self.client.statement(party["id"],dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("Statement",str(exc))
        rows=data["items"]; opening=data.get("opening",{})
        self.statement_rows=rows; self.statement_data=data; self.statement_tree.delete(*self.statement_tree.get_children())
        for row in rows:
            self.statement_tree.insert("","end",values=(row["invoice_date"],row["invoice_number"],row["description"],row["currency"],
                f'{row["debit"]:,.2f}',f'{row["credit"]:,.2f}',f'{row["balance"]:,.2f}'))
        totals={}
        for row in rows: totals[row["currency"]]=row["balance"]
        summary="   ".join(f"{code}: {value:,.2f}" for code,value in totals.items())
        if opening: summary="Opening: "+" / ".join(f"{k} {v:,.2f}" for k,v in opening.items())+"   Closing: "+summary
        self.statement_total.config(text=summary or "No transactions")

    def statement_report(self,format_name):
        rows=getattr(self,"statement_rows",[])
        if not rows: return messagebox.showwarning("Statement","No statement data to export")
        party=self.statement_data["party"]; title=f'Statement of Account - {party["name"]}'
        headers=["Date","Invoice","Description","Currency","Debit","Credit","Balance"]
        values=[[r["invoice_date"],r["invoice_number"],r["description"],r["currency"],r["debit"],r["credit"],r["balance"]] for r in rows]
        try:
            if format_name=="print": print_rows(title,headers,values); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],initialfile="Statement_"+party["name"].replace(" ","_")+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,values)
            messagebox.showinfo("Statement",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("Statement",str(exc))

    def build_accounts(self):
        controls=tk.Frame(self.accounts_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=(10,0))
        tk.Label(controls,text="Official Lebanese PCGL - Classes 1 to 7",bg=LIGHT,
                 font=("Segoe UI",11,"bold"),fg=NAVY).pack(side="left")
        self.action_button(controls,tr(self.language.get(),"refresh"),self.load_accounts).pack(side="right")
        self.accounts_tree=self.table(self.accounts_tab,[
            ("code","Account",100),("parent","Parent",80),("english","English",270),
            ("french","French",270),("arabic","Arabic",270),("type","Type",90)])
        self.load_accounts()

    def load_accounts(self):
        try:
            rows=self.client.accounts()
        except Exception as exc:
            return messagebox.showerror("Error",str(exc))
        self.accounts_tree.delete(*self.accounts_tree.get_children())
        for row in rows:
            self.accounts_tree.insert("","end",values=(row["code"],row.get("parent_code") or "",
                row["name_en"],row.get("name_fr") or "",row.get("name_ar") or "",row["type"]))

    def build_trial(self):
        filters=tk.Frame(self.trial_tab,bg=LIGHT); filters.pack(fill="x",padx=10,pady=(10,0))
        tk.Label(filters,text="From Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Entry(filters,textvariable=self.trial_from_date,width=13).pack(side="left",padx=(5,14))
        tk.Label(filters,text="To Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Entry(filters,textvariable=self.trial_to_date,width=13).pack(side="left",padx=(5,10))
        tk.Label(filters,text="DD-MM-YYYY",bg=LIGHT,fg="#5f6b76").pack(side="left",padx=(0,10))
        tk.Button(filters,text="Apply",command=self.apply_trial_date_filter,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=16,pady=6).pack(side="left")
        self.trial_tree=self.table(self.trial_tab,[("currency","Currency",90),("code","Account",110),("name","Name",280),("debit","Debit",150),("credit","Credit",150),("balance","Balance",160)])
        actions=tk.Frame(self.trial_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_trial).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("trial","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("trial","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("trial","print")).pack(side="left",padx=4); self.load_trial()

    def trial_date_range(self, show_error=True):
        values = []
        for label, raw_value in (("From Date", self.trial_from_date.get()), ("To Date", self.trial_to_date.get())):
            value = raw_value.strip()
            if not value:
                values.append(None)
                continue
            try:
                values.append(datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d"))
            except ValueError:
                if show_error:
                    messagebox.showwarning("Trial Balance", f"{label} must use DD-MM-YYYY")
                return None
        if values[0] and values[1] and values[0] > values[1]:
            if show_error:
                messagebox.showwarning("Trial Balance", "From Date cannot be after To Date")
            return None
        return tuple(values)

    def apply_trial_date_filter(self):
        if self.trial_date_range() is not None:
            self.load_trial()

    def load_trial(self):
        date_range = self.trial_date_range()
        if date_range is None:
            return
        try: rows=self.client.trial_balance(*date_range)
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.trial_rows=rows; self.trial_tree.delete(*self.trial_tree.get_children())
        for r in rows: self.trial_tree.insert("","end",values=(r["currency"],r["code"],r["name_en"],f'{r["debit"] or 0:,.2f}',f'{r["credit"] or 0:,.2f}',f'{r["balance"] or 0:,.2f}'))

    def action_button(self,parent,text,command):
        return tk.Button(parent,text=text,command=command,bg=NAVY,fg="white",border=0,padx=15,pady=7)

    def export_report(self,report,format_name):
        if report == "dashboard":
            title="Saber Accounting - Dashboard"; headers=["Type","Currency","Invoices","Before VAT","VAT","Total","Debit","Credit"]
            rows=[[r["kind"],r["currency"],r["count"],r["subtotal"],r["vat"],r["total"],r["debit"],r["credit"]] for r in getattr(self,"dashboard_rows",[])]
        else:
            title="Saber Accounting - Trial Balance"
            if self.trial_from_date.get().strip() or self.trial_to_date.get().strip():
                title += f" ({self.trial_from_date.get().strip() or 'Beginning'} to {self.trial_to_date.get().strip() or 'Today'})"
            headers=["Currency","Account","Name","Debit","Credit","Balance"]
            rows=[[r["currency"],r["code"],r["name_en"],r["debit"] or 0,r["credit"] or 0,r["balance"] or 0] for r in getattr(self,"trial_rows",[])]
            rows.append(["","","TOTAL",sum(float(r[3]) for r in rows),sum(float(r[4]) for r in rows),sum(float(r[5]) for r in rows)])
        if not rows: return messagebox.showwarning("Saber Accounting","No report data to export")
        try:
            if format_name == "print": print_rows(title,headers,rows); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],initialfile=title.replace(" - ","_").replace(" ","_")+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows)
            messagebox.showinfo("Saber Accounting",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("Saber Accounting",str(exc))

def main(): SaberApp().mainloop()

if __name__ == "__main__": main()
