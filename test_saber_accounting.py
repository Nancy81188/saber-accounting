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

    def test_report_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            rows=[["purchase","USD",2,300,33,333]]; headers=["Type","Currency","Invoices","Before VAT","VAT","Total"]
            xlsx=Path(folder)/"dashboard.xlsx"; pdf=Path(folder)/"dashboard.pdf"
            export_excel(xlsx,"Dashboard",headers,rows); export_pdf(pdf,"Dashboard",headers,rows)
            self.assertGreater(xlsx.stat().st_size,1000); self.assertGreater(pdf.stat().st_size,500)

if __name__ == "__main__": unittest.main()
