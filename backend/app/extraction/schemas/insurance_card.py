FIELDS = {
    "policy_number": {"labels": ["POLICY NUMBER", "Policy No."], "regex": r"(GWCA-[A-Z0-9 -]+)"},
    "insurer_name": {"regex": r"(GREAT WEST CASUALTY COMPANY)"},
    "effective_date": {"labels": ["EFFECTIVE DATE"]},
    "expiry_date": {"labels": ["EXPIRATION DATE", "EXPIRY DATE"]},
    "unit_number": {"regex": r"UNIT\s*(\d+)"},
    "vin": {"labels": ["VIN", "VEHICLE IDENTIFICATION"], "pattern": r"([A-HJ-NPR-Z0-9]{17})"},
    "license_plate": {"labels": ["LICENSE PLATE"]},
    "liability_limit": {"labels": ["LIABILITY LIMIT"]},
    "cargo_limit": {"regex": r"Cargo Limit:\s*\$?([\d,]+)"},
    "coverage_type": {"labels": ["COVERAGE", "POLICY TYPE"]},
    "agent_name": {"labels": ["Agent"]},
}

REQUIRED = ["policy_number", "effective_date", "expiry_date", "unit_number", "vin"]
