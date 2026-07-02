FIELDS = {
    "fleet_unit_no": {"labels": ["Fleet Unit No.", "Fleet Unit No", "Unit No."], "regex": r"Fleet Unit No\.?\s*(\d+)"},
    "document_number": {"labels": ["Document No.", "Document No"], "regex": r"(BOS-[A-Z0-9-]+)"},
    "document_date": {"labels": ["Date of Sale", "Date of Sale:"]},
    "vin": {"labels": ["VIN", "V.I.N.", "Vehicle Identification Number"], "pattern": r"([A-HJ-NPR-Z0-9]{17})"},
    "year": {"labels": ["YEAR", "Model Year"], "pattern": r"(\d{4})"},
    "make": {"labels": ["MAKE", "Manufacturer"]},
    "model": {"labels": ["MODEL", "Model"]},
    "body_type": {"labels": ["BODY TYPE", "Body Type", "Type"]},
    "color": {"labels": ["COLOR", "Color"]},
    "odometer": {"labels": ["ODOMETER", "Odometer Reading"], "pattern": r"([\d,]+)"},
    "purchase_price": {"labels": ["TOTAL PURCHASE PRICE", "Purchase Price", "Sale Price"]},
    "payment_method": {"labels": ["METHOD OF PAYMENT", "Payment Method"]},
    "seller_name": {"labels": ["SELLER"]},
    "buyer_name": {"labels": ["BUYER"]},
}

REQUIRED = ["vin", "year", "make", "fleet_unit_no", "document_date"]
