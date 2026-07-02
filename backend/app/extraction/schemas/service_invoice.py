FIELDS = {
    "vendor_name": {"regex": r"^(.+?)\n"},
    "invoice_number": {"labels": ["INVOICE NO.", "Invoice No.", "Invoice #"], "regex": r"INVOICE\s*NO\.?\s*([A-Z]{3}-\d+)"},
    "invoice_date": {"labels": ["DATE"]},
    "po_number": {"labels": ["PO NO.", "PO #"]},
    "unit_number": {"labels": ["UNIT #", "Unit #", "Unit No."], "pattern": r"(\d+)"},
    "category": {"labels": ["CATEGORY"]},
    "vin": {"labels": ["VIN"], "pattern": r"([A-HJ-NPR-Z0-9]{17})"},
    "subtotal": {"labels": ["SUBTOTAL"]},
    "labor_cost": {"labels": ["LABOR"]},
    "sales_tax": {"labels": ["SALES TAX"]},
    "total": {"labels": ["TOTAL"]},
    "payment_status": {"labels": ["STATUS"], "regex": r"(PAID|UNPAID)"},
    "payment_method": {"labels": ["METHOD"]},
    "technician": {"labels": ["TECHNICIAN"]},
}

REQUIRED = ["invoice_number", "invoice_date", "unit_number", "vin", "total", "category"]
