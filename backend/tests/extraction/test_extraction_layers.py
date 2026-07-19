"""Extraction pipeline unit tests."""

import os

import pytest

from app.config import settings
from app.extraction.layer1_reader import read_document
from app.extraction.layer2_layout import build_layout
from app.extraction.classifier import classify_document, classify_for_bulk_import
from app.extraction.layer4_normalizer import normalize_fields
from app.extraction.layer5_validator import vin_check_digit_valid, validate_fields
from app.extraction.text_utils import meaningful_char_count, collapse_spaced_text

# The Sunflower dataset is gitignored (data/) and only present on machines that
# downloaded it locally per the README setup instructions. Resolve the sample
# path via the same setting the rest of the app uses (SUNFLOWER_DATASET_PATH
# env var / settings.sunflower_dataset_path), instead of a hardcoded
# machine-specific path, and skip these tests when the file isn't available.
SAMPLE_BOS_PATH = os.path.join(settings.sunflower_dataset_path, "document_001.pdf")
_sample_missing_reason = (
    f"Sunflower sample dataset not found at '{SAMPLE_BOS_PATH}'. "
    "See README setup instructions to download it, or set SUNFLOWER_DATASET_PATH."
)


def test_meaningful_char_count_text_pdf():
    text = "Sunflower Freight Lines LLC " * 20
    assert meaningful_char_count(text) > 100


def test_collapse_spaced_text():
    assert "TRUCK" in collapse_spaced_text("T R U C K")


def test_vin_check_digit_known():
    # Valid test VIN from standard examples.
    assert vin_check_digit_valid("1HGCM82633A004352")


@pytest.mark.skipif(not os.path.exists(SAMPLE_BOS_PATH), reason=_sample_missing_reason)
def test_classify_bos_from_sample_path():
    reading = read_document(SAMPLE_BOS_PATH)
    layout = build_layout(reading)
    dtype = classify_document(reading, layout)
    assert dtype == "bill_of_sale_purchase"


@pytest.mark.skipif(not os.path.exists(SAMPLE_BOS_PATH), reason=_sample_missing_reason)
def test_bulk_wave_bos_purchase():
    assert classify_for_bulk_import(SAMPLE_BOS_PATH) == 1


def test_normalize_money():
    fields, issues = normalize_fields({"total": "$1,234.56"})
    assert fields["total"] is not None
    assert not issues or issues[0].field_name != "total"
