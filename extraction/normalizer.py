"""Explicit normalization from raw tax-invoice fields to canonical draft data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import ExtractedField, RawParty, RawTaxInvoiceData


class NormalizationError(ValueError):
    """Raised when a present raw value cannot be normalized safely."""


@dataclass(frozen=True)
class NormalizationResult:
    draft: dict[str, Any]
    field_confidences: dict[str, float]
    normalization_notes: tuple[str, ...]


def normalize_blank(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def normalize_business_registration_number(value: Any) -> str | None:
    value = normalize_blank(value)
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return digits or None


def normalize_korean_date(value: Any) -> str | None:
    value = normalize_blank(value)
    if value is None:
        return None
    text = str(value).strip()
    # OCR commonly substitutes typographic dash glyphs for an ASCII hyphen.
    # This is punctuation normalization only; no date component is inferred.
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)

    # Preserve an already valid canonical date exactly as supplied.
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            date.fromisoformat(text)
            return text
    except ValueError as error:
        raise NormalizationError(f"Invalid calendar date: {value!r}") from error

    match = re.fullmatch(
        r"(\d{4})\s*(?:년|[./-])\s*(\d{1,2})\s*(?:월|[./-])\s*(\d{1,2})\s*일?",
        text,
    )
    if not match:
        # The only supported month-first form is the explicit US-style
        # MM/DD/YYYY representation. Other day/month orders remain ambiguous.
        us_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if us_match:
            month, day_value, year = us_match.groups()
            match_parts = (year, month, day_value)
        else:
            match_parts = None
    else:
        match_parts = match.groups()
    if not match:
        match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text)
        if match:
            match_parts = match.groups()
    if match_parts is None:
        raise NormalizationError(f"Unsupported Korean date value: {value!r}")
    try:
        return date(*(int(part) for part in match_parts)).isoformat()
    except ValueError as error:
        raise NormalizationError(f"Invalid calendar date: {value!r}") from error


def normalize_krw(value: Any) -> int | None:
    """Normalize a whole-won value, returning null for a non-monetary token."""
    value = normalize_blank(value)
    if value is None:
        return None
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[\s,₩￦원]", "", text.strip("()"))
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        return None
    return int(amount)


def normalize_quantity(value: Any) -> int | float | None:
    value = normalize_blank(value)
    if value is None:
        return None
    cleaned = re.sub(r"[\s,]", "", str(value))
    try:
        quantity = Decimal(cleaned)
    except InvalidOperation as error:
        raise NormalizationError(f"Invalid quantity: {value!r}") from error
    if not quantity.is_finite():
        raise NormalizationError(f"Quantity must be finite: {value!r}")
    return int(quantity) if quantity == quantity.to_integral_value() else float(quantity)


def _text(field: ExtractedField) -> str | None:
    value = normalize_blank(field.value)
    return str(value) if value is not None else None


def _party(party: RawParty) -> dict[str, Any]:
    contact = _without_none(
        {
            "email": _text(party.email),
            "phone": _text(party.phone),
        }
    )
    return _without_none(
        {
            "name": _text(party.company_name),
            "business_registration_number": (
                normalize_business_registration_number(
                    party.business_registration_number.value
                )
            ),
            "representative": _text(party.representative),
            "address": _text(party.address),
            "business_type": _text(party.business_type),
            "business_item": _text(party.business_category),
            "contact": contact or None,
        }
    )


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _confidence_map(raw: RawTaxInvoiceData) -> dict[str, float]:
    result: dict[str, float] = {}

    def add(path: str, field: ExtractedField) -> None:
        if field.confidence is not None:
            result[path] = field.confidence

    add("issue_date", raw.issue_date)
    add("approval_number", raw.approval_number)
    add("receipt_claim_classification", raw.receipt_claim_classification)
    for side, party in (("supplier", raw.supplier), ("buyer", raw.buyer)):
        for name in party.__dataclass_fields__:
            add(f"{side}.{name}", getattr(party, name))
    for index, item in enumerate(raw.items):
        for name in item.__dataclass_fields__:
            add(f"items[{index}].{name}", getattr(item, name))
    for name in raw.totals.__dataclass_fields__:
        add(f"totals.{name}", getattr(raw.totals, name))
    return result


def normalize_tax_invoice(raw: RawTaxInvoiceData) -> NormalizationResult:
    items: list[dict[str, Any]] = []
    notes: list[str] = [
        "approval_number is mapped to canonical document.invoice_number.",
        "Currency is explicitly set to KRW for the Korean tax-invoice workflow.",
        "specification is not inferred to be canonical unit.",
    ]

    def money(value: Any, path: str) -> int | None:
        normalized = normalize_krw(value)
        if normalize_blank(value) is not None and normalized is None:
            notes.append(
                f"{path}: unparseable KRW token {value!r} was normalized to null "
                "and requires manual confirmation."
            )
        return normalized

    def normalized_date(value: Any, path: str) -> str | None:
        try:
            return normalize_korean_date(value)
        except NormalizationError as error:
            notes.append(
                f"{path}: unparseable date token {value!r} was normalized to "
                f"null and requires manual confirmation ({error})."
            )
            return None

    for line_number, item in enumerate(raw.items, start=1):
        index = line_number - 1
        supply = money(item.supply_amount.value, f"items[{index}].supply_amount")
        tax = money(item.tax_amount.value, f"items[{index}].tax_amount")
        canonical = _without_none(
            {
                "line_number": line_number,
                "description": _text(item.item_name),
                "quantity": normalize_quantity(item.quantity.value),
                "unit": _text(item.unit),
                "unit_price": money(
                    item.unit_price.value, f"items[{index}].unit_price"
                ),
                "supply_amount": supply,
                "vat": tax,
                "total": (
                    supply + tax if supply is not None and tax is not None else None
                ),
                "remarks": _text(item.remark),
            }
        )
        items.append(canonical)

    document = _without_none(
        {
            "invoice_number": _text(raw.approval_number),
            "dates": _without_none(
                {
                    "issue_date": normalized_date(
                        raw.issue_date.value,
                        "issue_date",
                    )
                }
            ),
            "seller": _party(raw.supplier),
            "buyer": _party(raw.buyer),
            "currency": "KRW",
            "items": items,
            "totals": _without_none(
                {
                    "supply_amount": money(
                        raw.totals.supply_amount.value,
                        "totals.supply_amount",
                    ),
                    "vat": money(raw.totals.vat.value, "totals.vat"),
                    "total": money(
                        raw.totals.grand_total.value,
                        "totals.grand_total",
                    ),
                }
            ),
        }
    )
    return NormalizationResult(
        draft={
            "schema_version": "1.0",
            "document_type": "invoice",
            "document": document,
        },
        field_confidences=_confidence_map(raw),
        normalization_notes=tuple(notes),
    )
