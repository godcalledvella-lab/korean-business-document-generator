"""Web OCR adapter with conservative total reconciliation.

When OCR reads the grand total correctly but misses/mislabels invoice-wide supply
or VAT totals, complete line-item amounts are a stronger arithmetic source. This
adapter only reconciles totals when every line has supply+VAT and the resulting
line grand total agrees with the extracted grand total (or the grand total is
missing). Raw OCR evidence is left untouched so review warnings remain visible.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from decimal import Decimal

import extraction.service as extraction_service
from extraction.normalizer import NormalizationResult, normalize_tax_invoice as base_normalize


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    return Decimal(str(value))


def normalize_tax_invoice(raw) -> NormalizationResult:
    result = base_normalize(raw)
    draft = deepcopy(result.draft)
    document = draft.get("document")
    if not isinstance(document, dict):
        return result
    items = document.get("items")
    totals = document.get("totals")
    if not isinstance(items, list) or not items or not isinstance(totals, dict):
        return result

    supplies = []
    vats = []
    for item in items:
        if not isinstance(item, dict):
            return result
        supply = _number(item.get("supply_amount"))
        vat = _number(item.get("vat"))
        if supply is None or vat is None:
            return result
        supplies.append(supply)
        vats.append(vat)

    line_supply = sum(supplies, Decimal(0))
    line_vat = sum(vats, Decimal(0))
    line_total = line_supply + line_vat
    extracted_total = _number(totals.get("total"))

    # Never override a conflicting extracted grand total automatically.
    if extracted_total is not None and extracted_total != line_total:
        return result

    def native(value: Decimal):
        return int(value) if value == value.to_integral_value() else float(value)

    totals["supply_amount"] = native(line_supply)
    totals["vat"] = native(line_vat)
    totals["total"] = native(line_total)
    notes = tuple(result.normalization_notes) + (
        "Invoice totals reconciled from complete line-item supply/VAT values because "
        "their grand total agrees with the extracted grand total.",
    )
    return NormalizationResult(
        draft=draft,
        field_confidences=result.field_confidences,
        normalization_notes=notes,
    )


# TaxInvoiceExtractionService imported normalize_tax_invoice directly, so patch
# the module-level reference before loading the existing web adapter.
extraction_service.normalize_tax_invoice = normalize_tax_invoice

import extract_invoice as base


if __name__ == "__main__":
    raise SystemExit(base.main())
