"""Thin web transport adapter over the existing extraction APIs."""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image

from business import PricingConfig
from extraction.models import RawTaxInvoiceData
from extraction.providers import (
    DEFAULT_PROVIDER_REGISTRY,
    AppleVisionProvider,
    AppleVisionUnavailableError,
    OCRResult,
)
from extraction.service import TaxInvoiceExtractionService
from pipeline.mapper import OCRInvoiceMapper

ROOT = Path(__file__).resolve().parents[2]

RMNTC_SELLER_DEFAULTS = {
    "name": "로맨틱어스",
    "business_registration_number": "102-21-34572",
    "representative": "정성우",
    "address": "경상남도 창원시 성산구 외동반림로126번길 57, 1층(중앙동)",
    "business_type": "제조업",
    "business_item": "날붙이 제조업",
    "contact": {
        "email": "bigthumbdesigner@gmail.com",
        "phone": "",
    },
}


def apply_rmntc_seller_defaults(draft: dict) -> None:
    """Set application-owned supplier data when a new Review session is created."""
    document = draft.get("document")
    if not isinstance(document, dict):
        raise ValueError("Extracted draft is missing document data.")
    document["seller"] = {
        **RMNTC_SELLER_DEFAULTS,
        "contact": dict(RMNTC_SELLER_DEFAULTS["contact"]),
    }

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
        self._vision_fallback = (
            AppleVisionProvider() if provider_name == "paddle" else None
        )

    def extract(self, input_path: str | Path) -> RawTaxInvoiceData:
        source = Path(input_path)
        result: OCRResult = self.provider.extract(source)
        mapped = result.tax_invoice_data or OCRInvoiceMapper().map(result)
        return self._recover_low_resolution_buyer_text(source, mapped)

    def _recover_low_resolution_buyer_text(
        self, source: Path, mapped: RawTaxInvoiceData
    ) -> RawTaxInvoiceData:
        """Use native text evidence for uncertain buyer text in tiny scans."""
        if self._vision_fallback is None or not _is_low_resolution_image(source):
            return mapped
        uncertain = any(
            field.value is None
            or field.confidence is None
            or field.confidence < 0.9
            for field in (mapped.buyer.company_name, mapped.buyer.address)
        )
        if not uncertain:
            return mapped
        try:
            vision = OCRInvoiceMapper().map(self._vision_fallback.extract(source))
        except (AppleVisionUnavailableError, RuntimeError, ValueError):
            return mapped

        raw = mapped.to_dict()
        for name in ("company_name", "address"):
            primary = getattr(mapped.buyer, name)
            candidate = getattr(vision.buyer, name)
            if (
                candidate.value
                and (
                    primary.value is None
                    or primary.confidence is None
                    or primary.confidence < 0.9
                )
            ):
                raw["buyer"][name] = candidate.to_dict()
        return RawTaxInvoiceData.from_dict(raw, provider=mapped.provider)


def _is_low_resolution_image(source: Path) -> bool:
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        return False
    try:
        with Image.open(source) as image:
            return min(image.size) < 650
    except OSError:
        return False


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


def extract_payload(
    extractor: WebExtractor,
    source: Path,
    directory: Path,
    original_name: str,
) -> dict:
    report = TaxInvoiceExtractionService(extractor).run(
        source,
        directory / "raw_tax_invoice.json",
        directory / "invoice_draft.json",
        directory / "review_report.md",
    )
    raw = json.loads(report.raw_output.read_text(encoding="utf-8"))
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))
    apply_rmntc_seller_defaults(draft)
    confidences = {
        path: confidence
        for path, confidence in confidence_map(raw).items()
        if not path.startswith("document.seller.")
    }
    payload = {
        "sessionId": directory.name,
        "sourceName": original_name,
        "sourceType": report.inspection.source_type,
        "draft": draft,
        "confidences": confidences,
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
    return payload


def worker(provider: str) -> int:
    protocol_output = sys.stdout
    with redirect_stdout(sys.stderr):
        extractor = WebExtractor(provider)
    for line in sys.stdin:
        try:
            job = json.loads(line)
            with redirect_stdout(sys.stderr):
                payload = extract_payload(
                    extractor,
                    Path(job["source"]).resolve(),
                    Path(job["directory"]).resolve(),
                    str(job["original_name"]),
                )
            response = {"ok": True, "payload": payload}
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        protocol_output.write(json.dumps(response, ensure_ascii=False) + "\n")
        protocol_output.flush()
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        return worker(sys.argv[2])
    source = Path(sys.argv[1]).resolve()
    provider = sys.argv[2]
    directory = Path(sys.argv[3]).resolve()
    original_name = sys.argv[4]
    payload = extract_payload(
        WebExtractor(provider), source, directory, original_name
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
