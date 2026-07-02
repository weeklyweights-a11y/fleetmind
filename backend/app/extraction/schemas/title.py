FIELDS = {
    "title_number": {"labels": ["TITLE NUMBER"], "pattern": r"([A-Z0-9]+)"},
    "issue_date": {"labels": ["DATE OF ISSUE"]},
    "vin": {"labels": ["VEHICLE IDENTIFICATION NUMBER", "VIN"], "pattern": r"([A-HJ-NPR-Z0-9]{17})"},
    "year": {"labels": ["YEAR"], "pattern": r"(\d{4})"},
    "make": {"labels": ["MAKE"]},
    "model": {"labels": ["MODEL"]},
    "color": {"labels": ["COLOR"]},
    "owner_name": {"labels": ["OWNER NAME"]},
    "fleet_unit_no": {"labels": ["FLEET UNIT NO."], "pattern": r"(\d+)"},
    "odometer": {"labels": ["ODOMETER"], "pattern": r"([\d,]+)"},
    "title_fee": {"labels": ["TITLE FEE"]},
}

REQUIRED = ["title_number", "vin", "issue_date", "owner_name"]
