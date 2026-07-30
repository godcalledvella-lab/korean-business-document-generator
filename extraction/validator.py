"""Validation and review reporting for normalized tax-invoice drafts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .models import RawTaxInvoiceData
from .normalizer import (
    NormalizationError,
    NormalizationResult,
    normalize_korean_date,
    normalize_krw,
    normalize_quantity,
)


@dataclass(frozen=True)
class ValidationIssue:
    category: str
    field: str
    message: str
    severity: str = "error"
    expected: Any = None
    actual: Any = None


@dataclass(frozen=True)
class ExtractionValidationReport:
    issues: tuple[ValidationIssue, ...]
    missing_required_fields: tuple[str, ...]
    low_confidence_fields: tuple[str, ...]
    arithmetic_mismatches: tuple[str, ...]
    manual_confirmation_fields: tuple[str, ...]
    schema_conformant: bool
    safe_to_approve: bool


REQUIRED_RAW_FIELDS = (
    "issue_date",
    "approval_number",
    "supplier.business_registration_number",
    "supplier.company_name",
    "supplier.representative",
    "supplier.address",
    "supplier.business_type",
    "supplier.business_category",
    "buyer.business_registration_number",
    "buyer.company_name",
    "buyer.representative",
    "buyer.address",
    "buyer.business_type",
    "buyer.business_category",
    "totals.supply_amount",
    "totals.vat",
    "totals.grand_total",
)


def _raw_value(raw: RawTaxInvoiceData, path: str) -> Any:
    current: Any = raw
    for part in path.split("."):
        current = getattr(current, part)
    return current.value


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def validate_tax_invoice(
    raw: RawTaxInvoiceData,
    normalized: NormalizationResult,
    schema_path: str | Path,
    *,
    low_confidence_threshold: float = 0.80,
) -> ExtractionValidationReport:
    issues: list[ValidationIssue] = []
    missing: list[str] = []
    arithmetic: list[str] = []
    manual: list[str] = []

    if not _blank(raw.issue_date.value):
        try:
            normalize_korean_date(raw.issue_date.value)
        except NormalizationError as error:
            manual.append("issue_date")
            issues.append(
                ValidationIssue(
                    "invalid_date",
                    "issue_date",
                    f"Unparseable or ambiguous date token "
                    f"{raw.issue_date.value!r}; no date was inferred. {error}",
                    severity="warning",
                    actual=raw.issue_date.value,
                )
            )

    monetary_fields = [
        ("totals.supply_amount", raw.totals.supply_amount.value, True),
        ("totals.vat", raw.totals.vat.value, True),
        ("totals.grand_total", raw.totals.grand_total.value, True),
    ]
    for index, item in enumerate(raw.items):
        monetary_fields.extend(
            (
                (f"items[{index}].unit_price", item.unit_price.value, False),
                (f"items[{index}].supply_amount", item.supply_amount.value, False),
                (f"items[{index}].tax_amount", item.tax_amount.value, False),
            )
        )
    for path, value, required_total in monetary_fields:
        if not _blank(value) and normalize_krw(value) is None:
            manual.append(path)
            issues.append(
                ValidationIssue(
                    "invalid_numeric",
                    path,
                    f"Unparseable KRW token {value!r}; no amount was inferred.",
                    severity="error" if required_total else "warning",
                    actual=value,
                )
            )

    for path in REQUIRED_RAW_FIELDS:
        if _blank(_raw_value(raw, path)):
            missing.append(path)
            issues.append(
                ValidationIssue(
                    "missing_required",
                    path,
                    "Required tax-invoice field was not extracted.",
                )
            )

    for index, item in enumerate(raw.items):
        for name in ("item_name", "quantity", "unit_price", "supply_amount", "tax_amount"):
            if _blank(getattr(item, name).value):
                path = f"items[{index}].{name}"
                missing.append(path)
                issues.append(
                    ValidationIssue(
                        "missing_required",
                        path,
                        "Required canonical item field is missing.",
                    )
                )
        if _blank(item.unit.value):
            path = f"items[{index}].unit"
            missing.append(path)
            manual.append(path)
            issues.append(
                ValidationIssue(
                    "missing_required",
                    path,
                    "Canonical unit is missing; specification was not reused as unit.",
                )
            )
        quantity = normalize_quantity(item.quantity.value)
        unit_price = normalize_krw(item.unit_price.value)
        supply = normalize_krw(item.supply_amount.value)
        if quantity is not None and unit_price is not None and supply is not None:
            expected = _decimal(quantity) * unit_price
            if expected != supply:
                path = f"items[{index}].supply_amount"
                arithmetic.append(path)
                issues.append(
                    ValidationIssue(
                        "arithmetic_mismatch",
                        path,
                        "Item supply amount does not equal quantity multiplied by unit price.",
                        expected=int(expected) if expected == int(expected) else str(expected),
                        actual=supply,
                    )
                )

    item_supplies = [
        normalize_krw(item.supply_amount.value) for item in raw.items
    ]
    total_supply = normalize_krw(raw.totals.supply_amount.value)
    if item_supplies and all(value is not None for value in item_supplies):
        expected_supply = sum(value for value in item_supplies if value is not None)
        if total_supply is not None and expected_supply != total_supply:
            arithmetic.append("totals.supply_amount")
            issues.append(
                ValidationIssue(
                    "arithmetic_mismatch",
                    "totals.supply_amount",
                    "Total supply amount does not equal the item supply sum.",
                    expected=expected_supply,
                    actual=total_supply,
                )
            )

    item_taxes = [normalize_krw(item.tax_amount.value) for item in raw.items]
    total_vat = normalize_krw(raw.totals.vat.value)
    if item_taxes and all(value is not None for value in item_taxes):
        expected_vat = sum(value for value in item_taxes if value is not None)
        if total_vat is not None and expected_vat != total_vat:
            arithmetic.append("totals.vat")
            issues.append(
                ValidationIssue(
                    "arithmetic_mismatch",
                    "totals.vat",
                    "Total VAT does not equal the item tax sum.",
                    expected=expected_vat,
                    actual=total_vat,
                )
            )

    grand_total = normalize_krw(raw.totals.grand_total.value)
    if total_supply is not None and total_vat is not None and grand_total is not None:
        expected_grand = total_supply + total_vat
        if expected_grand != grand_total:
            arithmetic.append("totals.grand_total")
            issues.append(
                ValidationIssue(
                    "arithmetic_mismatch",
                    "totals.grand_total",
                    "Grand total does not equal supply amount plus VAT.",
                    expected=expected_grand,
                    actual=grand_total,
                )
            )

    for side in ("supplier", "buyer"):
        path = f"{side}.business_registration_number"
        value = _raw_value(raw, path)
        digits = re.sub(r"\D", "", str(value or ""))
        if value is not None and len(digits) != 10:
            issues.append(
                ValidationIssue(
                    "format",
                    path,
                    "Korean business registration number must contain 10 digits.",
                )
            )

    low_confidence = sorted(
        path
        for path, confidence in normalized.field_confidences.items()
        if confidence < low_confidence_threshold
    )
    for path in low_confidence:
        issues.append(
            ValidationIssue(
                "low_confidence",
                path,
                f"Extraction confidence is below {low_confidence_threshold:.0%}.",
                severity="warning",
                actual=normalized.field_confidences[path],
            )
        )
        manual.append(path)

    if not _blank(raw.receipt_claim_classification.value):
        manual.append("receipt_claim_classification")
        issues.append(
            ValidationIssue(
                "manual_confirmation",
                "receipt_claim_classification",
                "Receipt/claim classification is preserved in raw output but has no canonical schema field.",
                severity="warning",
            )
        )

    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        validator.iter_errors(normalized.draft),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    for error in schema_errors:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        issues.append(
            ValidationIssue(
                "canonical_schema",
                path,
                error.message,
            )
        )

    schema_conformant = not schema_errors
    has_errors = any(issue.severity == "error" for issue in issues)
    return ExtractionValidationReport(
        issues=tuple(issues),
        missing_required_fields=tuple(sorted(set(missing))),
        low_confidence_fields=tuple(low_confidence),
        arithmetic_mismatches=tuple(sorted(set(arithmetic))),
        manual_confirmation_fields=tuple(sorted(set(manual))),
        schema_conformant=schema_conformant,
        safe_to_approve=schema_conformant and not has_errors and not low_confidence,
    )
