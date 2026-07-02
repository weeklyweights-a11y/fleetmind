FIELDS = {
    "driver_code": {"regex": r"CDL-(D\d+)"},
    "fleet_unit_assignment": {"regex": r"FLEET\s+(\d+|None)"},
    "full_name": {"regex": r"CLASS\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)"},
    "last_name": {"regex": r"1\s+([A-Z]+)"},
    "first_name": {"regex": r"2\s+([A-Z]+)"},
    "address": {"regex": r"8\s+(.+?)(?=3\s*DOB)"},
    "date_of_birth": {"labels": ["3 DOB", "DOB"]},
    "license_issue_date": {"labels": ["4a ISS", "ISS"]},
    "license_expiry_date": {"labels": ["4b EXP", "EXP"]},
    "sex": {"labels": ["15 SEX"], "pattern": r"([MF])"},
    "height": {"labels": ["16 HGT"]},
    "eye_color": {"labels": ["18 EYES"], "pattern": r"([A-Z]{3})"},
    "weight": {"labels": ["WGT"], "pattern": r"(\d+)"},
    "license_class": {"labels": ["9 CLASS"], "pattern": r"([A-Z])"},
    "license_number": {"labels": ["4d DLN", "DLN"], "pattern": r"([A-Z0-9-]+)"},
    "endorsements": {"labels": ["9a END", "END"]},
    "restrictions": {"labels": ["12 REST", "REST"]},
}

REQUIRED = ["license_number", "license_class", "license_expiry_date", "full_name"]
