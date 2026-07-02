"""Build human-readable recent activity descriptions."""

from __future__ import annotations

from decimal import Decimal

from app.models.document import Document


def build_activity_description(doc: Document) -> str:
    dtype = (doc.document_type or "document").replace("_", " ").title()
    if doc.document_type == "service_invoice":
        category = "Maintenance"
        return f"Service Invoice — {category}"
    if doc.document_type == "insurance_card":
        return "Insurance Card — Coverage"
    if doc.document_type == "irp_cab_card":
        return "Registration — IRP Cab Card"
    if doc.document_type == "cdl":
        return "CDL — Driver License"
    if doc.document_type in ("bill_of_sale_purchase", "bill_of_sale_sale"):
        return f"Bill of Sale — {dtype}"
    return dtype
