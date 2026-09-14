from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from client import ApiClient
from i18n import tr
from importer import read_invoices
from report_export import export_excel, export_pdf, print_rows

NAVY, GOLD, LIGHT = "#071b2e", "#c9a96a", "#f3f6f8"

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
        tk.Label(card, text="SABER", font=("Segoe UI", 28, "bold"), fg=NAVY, bg="white").grid(row=0, column=0, columnspan=2)
        tk.Label(card, text="ACCOUNTING", font=("Segoe UI", 11, "bold"), fg=GOLD, bg="white").grid(row=1, column=0, columnspan=2, pady=(0,25))
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
        tk.Label(top,text=tr(lang,"title"),bg=NAVY,fg="white",font=("Segoe UI",20,"bold")).pack(side="left",padx=28,pady=19)
        tk.Label(top,text="11% VAT  |  USD · LBP · EUR · AED",bg=NAVY,fg=GOLD,font=("Segoe UI",10,"bold")).pack(side="right",padx=28)
        notebook=ttk.Notebook(self); notebook.pack(fill="both",expand=True,padx=18,pady=16)
        self.dashboard_tab=tk.Frame(notebook,bg=LIGHT); self.invoices_tab=tk.Frame(notebook,bg=LIGHT); self.import_tab=tk.Frame(notebook,bg=LIGHT); self.trial_tab=tk.Frame(notebook,bg=LIGHT)
        notebook.add(self.dashboard_tab,text=tr(lang,"dashboard")); notebook.add(self.invoices_tab,text=tr(lang,"invoices")); notebook.add(self.import_tab,text=tr(lang,"import")); notebook.add(self.trial_tab,text="Trial Balance")
        self.build_dashboard(); self.build_invoices(); self.build_import(); self.build_trial()

    def table(self,parent,columns):
        frame=tk.Frame(parent,bg=LIGHT); frame.pack(fill="both",expand=True,padx=10,pady=10)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show="headings")
        for key,label,width in columns: tree.heading(key,text=label); tree.column(key,width=width,anchor="w")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        return tree

    def build_dashboard(self):
        self.dashboard_tree=self.table(self.dashboard_tab,[("kind","Type",130),("currency","Currency",100),("count","Invoices",100),("subtotal","Before VAT",160),("vat","VAT",140),("total","Total",160)])
        actions=tk.Frame(self.dashboard_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_dashboard).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("dashboard","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("dashboard","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("dashboard","print")).pack(side="left",padx=4)
        self.load_dashboard()

    def load_dashboard(self):
        try: rows=self.client.dashboard()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        self.dashboard_rows=rows; self.dashboard_tree.delete(*self.dashboard_tree.get_children())
        for r in rows: self.dashboard_tree.insert("", "end", values=(r["kind"],r["currency"],r["count"],f'{r["subtotal"]:,.2f}',f'{r["vat"]:,.2f}',f'{r["total"]:,.2f}'))

    def build_invoices(self):
        l=self.language.get(); self.invoice_tree=self.table(self.invoices_tab,[("no",tr(l,"invoice_no"),110),("date",tr(l,"date"),110),("party",tr(l,"party"),260),("kind","Type",90),("currency",tr(l,"currency"),80),("subtotal",tr(l,"before_vat"),120),("vat",tr(l,"vat"),100),("total",tr(l,"total"),120),("row",tr(l,"source_row"),90)])
        tk.Button(self.invoices_tab,text=tr(l,"refresh"),command=self.load_invoices,bg=NAVY,fg="white",border=0,padx=20,pady=7).pack(pady=(0,10)); self.load_invoices()

    def load_invoices(self):
        try: rows=self.client.invoices()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        self.invoice_tree.delete(*self.invoice_tree.get_children())
        for r in rows: self.invoice_tree.insert("","end",values=(r["invoice_number"],r["invoice_date"],r["party_name"],r["kind"],r["currency"],r["subtotal"],r["vat"],r["total"],r["source_row"]))

    def build_import(self):
        l=self.language.get(); controls=tk.Frame(self.import_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        self.file_label=tk.Label(controls,text="No file selected",bg=LIGHT,anchor="w"); self.file_label.pack(side="left",fill="x",expand=True)
        self.currency=tk.StringVar(value="USD"); ttk.Combobox(controls,textvariable=self.currency,values=["USD","LBP","EUR","AED"],state="readonly",width=8).pack(side="right",padx=6)
        self.kind=tk.StringVar(value="purchase"); ttk.Combobox(controls,textvariable=self.kind,values=["purchase","sale"],state="readonly",width=10).pack(side="right",padx=6)
        tk.Button(controls,text=tr(l,"choose_file"),command=self.choose_import,bg=NAVY,fg="white",border=0,padx=16,pady=7).pack(side="right")
        self.import_tree=self.table(self.import_tab,[("no",tr(l,"invoice_no"),100),("row",tr(l,"source_row"),90),("date",tr(l,"date"),110),("party",tr(l,"party"),260),("subtotal",tr(l,"before_vat"),120),("vat",tr(l,"vat"),100),("total",tr(l,"total"),120)])
        self.import_status=tk.Label(self.import_tab,text="",bg=LIGHT); self.import_status.pack()
        tk.Button(self.import_tab,text=tr(l,"send"),command=self.send_import,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=22,pady=8).pack(pady=10)

    def choose_import(self):
        path=filedialog.askopenfilename(filetypes=[("Excel files","*.xlsx")])
        if not path: return
        try: self.import_rows=read_invoices(path,default_currency=self.currency.get(),default_kind=self.kind.get())
        except Exception as exc: return messagebox.showerror("Import",str(exc))
        self.file_label.config(text=path); self.import_tree.delete(*self.import_tree.get_children())
        for r in self.import_rows[:1000]: self.import_tree.insert("","end",values=(r["invoice_number"],r["source_row"],r["invoice_date"],r["party_name"],r["subtotal"],r["vat"],r["total"]))
        self.import_status.config(text=f'{len(self.import_rows)} {tr(self.language.get(),"rows_ready")}')

    def send_import(self):
        if not self.import_rows: return messagebox.showwarning("Import","Choose a file first")
        try: result=self.client.import_invoices(self.import_rows)
        except Exception as exc: return messagebox.showerror("Import",str(exc))
        messagebox.showinfo("Import",f'{result["imported"]} {tr(self.language.get(),"imported")}\nErrors: {len(result["errors"])}')
        self.load_dashboard(); self.load_invoices()

    def build_trial(self):
        self.trial_tree=self.table(self.trial_tab,[("code","Account",110),("name","Name",280),("debit","Debit",150),("credit","Credit",150),("balance","Balance",160)])
        actions=tk.Frame(self.trial_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_trial).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("trial","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("trial","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("trial","print")).pack(side="left",padx=4); self.load_trial()

    def load_trial(self):
        try: rows=self.client.trial_balance()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        self.trial_rows=rows; self.trial_tree.delete(*self.trial_tree.get_children())
        for r in rows: self.trial_tree.insert("","end",values=(r["code"],r["name_en"],f'{r["debit"] or 0:,.2f}',f'{r["credit"] or 0:,.2f}',f'{r["balance"] or 0:,.2f}'))

    def action_button(self,parent,text,command):
        return tk.Button(parent,text=text,command=command,bg=NAVY,fg="white",border=0,padx=15,pady=7)

    def export_report(self,report,format_name):
        if report == "dashboard":
            title="Saber Accounting - Dashboard"; headers=["Type","Currency","Invoices","Before VAT","VAT","Total"]
            rows=[[r["kind"],r["currency"],r["count"],r["subtotal"],r["vat"],r["total"]] for r in getattr(self,"dashboard_rows",[])]
        else:
            title="Saber Accounting - Trial Balance"; headers=["Account","Name","Debit","Credit","Balance"]
            rows=[[r["code"],r["name_en"],r["debit"] or 0,r["credit"] or 0,r["balance"] or 0] for r in getattr(self,"trial_rows",[])]
            rows.append(["","TOTAL",sum(float(r[2]) for r in rows),sum(float(r[3]) for r in rows),sum(float(r[4]) for r in rows)])
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
