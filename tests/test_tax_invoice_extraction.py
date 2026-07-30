from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image
from jsonschema import Draft202012Validator, FormatChecker
from reportlab.pdfgen import canvas

from document_generator.service import RmntcDocumentGenerator
from extraction.cli import main as extraction_main
from extraction.models import RawTaxInvoiceData
from extraction.normalizer import (
    normalize_business_registration_number,
    normalize_korean_date,
    normalize_krw,
    normalize_tax_invoice,
)
from extraction.service import (
    ExtractionError,
    ManualJsonTaxInvoiceExtractor,
    TaxInvoiceExtractionService,
    inspect_document,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/tax_invoice"
SCHEMA = ROOT / "configs/invoice.schema.json"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict, name: str = "raw.json") -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def image_input(tmp_path) -> Path:
    path = tmp_path / "tax_invoice.png"
    Image.new("RGB", (1200, 1700), "white").save(path)
    return path


@pytest.fixture()
def pdf_input(tmp_path) -> Path:
    path = tmp_path / "tax_invoice.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(595.2756, 841.8898))
    pdf.drawString(72, 790, "Local tax invoice inspection fixture")
    pdf.showPage()
    pdf.save()
    return path


def _run(
    tmp_path: Path,
    source: Path,
    payload: dict,
):
    manual = _write_payload(tmp_path, payload)
    return TaxInvoiceExtractionService(
        ManualJsonTaxInvoiceExtractor(manual),
        schema_path=SCHEMA,
    ).run(
        source,
        tmp_path / "raw_tax_invoice.json",
        tmp_path / "invoice_draft.json",
        tmp_path / "review_report.md",
    )


def test_normalization_rules_preserve_korean_text_and_do_not_reuse_specification():
    raw = RawTaxInvoiceData.from_dict(_fixture("clean_single_item.json"))
    normalized = normalize_tax_invoice(raw)
    item = normalized.draft["document"]["items"][0]

    assert normalize_business_registration_number("123 45-67890") == "123-45-67890"
    assert normalize_korean_date("2026년 7월 29일") == "2026-07-29"
    assert normalize_krw(" ₩ 1,500,000 원 ") == 1500000
    assert normalized.draft["document"]["seller"]["name"] == "알엠엔티씨 주식회사"
    assert item["description"] == "업무 프로세스 분석"
    assert item["unit"] == "식"

    missing_unit = deepcopy(_fixture("clean_single_item.json"))
    missing_unit["items"][0]["unit"]["value"] = " "
    missing_raw = RawTaxInvoiceData.from_dict(missing_unit)
    missing_item = normalize_tax_invoice(missing_raw).draft["document"]["items"][0]
    assert "unit" not in missing_item
    assert missing_item["description"] == "업무 프로세스 분석"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (
        ("2026-05-18", "2026-05-18"),
        ("2026-05–18", "2026-05-18"),
        ("2026.05.18", "2026-05-18"),
        ("2026/05/18", "2026-05-18"),
        ("2026년 5월 18일", "2026-05-18"),
        ("2026년 05월 18일", "2026-05-18"),
        ("05/18/2026", "2026-05-18"),
    ),
)
def test_supported_invoice_date_formats_normalize_to_iso(raw_value, expected):
    assert normalize_korean_date(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    ("2026-02-30", "18/05/2026", "not-a-date"),
)
def test_invalid_or_ambiguous_dates_create_review_warning_without_crashing(
    tmp_path,
    image_input,
    raw_value,
):
    payload = deepcopy(_fixture("clean_single_item.json"))
    payload["issue_date"]["value"] = raw_value

    report = _run(tmp_path, image_input, payload)
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))
    review = report.review_output.read_text(encoding="utf-8")

    assert "issue_date" not in draft["document"]["dates"]
    assert any(
        issue.category == "invalid_date"
        and issue.field == "issue_date"
        and issue.severity == "warning"
        and issue.actual == raw_value
        for issue in report.validation.issues
    )
    assert "issue_date" in report.validation.manual_confirmation_fields
    assert repr(raw_value) in review
    assert not report.validation.schema_conformant
    assert not report.validation.safe_to_approve


def test_clean_single_item_generates_schema_conformant_reviewable_draft(
    tmp_path, image_input
):
    before = hashlib.sha256(image_input.read_bytes()).hexdigest()
    report = _run(
        tmp_path,
        image_input,
        _fixture("clean_single_item.json"),
    )
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))
    raw = json.loads(report.raw_output.read_text(encoding="utf-8"))

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(draft)
    )
    assert errors == []
    assert report.validation.schema_conformant
    assert report.validation.safe_to_approve
    assert draft["document"]["dates"]["issue_date"] == "2026-07-29"
    assert draft["document"]["seller"]["business_registration_number"] == (
        "123-45-67890"
    )
    assert draft["document"]["items"][0]["total"] == 1650000
    assert raw["supplier"]["company_name"]["value"] == "알엠엔티씨 주식회사"
    assert raw["source_type"] == "png"
    assert hashlib.sha256(image_input.read_bytes()).hexdigest() == before
    review = report.review_output.read_text(encoding="utf-8")
    assert "Human review completed: **no**" in review
    assert "document generation" in review


