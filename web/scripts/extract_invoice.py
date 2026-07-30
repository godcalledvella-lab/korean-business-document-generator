"""Thin web transport adapter over the existing extraction APIs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from business import PricingConfig
from extraction.models import RawTaxInvoiceData
from extraction.providers import DEFAULT_PROVIDER_REGISTRY, OCRResult
from extraction.service import TaxInvoiceExtractionService
from pipeline.mapper import OCRInvoiceMapper

ROOT = Path(__file__).resolve().parents[2]

class WebExtractor:
    def __init__(self, provider_name: str) -> None:
        self.provider = (
            DEFAULT_PROVIDER_REGISTRY.create(
                provider_name,
                fixture_path=Path(
                    os.environ.get(
                        "OCR_MOCK_JSON",
                        "tests/fixtures/tax_invoice/clean_single_item.json",
                    )
                ),
            )
            if provider_name == "mock"
            else DEFAULT_PROVIDER_REGISTRY.create(provider_name)
        )
        self.name = provider_name

    def extract(self, input_path: str | Path) -> RawTaxInvoiceData:
        result: OCRResult = self.provider.extract(Path(input_path))
        return result.tax_invoice_data or OCRInvoiceMapper().map(result)


def confidence_map(raw: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    party_names = {"supplier": "seller", "buyer": "buyer"}

    def add(path: str, field: object) -> None:
        if isinstance(field, dict) and field.get("confidence") is not None:
            values[path] = float(field["confidence"])

    add("document.dates.issue_date", raw.get("issue_date"))
    add("document.invoice_number", raw.get("approval_number"))
    for raw_name, canonical_name in party_names.items():
        party = raw.get(raw_name, {})
        aliases = {
            "company_name": "name",
            "business_registration_number": "business_registration_number",
            "representative": "representative",
            "address": "address",
            "business_type": "business_type",
            "business_category": "business_item",
            "email": "contact.email",
            "phone": "contact.phone",
        }
        for source, target in aliases.items():
            add(f"document.{canonical_name}.{target}", party.get(source))
    aliases = {
        "item_name": "description",
        "quantity": "quantity",
        "unit": "unit",
        "unit_price": "unit_price",
        "supply_amount": "supply_amount",
        "tax_amount": "vat",
        "remark": "remarks",
    }
    for index, item in enumerate(raw.get("items", [])):
        for source, target in aliases.items():
            add(f"document.items.{index}.{target}", item.get(source))
    for source, target in (
        ("supply_amount", "supply_amount"),
        ("vat", "vat"),
        ("grand_total", "total"),
    ):
        add(f"document.totals.{target}", raw.get("totals", {}).get(source))
    return values


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    provider = sys.argv[2]
    directory = Path(sys.argv[3]).resolve()
    original_name = sys.argv[4]
    report = TaxInvoiceExtractionService(WebExtractor(provider)).run(
        source,
        directory / "raw_tax_invoice.json",
        directory / "invoice_draft.json",
        directory / "review_report.md",
    )
    raw = json.loads(report.raw_output.read_text(encoding="utf-8"))
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))
    payload = {
        "sessionId": directory.name,
        "sourceName": original_name,
        "sourceType": report.inspection.source_type,
        "draft": draft,
        "confidences": confidence_map(raw),
        "validation": {
            "safeToApprove": report.validation.safe_to_approve,
            "schemaConformant": report.validation.schema_conformant,
            "missing": list(report.validation.missing_required_fields),
            "lowConfidence": list(report.validation.low_confidence_fields),
            "arithmeticMismatches": list(report.validation.arithmetic_mismatches),
        },
        "comparisonMarkupPercentage": float(
            PricingConfig.from_file(
                ROOT / "configs/business_rules.json"
            ).comparison_markup_rate
            * 100
        ),
    }
    (directory / "session.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
