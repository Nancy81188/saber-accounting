from __future__ import annotations

import tkinter as tk
import sys
import mimetypes
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from client import ApiClient
from i18n import tr
from importer import read_invoices
from report_export import export_excel, export_invoice_pdf, export_pdf, print_rows

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
        self.current_user = None
        self.last_activity = time.monotonic()
        self.import_rows = []
        self.manual_items = []
        self.view_currency = tk.StringVar(value="All Currencies")
        self.import_view_currency = tk.StringVar(value="All Currencies")
        self.trial_from_date = tk.StringVar()
        self.trial_to_date = tk.StringVar()
        self.trial_account = tk.StringVar(); self.trial_account_from=tk.StringVar(); self.trial_account_to=tk.StringVar(); self.trial_scope=tk.StringVar(value="Detailed Trial Balance"); self.trial_display_currency=tk.StringVar(value="USD + LBP")
        self.invoice_account_search=tk.StringVar()
        self.statement_party = tk.StringVar()
        self.statement_from_date = tk.StringVar()
        self.statement_to_date = tk.StringVar()
        self.statement_currency = tk.StringVar(value="All Currencies")
        self.statement_display_currency = tk.StringVar(value="Original")
        self.statement_include_opening = tk.BooleanVar(value=True)
        self.journal_from_date = tk.StringVar()
        self.journal_to_date = tk.StringVar()
        self.pnl_from_date = tk.StringVar(value=f"01-01-{datetime.now().year}")
        self.pnl_to_date = tk.StringVar(value=f"31-12-{datetime.now().year}")
        self.close_year = tk.StringVar(value=str(datetime.now().year))
        self.report_from_date = tk.StringVar(value=f"01-01-{datetime.now().year}")
        self.report_to_date = tk.StringVar(value=f"31-12-{datetime.now().year}")
        self.ledger_account = tk.StringVar()
        self._style()
        self.login_screen()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook.Tab", padding=(8, 8), font=("Segoe UI", 8, "bold"))
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
            entry=tk.Entry(card,textvariable=var,width=34,show="*" if secret else "")
            entry.grid(row=row,column=1,pady=7)
            if secret:
                entry.bind("<Return>",lambda _event:self.login())
        tk.Label(card,text="Language",bg="white").grid(row=5,column=0,sticky="w",pady=7)
        ttk.Combobox(card,textvariable=self.language,values=["en","ar","fr"],state="readonly",width=31).grid(row=5,column=1,pady=7)
        tk.Button(card,text="Sign in",command=self.login,bg=NAVY,fg="white",activebackground=GOLD,width=29,pady=8,border=0).grid(row=6,column=0,columnspan=2,pady=(22,0))

    def login(self):
        try:
            self.client = ApiClient(self.server.get())
            self.current_user=self.client.login(self.username.get(), self.password.get())
            self.last_activity=time.monotonic(); self.bind_all("<Any-KeyPress>",self.record_activity); self.bind_all("<Any-Button>",self.record_activity); self.after(60000,self.check_auto_logout)
            self.company_selection_screen()
        except Exception as exc: messagebox.showerror("Saber Accounting", str(exc))

    def company_selection_screen(self):
        try: companies=self.client.companies()
        except Exception as exc: return messagebox.showerror("Companies",str(exc))
        self.available_companies=companies; self.clear()
        card=tk.Frame(self,bg="white",padx=42,pady=34); card.place(relx=.5,rely=.5,anchor="center")
        tk.Label(card,text="Select Company & Fiscal Year",bg="white",fg=NAVY,font=("Segoe UI",18,"bold")).grid(row=0,column=0,columnspan=2,pady=(0,20))
        labels={f'{c["name"]} ({"Active" if c.get("active",True) else "Inactive"})':c for c in companies}; company_var=tk.StringVar(value=next(iter(labels),"")); year_var=tk.StringVar()
        tk.Label(card,text="Company",bg="white").grid(row=1,column=0,sticky="w",pady=8); company_box=ttk.Combobox(card,textvariable=company_var,values=list(labels),state="readonly",width=34); company_box.grid(row=1,column=1,pady=8)
        tk.Label(card,text="Fiscal Year",bg="white").grid(row=2,column=0,sticky="w",pady=8); year_box=ttk.Combobox(card,textvariable=year_var,state="readonly",width=34); year_box.grid(row=2,column=1,pady=8)
        def refresh_years(*_args):
            company=labels.get(company_var.get()); years=[str(y["year"]) for y in company.get("years",[])] if company else []
            year_box["values"]=years; year_var.set(years[-1] if years else "")
        company_box.bind("<<ComboboxSelected>>",refresh_years); refresh_years()
        def open_company():
            company=labels.get(company_var.get())
            if not company or not year_var.get(): return messagebox.showwarning("Companies","Select a company and fiscal year")
            if not company.get("active",True): return messagebox.showwarning("Companies","This company is inactive")
            self.client.select_company_year(company["id"],year_var.get()); self.current_company=company; self.current_fiscal_year=int(year_var.get()); self.main_screen()
        tk.Button(card,text="Open Company",command=open_company,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=25,pady=8).grid(row=3,column=0,columnspan=2,pady=(18,6))
        if self.current_user.get("role")=="admin":
            self.action_button(card,"Create Company",self.create_company_dialog).grid(row=4,column=0,padx=4,pady=5)
            self.action_button(card,"Manage Selected",lambda:self.manage_company_dialog(labels.get(company_var.get()))).grid(row=4,column=1,padx=4,pady=5)

    def create_company_dialog(self):
        window=tk.Toplevel(self); window.title("Create Company"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        fields={key:tk.StringVar(value=str(datetime.now().year) if key=="year" else "") for key in ("name","year","address","phone","mof_number","email","website")}
        for row,(key,label) in enumerate((("name","Company Name"),("year","Opening Fiscal Year"),("address","Address"),("phone","Phone"),("mof_number","MOF / VAT Number"),("email","Email"),("website","Website"))):
            tk.Label(window,text=label,bg=LIGHT).grid(row=row,column=0,sticky="w",padx=14,pady=7); tk.Entry(window,textvariable=fields[key],width=38).grid(row=row,column=1,padx=14,pady=7)
        def save():
            try: self.client.create_company({key:var.get().strip() for key,var in fields.items()})
            except Exception as exc: return messagebox.showerror("Create Company",str(exc),parent=window)
            window.destroy(); self.company_selection_screen()
        self.action_button(window,"Create Company",save).grid(row=7,column=0,columnspan=2,pady=14)

    def manage_company_dialog(self,company):
        if not company: return
        window=tk.Toplevel(self); window.title("Manage Company"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        name=tk.StringVar(value=company["name"]); new_year=tk.StringVar(value=str(max(int(y["year"]) for y in company.get("years",[]))+1)); active=tk.BooleanVar(value=company.get("active",True))
        tk.Label(window,text="Company Name",bg=LIGHT).grid(row=0,column=0,padx=14,pady=8); tk.Entry(window,textvariable=name,width=32).grid(row=0,column=1,padx=14,pady=8)
        tk.Checkbutton(window,text="Active",variable=active,bg=LIGHT).grid(row=1,column=0,columnspan=2,pady=5)
        tk.Label(window,text="New Fiscal Year",bg=LIGHT).grid(row=2,column=0,padx=14,pady=8); tk.Entry(window,textvariable=new_year,width=12).grid(row=2,column=1,padx=14,pady=8,sticky="w")
        def update():
            try: self.client.update_company(company["id"],{"name":name.get(),"active":active.get()})
            except Exception as exc: return messagebox.showerror("Company",str(exc),parent=window)
            window.destroy(); self.company_selection_screen()
        def create_year():
            if not messagebox.askyesno("Fiscal Year","Close the latest year and create the new year with opening balances?",parent=window): return
            try: self.client.create_fiscal_year(company["id"],int(new_year.get()))
            except Exception as exc: return messagebox.showerror("Fiscal Year",str(exc),parent=window)
            window.destroy(); self.company_selection_screen()
        self.action_button(window,"Save Company",update).grid(row=3,column=0,padx=6,pady=14); self.action_button(window,"Close & Create Year",create_year).grid(row=3,column=1,padx=6,pady=14)

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
        tk.Button(top,text="Switch Company / Year",command=self.company_selection_screen,bg=GOLD,fg=NAVY,border=0,padx=10,pady=5).pack(side="right",padx=5)
        tk.Label(top,text=f'{getattr(self,"current_company",{}).get("name","")} · {getattr(self,"current_fiscal_year","")}',bg=NAVY,fg="white",font=("Segoe UI",9,"bold")).pack(side="right",padx=8)
        tab_nav=tk.Frame(self,bg=LIGHT); tab_nav.pack(fill="x",padx=18,pady=(8,0))
        ttk.Style(self).layout("Tabless.TNotebook.Tab",[])
        notebook=ttk.Notebook(self,style="Tabless.TNotebook"); self.main_notebook=notebook; notebook.pack(fill="both",expand=True,padx=18,pady=(6,16))
        self.dashboard_tab=tk.Frame(notebook,bg=LIGHT); self.invoices_tab=tk.Frame(notebook,bg=LIGHT); self.manual_tab=tk.Frame(notebook,bg=LIGHT); self.import_tab=tk.Frame(notebook,bg=LIGHT); self.parties_tab=tk.Frame(notebook,bg=LIGHT); self.transactions_tab=tk.Frame(notebook,bg=LIGHT); self.journal_tab=tk.Frame(notebook,bg=LIGHT); self.trial_tab=tk.Frame(notebook,bg=LIGHT); self.pnl_tab=tk.Frame(notebook,bg=LIGHT); self.reports_tab=tk.Frame(notebook,bg=LIGHT); self.accounts_tab=tk.Frame(notebook,bg=LIGHT); self.statement_tab=tk.Frame(notebook,bg=LIGHT); self.settings_tab=tk.Frame(notebook,bg=LIGHT)
        notebook.add(self.dashboard_tab,text=tr(lang,"dashboard")); notebook.add(self.invoices_tab,text=tr(lang,"invoices")); notebook.add(self.manual_tab,text=tr(lang,"manual_entry")); notebook.add(self.import_tab,text=tr(lang,"import")); notebook.add(self.parties_tab,text=tr(lang,"customers_suppliers")); notebook.add(self.transactions_tab,text=tr(lang,"payments_expenses")); notebook.add(self.journal_tab,text=tr(lang,"general_journal")); notebook.add(self.trial_tab,text=tr(lang,"trial_balance")); notebook.add(self.pnl_tab,text=tr(lang,"profit_loss")); notebook.add(self.reports_tab,text=tr(lang,"financial_reports")); notebook.add(self.statement_tab,text=tr(lang,"statement_account")); notebook.add(self.accounts_tab,text=tr(lang,"chart_accounts")); notebook.add(self.settings_tab,text=tr(lang,"security_backup_rates"))
        self.main_tab_pages=[self.dashboard_tab,self.invoices_tab,self.manual_tab,self.import_tab,self.parties_tab,self.transactions_tab,self.journal_tab,self.trial_tab,self.pnl_tab,self.reports_tab,self.statement_tab,self.accounts_tab,self.settings_tab]
        self.tab_names=[notebook.tab(tab,"text") for tab in notebook.tabs()]
        self.tab_choice=tk.StringVar(value=self.tab_names[0])
        self.tab_buttons=[]
        for index,(page,name) in enumerate(zip(self.main_tab_pages,self.tab_names)):
            row=0 if index<7 else 1; column=index if index<7 else index-7
            tab_nav.grid_columnconfigure(column,weight=1,uniform="main_tabs")
            button=tk.Button(tab_nav,text=name,command=lambda p=page:self.select_main_tab(p),bg=NAVY,fg="white",
                activebackground=GOLD,activeforeground=NAVY,border=1,font=("Segoe UI",8,"bold"),pady=5,wraplength=145)
            button.grid(row=row,column=column,sticky="nsew",padx=2,pady=2); self.tab_buttons.append(button)
        notebook.bind("<<NotebookTabChanged>>",lambda _event:self.highlight_main_tab())
        self.highlight_main_tab()
        filter_bar=tk.Frame(self,bg=LIGHT); filter_bar.pack(fill="x",padx=28)
        tk.Label(filter_bar,text="Show currency:",bg=LIGHT,font=("Segoe UI",10,"bold")).pack(side="left")
        currency_filter=ttk.Combobox(filter_bar,textvariable=self.view_currency,values=["All Currencies","USD","EUR","LBP","AED"],state="readonly",width=16)
        currency_filter.pack(side="left",padx=8); currency_filter.bind("<<ComboboxSelected>>",lambda _event:self.currency_changed())
        self.build_dashboard(); self.build_invoices(); self.build_manual(); self.build_import(); self.build_parties(); self.build_transactions(); self.build_journal(); self.build_trial(); self.build_profit_loss(); self.build_financial_reports(); self.build_statement(); self.build_accounts(); self.build_settings()

    def record_activity(self,_event=None): self.last_activity=time.monotonic()

    def check_auto_logout(self):
        if self.client and time.monotonic()-self.last_activity>=1800:
            self.client=None; self.current_user=None; self.login_screen(); messagebox.showinfo("Saber Accounting","Signed out automatically after 30 minutes of inactivity"); return
        self.after(60000,self.check_auto_logout)

    def move_main_tab(self,direction):
        try: current_page=self.main_notebook.select(); current=self.main_tab_pages.index(self.nametowidget(current_page))
        except (ValueError,KeyError): current=self.visible_tab_start
        target=(current+direction)%len(self.main_tab_pages)
        start=self.visible_tab_start
        if target<start: start=target
        elif target>=start+6: start=target-5
        if direction>0 and current==len(self.main_tab_pages)-1: start=0
        elif direction<0 and current==0: start=max(0,len(self.main_tab_pages)-6)
        self.show_tab_window(start,target)

    def select_main_tab(self,page):
        self.main_notebook.select(page); self.highlight_main_tab()

    def highlight_main_tab(self):
        selected=self.main_notebook.select()
        for page,button in zip(getattr(self,"main_tab_pages",[]),getattr(self,"tab_buttons",[])):
            button.config(bg=GOLD if str(page)==selected else NAVY,fg=NAVY if str(page)==selected else "white")

    def show_tab_window(self,start,selected_index=None):
        maximum=max(0,len(self.main_tab_pages)-6); self.visible_tab_start=max(0,min(start,maximum))
        for page in self.main_tab_pages:
            try: self.main_notebook.forget(page)
            except tk.TclError: pass
        end=min(len(self.main_tab_pages),self.visible_tab_start+6)
        for index in range(self.visible_tab_start,end):
            self.main_notebook.add(self.main_tab_pages[index],text=self.tab_names[index],padding=(8,4))
        target=selected_index if selected_index is not None and self.visible_tab_start<=selected_index<end else self.visible_tab_start
        self.main_notebook.select(self.main_tab_pages[target]); self.tab_choice.set(self.tab_names[target])

    def select_named_tab(self):
        try:
            index=self.tab_names.index(self.tab_choice.get()); self.show_tab_window(max(0,min(index,len(self.main_tab_pages)-6)),index)
        except ValueError: pass

    def currency_changed(self):
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial(); self.load_profit_loss(); self.load_financial_reports()

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
        tree._sort_reverse={}
        def sort_column(key):
            reverse=tree._sort_reverse.get(key,False)
            def sortable(value):
                clean=str(value).replace(",","").strip()
                try: return (0,float(clean))
                except ValueError: return (1,clean.casefold())
            ordered=sorted(tree.get_children(""),key=lambda item:sortable(tree.set(item,key)),reverse=reverse)
            for position,item in enumerate(ordered): tree.move(item,"",position)
            tree._sort_reverse[key]=not reverse
        for key,label,_width in columns: tree.heading(key,text=label,command=lambda column=key:sort_column(column))
        search_var.trace_add("write",apply_search)
        search_entry.bind("<Escape>",lambda _event:search_var.set(""))
        return tree

    def build_dashboard(self):
        self.dashboard_tree=self.table(self.dashboard_tab,[("currency","Currency",85),("sales","Sales",120),("purchases","Purchases",120),("expenses","Expenses",120),("profit","Net Profit",120),("receivables","Receivables",120),("payables","Payables",120),("overdue","Overdue",80)])
        self.dashboard_chart=tk.Canvas(self.dashboard_tab,height=150,bg="white",highlightthickness=0); self.dashboard_chart.pack(fill="x",padx=10,pady=(0,8))
        actions=tk.Frame(self.dashboard_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_dashboard).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("dashboard","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("dashboard","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("dashboard","print")).pack(side="left",padx=4)
        self.load_dashboard()

    def load_dashboard(self):
        try: data=self.client.professional_dashboard(); rows=data["metrics"]
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.dashboard_rows=rows; self.dashboard_tree.delete(*self.dashboard_tree.get_children())
        for r in rows: self.dashboard_tree.insert("", "end", values=(r["currency"],f'{r["sales"]:,.2f}',f'{r["purchases"]:,.2f}',f'{r["expenses"]:,.2f}',f'{r["profit"]:,.2f}',f'{r["receivables"]:,.2f}',f'{r["payables"]:,.2f}',r["overdue"]))
        self.draw_dashboard_chart([r for r in data.get("monthly",[]) if selected=="All Currencies" or r["currency"]==selected])

    def draw_dashboard_chart(self,rows):
        canvas=self.dashboard_chart; canvas.delete("all"); canvas.update_idletasks(); width=max(canvas.winfo_width(),700); height=145
        values=[float(row["amount"] or 0) for row in rows[-12:]]; maximum=max(values or [1])
        canvas.create_text(10,10,anchor="nw",text="Monthly Sales / Purchases",fill=NAVY,font=("Segoe UI",10,"bold"))
        for index,row in enumerate(rows[-12:]):
            x=20+index*max(48,(width-40)//max(1,min(12,len(rows))))
            bar_height=(float(row["amount"] or 0)/maximum)*90
            color="#1F6E8C" if row["kind"]=="sale" else GOLD
            canvas.create_rectangle(x,height-25-bar_height,x+24,height-25,fill=color,outline="")
            canvas.create_text(x+12,height-12,text=str(row["month"])[5:],font=("Segoe UI",7))

    def build_invoices(self):
        l=self.language.get(); self.invoice_tree=self.table(self.invoices_tab,[("no",tr(l,"invoice_no"),90),("date",tr(l,"date"),90),("party",tr(l,"party"),160),("kind","Type",90),("currency",tr(l,"currency"),60),("deductible","Deductible",95),("non_deductible","Non-Deductible",105),("total",tr(l,"total"),90),("payment_method","Payment Method",110),("paid","Paid Amount",100),("lbp","LBP Eq.",105),("usd","USD Eq.",90),("debit","D",80),("credit","C",80)])
        invoice_actions=tk.Frame(self.invoices_tab,bg=LIGHT); invoice_actions.pack(pady=(0,10))
        tk.Label(invoice_actions,text="Account:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left",padx=(2,0))
        self.account_search_box(invoice_actions,self.invoice_account_search,18).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Apply",command=self.load_invoices,bg=GOLD,fg=NAVY,border=0,padx=10,pady=7).pack(side="left",padx=3)
        tk.Button(invoice_actions,text=tr(l,"refresh"),command=self.load_invoices,bg=NAVY,fg="white",border=0,padx=20,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Save Data",command=self.confirm_invoice_data_saved,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Export Excel",command=self.export_invoices_excel,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Add Invoice Row",command=self.add_invoice_row,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Add Item",command=self.add_item_to_selected_invoice,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Edit Selected",command=self.edit_selected_invoice,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=20,pady=7).pack(side="left",padx=4)
        lifecycle=tk.Frame(self.invoices_tab,bg=LIGHT); lifecycle.pack(pady=(0,8))
        self.action_button(lifecycle,"Duplicate",self.duplicate_selected_invoice).pack(side="left",padx=4)
        tk.Button(lifecycle,text="Cancel Invoice",command=self.cancel_selected_invoice,bg="#8B1E1E",fg="white",border=0,padx=15,pady=7).pack(side="left",padx=4)
        tk.Button(lifecycle,text="Delete Selected",command=self.delete_selected_invoice,bg="#6B1010",fg="white",border=0,padx=15,pady=7).pack(side="left",padx=4)
        self.action_button(lifecycle,"Attach PDF / Image",self.attach_to_selected_invoice).pack(side="left",padx=4)
        self.action_button(lifecycle,"Attachments",self.show_selected_attachments).pack(side="left",padx=4)
        self.action_button(lifecycle,"History",self.show_invoice_history).pack(side="left",padx=4)
        self.action_button(lifecycle,"Branded Invoice PDF",self.export_selected_invoice_pdf).pack(side="left",padx=4)
        self.invoice_tree.bind("<Double-1>",lambda _event:self.edit_selected_invoice())
        self.load_invoices()

    def load_invoices(self):
        try: rows=self.client.invoices(); rates=self.client.exchange_rates()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        account=self.invoice_account_search.get().split(" - ",1)[0].strip()
        if account: rows=[row for row in rows if account in (str(row.get("supplier_account") or ""),str(row.get("vat_account") or ""),str(row.get("expense_account") or ""),str(row.get("expense_no_vat_account") or ""))]
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.invoice_rows={str(r["id"]):r for r in rows}
        self.invoice_tree.delete(*self.invoice_tree.get_children())
        for r in rows:
            lbp,usd=self.exchange_equivalents(float(r["total"] or 0),r["currency"],rates)
            self.invoice_tree.insert("","end",iid=str(r["id"]),values=(r["invoice_number"],r["invoice_date"],r["party_name"],r.get("entry_type") or r["kind"],r["currency"],r.get("deductible_subtotal",r["subtotal"]),r.get("non_deductible_subtotal",0),r["total"],r.get("payment_method") or "",r.get("amount_paid") or 0,"" if lbp is None else f"{lbp:,.2f}","" if usd is None else f"{usd:,.2f}",r["debit"],r["credit"]))

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
            "kind":tk.StringVar(value=row.get("entry_type") or ("sales" if row["kind"]=="sale" else "purchases")),
            "currency":tk.StringVar(value=row["currency"]),
            "deductible_subtotal":tk.StringVar(value=row.get("deductible_subtotal") or row["subtotal"]),
            "non_deductible_subtotal":tk.StringVar(value=row.get("non_deductible_subtotal") or "0"),
            "vat":tk.StringVar(value=row["vat"]),
            "total":tk.StringVar(value=row["total"]),
            "supplier_account":tk.StringVar(value=row["supplier_account"]),
            "vat_account":tk.StringVar(value=row["vat_account"]),
            "expense_account":tk.StringVar(value=row["expense_account"]),
            "expense_no_vat_account":tk.StringVar(value=row.get("expense_no_vat_account") or "601100001"),
            "supplier_side":tk.StringVar(value="C - Credit" if (row.get("supplier_side") or "C")=="C" else "D - Debit"),
            "vat_side":tk.StringVar(value="C - Credit" if (row.get("vat_side") or "D")=="C" else "D - Debit"),
            "expense_side":tk.StringVar(value="C - Credit" if (row.get("expense_side") or "D")=="C" else "D - Debit"),
            "expense_no_vat_side":tk.StringVar(value="C - Credit" if (row.get("expense_no_vat_side") or "D")=="C" else "D - Debit"),
            "status":tk.StringVar(value=row["status"]),
            "due_date":tk.StringVar(value=row.get("due_date") or ""),
            "amount_paid":tk.StringVar(value=row.get("amount_paid") or "0"),
            "payment_method":tk.StringVar(value=row.get("payment_method") or "Cash"),
            "debit":tk.StringVar(value=row.get("debit") or "0"),
            "credit":tk.StringVar(value=row.get("credit") or "0"),
        }
        fields=[
            ("Invoice Number","invoice_number"),("Date (DD-MM-YYYY)","invoice_date"),
            ("Customer / Supplier","party_name"),("Type","kind"),("Currency","currency"),
            ("Before VAT Deductible","deductible_subtotal"),("Before VAT Non-Deductible","non_deductible_subtotal"),("VAT","vat"),("Total","total"),
            ("Supplier Account","supplier_account"),("VAT Account","vat_account"),
            ("Expense Account","expense_account"),("Expense Account without VAT","expense_no_vat_account"),("Status","status"),
            ("Due Date (DD-MM-YYYY)","due_date"),("Payment Method","payment_method"),("Paid Amount","amount_paid"),("D","debit"),("C","credit"),
        ]
        for index,(label,key) in enumerate(fields):
            grid_row=index//2; grid_column=(index%2)*2
            tk.Label(window,text=label,bg=LIGHT,anchor="w").grid(row=grid_row,column=grid_column,sticky="w",padx=(14,5),pady=8)
            if key=="kind":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["assets","expenses","purchases","sales"],state="readonly",width=24)
            elif key=="currency":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["USD","EUR","LBP","AED"],state="readonly",width=24)
            elif key=="status":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["posted","review"],state="readonly",width=24)
            elif key=="payment_method":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["Cash","Bank Transfer","Cheque","Card","Other"],state="readonly",width=24)
            elif key in ("supplier_account","vat_account","expense_account","expense_no_vat_account"):
                frame=tk.Frame(window,bg=LIGHT); side_key={"supplier_account":"supplier_side","vat_account":"vat_side","expense_account":"expense_side","expense_no_vat_account":"expense_no_vat_side"}[key]
                self.account_search_box(frame,variables[key],18).pack(side="left")
                ttk.Combobox(frame,textvariable=variables[side_key],values=["D - Debit","C - Credit"],state="readonly",width=10).pack(side="left",padx=(5,0))
                widget=frame
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
                deductible=float(values["deductible_subtotal"]); non_deductible=float(values["non_deductible_subtotal"]); subtotal=deductible+non_deductible; vat=float(values["vat"]); total=float(values["total"]); float(values["debit"]); float(values["credit"])
                amount_paid=float(values["amount_paid"] or 0)
            except ValueError:
                return messagebox.showwarning("Invoices","Deductible, Non-Deductible, VAT, and Total must be valid numbers",parent=window)
            if abs((subtotal+vat)-total)>0.005:
                return messagebox.showwarning("Invoices","Total must equal Before VAT plus VAT",parent=window)
            if amount_paid<0 or amount_paid>total:
                return messagebox.showwarning("Invoices","Amount paid must be between zero and Total",parent=window)
            try:
                self.client.update_invoice(int(invoice_id),values)
            except Exception as exc:
                return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy()
            self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Invoices","Invoice updated successfully")

        exchange_label=tk.Label(window,text=self.exchange_equivalent_text(float(row["total"] or 0),row["currency"]),bg=LIGHT,fg=NAVY,font=("Segoe UI",9,"bold"))
        exchange_label.grid(row=(len(fields)+1)//2,column=0,columnspan=4,pady=(6,0))
        buttons=tk.Frame(window,bg=LIGHT); buttons.grid(row=(len(fields)+1)//2+1,column=0,columnspan=4,pady=16)
        tk.Button(buttons,text="Save Update",command=save_update,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),
                  border=0,padx=24,pady=8).pack(side="left",padx=5)
        tk.Button(buttons,text="Cancel",command=window.destroy,bg=NAVY,fg="white",border=0,padx=20,pady=8).pack(side="left",padx=5)

    def selected_invoice_id(self):
        selected=self.invoice_tree.selection()
        if not selected:
            messagebox.showwarning("Invoices","Select one invoice row first"); return None
        return int(selected[0])

    def delete_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        if not messagebox.askyesno("Delete Uploaded Data","Permanently delete the selected row and its journal entry?\nThis action is recorded in the audit log."): return
        try: self.client.delete_invoice(invoice_id)
        except Exception as exc: return messagebox.showerror("Delete Uploaded Data",str(exc))
        self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial(); messagebox.showinfo("Uploaded Data","Selected row deleted")

    def duplicate_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: created=self.client.duplicate_invoice(invoice_id)
        except Exception as exc: return messagebox.showerror("Invoices",str(exc))
        self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
        messagebox.showinfo("Invoices",f'Invoice duplicated as {created["invoice_number"]}')

    def cancel_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        row=self.invoice_rows.get(str(invoice_id),{})
        if row.get("status")=="cancelled": return messagebox.showwarning("Invoices","Invoice is already cancelled")
        window=tk.Toplevel(self); window.title("Cancel Invoice"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        reason=tk.StringVar()
        tk.Label(window,text="Cancellation reason:",bg=LIGHT).grid(row=0,column=0,padx=14,pady=14)
        tk.Entry(window,textvariable=reason,width=45).grid(row=0,column=1,padx=14,pady=14)
        def confirm():
            if not reason.get().strip(): return messagebox.showwarning("Cancel Invoice","Enter a cancellation reason",parent=window)
            try: self.client.cancel_invoice(invoice_id,reason.get().strip())
            except Exception as exc: return messagebox.showerror("Cancel Invoice",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Cancel Invoice","Invoice cancelled and reversing journal entry created")
        tk.Button(window,text="Confirm Cancellation",command=confirm,bg="#8B1E1E",fg="white",border=0,padx=18,pady=7).grid(row=1,column=0,columnspan=2,pady=12)

    def attach_to_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        path=filedialog.askopenfilename(filetypes=[("Invoice files","*.pdf *.png *.jpg *.jpeg"),("All files","*.*")])
        if not path: return
        try:
            content=Path(path).read_bytes()
            mime=mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.client.upload_attachment(invoice_id,Path(path).name,mime,content)
        except Exception as exc: return messagebox.showerror("Attachments",str(exc))
        self.load_invoices(); messagebox.showinfo("Attachments","File attached successfully")

    def show_selected_attachments(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: items=self.client.attachments(invoice_id)
        except Exception as exc: return messagebox.showerror("Attachments",str(exc))
        if not items: return messagebox.showinfo("Attachments","This invoice has no attachments")
        window=tk.Toplevel(self); window.title("Invoice Attachments"); window.geometry("620x340")
        tree=ttk.Treeview(window,columns=("name","type","size","date"),show="headings")
        for key,label,width in (("name","File Name",240),("type","Type",140),("size","Size",80),("date","Uploaded",140)):
            tree.heading(key,text=label); tree.column(key,width=width)
        for item in items: tree.insert("","end",iid=str(item["id"]),values=(item["file_name"],item["mime_type"],f'{item["size"]/1024:,.1f} KB',item["uploaded_at"][:19]))
        tree.pack(fill="both",expand=True,padx=10,pady=10)
        def download():
            selected=tree.selection()
            if not selected: return messagebox.showwarning("Attachments","Select one file",parent=window)
            record=next(item for item in items if str(item["id"])==selected[0])
            path=filedialog.asksaveasfilename(initialfile=record["file_name"],parent=window)
            if not path: return
            try: Path(path).write_bytes(self.client.download_attachment(record["id"])["content"])
            except Exception as exc: return messagebox.showerror("Attachments",str(exc),parent=window)
            messagebox.showinfo("Attachments",f"Saved successfully:\n{path}",parent=window)
        self.action_button(window,"Download Selected",download).pack(pady=(0,10))

    def show_invoice_history(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: items=self.client.invoice_history(invoice_id)
        except Exception as exc: return messagebox.showerror("History",str(exc))
        window=tk.Toplevel(self); window.title("Invoice Modification History"); window.geometry("760x380")
        tree=ttk.Treeview(window,columns=("date","user","action","details"),show="headings")
        for key,label,width in (("date","Date",170),("user","User",100),("action","Action",100),("details","Details",370)):
            tree.heading(key,text=label); tree.column(key,width=width)
        for item in items: tree.insert("","end",values=(item["created_at"][:19],item.get("username") or "",item["action"],item.get("details") or ""))
        tree.pack(fill="both",expand=True,padx=10,pady=10)

    def export_selected_invoice_pdf(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: detail=self.client.invoice_detail(invoice_id)
        except Exception as exc: return messagebox.showerror("Invoice PDF",str(exc))
        invoice=detail["invoice"]; path=filedialog.asksaveasfilename(defaultextension=".pdf",initialfile=f'Invoice_{invoice["invoice_number"]}.pdf',filetypes=[("PDF document","*.pdf")])
        if not path: return
        try:
            company=self.client.settings(); custom_logo=company.get("company_logo")
            logo=Path(custom_logo) if custom_logo and Path(custom_logo).exists() else resource_path("assets/Saber_for_Audit_logo.png")
            export_invoice_pdf(path,invoice,detail["items"],logo,company)
        except Exception as exc: return messagebox.showerror("Invoice PDF",str(exc))
        messagebox.showinfo("Invoice PDF",f"Saved successfully:\n{path}")

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
        headers=["Invoice Number","Date","Customer / Supplier","Type","Currency","Before VAT Deductible","Before VAT Non-Deductible","VAT","Total","Payment Method","Paid Amount","Debit","Credit",
                 "Supplier Account","VAT Account","Expense Account","Expense without VAT","Status","Source Row"]
        values=[[r["invoice_number"],r["invoice_date"],r["party_name"],r.get("entry_type") or r["kind"],r["currency"],r.get("deductible_subtotal",r["subtotal"]),r.get("non_deductible_subtotal",0),
                 r["vat"],r["total"],r.get("payment_method") or "",r.get("amount_paid") or 0,r["debit"],r["credit"],r["supplier_account"],r["vat_account"],r["expense_account"],r.get("expense_no_vat_account","601100001"),r["status"],r["source_row"]] for r in rows]
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
                  "kind":"purchases","currency":"USD","deductible_subtotal":"0","non_deductible_subtotal":"0","vat":"0","total":"0",
                  "supplier_account":"4011","vat_account":"442660000","expense_account":"601100000",
                  "expense_no_vat_account":"601100001",
                  "due_date":"","payment_method":"Cash","amount_paid":"0"}
        variables={key:tk.StringVar(value=value) for key,value in defaults.items()}
        fields=[("Invoice Number","invoice_number"),("Date (DD-MM-YYYY)","invoice_date"),("Customer / Supplier","party_name"),
                ("Type","kind"),("Currency","currency"),("Before VAT Deductible","deductible_subtotal"),("Before VAT Non-Deductible","non_deductible_subtotal"),("VAT","vat"),("Total","total"),
                ("Supplier Account (C - Credit)","supplier_account"),("VAT Account (D - Debit)","vat_account"),("Expense Account (D - Debit)","expense_account"),("Expense without VAT","expense_no_vat_account"),
                ("Due Date (DD-MM-YYYY)","due_date"),("Payment Method","payment_method"),("Paid Amount","amount_paid")]
        for index,(label,key) in enumerate(fields):
            rr=index//2; cc=(index%2)*2
            tk.Label(window,text=label,bg=LIGHT).grid(row=rr,column=cc,sticky="w",padx=(14,5),pady=7)
            if key=="kind": widget=ttk.Combobox(window,textvariable=variables[key],values=["assets","expenses","purchases","sales"],state="readonly",width=24)
            elif key=="currency": widget=ttk.Combobox(window,textvariable=variables[key],values=["USD","EUR","LBP","AED"],state="readonly",width=24)
            elif key=="payment_method": widget=ttk.Combobox(window,textvariable=variables[key],values=["Cash","Bank Transfer","Cheque","Card","Other"],state="readonly",width=24)
            elif key in ("supplier_account","vat_account","expense_account","expense_no_vat_account"): widget=self.account_search_box(window,variables[key],24)
            else: widget=tk.Entry(window,textvariable=variables[key],width=27)
            widget.grid(row=rr,column=cc+1,padx=(5,14),pady=7)
        def save():
            values={key:var.get().strip() for key,var in variables.items()}
            try:
                datetime.strptime(values["invoice_date"],"%d-%m-%Y")
                deductible=float(values["deductible_subtotal"]); non_deductible=float(values["non_deductible_subtotal"]); subtotal=deductible+non_deductible; vat=float(values["vat"]); total=float(values["total"])
            except ValueError:
                return messagebox.showwarning("Invoices","Check the date and amounts",parent=window)
            if not values["party_name"] or abs(subtotal+vat-total)>0.005:
                return messagebox.showwarning("Invoices","Enter customer/supplier; Total must equal Before VAT plus VAT",parent=window)
            item={"description":"Manual invoice row","quantity":1,"unit_price":deductible,"deductible_subtotal":deductible,"non_deductible_subtotal":non_deductible,
                  "vat_rate":0 if deductible==0 else vat*100/deductible,"vat":vat,"total":total}
            try: self.client.create_manual_invoice(values,[item])
            except Exception as exc: return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial(); self.load_statement_parties()
            messagebox.showinfo("Invoices","Invoice row added successfully")
        tk.Button(window,text="Save Invoice",command=save,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=24,pady=8).grid(row=8,column=0,columnspan=4,pady=16)

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
        header=tk.LabelFrame(self.manual_tab,text="Journal Voucher Details",bg=LIGHT,padx=10,pady=8)
        header.pack(fill="x",padx=10,pady=(10,4))
        self.manual_no=tk.StringVar(); self.manual_date=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y"))
        self.manual_party=tk.StringVar(); self.manual_kind=tk.StringVar(value="purchases"); self.manual_currency=tk.StringVar(value="USD")
        self.manual_supplier_account=tk.StringVar(value="4011")
        self.manual_vat_account=tk.StringVar(value="442660000")
        self.manual_expense_account=tk.StringVar(value="601100000")
        self.manual_expense_no_vat_account=tk.StringVar(value="601100001")
        self.manual_supplier_side=tk.StringVar(value="C - Credit"); self.manual_vat_side=tk.StringVar(value="D - Debit"); self.manual_expense_side=tk.StringVar(value="D - Debit"); self.manual_expense_no_vat_side=tk.StringVar(value="D - Debit")
        fields=[("Invoice Number",self.manual_no,16),("Date",self.manual_date,14),("Customer / Supplier",self.manual_party,28)]
        for col,(label,var,width) in enumerate(fields):
            tk.Label(header,text=label,bg=LIGHT).grid(row=0,column=col*2,sticky="w",padx=4)
            tk.Entry(header,textvariable=var,width=width).grid(row=0,column=col*2+1,padx=4)
        manual_type=ttk.Combobox(header,textvariable=self.manual_kind,values=["assets","expenses","purchases","sales"],state="readonly",width=18)
        manual_type.grid(row=0,column=6,padx=5); manual_type.bind("<<ComboboxSelected>>",lambda _event:self.manual_type_changed())
        ttk.Combobox(header,textvariable=self.manual_currency,values=["USD","EUR","LBP","AED"],state="readonly",width=8).grid(row=0,column=7,padx=5)
        account_fields=[
            ("Supplier Account",self.manual_supplier_account,self.manual_supplier_side),
            ("VAT Account",self.manual_vat_account,self.manual_vat_side),
            ("Expense Account",self.manual_expense_account,self.manual_expense_side),
            ("Expense without VAT",self.manual_expense_no_vat_account,self.manual_expense_no_vat_side),
        ]
        for index,(label,var,side) in enumerate(account_fields):
            rr=1+index//2; cc=(index%2)*4
            tk.Label(header,text=label,bg=LIGHT).grid(row=rr,column=cc,sticky="w",padx=4,pady=(8,2))
            box=tk.Frame(header,bg=LIGHT); box.grid(row=rr,column=cc+1,columnspan=3,sticky="w",padx=4,pady=(8,2))
            self.account_search_box(box,var,16).pack(side="left")
            if side is not None:
                side_box=ttk.Combobox(box,textvariable=side,values=["D - Debit","C - Credit"],state="readonly",width=10)
                side_box.pack(side="left",padx=4); side_box.bind("<<ComboboxSelected>>",lambda _event:self.update_manual_totals())

        self.manual_exchange=tk.Label(header,text="Exchange equivalent: enter/save rates in Security / Backup / Rates",bg=LIGHT,fg="#5f6b76",anchor="w")
        self.manual_exchange.grid(row=3,column=0,columnspan=8,sticky="w",padx=4,pady=(8,0))
        self.manual_currency.trace_add("write",lambda *_args:self.update_manual_totals())
        self.manual_date.trace_add("write",lambda *_args:self.update_manual_totals())

        editor=tk.LabelFrame(self.manual_tab,text="Add Voucher Line",bg=LIGHT,padx=10,pady=8)
        editor.pack(fill="x",padx=10,pady=4)
        self.item_description=tk.StringVar(); self.item_quantity=tk.StringVar(value="1"); self.item_price=tk.StringVar(value="0")
        self.item_subtotal=tk.StringVar(value="0.00"); self.item_non_deductible=tk.StringVar(value="0.00"); self.item_vat_rate=tk.StringVar(value="11")
        self.item_vat=tk.StringVar(value="0.00"); self.item_total=tk.StringVar(value="0.00")
        self.subtotal_override=tk.BooleanVar(value=False); self.vat_override=tk.BooleanVar(value=False)
        item_fields=[("Description",self.item_description,22),("Quantity",self.item_quantity,8),("Unit Price",self.item_price,11),
                     ("Deductible",self.item_subtotal,10),("Non-Deductible",self.item_non_deductible,11),("VAT %",self.item_vat_rate,7),("VAT Amount",self.item_vat,10),("After VAT",self.item_total,10)]
        for col,(label,var,width) in enumerate(item_fields):
            tk.Label(editor,text=label,bg=LIGHT).grid(row=0,column=col,sticky="w",padx=3)
            entry=tk.Entry(editor,textvariable=var,width=width)
            entry.grid(row=1,column=col,padx=3,pady=3)
            entry.bind("<FocusOut>",lambda _event:self.calculate_manual_line())
        tk.Checkbutton(editor,text="Edit Deductible",variable=self.subtotal_override,command=self.calculate_manual_line,bg=LIGHT).grid(row=2,column=3)
        tk.Checkbutton(editor,text="Edit VAT amount",variable=self.vat_override,command=self.calculate_manual_line,bg=LIGHT).grid(row=2,column=6)
        tk.Button(editor,text="Add Item",command=self.add_manual_item,bg=NAVY,fg="white",border=0,padx=16,pady=6).grid(row=1,column=8,padx=8)

        self.manual_tree=self.table(self.manual_tab,[("description","Description",220),("quantity","Qty",60),("price","Unit Price",90),
            ("deductible","Deductible",95),("non_deductible","Non-Deductible",105),("rate","VAT %",65),("vat","VAT",85),("total","After VAT",95),("debit","Debit",90),("credit","Credit",90)])
        actions=tk.Frame(self.manual_tab,bg=LIGHT); actions.pack(pady=(0,10))
        tk.Button(actions,text="Remove Selected Item",command=self.remove_manual_item,bg="#8B1E1E",fg="white",border=0,padx=14,pady=7).pack(side="left",padx=5)
        tk.Button(actions,text="Save Journal Voucher",command=self.save_manual_invoice,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=22,pady=7).pack(side="left",padx=5)
        tk.Button(actions,text="Excel",command=lambda:self.manual_entry_report("xlsx"),bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=3)
        tk.Button(actions,text="PDF",command=lambda:self.manual_entry_report("pdf"),bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=3)
        tk.Button(actions,text="Print",command=lambda:self.manual_entry_report("print"),bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=3)
        self.manual_totals=tk.Label(actions,text="Deductible: 0.00   Non-Deductible: 0.00   VAT: 0.00   Total: 0.00",bg=LIGHT,font=("Segoe UI",10,"bold"))
        self.manual_totals.pack(side="left",padx=18)

    def manual_debit_credit_totals(self):
        deductible=sum(float(item.get("deductible_subtotal",item["subtotal"])) for item in self.manual_items)
        non_deductible=sum(float(item.get("non_deductible_subtotal",0)) for item in self.manual_items)
        vat=sum(float(item.get("vat",0)) for item in self.manual_items); total=deductible+non_deductible+vat
        if self.manual_kind.get()=="sales": return total,total
        debit=credit=0.0
        for amount,side in ((deductible,self.manual_expense_side.get()),(non_deductible,self.manual_expense_no_vat_side.get()),(vat,self.manual_vat_side.get()),(total,self.manual_supplier_side.get())):
            if str(side).upper().startswith("D"): debit+=amount
            else: credit+=amount
        return debit,credit

    def calculate_manual_line(self):
        try:
            quantity=float(self.item_quantity.get() or 0); price=float(self.item_price.get() or 0)
            deductible=float(self.item_subtotal.get() or 0) if self.subtotal_override.get() else quantity*price
            non_deductible=float(self.item_non_deductible.get() or 0)
            if not self.subtotal_override.get(): self.item_subtotal.set(f"{deductible:.2f}")
            rate=float(self.item_vat_rate.get() or 0)
            vat=float(self.item_vat.get() or 0) if self.vat_override.get() else deductible*rate/100
            if not self.vat_override.get(): self.item_vat.set(f"{vat:.2f}")
            self.item_total.set(f"{deductible+non_deductible+vat:.2f}")
            return deductible,non_deductible,vat,deductible+non_deductible+vat
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
        deductible,non_deductible,vat,total=calculated
        item={"description":self.item_description.get().strip(),"quantity":quantity,"unit_price":price,
              "deductible_subtotal":deductible,"non_deductible_subtotal":non_deductible,"subtotal":deductible+non_deductible,"vat_rate":rate,"vat":vat,"total":total}
        self.manual_items.append(item)
        debit=total if self.manual_kind.get()=="sales" else 0
        credit=total if self.manual_kind.get()!="sales" else 0
        self.manual_tree.insert("","end",values=(item["description"],item["quantity"],f'{price:,.2f}',f'{deductible:,.2f}',f'{non_deductible:,.2f}',f'{rate:g}',f'{vat:,.2f}',f'{total:,.2f}',f'{debit:,.2f}',f'{credit:,.2f}'))
        self.item_description.set(""); self.item_quantity.set("1"); self.item_price.set("0"); self.item_subtotal.set("0.00"); self.item_non_deductible.set("0.00")
        self.item_vat_rate.set("11"); self.item_vat.set("0.00"); self.item_total.set("0.00")
        self.subtotal_override.set(False); self.vat_override.set(False); self.update_manual_totals()

    def remove_manual_item(self):
        selected=self.manual_tree.selection()
        if not selected: return
        index=self.manual_tree.index(selected[0]); self.manual_tree.delete(selected[0]); self.manual_items.pop(index); self.update_manual_totals()

    def update_manual_totals(self):
        deductible=sum(float(item.get("deductible_subtotal",item["subtotal"])) for item in self.manual_items); non_deductible=sum(float(item.get("non_deductible_subtotal",0)) for item in self.manual_items); subtotal=deductible+non_deductible
        vat=sum(float(item["vat"]) for item in self.manual_items)
        total=subtotal+vat
        debit,credit=self.manual_debit_credit_totals(); difference=debit-credit
        remaining="Balanced" if abs(difference)<0.005 else (f"Credit needed: {difference:,.2f}" if difference>0 else f"Debit needed: {-difference:,.2f}")
        self.manual_totals.config(text=f"Total D: {debit:,.2f}   Total C: {credit:,.2f}   Remaining: {remaining}")
        if hasattr(self,"manual_exchange"):
            self.manual_exchange.config(text=self.exchange_equivalent_text(total,self.manual_currency.get()))

    def manual_type_changed(self):
        self.calculate_manual_line(); self.update_manual_totals()

    def exchange_equivalents(self,amount,currency,rates):
        def convert(value,source,target):
            if source==target: return value
            for row in rates:
                rate=float(row["rate"])
                if row["from_currency"]==source and row["to_currency"]==target: return value*rate
                if row["from_currency"]==target and row["to_currency"]==source and rate: return value/rate
            return None
        if currency=="LBP": return amount,convert(amount,"LBP","USD")
        lbp=convert(amount,currency,"LBP"); usd=amount if currency=="USD" else convert(amount,currency,"USD")
        if usd is None and lbp is not None: usd=convert(lbp,"LBP","USD")
        if lbp is None and usd is not None: lbp=convert(usd,"USD","LBP")
        return lbp,usd

    def exchange_equivalent_text(self, amount, currency):
        if not amount:
            return "Exchange equivalent: 0.00"
        try: rates=self.client.exchange_rates()
        except Exception: rates=[]
        lbp,usd=self.exchange_equivalents(amount,currency,rates)
        if currency=="LBP":
            return f"Exchange equivalent: USD {usd:,.2f}" if usd is not None else "Exchange equivalent: USD rate not entered"
        lbp_text=f"LBP {lbp:,.2f}" if lbp is not None else "LBP rate not entered"
        usd_text=f"USD {usd:,.2f}" if usd is not None else "USD rate not entered"
        return f"Exchange equivalent: {lbp_text}   |   {usd_text}"

    def manual_entry_report(self, format_name):
        if not self.manual_items:
            return messagebox.showwarning("Manual Entry","Add at least one invoice item")
        invoice_no=self.manual_no.get().strip() or "Draft"
        party=self.manual_party.get().strip() or "Unspecified"
        currency=self.manual_currency.get()
        title=f"Invoice {invoice_no} - {party} - {currency}"
        headers=["Description","Quantity","Unit Price","Deductible","Non-Deductible","VAT %","VAT Amount","After VAT","Debit","Credit"]
        rows=[[item["description"],item["quantity"],item["unit_price"],item.get("deductible_subtotal",item["subtotal"]),item.get("non_deductible_subtotal",0),item["vat_rate"],item["vat"],item["total"],
               item["total"] if self.manual_kind.get()=="sales" else 0,item["total"] if self.manual_kind.get()!="sales" else 0] for item in self.manual_items]
        total_amount=sum(float(item["total"]) for item in self.manual_items)
        rows.append(["","",f"TOTAL {currency}",sum(float(item.get("deductible_subtotal",item["subtotal"])) for item in self.manual_items),sum(float(item.get("non_deductible_subtotal",0)) for item in self.manual_items),
                     "",sum(float(item["vat"]) for item in self.manual_items),total_amount,
                     total_amount if self.manual_kind.get()=="sales" else 0,total_amount if self.manual_kind.get()!="sales" else 0])
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
                 "vat_account":self.manual_vat_account.get().strip() or "442660000",
                 "expense_account":self.manual_expense_account.get().strip() or "601100000",
                 "expense_no_vat_account":self.manual_expense_no_vat_account.get().strip() or "601100001",
                 "supplier_side":self.manual_supplier_side.get(),"vat_side":self.manual_vat_side.get(),"expense_side":self.manual_expense_side.get(),"expense_no_vat_side":self.manual_expense_no_vat_side.get(),
                 "source_file":"Journal Voucher","source_row":None}
        if not all((invoice["invoice_date"],invoice["party_name"])):
            return messagebox.showwarning("Manual Entry","Enter date and customer/supplier; invoice number can be automatic")
        if not self.manual_items: return messagebox.showwarning("Manual Entry","Add at least one invoice item")
        debit,credit=self.manual_debit_credit_totals()
        if abs(debit-credit)>=0.005:
            needed=f"Credit {debit-credit:,.2f}" if debit>credit else f"Debit {credit-debit:,.2f}"
            return messagebox.showerror("Unbalanced Journal Voucher",f"Total Debit: {debit:,.2f}\nTotal Credit: {credit:,.2f}\nRemaining: {needed}\n\nDebit must equal Credit before saving.")
        try: self.client.create_manual_invoice(invoice,self.manual_items)
        except Exception as exc: return messagebox.showerror("Manual Entry",str(exc))
        messagebox.showinfo("Manual Entry","Invoice saved successfully")
        self.manual_items=[]; self.manual_tree.delete(*self.manual_tree.get_children())
        self.manual_no.set(""); self.manual_party.set(""); self.update_manual_totals()
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial()

    # Journal Voucher editor: direct accounting lines (no quantities or unit prices).
    def build_manual(self):
        self.manual_items=[]; self.editing_voucher_id=None
        header=tk.LabelFrame(self.manual_tab,text="Journal Voucher",bg=LIGHT,padx=10,pady=8); header.pack(fill="x",padx=10,pady=(10,4))
        self.manual_no=tk.StringVar(); self.manual_date=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y")); self.manual_description=tk.StringVar(); self.manual_currency=tk.StringVar(value="USD")
        for column,(label,var,width) in enumerate((("Voucher Number",self.manual_no,18),("Date",self.manual_date,14),("Description",self.manual_description,32))):
            tk.Label(header,text=label,bg=LIGHT).grid(row=0,column=column*2,sticky="w",padx=4); tk.Entry(header,textvariable=var,width=width).grid(row=0,column=column*2+1,padx=4)
        ttk.Combobox(header,textvariable=self.manual_currency,values=["USD","EUR","LBP","AED"],state="readonly",width=8).grid(row=0,column=6,padx=5)
        editor=tk.LabelFrame(self.manual_tab,text="Add Debit / Credit Line",bg=LIGHT,padx=10,pady=8); editor.pack(fill="x",padx=10,pady=4)
        self.jv_account=tk.StringVar(); self.jv_description=tk.StringVar(); self.jv_debit=tk.StringVar(value="0"); self.jv_credit=tk.StringVar(value="0")
        tk.Label(editor,text="Account (type first 3 letters)",bg=LIGHT).grid(row=0,column=0,sticky="w"); self.account_search_box(editor,self.jv_account,30).grid(row=1,column=0,padx=4)
        for col,(label,var,width) in enumerate((("Line Description",self.jv_description,34),("Debit",self.jv_debit,14),("Credit",self.jv_credit,14)),1):
            tk.Label(editor,text=label,bg=LIGHT).grid(row=0,column=col,sticky="w"); tk.Entry(editor,textvariable=var,width=width).grid(row=1,column=col,padx=4)
        self.action_button(editor,"Add Line",self.add_manual_item).grid(row=1,column=4,padx=8)
        self.manual_tree=self.table(self.manual_tab,[("account","Account",120),("name","Account Name",260),("description","Description",260),("debit","Debit",130),("credit","Credit",130)])
        actions=tk.Frame(self.manual_tab,bg=LIGHT); actions.pack(pady=(0,6))
        tk.Button(actions,text="Remove Line",command=self.remove_manual_item,bg="#8B1E1E",fg="white",border=0,padx=12,pady=6).pack(side="left",padx=3)
        self.action_button(actions,"New Voucher",self.new_manual_voucher).pack(side="left",padx=3)
        tk.Button(actions,text="Save Voucher",command=self.save_manual_invoice,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=18,pady=7).pack(side="left",padx=3)
        self.action_button(actions,"Excel",lambda:self.manual_entry_report("xlsx")).pack(side="left",padx=3); self.action_button(actions,"PDF",lambda:self.manual_entry_report("pdf")).pack(side="left",padx=3)
        self.manual_totals=tk.Label(actions,text="Total D: 0.00   Total C: 0.00   Remaining: Balanced",bg=LIGHT,font=("Segoe UI",10,"bold")); self.manual_totals.pack(side="left",padx=12)
        vouchers=tk.LabelFrame(self.manual_tab,text="Saved Journal Vouchers",bg=LIGHT); vouchers.pack(fill="both",expand=True,padx=10,pady=(0,8))
        self.manual_vouchers_tree=self.table(vouchers,[("number","Voucher Number",150),("date","Date",100),("description","Description",300),("currency","Currency",80),("debit","Total Debit",130),("credit","Total Credit",130)])
        voucher_actions=tk.Frame(vouchers,bg=LIGHT); voucher_actions.pack(pady=(0,6))
        self.action_button(voucher_actions,"Edit Selected Voucher",self.edit_selected_manual_voucher).pack(side="left",padx=4)
        tk.Button(voucher_actions,text="Delete Selected Voucher",command=self.delete_selected_manual_from_tab,bg="#6B1010",fg="white",border=0,padx=14,pady=7).pack(side="left",padx=4)
        self.manual_vouchers_tree.bind("<Double-1>",lambda _event:self.edit_selected_manual_voucher()); self.load_manual_vouchers()

    def add_manual_item(self):
        value=self.jv_account.get(); code=value.split(" - ",1)[0].strip()
        try: debit=float(self.jv_debit.get() or 0); credit=float(self.jv_credit.get() or 0)
        except ValueError: return messagebox.showwarning("Journal Voucher","Debit and Credit must be valid numbers")
        if not code or min(debit,credit)<0 or (debit>0 and credit>0) or (debit==0 and credit==0): return messagebox.showwarning("Journal Voucher","Choose an account and enter either Debit or Credit")
        try: account=next(row for row in self.client.accounts() if str(row["code"])==code)
        except StopIteration: return messagebox.showwarning("Journal Voucher","Account was not found")
        item={"account_code":code,"account_name":account["name_en"],"description":self.jv_description.get().strip(),"debit":debit,"credit":credit}; self.manual_items.append(item)
        self.manual_tree.insert("","end",values=(code,account["name_en"],item["description"],f"{debit:,.2f}",f"{credit:,.2f}"))
        self.jv_account.set(""); self.jv_description.set(""); self.jv_debit.set("0"); self.jv_credit.set("0"); self.update_manual_totals()

    def remove_manual_item(self):
        selected=self.manual_tree.selection()
        if not selected: return
        index=self.manual_tree.index(selected[0]); self.manual_tree.delete(selected[0]); self.manual_items.pop(index); self.update_manual_totals()

    def update_manual_totals(self):
        debit=sum(float(item["debit"]) for item in self.manual_items); credit=sum(float(item["credit"]) for item in self.manual_items); difference=debit-credit
        remaining="Balanced" if abs(difference)<.005 else (f"Credit needed: {difference:,.2f}" if difference>0 else f"Debit needed: {-difference:,.2f}")
        if hasattr(self,"manual_totals"): self.manual_totals.config(text=f"Total D: {debit:,.2f}   Total C: {credit:,.2f}   Remaining: {remaining}")
        return debit,credit

    def new_manual_voucher(self):
        self.editing_voucher_id=None; self.manual_no.set(""); self.manual_date.set(datetime.now().strftime("%d-%m-%Y")); self.manual_description.set(""); self.manual_currency.set("USD"); self.manual_items=[]; self.manual_tree.delete(*self.manual_tree.get_children()); self.update_manual_totals()

    def save_manual_invoice(self):
        debit,credit=self.update_manual_totals()
        if len(self.manual_items)<2: return messagebox.showwarning("Journal Voucher","Add at least two debit/credit lines")
        if abs(debit-credit)>=.005: return messagebox.showerror("Unbalanced Journal Voucher",f"Total Debit: {debit:,.2f}\nTotal Credit: {credit:,.2f}\nDebit must equal Credit before saving.")
        voucher={"entry_number":self.manual_no.get().strip(),"entry_date":self.manual_date.get().strip(),"description":self.manual_description.get().strip(),"currency":self.manual_currency.get()}
        try: saved=self.client.save_journal_voucher(voucher,self.manual_items,self.editing_voucher_id)
        except Exception as exc: return messagebox.showerror("Journal Voucher",str(exc))
        messagebox.showinfo("Journal Voucher",f'Voucher {saved["voucher"]["entry_number"]} saved successfully'); self.new_manual_voucher(); self.load_manual_vouchers(); self.load_journal(); self.load_trial()

    def load_manual_vouchers(self):
        if not hasattr(self,"manual_vouchers_tree"): return
        try: rows=[row for row in self.client.journal(limit=5000) if row.get("source_type")=="journal_voucher"]
        except TypeError: rows=[row for row in self.client.journal() if row.get("source_type")=="journal_voucher"]
        except Exception: rows=[]
        grouped={}
        for row in rows:
            item=grouped.setdefault(row["entry_id"],{"id":row["entry_id"],"number":row["entry_number"],"date":row["entry_date"],"description":row["description"],"currency":row["currency"],"debit":0.0,"credit":0.0})
            item["debit"]+=float(row["debit"] or 0); item["credit"]+=float(row["credit"] or 0)
        self.manual_voucher_rows=grouped; self.manual_vouchers_tree.delete(*self.manual_vouchers_tree.get_children())
        for entry_id,row in sorted(grouped.items(),key=lambda pair:(pair[1]["date"],pair[1]["number"]),reverse=True): self.manual_vouchers_tree.insert("","end",iid=str(entry_id),values=(row["number"],row["date"],row["description"],row["currency"],f'{row["debit"]:,.2f}',f'{row["credit"]:,.2f}'))

    def edit_selected_manual_voucher(self):
        selected=self.manual_vouchers_tree.selection()
        if not selected: return messagebox.showwarning("Journal Voucher","Select a voucher first")
        try: detail=self.client.journal_voucher(int(selected[0]))
        except Exception as exc: return messagebox.showerror("Journal Voucher",str(exc))
        voucher=detail["voucher"]; self.editing_voucher_id=int(voucher["id"]); self.manual_no.set(voucher["entry_number"]); self.manual_date.set(voucher["entry_date"]); self.manual_description.set(voucher["description"]); self.manual_currency.set(voucher["currency"])
        self.manual_items=detail["lines"]; self.manual_tree.delete(*self.manual_tree.get_children())
        for line in self.manual_items: self.manual_tree.insert("","end",values=(line["account_code"],line["account_name"],line["description"],f'{line["debit"]:,.2f}',f'{line["credit"]:,.2f}'))
        self.update_manual_totals()

    def delete_selected_manual_from_tab(self):
        selected=self.manual_vouchers_tree.selection()
        if not selected: return messagebox.showwarning("Journal Voucher","Select a voucher first")
        if not messagebox.askyesno("Delete Journal Voucher","Delete the selected voucher and all its lines?"): return
        try: self.client.delete_journal_voucher(int(selected[0]))
        except Exception as exc: return messagebox.showerror("Journal Voucher",str(exc))
        self.new_manual_voucher(); self.load_manual_vouchers(); self.load_journal(); self.load_trial()

    def manual_entry_report(self,format_name):
        if not self.manual_items: return messagebox.showwarning("Journal Voucher","No lines to export")
        title=f"Journal Voucher {self.manual_no.get().strip() or 'Draft'}"; headers=["Account","Account Name","Description","Debit","Credit"]
        rows=[[r["account_code"],r.get("account_name",""),r.get("description",""),r["debit"],r["credit"]] for r in self.manual_items]
        rows.append(["","","TOTAL",sum(float(r[3]) for r in rows),sum(float(r[4]) for r in rows)])
        if format_name=="print": return print_rows(title,headers,rows)
        extension=".xlsx" if format_name=="xlsx" else ".pdf"; path=filedialog.asksaveasfilename(defaultextension=extension,initialfile=title.replace(" ","_")+extension)
        if path: (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows)

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

    def build_parties(self):
        controls=tk.Frame(self.parties_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        self.edit_party_id=None; self.party_name=tk.StringVar(); self.party_kind=tk.StringVar(value="customer"); self.party_tax=tk.StringVar(); self.party_mof=tk.StringVar(); self.party_address=tk.StringVar(); self.party_contact=tk.StringVar(); self.party_currency=tk.StringVar(value="USD")
        for label,var,width in (("Name",self.party_name,28),("Tax Number",self.party_tax,18)):
            tk.Label(controls,text=label,bg=LIGHT).pack(side="left",padx=(5,2)); tk.Entry(controls,textvariable=var,width=width).pack(side="left",padx=4)
        ttk.Combobox(controls,textvariable=self.party_kind,values=["customer","supplier","both"],state="readonly",width=11).pack(side="left",padx=4)
        ttk.Combobox(controls,textvariable=self.party_currency,values=["USD","EUR","LBP","AED"],state="readonly",width=7).pack(side="left",padx=4)
        self.action_button(controls,"Save Customer / Supplier",self.save_party).pack(side="left",padx=6)
        self.action_button(controls,"Edit Selected",self.edit_selected_party).pack(side="left",padx=4)
        details=tk.Frame(self.parties_tab,bg=LIGHT); details.pack(fill="x",padx=10,pady=(0,8))
        for label,var,width in (("MOF Number",self.party_mof,18),("Address",self.party_address,32),("Contact Number",self.party_contact,18)):
            tk.Label(details,text=label,bg=LIGHT).pack(side="left",padx=(5,2)); tk.Entry(details,textvariable=var,width=width).pack(side="left",padx=4)
        self.parties_tree=self.table(self.parties_tab,[("id","ID",55),("account","9-Digit Account",115),("name","Name",180),("kind","Type",85),("tax","Tax Number",110),("mof","MOF Number",110),("address","Address",180),("contact","Contact",110),("currency","Currency",70)])
        self.parties_tree.bind("<Double-1>",lambda _event:self.edit_selected_party())
        self.load_parties_page()

    def save_party(self):
        try: self.client.save_party({"id":self.edit_party_id,"name":self.party_name.get(),"kind":self.party_kind.get(),"tax_number":self.party_tax.get(),"mof_number":self.party_mof.get(),"address":self.party_address.get(),"contact_number":self.party_contact.get(),"currency":self.party_currency.get()})
        except Exception as exc: return messagebox.showerror("Customers / Suppliers",str(exc))
        self.edit_party_id=None; self.party_name.set(""); self.party_tax.set(""); self.party_mof.set(""); self.party_address.set(""); self.party_contact.set(""); self.load_parties_page(); self.load_statement_parties()
        messagebox.showinfo("Customers / Suppliers","Saved successfully")

    def edit_selected_party(self):
        selected=self.parties_tree.selection()
        if not selected: return messagebox.showwarning("Customers / Suppliers","Select a customer or supplier first")
        values=self.parties_tree.item(selected[0],"values"); self.edit_party_id=int(values[0]); self.party_name.set(values[2]); self.party_kind.set(values[3]); self.party_tax.set(values[4]); self.party_mof.set(values[5]); self.party_address.set(values[6]); self.party_contact.set(values[7]); self.party_currency.set(values[8])

    def load_parties_page(self):
        try: rows=self.client.parties()
        except Exception as exc: return messagebox.showerror("Customers / Suppliers",str(exc))
        self.party_rows=rows; self.parties_tree.delete(*self.parties_tree.get_children())
        for row in rows: self.parties_tree.insert("","end",values=(row["id"],row.get("account_number") or "",row["name"],row["kind"],row.get("tax_number") or "",row.get("mof_number") or "",row.get("address") or "",row.get("contact_number") or "",row["currency"]))

    def build_transactions(self):
        buttons=tk.Frame(self.transactions_tab,bg=LIGHT); buttons.pack(fill="x",padx=10,pady=10)
        self.action_button(buttons,"Add Customer Receipt",lambda:self.payment_dialog("customer_receipt")).pack(side="left",padx=4)
        self.action_button(buttons,"Add Supplier Payment",lambda:self.payment_dialog("supplier_payment")).pack(side="left",padx=4)
        tk.Button(buttons,text="Add Expense",command=self.expense_dialog,bg=GOLD,fg=NAVY,border=0,padx=16,pady=7).pack(side="left",padx=4)
        self.action_button(buttons,"Refresh",self.load_transactions).pack(side="left",padx=4)
        nested=ttk.Notebook(self.transactions_tab); nested.pack(fill="both",expand=True,padx=10,pady=(0,10))
        payment_frame=tk.Frame(nested,bg=LIGHT); expense_frame=tk.Frame(nested,bg=LIGHT)
        nested.add(payment_frame,text="Receipts & Payments"); nested.add(expense_frame,text="Expenses")
        self.payments_tree=self.table(payment_frame,[("date","Date",100),("kind","Type",130),("party","Customer / Supplier",220),("currency","Currency",80),("amount","Amount",120),("cash","Cash / Bank A/C",110),("reference","Reference",130),("description","Description",220)])
        self.expenses_tree=self.table(expense_frame,[("date","Date",95),("description","Description",190),("category","Category",110),("currency","Currency",70),("with_vat","Expense with VAT",120),("without_vat","Expense without VAT",130),("vat","VAT",80),("total","Total",100),("account","With VAT A/C",100),("no_vat_account","Without VAT A/C",110),("payment","Payment A/C",95)])
        self.load_transactions()

    def payment_dialog(self,kind):
        try: parties=self.client.parties()
        except Exception as exc: return messagebox.showerror("Payments",str(exc))
        wanted="customer" if kind=="customer_receipt" else "supplier"
        parties=[p for p in parties if p["kind"] in (wanted,"both")]
        if not parties: return messagebox.showwarning("Payments",f"Add a {wanted} first")
        window=tk.Toplevel(self); window.title("Customer Receipt" if kind=="customer_receipt" else "Supplier Payment"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        mapping={f'{p["name"]} ({p["currency"]})':p for p in parties}; party=tk.StringVar(value=next(iter(mapping)))
        values={"payment_date":tk.StringVar(value=datetime.now().strftime("%d-%m-%Y")),"currency":tk.StringVar(value="USD"),"amount":tk.StringVar(value="0"),"cash_account":tk.StringVar(value="531"),"party_account":tk.StringVar(value="4111" if kind=="customer_receipt" else "4011"),"reference":tk.StringVar(),"description":tk.StringVar()}
        fields=[("Customer / Supplier",party),("Date",values["payment_date"]),("Currency",values["currency"]),("Amount",values["amount"]),("Cash / Bank Account",values["cash_account"]),("Party Account",values["party_account"]),("Reference",values["reference"]),("Description",values["description"])]
        for index,(label,var) in enumerate(fields):
            tk.Label(window,text=label,bg=LIGHT).grid(row=index,column=0,sticky="w",padx=14,pady=6)
            widget=ttk.Combobox(window,textvariable=var,values=list(mapping),state="readonly",width=31) if index==0 else ttk.Combobox(window,textvariable=var,values=["USD","EUR","LBP","AED"],state="readonly",width=31) if label=="Currency" else self.account_search_box(window,var,31) if label in ("Cash / Bank Account","Party Account") else tk.Entry(window,textvariable=var,width=34)
            widget.grid(row=index,column=1,padx=14,pady=6)
        def save():
            item={key:var.get().strip() for key,var in values.items()}; item.update({"kind":kind,"party_id":mapping[party.get()]["id"]})
            try: self.client.add_payment(item)
            except Exception as exc: return messagebox.showerror("Payments",str(exc),parent=window)
            window.destroy(); self.load_transactions(); self.load_journal(); self.load_trial(); self.load_financial_reports(); messagebox.showinfo("Payments","Saved successfully")
        self.action_button(window,"Save",save).grid(row=len(fields),column=0,columnspan=2,pady=14)

    def expense_dialog(self):
        window=tk.Toplevel(self); window.title("Add Expense"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        defaults={"expense_date":datetime.now().strftime("%d-%m-%Y"),"description":"","category":"General","currency":"USD","with_vat_subtotal":"0","without_vat_subtotal":"0","vat":"0","expense_account":"601100000","expense_without_vat_account":"601100001","vat_account":"442660000","payment_account":"531","expense_side":"D - Debit","expense_without_vat_side":"D - Debit","vat_side":"D - Debit","payment_side":"C - Credit","reference":""}
        values={key:tk.StringVar(value=value) for key,value in defaults.items()}
        labels=[("Date","expense_date"),("Description","description"),("Category","category"),("Currency","currency"),("Expense with VAT","with_vat_subtotal"),("Expense without VAT","without_vat_subtotal"),("VAT","vat"),("With VAT Account","expense_account"),("Without VAT Account","expense_without_vat_account"),("VAT Account","vat_account"),("Cash / Bank Account","payment_account"),("Reference","reference")]
        for index,(label,key) in enumerate(labels):
            tk.Label(window,text=label,bg=LIGHT).grid(row=index,column=0,sticky="w",padx=14,pady=5)
            if key=="currency": widget=ttk.Combobox(window,textvariable=values[key],values=["USD","EUR","LBP","AED"],state="readonly",width=31)
            elif key in ("expense_account","expense_without_vat_account","vat_account","payment_account"):
                frame=tk.Frame(window,bg=LIGHT); self.account_search_box(frame,values[key],20).pack(side="left")
                side_key={"expense_account":"expense_side","expense_without_vat_account":"expense_without_vat_side","vat_account":"vat_side","payment_account":"payment_side"}[key]
                ttk.Combobox(frame,textvariable=values[side_key],values=["D - Debit","C - Credit"],state="readonly",width=10).pack(side="left",padx=(5,0)); widget=frame
            else: widget=tk.Entry(window,textvariable=values[key],width=34)
            widget.grid(row=index,column=1,padx=14,pady=5)
        try: expense_rates=self.client.exchange_rates()
        except Exception: expense_rates=[]
        exchange_text=tk.Label(window,text="Exchange equivalent: 0.00",bg=LIGHT,fg=NAVY,font=("Segoe UI",9,"bold"))
        exchange_text.grid(row=len(labels),column=0,columnspan=2,pady=(8,2))
        def update_exchange(*_args):
            try: amount=float(values["with_vat_subtotal"].get() or 0)+float(values["without_vat_subtotal"].get() or 0)+float(values["vat"].get() or 0)
            except ValueError: amount=0
            lbp,usd=self.exchange_equivalents(amount,values["currency"].get(),expense_rates)
            currency=values["currency"].get()
            if currency=="LBP": text="USD rate not entered" if usd is None else f"USD {usd:,.2f}"
            elif currency=="USD": text="LBP rate not entered" if lbp is None else f"LBP {lbp:,.2f}"
            else: text=f'{"LBP rate not entered" if lbp is None else f"LBP {lbp:,.2f}"}   |   {"USD rate not entered" if usd is None else f"USD {usd:,.2f}"}'
            exchange_text.config(text="Exchange equivalent: "+text)
        for key in ("with_vat_subtotal","without_vat_subtotal","vat","currency"): values[key].trace_add("write",update_exchange)
        def save():
            try: self.client.add_expense({key:var.get().strip() for key,var in values.items()})
            except Exception as exc: return messagebox.showerror("Expenses",str(exc),parent=window)
            window.destroy(); self.load_transactions(); self.load_journal(); self.load_trial(); self.load_profit_loss(); self.load_financial_reports(); messagebox.showinfo("Expenses","Saved successfully")
        self.action_button(window,"Save Expense",save).grid(row=len(labels)+1,column=0,columnspan=2,pady=14)

    def load_transactions(self):
        try: payments=self.client.payments(); expenses=self.client.expenses()
        except Exception as exc: return messagebox.showerror("Payments / Expenses",str(exc))
        self.payments_tree.delete(*self.payments_tree.get_children()); self.expenses_tree.delete(*self.expenses_tree.get_children())
        for row in payments: self.payments_tree.insert("","end",values=(row["payment_date"],row["kind"],row["party_name"],row["currency"],f'{row["amount"]:,.2f}',row["cash_account"],row["reference"],row["description"]))
        for row in expenses: self.expenses_tree.insert("","end",values=(row["expense_date"],row["description"],row["category"],row["currency"],f'{row.get("with_vat_subtotal",row["subtotal"]):,.2f}',f'{row.get("without_vat_subtotal",0):,.2f}',f'{row["vat"]:,.2f}',f'{row["total"]:,.2f}',row["expense_account"],row.get("expense_without_vat_account","601100001"),row["payment_account"]))

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
        tk.Button(actions,text="Delete Selected Voucher",command=self.delete_selected_journal_voucher,bg="#6B1010",fg="white",border=0,padx=14,pady=7).pack(side="left",padx=4)
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

    def delete_selected_journal_voucher(self):
        selected=self.journal_tree.selection()
        if not selected: return messagebox.showwarning("General Journal","Select a Journal Voucher line first")
        entry_number=str(self.journal_tree.item(selected[0],"values")[0])
        row=next((item for item in getattr(self,"journal_rows",[]) if str(item["entry_number"])==entry_number),None)
        if not row: return messagebox.showwarning("General Journal","Selected entry was not found")
        if not messagebox.askyesno("Delete Journal Voucher",f"Delete {entry_number} and all its debit/credit lines?\nThis action is recorded in the audit log."): return
        try: self.client.delete_journal_voucher(row["entry_id"])
        except Exception as exc: return messagebox.showerror("Delete Journal Voucher",str(exc))
        self.load_journal(); self.load_invoices(); self.load_dashboard(); self.load_trial(); messagebox.showinfo("General Journal","Journal Voucher deleted")

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

    def build_profit_loss(self):
        controls=tk.Frame(self.pnl_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        tk.Label(controls,text="From:",bg=LIGHT).pack(side="left")
        tk.Entry(controls,textvariable=self.pnl_from_date,width=13).pack(side="left",padx=(4,10))
        tk.Label(controls,text="To:",bg=LIGHT).pack(side="left")
        tk.Entry(controls,textvariable=self.pnl_to_date,width=13).pack(side="left",padx=(4,10))
        tk.Button(controls,text="Apply",command=self.load_profit_loss,bg=GOLD,fg=NAVY,border=0,padx=15,pady=6).pack(side="left")
        tk.Label(controls,text="Close Fiscal Year:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="right",padx=(10,4))
        tk.Entry(controls,textvariable=self.close_year,width=8).pack(side="right")
        tk.Button(controls,text="Close Year & Open Next",command=self.close_fiscal_year,bg="#8B1E1E",fg="white",border=0,padx=14,pady=6).pack(side="right",padx=6)
        self.pnl_tree=self.table(self.pnl_tab,[("currency","Currency",85),("type","Type",90),("account","Account",100),
            ("name","Account Name",300),("debit","Debit",130),("credit","Credit",130),("amount","P&L Amount",140)])
        actions=tk.Frame(self.pnl_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,"Export Excel",lambda:self.profit_loss_report("xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.profit_loss_report("pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.profit_loss_report("print")).pack(side="left",padx=4)
        self.pnl_totals=tk.Label(actions,text="",bg=LIGHT,font=("Segoe UI",10,"bold")); self.pnl_totals.pack(side="left",padx=15)
        self.load_profit_loss()

    def profit_loss_range(self):
        values=[]
        for label,raw in (("From Date",self.pnl_from_date.get()),("To Date",self.pnl_to_date.get())):
            try: values.append(datetime.strptime(raw.strip(),"%d-%m-%Y").strftime("%Y-%m-%d"))
            except ValueError: messagebox.showwarning("Profit & Loss",f"{label} must use DD-MM-YYYY"); return None
        if values[0]>values[1]: messagebox.showwarning("Profit & Loss","From Date cannot be after To Date"); return None
        return values

    def load_profit_loss(self):
        if not hasattr(self,"pnl_tree"): return
        dates=self.profit_loss_range()
        if dates is None: return
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try: rows=self.client.profit_loss(dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("Profit & Loss",str(exc))
        self.pnl_rows=rows; self.pnl_tree.delete(*self.pnl_tree.get_children())
        for row in rows: self.pnl_tree.insert("","end",values=(row["currency"],row["type"],row["code"],row["name_en"],
            f'{row["debit"]:,.2f}',f'{row["credit"]:,.2f}',f'{row["amount"]:,.2f}'))
        totals={}
        for row in rows:
            totals.setdefault(row["currency"],0)
            totals[row["currency"]]+=row["amount"] if row["type"]=="income" else -row["amount"]
        self.pnl_totals.config(text="   ".join(f"{code} Net P&L: {amount:,.2f}" for code,amount in totals.items()) or "No activity")

    def profit_loss_report(self,format_name):
        rows=getattr(self,"pnl_rows",[])
        if not rows: return messagebox.showwarning("Profit & Loss","No data to export")
        title=f"Saber Accounting - Profit & Loss ({self.pnl_from_date.get()} to {self.pnl_to_date.get()})"
        headers=["Currency","Type","Account","Account Name","Debit","Credit","P&L Amount"]
        values=[[r["currency"],r["type"],r["code"],r["name_en"],r["debit"],r["credit"],r["amount"]] for r in rows]
        try:
            if format_name=="print": print_rows(title,headers,values); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,initialfile="Profit_and_Loss"+extension,
                filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")])
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,values)
            messagebox.showinfo("Profit & Loss",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("Profit & Loss",str(exc))

    def close_fiscal_year(self):
        try: year=int(self.close_year.get())
        except ValueError: return messagebox.showwarning("Fiscal Year","Enter a valid four-digit year")
        if year<2000 or year>2100: return messagebox.showwarning("Fiscal Year","Enter a valid four-digit year")
        warning=f"Close fiscal year {year}?\n\nIncome and expense accounts will be closed to retained results, and fiscal year {year+1} will be opened. This cannot be repeated."
        if not messagebox.askyesno("Close Fiscal Year",warning): return
        try: result=self.client.close_fiscal_year(year)
        except Exception as exc: return messagebox.showerror("Close Fiscal Year",str(exc))
        self.pnl_from_date.set(f"01-01-{year+1}"); self.pnl_to_date.set(f"31-12-{year+1}"); self.close_year.set(str(year+1))
        self.load_profit_loss(); self.load_journal(); self.load_trial()
        summary=" / ".join(f"{code}: {amount:,.2f}" for code,amount in result.get("net_results",{}).items()) or "No P&L activity"
        messagebox.showinfo("Fiscal Year",f"Year {year} closed successfully.\nYear {year+1} opened.\nNet results: {summary}")

    def build_financial_reports(self):
        controls=tk.Frame(self.reports_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        tk.Label(controls,text="From:",bg=LIGHT).pack(side="left"); tk.Entry(controls,textvariable=self.report_from_date,width=13).pack(side="left",padx=(4,10))
        tk.Label(controls,text="To:",bg=LIGHT).pack(side="left"); tk.Entry(controls,textvariable=self.report_to_date,width=13).pack(side="left",padx=(4,10))
        tk.Label(controls,text="Ledger Account:",bg=LIGHT).pack(side="left"); self.account_search_box(controls,self.ledger_account,18).pack(side="left",padx=(4,10))
        tk.Button(controls,text="Apply",command=self.load_financial_reports,bg=GOLD,fg=NAVY,border=0,padx=15,pady=6).pack(side="left")
        nested=ttk.Notebook(self.reports_tab); nested.pack(fill="both",expand=True,padx=10,pady=(0,10))
        gl=tk.Frame(nested,bg=LIGHT); bs=tk.Frame(nested,bg=LIGHT); vat=tk.Frame(nested,bg=LIGHT)
        nested.add(gl,text="General Ledger"); nested.add(bs,text="Balance Sheet"); nested.add(vat,text="Lebanese VAT Report")
        self.ledger_tree=self.table(gl,[("date","Date",95),("entry","Entry",90),("account","Account",85),("name","Account Name",180),("description","Description",200),("currency","Currency",70),("debit","Debit",105),("credit","Credit",105),("balance","Balance",110)])
        self.report_buttons(gl,"ledger")
        self.balance_tree=self.table(bs,[("currency","Currency",80),("type","Type",90),("account","Account",90),("name","Account Name",280),("debit","Debit",120),("credit","Credit",120),("balance","Balance",130)])
        self.report_buttons(bs,"balance")
        self.vat_tree=self.table(vat,[("currency","Currency",85),("type","Type",100),("invoices","Count",75),("subtotal","Before VAT",130),("vat","VAT",110),("total","Total",130)])
        self.report_buttons(vat,"vat")
        self.vat_summary=tk.Label(vat,text="",bg=LIGHT,font=("Segoe UI",10,"bold")); self.vat_summary.pack(pady=(0,8))
        self.load_financial_reports()

    def report_buttons(self,parent,report):
        frame=tk.Frame(parent,bg=LIGHT); frame.pack(pady=(0,8))
        self.action_button(frame,"Excel",lambda:self.financial_report_export(report,"xlsx")).pack(side="left",padx=4)
        self.action_button(frame,"PDF",lambda:self.financial_report_export(report,"pdf")).pack(side="left",padx=4)
        self.action_button(frame,"Print",lambda:self.financial_report_export(report,"print")).pack(side="left",padx=4)

    def financial_report_range(self):
        values=[]
        for raw in (self.report_from_date.get(),self.report_to_date.get()):
            try: values.append(datetime.strptime(raw.strip(),"%d-%m-%Y").strftime("%Y-%m-%d"))
            except ValueError: messagebox.showwarning("Financial Reports","Dates must use DD-MM-YYYY"); return None
        if values[0]>values[1]: messagebox.showwarning("Financial Reports","From Date cannot be after To Date"); return None
        return values

    def load_financial_reports(self):
        if not hasattr(self,"ledger_tree"): return
        dates=self.financial_report_range()
        if dates is None: return
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try:
            ledger=self.client.general_ledger(self.ledger_account.get().strip() or None,dates[0],dates[1],currency)
            balance=self.client.balance_sheet(dates[1],currency)
            vat=self.client.vat_report(dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("Financial Reports",str(exc))
        self.ledger_rows=ledger["items"]; self.balance_rows=balance; self.vat_rows=vat["items"]
        self.ledger_tree.delete(*self.ledger_tree.get_children()); self.balance_tree.delete(*self.balance_tree.get_children()); self.vat_tree.delete(*self.vat_tree.get_children())
        for r in self.ledger_rows: self.ledger_tree.insert("","end",values=(r["entry_date"],r["entry_number"],r["account_code"],r["account_name"],r["description"],r["currency"],f'{r["debit"]:,.2f}',f'{r["credit"]:,.2f}',f'{r["balance"]:,.2f}'))
        for r in balance: self.balance_tree.insert("","end",values=(r["currency"],r["type"],r["code"],r["name_en"],f'{r["debit"]:,.2f}',f'{r["credit"]:,.2f}',f'{r["balance"]:,.2f}'))
        for r in self.vat_rows: self.vat_tree.insert("","end",values=(r["currency"],r["kind"],r["invoices"],f'{r["subtotal"] or 0:,.2f}',f'{r["vat"] or 0:,.2f}',f'{r["total"] or 0:,.2f}'))
        self.vat_summary.config(text="   ".join(f'{r["currency"]} VAT payable: {r["vat_payable"]:,.2f}' for r in vat["summary"]) or "No VAT activity")

    def financial_report_export(self,report,format_name):
        if report=="ledger": title="General Ledger"; headers=["Date","Entry","Account","Name","Description","Currency","Debit","Credit","Balance"]; rows=[[r["entry_date"],r["entry_number"],r["account_code"],r["account_name"],r["description"],r["currency"],r["debit"],r["credit"],r["balance"]] for r in getattr(self,"ledger_rows",[])]
        elif report=="balance": title="Balance Sheet"; headers=["Currency","Type","Account","Name","Debit","Credit","Balance"]; rows=[[r["currency"],r["type"],r["code"],r["name_en"],r["debit"],r["credit"],r["balance"]] for r in getattr(self,"balance_rows",[])]
        else: title="Lebanese VAT Report"; headers=["Currency","Type","Count","Before VAT","VAT","Total"]; rows=[[r["currency"],r["kind"],r["invoices"],r["subtotal"],r["vat"],r["total"]] for r in getattr(self,"vat_rows",[])]
        if not rows: return messagebox.showwarning(title,"No data to export")
        try:
            if format_name=="print": print_rows(title,headers,rows); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"; path=filedialog.asksaveasfilename(defaultextension=extension,initialfile=title.replace(" ","_")+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows); messagebox.showinfo(title,f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror(title,str(exc))

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
        ttk.Combobox(controls,textvariable=self.statement_display_currency,values=["Original","USD","LBP"],state="readonly",width=9).pack(side="left",padx=3)
        tk.Checkbutton(controls,text="With Opening",variable=self.statement_include_opening,bg=LIGHT).pack(side="left",padx=3)
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
        display=None if self.statement_display_currency.get()=="Original" else self.statement_display_currency.get()
        try: data=self.client.statement(party["id"],dates[0],dates[1],currency,self.statement_include_opening.get(),display)
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
        self.new_account_code=tk.StringVar(); self.new_account_name=tk.StringVar(); self.new_account_parent=tk.StringVar(); self.new_account_type=tk.StringVar(value="expense")
        tk.Label(controls,text="9-digit account (blank = automatic):",bg=LIGHT,font=("Segoe UI",9,"bold"),fg=NAVY).pack(side="left",padx=(0,4))
        tk.Entry(controls,textvariable=self.new_account_code,width=11).pack(side="left",padx=3)
        tk.Entry(controls,textvariable=self.new_account_name,width=22).pack(side="left",padx=3)
        tk.Entry(controls,textvariable=self.new_account_parent,width=9).pack(side="left",padx=3)
        ttk.Combobox(controls,textvariable=self.new_account_type,values=["asset","liability","equity","income","expense"],state="readonly",width=9).pack(side="left",padx=3)
        self.action_button(controls,"Create Account",self.save_new_account).pack(side="left",padx=5)
        self.action_button(controls,"Edit Selected Name",self.rename_selected_account).pack(side="left",padx=5)
        self.action_button(controls,tr(self.language.get(),"refresh"),self.load_accounts).pack(side="right")
        self.accounts_tree=self.table(self.accounts_tab,[
            ("code","Account",100),("parent","Parent",80),("english","English",270),
            ("french","French",270),("arabic","Arabic",270),("type","Type",90)])
        self.accounts_tree.bind("<Double-1>",lambda _event:self.load_selected_account_name())
        self.load_accounts()

    def save_new_account(self):
        try: account=self.client.save_account({"code":self.new_account_code.get(),"name_en":self.new_account_name.get(),"parent_code":self.new_account_parent.get(),"type":self.new_account_type.get()})
        except Exception as exc: return messagebox.showerror("Chart of Accounts",str(exc))
        self.new_account_code.set(""); self.new_account_name.set(""); self.new_account_parent.set(""); self.load_accounts()
        messagebox.showinfo("Chart of Accounts",f'Account {account["code"]} created successfully')

    def load_selected_account_name(self):
        selected=self.accounts_tree.selection()
        if not selected: return
        values=self.accounts_tree.item(selected[0],"values"); self.new_account_code.set(values[0]); self.new_account_name.set(values[2])

    def rename_selected_account(self):
        selected=self.accounts_tree.selection()
        if not selected: return messagebox.showwarning("Chart of Accounts","Select an account first")
        code=str(self.accounts_tree.item(selected[0],"values")[0]); name=self.new_account_name.get().strip()
        try: self.client.rename_account(code,name)
        except Exception as exc: return messagebox.showerror("Chart of Accounts",str(exc))
        self.load_accounts(); messagebox.showinfo("Chart of Accounts",f"Account {code} name updated")

    def load_accounts(self):
        try:
            rows=self.client.accounts()
        except Exception as exc:
            return messagebox.showerror("Error",str(exc))
        self.accounts_tree.delete(*self.accounts_tree.get_children())
        for row in rows:
            self.accounts_tree.insert("","end",values=(row["code"],row.get("parent_code") or "",
                row["name_en"],row.get("name_fr") or "",row.get("name_ar") or "",row["type"]))

    def build_settings(self):
        nested=ttk.Notebook(self.settings_tab); nested.pack(fill="both",expand=True,padx=10,pady=10)
        users=tk.Frame(nested,bg=LIGHT); backups=tk.Frame(nested,bg=LIGHT); rates=tk.Frame(nested,bg=LIGHT); general=tk.Frame(nested,bg=LIGHT)
        nested.add(users,text="Users & Permissions"); nested.add(backups,text="Backup & Restore"); nested.add(rates,text="Exchange Rates"); nested.add(general,text="General Settings")
        user_controls=tk.Frame(users,bg=LIGHT); user_controls.pack(fill="x",padx=10,pady=10)
        self.user_name=tk.StringVar(); self.user_password=tk.StringVar(); self.user_role=tk.StringVar(value="viewer"); self.user_language=tk.StringVar(value="en"); self.edit_user_id=None
        for label,var,width in (("Username",self.user_name,16),("Password",self.user_password,16)):
            tk.Label(user_controls,text=label,bg=LIGHT).pack(side="left",padx=(4,2)); tk.Entry(user_controls,textvariable=var,width=width,show="*" if label=="Password" else "").pack(side="left",padx=4)
        ttk.Combobox(user_controls,textvariable=self.user_role,values=["admin","accountant","viewer"],state="readonly",width=11).pack(side="left",padx=4)
        ttk.Combobox(user_controls,textvariable=self.user_language,values=["en","ar","fr"],state="readonly",width=6).pack(side="left",padx=4)
        self.action_button(user_controls,"Create / Update User",self.add_user).pack(side="left",padx=5)
        self.users_tree=self.table(users,[("id","ID",60),("username","Username",200),("role","Role",120),("language","Language",90),("active","Active",80)])
        self.users_tree.bind("<Double-1>",lambda _event:self.edit_selected_user())
        backup_controls=tk.Frame(backups,bg=LIGHT); backup_controls.pack(fill="x",padx=10,pady=10)
        self.action_button(backup_controls,"Create Backup Now",self.create_backup).pack(side="left",padx=4)
        tk.Button(backup_controls,text="Restore Selected",command=self.restore_selected_backup,bg="#8B1E1E",fg="white",border=0,padx=15,pady=7).pack(side="left",padx=4)
        self.backups_tree=self.table(backups,[("name","Backup File",360),("size","Size",120),("modified","Created",180)])
        rate_controls=tk.Frame(rates,bg=LIGHT); rate_controls.pack(fill="x",padx=10,pady=10)
        self.rate_date=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y")); self.rate_date_to=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y")); self.rate_from=tk.StringVar(value="USD"); self.rate_to=tk.StringVar(value="LBP"); self.rate_value=tk.StringVar(value="1")
        tk.Label(rate_controls,text="Date From",bg=LIGHT).pack(side="left"); tk.Entry(rate_controls,textvariable=self.rate_date,width=12).pack(side="left",padx=4)
        tk.Label(rate_controls,text="Date To",bg=LIGHT).pack(side="left"); tk.Entry(rate_controls,textvariable=self.rate_date_to,width=12).pack(side="left",padx=4)
        ttk.Combobox(rate_controls,textvariable=self.rate_from,values=["USD","EUR","LBP","AED"],state="readonly",width=7).pack(side="left",padx=4)
        tk.Label(rate_controls,text="to",bg=LIGHT).pack(side="left")
        ttk.Combobox(rate_controls,textvariable=self.rate_to,values=["USD","EUR","LBP","AED"],state="readonly",width=7).pack(side="left",padx=4)
        tk.Entry(rate_controls,textvariable=self.rate_value,width=14).pack(side="left",padx=4)
        self.action_button(rate_controls,"Save Rate",self.save_exchange_rate).pack(side="left",padx=5)
        self.rates_tree=self.table(rates,[("date","Date",110),("from","From",80),("to","To",80),("rate","Rate",150),("created","Saved",180)])
        self.rates_tree.bind("<Double-1>",lambda _event:self.edit_selected_exchange_rate())
        self.base_currency=tk.StringVar(value="USD"); self.backup_hours=tk.StringVar(value="24")
        self.company_fields={key:tk.StringVar() for key in ("company_name","company_address","company_phone","company_mof","company_email","company_website","company_logo")}
        tk.Label(general,text="Base Currency",bg=LIGHT).grid(row=0,column=0,padx=14,pady=14,sticky="w")
        ttk.Combobox(general,textvariable=self.base_currency,values=["USD","EUR","LBP","AED"],state="readonly",width=15).grid(row=0,column=1,padx=14,pady=14)
        tk.Label(general,text="Automatic backup every (hours)",bg=LIGHT).grid(row=1,column=0,padx=14,pady=14,sticky="w")
        tk.Entry(general,textvariable=self.backup_hours,width=18).grid(row=1,column=1,padx=14,pady=14)
        for row,(key,label) in enumerate((("company_name","Company Name"),("company_address","Address"),("company_phone","Phone"),("company_mof","MOF / VAT Number"),("company_email","Email"),("company_website","Website"),("company_logo","Logo File Path")),2):
            tk.Label(general,text=label,bg=LIGHT).grid(row=row,column=0,padx=14,pady=7,sticky="w")
            tk.Entry(general,textvariable=self.company_fields[key],width=42).grid(row=row,column=1,padx=14,pady=7,sticky="w")
        self.action_button(general,"Save Settings",self.save_general_settings).grid(row=9,column=0,columnspan=2,pady=14)
        self.load_settings_pages()

    def load_settings_pages(self):
        if not hasattr(self,"users_tree"): return
        try:
            settings=self.client.settings(); rates=self.client.exchange_rates()
            self.base_currency.set(settings.get("base_currency","USD")); self.backup_hours.set(settings.get("backup_interval_hours","24"))
            for key,var in self.company_fields.items(): var.set(settings.get(key,"Saber for Audit" if key=="company_name" else ""))
        except Exception as exc: return messagebox.showerror("Settings",str(exc))
        self.rates_tree.delete(*self.rates_tree.get_children())
        for row in rates: self.rates_tree.insert("","end",values=(row["rate_date"],row["from_currency"],row["to_currency"],row["rate"],row["created_at"][:19]))
        try: users=self.client.users(); backups=self.client.backups()
        except Exception:
            users=[]; backups=[]
        self.users_tree.delete(*self.users_tree.get_children()); self.backups_tree.delete(*self.backups_tree.get_children())
        for row in users: self.users_tree.insert("","end",values=(row["id"],row["username"],row["role"],row["language"],"Yes" if row["active"] else "No"))
        for row in backups: self.backups_tree.insert("","end",iid=row["name"],values=(row["name"],f'{row["size"]/1024/1024:,.2f} MB',row["modified"][:19]))

    def add_user(self):
        try: self.client.save_user({"id":self.edit_user_id,"username":self.user_name.get(),"password":self.user_password.get(),"role":self.user_role.get(),"language":self.user_language.get(),"active":True})
        except Exception as exc: return messagebox.showerror("Users",str(exc))
        self.edit_user_id=None; self.user_name.set(""); self.user_password.set(""); self.load_settings_pages(); messagebox.showinfo("Users","User saved successfully")

    def edit_selected_user(self):
        selected=self.users_tree.selection()
        if not selected: return
        values=self.users_tree.item(selected[0],"values"); self.edit_user_id=int(values[0])
        self.user_name.set(values[1]); self.user_role.set(values[2]); self.user_language.set(values[3]); self.user_password.set("")

    def create_backup(self):
        try: result=self.client.create_backup()
        except Exception as exc: return messagebox.showerror("Backup",str(exc))
        self.load_settings_pages(); messagebox.showinfo("Backup",f'Backup created:\n{result["path"]}')

    def restore_selected_backup(self):
        selected=self.backups_tree.selection()
        if not selected: return messagebox.showwarning("Restore","Select one backup")
        if not messagebox.askyesno("Restore Database","Restore this backup? A safety backup of current data will be created first."): return
        try: self.client.restore_backup(selected[0])
        except Exception as exc: return messagebox.showerror("Restore",str(exc))
        messagebox.showinfo("Restore","Database restored successfully. Refreshing all pages."); self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial(); self.load_settings_pages()

    def save_exchange_rate(self):
        try: self.client.save_exchange_rate({"date_from":self.rate_date.get(),"date_to":self.rate_date_to.get(),"from_currency":self.rate_from.get(),"to_currency":self.rate_to.get(),"rate":self.rate_value.get()})
        except Exception as exc: return messagebox.showerror("Exchange Rates",str(exc))
        self.load_settings_pages(); messagebox.showinfo("Exchange Rates","Rate saved successfully")

    def edit_selected_exchange_rate(self):
        selected=self.rates_tree.selection()
        if not selected: return
        values=self.rates_tree.item(selected[0],"values")
        self.rate_date.set(values[0]); self.rate_date_to.set(values[0]); self.rate_from.set(values[1]); self.rate_to.set(values[2]); self.rate_value.set(values[3])

    def save_general_settings(self):
        payload={"base_currency":self.base_currency.get(),"backup_interval_hours":self.backup_hours.get()}
        payload.update({key:var.get().strip() for key,var in self.company_fields.items()})
        try: self.client.save_settings(payload)
        except Exception as exc: return messagebox.showerror("Settings",str(exc))
        messagebox.showinfo("Settings","Settings saved successfully")

    def build_trial(self):
        filters=tk.Frame(self.trial_tab,bg=LIGHT); filters.pack(fill="x",padx=10,pady=(10,0))
        tk.Label(filters,text="From Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Entry(filters,textvariable=self.trial_from_date,width=13).pack(side="left",padx=(5,14))
        tk.Label(filters,text="To Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Entry(filters,textvariable=self.trial_to_date,width=13).pack(side="left",padx=(5,10))
        tk.Label(filters,text="DD-MM-YYYY",bg=LIGHT,fg="#5f6b76").pack(side="left",padx=(0,10))
        tk.Label(filters,text="Account From:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        self.account_search_box(filters,self.trial_account_from,16).pack(side="left",padx=3)
        tk.Label(filters,text="To:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        self.account_search_box(filters,self.trial_account_to,16).pack(side="left",padx=3)
        ttk.Combobox(filters,textvariable=self.trial_scope,values=["Detailed Trial Balance","Main Account Summary"],state="readonly",width=20).pack(side="left",padx=4)
        ttk.Combobox(filters,textvariable=self.trial_display_currency,values=["USD Only","LBP Only","USD + LBP"],state="readonly",width=11).pack(side="left",padx=4)
        tk.Button(filters,text="Apply",command=self.apply_trial_date_filter,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=16,pady=6).pack(side="left")
        self.trial_tree=self.table(self.trial_tab,[("currency","Currency",80),("code","Account",105),("name","Account Name",270),
            ("opening","Opening Balance",130),("debit","Debit",125),("credit","Credit",125),("closing","Closing Balance",140)])
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
        account_from=self.trial_account_from.get().split(" - ",1)[0].strip() or None; account_to=self.trial_account_to.get().split(" - ",1)[0].strip() or None
        try: rows=self.client.trial_balance(*date_range,None,True,account_from,account_to)
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        targets=["USD","LBP"] if self.trial_display_currency.get()=="USD + LBP" else ["USD" if self.trial_display_currency.get()=="USD Only" else "LBP"]
        displayed=[]
        for target in targets:
            prefix=target.lower(); grouped={}
            for row in rows:
                item=grouped.setdefault((row["code"],row["name_en"]),{"currency":target,"code":row["code"],"name_en":row["name_en"],"opening":0.0,"debit":0.0,"credit":0.0,"closing_balance":0.0})
                item["opening"]+=float(row[prefix+"_opening"]); item["debit"]+=float(row[prefix+"_debit"]); item["credit"]+=float(row[prefix+"_credit"]); item["closing_balance"]+=float(row[prefix+"_closing_balance"])
            displayed.extend(grouped.values())
        rows=displayed
        if self.trial_scope.get()=="Main Account Summary":
            try: accounts=self.client.accounts()
            except Exception: accounts=[]
            parents={str(item["code"]):str(item.get("parent_code") or "") for item in accounts}; names={str(item["code"]):item["name_en"] for item in accounts}
            def root(code):
                seen=set(); current=str(code)
                while parents.get(current) and current not in seen: seen.add(current); current=parents[current]
                return current
            summary={}
            for row in rows:
                code=root(row["code"]); key=(row["currency"],code)
                item=summary.setdefault(key,{"currency":row["currency"],"code":code,"name_en":names.get(code,row["name_en"]),"opening":0.0,"debit":0.0,"credit":0.0,"closing_balance":0.0})
                for field in ("opening","debit","credit","closing_balance"): item[field]+=float(row.get(field,0))
            rows=list(summary.values())
        def account_sort(row):
            digits="".join(character for character in str(row.get("code", "")) if character.isdigit())
            return (str(row.get("currency","")),int(digits or 0),str(row.get("code","")))
        ordered=[]
        for currency in targets:
            currency_rows=sorted([row for row in rows if row["currency"]==currency],key=account_sort)
            classes={}
            for row in currency_rows:
                class_code=next((character for character in str(row["code"]) if character.isdigit()),"Other")
                classes.setdefault(class_code,[]).append(row)
            for class_code in sorted(classes,key=lambda value:int(value) if str(value).isdigit() else 99):
                class_rows=classes[class_code]; ordered.extend(class_rows)
                ordered.append({"currency":currency,"code":f"CLASS {class_code}","name_en":"CLASS TOTAL","opening":sum(r["opening"] for r in class_rows),"debit":sum(r["debit"] for r in class_rows),"credit":sum(r["credit"] for r in class_rows),"closing_balance":sum(r["closing_balance"] for r in class_rows),"row_type":"class_total"})
            ordered.append({"currency":currency,"code":"","name_en":"TOTAL TRIAL BALANCE","opening":sum(r["opening"] for r in currency_rows),"debit":sum(r["debit"] for r in currency_rows),"credit":sum(r["credit"] for r in currency_rows),"closing_balance":sum(r["closing_balance"] for r in currency_rows),"row_type":"currency_total"})
        rows=ordered
        self.trial_rows=rows; self.trial_tree.delete(*self.trial_tree.get_children())
        self.trial_tree.tag_configure("class_total",background="#e8edf2",font=("Segoe UI",9,"bold")); self.trial_tree.tag_configure("currency_total",background=GOLD,foreground=NAVY,font=("Segoe UI",9,"bold"))
        for r in rows: self.trial_tree.insert("","end",values=(r["currency"],r["code"],r["name_en"],f'{r.get("opening",0):,.2f}',f'{r["debit"] or 0:,.2f}',f'{r["credit"] or 0:,.2f}',f'{r["closing_balance"] or 0:,.2f}'),tags=(r.get("row_type","") or "",))

    def action_button(self,parent,text,command):
        return tk.Button(parent,text=text,command=command,bg=NAVY,fg="white",border=0,padx=15,pady=7)

    def account_search_box(self,parent,variable,width=22):
        try: accounts=self.client.accounts() if self.client else []
        except Exception: accounts=[]
        choices=[f'{row["code"]} - {row["name_en"]}' for row in accounts]
        box=ttk.Combobox(parent,textvariable=variable,values=choices,width=width)
        def search(_event=None):
            typed=variable.get().strip().casefold()
            box["values"]=[value for value in choices if typed in value.casefold()] if typed else choices
            if len(typed)>=3 and box["values"]: box.after_idle(lambda: box.event_generate("<Down>"))
        def choose(_event=None):
            value=variable.get(); variable.set(value.split(" - ",1)[0].strip() if " - " in value else value.strip())
        box.bind("<KeyRelease>",search); box.bind("<<ComboboxSelected>>",choose); box.bind("<FocusOut>",choose)
        return box

    def export_report(self,report,format_name):
        if report == "dashboard":
            title="Saber Accounting - Dashboard"; headers=["Currency","Sales","Purchases","Expenses","Net Profit","Receivables","Payables","Overdue"]
            rows=[[r["currency"],r["sales"],r["purchases"],r["expenses"],r["profit"],r["receivables"],r["payables"],r["overdue"]] for r in getattr(self,"dashboard_rows",[])]
        else:
            title="Saber Accounting - Trial Balance"
            if self.trial_from_date.get().strip() or self.trial_to_date.get().strip():
                title += f" ({self.trial_from_date.get().strip() or 'Beginning'} to {self.trial_to_date.get().strip() or 'Today'})"
            headers=["Currency","Account","Account Name","Opening Balance","Debit","Credit","Closing Balance"]
            rows=[[r["currency"],r["code"],r["name_en"],r.get("opening",0),r["debit"] or 0,r["credit"] or 0,r.get("closing_balance",0)] for r in getattr(self,"trial_rows",[])]
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
