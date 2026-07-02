"""Compliance agent unit tests."""

from app.agents._compliance import rollup_compliance_status
from app.schemas.common import ComplianceCategoryDetail
from app.schemas.trucks import ComplianceCategories


def test_rollup_red_wins():
    assert rollup_compliance_status(["green", "red", "yellow"]) == "red"


def test_rollup_yellow():
    assert rollup_compliance_status(["green", "yellow"]) == "yellow"


def test_rollup_green():
    assert rollup_compliance_status(["green", "green"]) == "green"


def test_rollup_incomplete():
    assert rollup_compliance_status(["grey", "grey"]) == "incomplete"


def test_urgent_items_from_categories():
    from app.agents._compliance import build_urgent_items

    categories = ComplianceCategories(
        insurance=ComplianceCategoryDetail(status="yellow", days_remaining=5, expiry_date="2026-07-01"),
        registration=ComplianceCategoryDetail(status="green", days_remaining=100),
        title=ComplianceCategoryDetail(status="green"),
        emission=ComplianceCategoryDetail(status="grey"),
        driver_cdl=ComplianceCategoryDetail(status="green", days_remaining=200),
        medical_cert=ComplianceCategoryDetail(status="grey"),
    )
    urgent = build_urgent_items(categories, window_days=7)
    assert len(urgent) == 1
    assert urgent[0].category == "insurance"
