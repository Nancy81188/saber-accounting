from __future__ import annotations

import tkinter as tk
from datetime import datetime
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
        self.manual_items = []
        self.view_currency = tk.StringVar(value="All Currencies")
        self.import_view_currency = tk.StringVar(value="All Currencies")
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
        self.dashboard_tab=tk.Frame(notebook,bg=LIGHT); self.invoices_tab=tk.Frame(notebook,bg=LIGHT); self.manual_tab=tk.Frame(notebook,bg=LIGHT); self.import_tab=tk.Frame(notebook,bg=LIGHT); self.trial_tab=tk.Frame(notebook,bg=LIGHT)
        notebook.add(self.dashboard_tab,text=tr(lang,"dashboard")); notebook.add(self.invoices_tab,text=tr(lang,"invoices")); notebook.add(self.manual_tab,text="Manual Entry"); notebook.add(self.import_tab,text=tr(lang,"import")); notebook.add(self.trial_tab,text="Trial Balance")
        filter_bar=tk.Frame(self,bg=LIGHT); filter_bar.pack(fill="x",padx=28)
        tk.Label(filter_bar,text="Show currency:",bg=LIGHT,font=("Segoe UI",10,"bold")).pack(side="left")
        currency_filter=ttk.Combobox(filter_bar,textvariable=self.view_currency,values=["All Currencies","USD","EUR","LBP","AED"],state="readonly",width=16)
        currency_filter.pack(side="left",padx=8); currency_filter.bind("<<ComboboxSelected>>",lambda _event:self.currency_changed())
        self.build_dashboard(); self.build_invoices(); self.build_manual(); self.build_import(); self.build_trial()

    def currency_changed(self):
        self.load_dashboard(); self.load_invoices(); self.load_trial()

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
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.dashboard_rows=rows; self.dashboard_tree.delete(*self.dashboard_tree.get_children())
        for r in rows: self.dashboard_tree.insert("", "end", values=(r["kind"],r["currency"],r["count"],f'{r["subtotal"]:,.2f}',f'{r["vat"]:,.2f}',f'{r["total"]:,.2f}'))

    def build_invoices(self):
        l=self.language.get(); self.invoice_tree=self.table(self.invoices_tab,[("no",tr(l,"invoice_no"),110),("date",tr(l,"date"),110),("party",tr(l,"party"),230),("kind","Type",80),("currency",tr(l,"currency"),75),("subtotal",tr(l,"before_vat"),110),("vat",tr(l,"vat"),90),("total",tr(l,"total"),110),("status","Status",90),("row",tr(l,"source_row"),75)])
        tk.Button(self.invoices_tab,text=tr(l,"refresh"),command=self.load_invoices,bg=NAVY,fg="white",border=0,padx=20,pady=7).pack(pady=(0,10)); self.load_invoices()

    def load_invoices(self):
        try: rows=self.client.invoices()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.invoice_tree.delete(*self.invoice_tree.get_children())
        for r in rows: self.invoice_tree.insert("","end",values=(r["invoice_number"],r["invoice_date"],r["party_name"],r["kind"],r["currency"],r["subtotal"],r["vat"],r["total"],r["status"],r["source_row"]))

    def build_manual(self):
        header=tk.LabelFrame(self.manual_tab,text="Invoice Details",bg=LIGHT,padx=10,pady=8)
        header.pack(fill="x",padx=10,pady=(10,4))
        self.manual_no=tk.StringVar(); self.manual_date=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y"))
        self.manual_party=tk.StringVar(); self.manual_kind=tk.StringVar(value="purchase"); self.manual_currency=tk.StringVar(value="USD")
        fields=[("Invoice Number",self.manual_no,16),("Date",self.manual_date,14),("Customer / Supplier",self.manual_party,28)]
        for col,(label,var,width) in enumerate(fields):
            tk.Label(header,text=label,bg=LIGHT).grid(row=0,column=col*2,sticky="w",padx=4)
            tk.Entry(header,textvariable=var,width=width).grid(row=0,column=col*2+1,padx=4)
        ttk.Combobox(header,textvariable=self.manual_kind,values=["purchase","sale"],state="readonly",width=10).grid(row=0,column=6,padx=5)
        ttk.Combobox(header,textvariable=self.manual_currency,values=["USD","EUR","LBP","AED"],state="readonly",width=8).grid(row=0,column=7,padx=5)

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

        self.manual_tree=self.table(self.manual_tab,[("description","Description",250),("quantity","Qty",70),("price","Unit Price",100),
            ("subtotal","Before VAT",110),("rate","VAT %",75),("vat","VAT",100),("total","After VAT",110)])
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
        self.manual_tree.insert("","end",values=(item["description"],item["quantity"],f'{price:,.2f}',f'{subtotal:,.2f}',f'{rate:g}',f'{vat:,.2f}',f'{total:,.2f}'))
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
        headers=["Description","Quantity","Unit Price","Before VAT","VAT %","VAT Amount","After VAT"]
        rows=[[item["description"],item["quantity"],item["unit_price"],item["subtotal"],item["vat_rate"],item["vat"],item["total"]] for item in self.manual_items]
        rows.append(["","",f"TOTAL {currency}",sum(float(item["subtotal"]) for item in self.manual_items),
                     "",sum(float(item["vat"]) for item in self.manual_items),sum(float(item["total"]) for item in self.manual_items)])
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
                 "source_file":"Manual Entry","source_row":None}
        if not all((invoice["invoice_number"],invoice["invoice_date"],invoice["party_name"])):
            return messagebox.showwarning("Manual Entry","Enter invoice number, date, and customer/supplier")
        if not self.manual_items: return messagebox.showwarning("Manual Entry","Add at least one invoice item")
        try: self.client.create_manual_invoice(invoice,self.manual_items)
        except Exception as exc: return messagebox.showerror("Manual Entry",str(exc))
        messagebox.showinfo("Manual Entry","Invoice saved successfully")
        self.manual_items=[]; self.manual_tree.delete(*self.manual_tree.get_children())
        self.manual_no.set(""); self.manual_party.set(""); self.update_manual_totals()
        self.load_dashboard(); self.load_invoices(); self.load_trial()

    def build_import(self):
        l=self.language.get(); controls=tk.Frame(self.import_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        self.file_label=tk.Label(controls,text="No file selected",bg=LIGHT,anchor="w"); self.file_label.pack(side="left",fill="x",expand=True)
        self.currency=tk.StringVar(value="USD")
        ttk.Combobox(controls,textvariable=self.currency,values=["USD","LBP","EUR","AED"],state="readonly",width=8).pack(side="right",padx=6)
        import_filter=ttk.Combobox(controls,textvariable=self.import_view_currency,values=["All Currencies","USD","EUR","LBP","AED"],state="readonly",width=15)
        import_filter.pack(side="right",padx=6); import_filter.bind("<<ComboboxSelected>>",lambda _event:self.populate_import_preview())
        tk.Label(controls,text="Show:",bg=LIGHT).pack(side="right")
        self.kind=tk.StringVar(value="purchase"); ttk.Combobox(controls,textvariable=self.kind,values=["purchase","sale"],state="readonly",width=10).pack(side="right",padx=6)
        tk.Button(controls,text=tr(l,"choose_file"),command=self.choose_import,bg=NAVY,fg="white",border=0,padx=16,pady=7).pack(side="right")
        self.import_tree=self.table(self.import_tab,[("no",tr(l,"invoice_no"),90),("row",tr(l,"source_row"),70),("date",tr(l,"date"),100),("party",tr(l,"party"),220),("currency",tr(l,"currency"),75),("subtotal",tr(l,"before_vat"),105),("vat",tr(l,"vat"),85),("total",tr(l,"total"),105),("review","Currency Review",180)])
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
            self.import_tree.insert("","end",values=(r["invoice_number"],r["source_row"],r["invoice_date"],r["party_name"],r["currency"],r["subtotal"],r["vat"],r["total"],r["currency_issue"]))
        self.import_status.config(text=f'{len(rows)} {tr(self.language.get(),"rows_ready")} ({selected})')

    def send_import(self):
        if not self.import_rows: return messagebox.showwarning("Import","Choose a file first")
        if not messagebox.askyesno("Replace previous data","This import will remove all previous invoices and replace them with the selected Excel file. A safety backup will be created. Continue?"):
            return
        try: result=self.client.import_invoices(self.import_rows,replace_existing=True)
        except Exception as exc: return messagebox.showerror("Import",str(exc))
        messagebox.showinfo("Import",f'Previous invoices removed: {result["deleted"]}\n{result["imported"]} {tr(self.language.get(),"imported")}\nErrors: {len(result["errors"])}')
        self.load_dashboard(); self.load_invoices()

    def build_trial(self):
        self.trial_tree=self.table(self.trial_tab,[("currency","Currency",90),("code","Account",110),("name","Name",280),("debit","Debit",150),("credit","Credit",150),("balance","Balance",160)])
        actions=tk.Frame(self.trial_tab,bg=LIGHT); actions.pack(pady=(0,10))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_trial).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("trial","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("trial","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("trial","print")).pack(side="left",padx=4); self.load_trial()

    def load_trial(self):
        try: rows=self.client.trial_balance()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        self.trial_rows=rows; self.trial_tree.delete(*self.trial_tree.get_children())
        for r in rows: self.trial_tree.insert("","end",values=(r["currency"],r["code"],r["name_en"],f'{r["debit"] or 0:,.2f}',f'{r["credit"] or 0:,.2f}',f'{r["balance"] or 0:,.2f}'))

    def action_button(self,parent,text,command):
        return tk.Button(parent,text=text,command=command,bg=NAVY,fg="white",border=0,padx=15,pady=7)

    def export_report(self,report,format_name):
        if report == "dashboard":
            title="Saber Accounting - Dashboard"; headers=["Type","Currency","Invoices","Before VAT","VAT","Total"]
            rows=[[r["kind"],r["currency"],r["count"],r["subtotal"],r["vat"],r["total"]] for r in getattr(self,"dashboard_rows",[])]
        else:
            title="Saber Accounting - Trial Balance"; headers=["Currency","Account","Name","Debit","Credit","Balance"]
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
