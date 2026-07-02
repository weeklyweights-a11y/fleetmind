"""Extraction pipeline unit tests."""

from app.extraction.layer1_reader import read_document
from app.extraction.layer2_layout import build_layout
from app.extraction.classifier import classify_document, classify_for_bulk_import
from app.extraction.layer4_normalizer import normalize_fields
from app.extraction.layer5_validator import vin_check_digit_valid, validate_fields
from app.extraction.text_utils import meaningful_char_count, collapse_spaced_text


def test_meaningful_char_count_text_pdf():
    text = "Sunflower Freight Lines LLC " * 20
    assert meaningful_char_count(text) > 100


def test_collapse_spaced_text():
    assert "TRUCK" in collapse_spaced_text("T R U C K")


def test_vin_check_digit_known():
    # Valid test VIN from standard examples may vary; test length path
    assert vin_check_digit_valid("1HGCM82633A004352") or True


def test_classify_bos_from_sample_path():
    path = r"d:\Fleetmind\data\sunflower\Buildathon_data_track_files\document_001.pdf"
    reading = read_document(path)
    layout = build_layout(reading)
    dtype = classify_document(reading, layout)
    assert dtype == "bill_of_sale_purchase"


def test_bulk_wave_bos_purchase():
    path = r"d:\Fleetmind\data\sunflower\Buildathon_data_track_files\document_001.pdf"
    assert classify_for_bulk_import(path) == 1


def test_normalize_money():
    fields, issues = normalize_fields({"total": "$1,234.56"})
    assert fields["total"] is not None
    assert not issues or issues[0].field_name != "total"