def test_multi_item_pdf_input_and_receipt_claim_preservation(tmp_path, pdf_input):
    report = _run(tmp_path, pdf_input, _fixture("multi_item.json"))
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))
    raw = json.loads(report.raw_output.read_text(encoding="utf-8"))

    assert report.inspection.source_type == "pdf"
    assert report.inspection.page_count == 1
    assert len(draft["document"]["items"]) == 2
    assert draft["document"]["totals"] == {
        "supply_amount": 2000000,
        "vat": 200000,
        "total": 2200000,
    }
    assert raw["receipt_claim_classification"]["value"] == "청구"
    assert "receipt_claim_classification" in (
        report.validation.manual_confirmation_fields
    )


def test_missing_quantity_is_reported_and_not_silently_inferred(
    tmp_path, image_input
):
    payload = deepcopy(_fixture("clean_single_item.json"))
    payload["items"][0]["quantity"]["value"] = " "
    report = _run(tmp_path, image_input, payload)
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))

    assert "quantity" not in draft["document"]["items"][0]
    assert "items[0].quantity" in report.validation.missing_required_fields
    assert not report.validation.schema_conformant
    assert not report.validation.safe_to_approve


def test_malformed_business_number_is_flagged(tmp_path, image_input):
    payload = deepcopy(_fixture("clean_single_item.json"))
    payload["supplier"]["business_registration_number"]["value"] = "12-34"
    report = _run(tmp_path, image_input, payload)

    assert any(
        issue.category == "format"
        and issue.field == "supplier.business_registration_number"
        for issue in report.validation.issues
    )
    assert not report.validation.safe_to_approve


def test_supply_vat_and_total_mismatches_are_all_flagged(tmp_path, image_input):
    payload = deepcopy(_fixture("clean_single_item.json"))
    payload["items"][0]["supply_amount"]["value"] = "1,400,000"
    payload["items"][0]["tax_amount"]["value"] = "140,000"
    payload["totals"]["supply_amount"]["value"] = "1,500,000"
    payload["totals"]["vat"]["value"] = "150,000"
    payload["totals"]["grand_total"]["value"] = "1,700,000"
    report = _run(tmp_path, image_input, payload)

    assert set(report.validation.arithmetic_mismatches) == {
        "items[0].supply_amount",
        "totals.grand_total",
        "totals.supply_amount",
        "totals.vat",
    }
    assert not report.validation.safe_to_approve


def test_invalid_optional_krw_token_is_reviewed_without_crashing(
    tmp_path, image_input
):
    payload = deepcopy(_fixture("clean_single_item.json"))
    payload["items"][0]["unit_price"]["value"] = "현금"

    report = _run(tmp_path, image_input, payload)
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))
    review = report.review_output.read_text(encoding="utf-8")

    assert "unit_price" not in draft["document"]["items"][0]
    assert any(
        issue.category == "invalid_numeric"
        and issue.field == "items[0].unit_price"
        and issue.severity == "warning"
        and issue.actual == "현금"
        for issue in report.validation.issues
    )
    assert "Unparseable KRW token '현금'" in review
    assert "normalized to null" in review


def test_low_confidence_field_is_reported(tmp_path, image_input):
    payload = deepcopy(_fixture("clean_single_item.json"))
    payload["buyer"]["company_name"]["confidence"] = 0.42
    report = _run(tmp_path, image_input, payload)

    assert report.validation.low_confidence_fields == ("buyer.company_name",)
    assert "buyer.company_name" in report.validation.manual_confirmation_fields
    assert not report.validation.safe_to_approve


def test_document_inspection_rejects_multi_page_pdf(tmp_path):
    path = tmp_path / "two-pages.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 700, "page one")
    pdf.showPage()
    pdf.drawString(72, 700, "page two")
    pdf.showPage()
    pdf.save()

    with pytest.raises(ExtractionError, match="exactly one page; found 2"):
        inspect_document(path)


def test_cli_does_not_trigger_document_generation(
    tmp_path, image_input, monkeypatch
):
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("document generation must not run")

    monkeypatch.setattr(RmntcDocumentGenerator, "generate", forbidden)
    manual = _write_payload(tmp_path, _fixture("clean_single_item.json"))
    code = extraction_main(
        [
            str(image_input),
            "--provider",
            "mock",
            "--mock-json",
            str(manual),
            "--raw-output",
            str(tmp_path / "raw.json"),
            "--draft-output",
            str(tmp_path / "draft.json"),
            "--review-output",
            str(tmp_path / "review.md"),
        ]
    )

    assert code == 0
    assert not called


def test_cli_requires_explicit_manual_provider_when_no_ocr_is_configured(
    tmp_path, image_input
):
    code = extraction_main(
        [
            str(image_input),
            "--raw-output",
            str(tmp_path / "raw.json"),
            "--draft-output",
            str(tmp_path / "draft.json"),
        ]
    )
    assert code == 2
    assert not (tmp_path / "raw.json").exists()
