FIELDS = {
    "plate_number": {"labels": ["LICENSE PLATE NO.", "License Plate"]},
    "vin": {"labels": ["VIN", "VEHICLE IDENTIFICATION NUMBER"], "pattern": r"([A-HJ-NPR-Z0-9]{17})"},
    "year": {"labels": ["YEAR"], "pattern": r"(\d{4})"},
    "make": {"labels": ["MAKE"]},
    "model": {"labels": ["MODEL"]},
    "unit_number": {"labels": ["UNIT NO.", "EQUIPMENT / UNIT NO."], "pattern": r"(\d+)"},
    "effective_date": {"labels": ["EFFECTIVE DATE"]},
    "expiry_date": {"labels": ["EXPIRES", "EXPIRATION DATE"]},
    "registration_fee": {"labels": ["Registration Fee"]},
    "property_tax": {"labels": ["Personal Property Tax", "PPT"]},
    "irp_apportioned_fee": {"labels": ["IRP Apportioned Fee"]},
    "title_fee": {"labels": ["Title Fee"]},
    "total_fees": {"labels": ["TOTAL FEES PAID"]},
    "issue_date": {"labels": ["ISSUED"]},
}

REQUIRED = ["vin", "unit_number", "effective_date", "expiry_date", "plate_number"]
