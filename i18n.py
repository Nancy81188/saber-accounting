TRANSLATIONS = {
    "en": {
        "title": "Saber Accounting", "login": "Sign in", "username": "Username",
        "password": "Password", "server": "Server address", "language": "Language",
        "dashboard": "Dashboard", "invoices": "Invoices", "import": "Import Excel",
        "refresh": "Refresh", "choose_file": "Choose Excel file", "preview": "Preview",
        "send": "Import to shared database", "invoice_no": "Invoice No.", "date": "Date",
        "party": "Customer / Supplier", "before_vat": "Before VAT", "vat": "VAT",
        "total": "Total", "currency": "Currency", "status": "Status",
        "source_row": "Source Row", "rows_ready": "rows ready", "imported": "rows imported",
        "sales": "Sales", "purchases": "Purchases", "vat_due": "VAT",
    },
    "fr": {
        "title": "Saber Comptabilité", "login": "Connexion", "username": "Utilisateur",
        "password": "Mot de passe", "server": "Adresse du serveur", "language": "Langue",
        "dashboard": "Tableau de bord", "invoices": "Factures", "import": "Importer Excel",
        "refresh": "Actualiser", "choose_file": "Choisir un fichier Excel", "preview": "Aperçu",
        "send": "Importer vers la base partagée", "invoice_no": "N° facture", "date": "Date",
        "party": "Client / Fournisseur", "before_vat": "Hors TVA", "vat": "TVA",
        "total": "Total", "currency": "Devise", "status": "Statut",
        "source_row": "Ligne source", "rows_ready": "lignes prêtes", "imported": "lignes importées",
        "sales": "Ventes", "purchases": "Achats", "vat_due": "TVA",
    },
    "ar": {
        "title": "سيبر للمحاسبة", "login": "تسجيل الدخول", "username": "اسم المستخدم",
        "password": "كلمة المرور", "server": "عنوان الخادم", "language": "اللغة",
        "dashboard": "لوحة التحكم", "invoices": "الفواتير", "import": "استيراد إكسل",
        "refresh": "تحديث", "choose_file": "اختيار ملف إكسل", "preview": "معاينة",
        "send": "استيراد إلى قاعدة البيانات المشتركة", "invoice_no": "رقم الفاتورة", "date": "التاريخ",
        "party": "العميل / المورد", "before_vat": "قبل الضريبة", "vat": "الضريبة",
        "total": "المجموع", "currency": "العملة", "status": "الحالة",
        "source_row": "سطر المصدر", "rows_ready": "أسطر جاهزة", "imported": "أسطر مستوردة",
        "sales": "المبيعات", "purchases": "المشتريات", "vat_due": "الضريبة",
    },
}

def tr(language, key):
    return TRANSLATIONS.get(language, TRANSLATIONS["en"]).get(key, key)

