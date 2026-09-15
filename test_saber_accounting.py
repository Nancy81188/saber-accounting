import tempfile
import unittest
from pathlib import Path
from openpyxl import Workbook
from database import Database
from importer import read_invoices
from report_export import export_excel, export_pdf

class SaberAccountingTest(unittest.TestCase):
    def test_import_rules_and_balancing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.xlsx"
            wb = Workbook(); ws = wb.active
            ws.append(["Invoice Number","Date","Supplier Name","Total Before VAT","VAT","Total After VAT"])
            ws.append(["A-100","01-09-2026","Supplier A",100,11,111])
            ws.append([None,None,None,None,None,None])
            ws.append([None,"02-09-2026","Supplier B",200,22,200])
            ws.append(["A-100","01-09-2026","Supplier A",100,11,111]); wb.save(path)
            rows = read_invoices(path)
            self.assertEqual([r["invoice_number"] for r in rows], ["A-100","4","A-100"])
            db=Database(Path(folder)/"test.db"); db.initialize("secret")
            user=db.user_for_token(db.login("admin","secret")["token"])
            for row in rows: db.import_invoice(row,user["id"])
            self.assertEqual(len(db.list_invoices()),3)
            tb=db.trial_balance()
            self.assertAlmostEqual(sum(float(r["debit"] or 0) for r in tb),sum(float(r["credit"] or 0) for r in tb),places=2)

    def test_currency_detection_defaults_conflicts_and_separation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "currencies.xlsx"
            wb = Workbook(); ws = wb.active
            ws.append(["Invoice Number","Date","Supplier Name","Total Before VAT","VAT","Total After VAT","Currency"])
            ws.append(["USD-1","01-09-2026","A","$100","$11","$111",None])
            ws.append(["EUR-1","02-09-2026","B","€200","€22","€222",None])
            ws.append(["LBP-1","03-09-2026","C","300 L.L.","33 L.L.","333 L.L.",None])
            ws.append(["AED-1","04-09-2026","D","AED 400","AED 44","AED 444",None])
            ws.append(["DEFAULT-1","05-09-2026","E",500,55,555,None])
            ws.append(["CONFLICT-1","06-09-2026","F","$600","$66","$666","EUR"])
            ws.append(["PRICE-WINS","07-09-2026","G","€700","€77","€777","USD"])
            wb.save(path)
            rows = read_invoices(path)
            self.assertEqual([r["currency"] for r in rows[:5]], ["USD","EUR","LBP","AED","USD"])
            self.assertEqual(rows[6]["currency"], "EUR")
            self.assertTrue(rows[6]["currency_issue"].startswith("conflicting:"))
            self.assertEqual(rows[4]["currency_issue"], "missing_defaulted_to_usd")
            self.assertTrue(rows[5]["currency_issue"].startswith("conflicting:"))

            db=Database(Path(folder)/"currency.db"); db.initialize("secret")
            user=db.user_for_token(db.login("admin","secret")["token"])
            for row in rows: db.import_invoice(row,user["id"])
            self.assertEqual({r["currency"] for r in db.dashboard()}, {"USD","EUR","LBP","AED"})
            trial=db.trial_balance()
            self.assertEqual({r["currency"] for r in trial}, {"USD","EUR","LBP","AED"})
            conflict=next(r for r in db.list_invoices() if r["invoice_number"]=="CONFLICT-1")
            self.assertEqual(conflict["status"], "review")

    def test_manual_invoice_items_editable_subtotal_and_vat(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/"manual.db"); db.initialize("secret")
            user=db.user_for_token(db.login("admin","secret")["token"])
            invoice={"invoice_number":"M-1","invoice_date":"14-09-2026","party_name":"Manual Supplier",
                     "kind":"purchase","currency":"USD","source_file":"Manual Entry"}
            items=[
                {"description":"Automatic VAT","quantity":2,"unit_price":50,"vat_rate":11},
                {"description":"Edited subtotal","quantity":1,"unit_price":100,"subtotal":90,"vat_rate":5},
                {"description":"Edited VAT","quantity":1,"unit_price":20,"vat_rate":11,"vat":1},
            ]
            invoice_id=db.create_manual_invoice(invoice,items,user["id"])
            saved=next(row for row in db.list_invoices() if row["id"]==invoice_id)
            self.assertEqual(float(saved["subtotal"]),210.0)
            self.assertEqual(float(saved["vat"]),16.5)
            self.assertEqual(float(saved["total"]),226.5)
            with db.connect() as connection:
                lines=connection.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id",(invoice_id,)).fetchall()
            self.assertEqual(len(lines),3)
            self.assertEqual(float(lines[1]["subtotal"]),90.0)
            self.assertEqual(float(lines[2]["vat"]),1.0)

    def test_currency_detection_from_excel_number_formats(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "formatted-currencies.xlsx"
            wb = Workbook(); ws = wb.active
            ws.append(["Invoice Number","Date","Supplier Name","Total Before VAT","VAT","Total After VAT"])
            formats = [
                ("USD-FMT", '"$"#,##0.00'),
                ("EUR-FMT", '€#,##0.00'),
                ("LBP-FMT", '#,##0.00 "L.L."'),
                ("AED-FMT", '#,##0.00 "AED"'),
            ]
            for invoice_number, number_format in formats:
                ws.append([invoice_number,"14-09-2026","Supplier",100,11,111])
                for column in (4,5,6):
                    ws.cell(ws.max_row,column).number_format=number_format
            ws.append(["EUR-BLANK-VAT","14-09-2026","Supplier",100,None,100])
            ws.cell(ws.max_row,4).number_format='€#,##0.00'
            ws.cell(ws.max_row,5).number_format='"$"#,##0.00'
            ws.cell(ws.max_row,6).number_format='€#,##0.00'
            ws.append(["EUR-MAJORITY","14-09-2026","Supplier",100,11,111])
            ws.cell(ws.max_row,4).number_format='€#,##0.00'
            ws.cell(ws.max_row,5).number_format='"$"#,##0.00'
            ws.cell(ws.max_row,6).number_format='€#,##0.00'
            wb.save(path)
            rows=read_invoices(path)
            self.assertEqual([row["currency"] for row in rows],["USD","EUR","LBP","AED","EUR","EUR"])
            self.assertNotIn("conflicting",rows[4]["currency_issue"])
            self.assertTrue(rows[5]["currency_issue"].startswith("conflicting:"))

    def test_report_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            rows=[["purchase","USD",2,300,33,333]]; headers=["Type","Currency","Invoices","Before VAT","VAT","Total"]
            xlsx=Path(folder)/"dashboard.xlsx"; pdf=Path(folder)/"dashboard.pdf"
            export_excel(xlsx,"Dashboard",headers,rows); export_pdf(pdf,"Dashboard",headers,rows)
            self.assertGreater(xlsx.stat().st_size,1000); self.assertGreater(pdf.stat().st_size,500)

    def test_replacement_removes_previous_invoice_set(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/"test.db"); db.initialize("secret")
            user=db.user_for_token(db.login("admin","secret")["token"])
            first={"invoice_number":"1","invoice_date":"2026-09-01","party_name":"A","kind":"purchase","currency":"USD","subtotal":100,"vat":11,"total":111}
            second={"invoice_number":"2","invoice_date":"2026-09-02","party_name":"B","kind":"purchase","currency":"USD","subtotal":200,"vat":22,"total":222}
            db.import_invoice(first,user["id"]); result=db.clear_invoices(user["id"]); db.import_invoice(second,user["id"])
            self.assertEqual(result["deleted"],1); self.assertTrue(Path(result["backup"]).exists())
            invoices=db.list_invoices(); self.assertEqual(len(invoices),1); self.assertEqual(invoices[0]["invoice_number"],"2")

if __name__ == "__main__": unittest.main()
