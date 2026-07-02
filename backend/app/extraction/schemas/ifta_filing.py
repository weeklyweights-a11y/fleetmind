FIELDS = {
    "ifta_account": {"labels": ["IFTA ACCOUNT NO.", "IFTA Licensee Account"]},
    "quarter": {"regex": r"(20\d{2}\s*Q[1-4])"},
    "filing_date": {"labels": ["DATE"]},
    "total_miles": {"labels": ["Total miles", "TOTAL MILES"]},
    "total_gallons": {"labels": ["Total gallons", "TOTAL GALLONS"]},
    "total_tax_due": {"labels": ["Total tax", "tax due"]},
    "balance_due": {"labels": ["BALANCE DUE"]},
    "average_fleet_mpg": {"labels": ["Average Fleet Fuel Mileage", "MPG"]},
}

REQUIRED = ["quarter", "filing_date"]
