"""Typed provider-neutral raw extraction models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ExtractedField:
    """One raw extracted value plus optional provider confidence and source text."""

    value: Any = None
    confidence: float | None = None
    source_text: str | None = None

    @classmethod
    def from_raw(cls, raw: Any) -> "ExtractedField":
        if isinstance(raw, Mapping) and (
            "value" in raw or "confidence" in raw or "source_text" in raw
        ):
            confidence = raw.get("confidence")
            if confidence is not None:
                confidence = float(confidence)
                if not 0 <= confidence <= 1:
                    raise ValueError("Extraction confidence must be between 0 and 1.")
            return cls(
                value=raw.get("value"),
                confidence=confidence,
                source_text=raw.get("source_text"),
            )
        return cls(value=raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "source_text": self.source_text,
        }


@dataclass(frozen=True)
class RawParty:
    business_registration_number: ExtractedField = field(
        default_factory=ExtractedField
    )
    company_name: ExtractedField = field(default_factory=ExtractedField)
    representative: ExtractedField = field(default_factory=ExtractedField)
    address: ExtractedField = field(default_factory=ExtractedField)
    business_type: ExtractedField = field(default_factory=ExtractedField)
    business_category: ExtractedField = field(default_factory=ExtractedField)
    email: ExtractedField = field(default_factory=ExtractedField)
    phone: ExtractedField = field(default_factory=ExtractedField)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "RawParty":
        source = raw or {}
        return cls(
            **{
                name: ExtractedField.from_raw(source.get(name))
                for name in cls.__dataclass_fields__
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name).to_dict()
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class RawTaxInvoiceItem:
    date: ExtractedField = field(default_factory=ExtractedField)
    item_name: ExtractedField = field(default_factory=ExtractedField)
    specification: ExtractedField = field(default_factory=ExtractedField)
    unit: ExtractedField = field(default_factory=ExtractedField)
    quantity: ExtractedField = field(default_factory=ExtractedField)
    unit_price: ExtractedField = field(default_factory=ExtractedField)
    supply_amount: ExtractedField = field(default_factory=ExtractedField)
    tax_amount: ExtractedField = field(default_factory=ExtractedField)
    remark: ExtractedField = field(default_factory=ExtractedField)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RawTaxInvoiceItem":
        return cls(
            **{
                name: ExtractedField.from_raw(raw.get(name))
                for name in cls.__dataclass_fields__
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name).to_dict()
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class RawTaxInvoiceTotals:
    supply_amount: ExtractedField = field(default_factory=ExtractedField)
    vat: ExtractedField = field(default_factory=ExtractedField)
    grand_total: ExtractedField = field(default_factory=ExtractedField)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any] | None
    ) -> "RawTaxInvoiceTotals":
        source = raw or {}
        return cls(
            **{
                name: ExtractedField.from_raw(source.get(name))
                for name in cls.__dataclass_fields__
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name).to_dict()
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class RawTaxInvoiceData:
    issue_date: ExtractedField
    approval_number: ExtractedField
    supplier: RawParty
    buyer: RawParty
    items: tuple[RawTaxInvoiceItem, ...]
    totals: RawTaxInvoiceTotals
    receipt_claim_classification: ExtractedField = field(
        default_factory=ExtractedField
    )
    provider: str = "unknown"
    source_path: str | None = None
    source_type: str | None = None
    source_sha256: str | None = None

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, Any],
        *,
        provider: str = "manual-json",
    ) -> "RawTaxInvoiceData":
        items = raw.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Raw tax invoice items must be a list.")
        return cls(
            issue_date=ExtractedField.from_raw(raw.get("issue_date")),
            approval_number=ExtractedField.from_raw(raw.get("approval_number")),
            supplier=RawParty.from_dict(raw.get("supplier")),
            buyer=RawParty.from_dict(raw.get("buyer")),
            items=tuple(RawTaxInvoiceItem.from_dict(item) for item in items),
            totals=RawTaxInvoiceTotals.from_dict(raw.get("totals")),
            receipt_claim_classification=ExtractedField.from_raw(
                raw.get("receipt_claim_classification")
            ),
            provider=str(raw.get("provider") or provider),
            source_path=raw.get("source_path"),
            source_type=raw.get("source_type"),
            source_sha256=raw.get("source_sha256"),
        )

    def with_source(
        self,
        *,
        source_path: Path,
        source_type: str,
        source_sha256: str,
    ) -> "RawTaxInvoiceData":
        return RawTaxInvoiceData(
            issue_date=self.issue_date,
            approval_number=self.approval_number,
            supplier=self.supplier,
            buyer=self.buyer,
            items=self.items,
            totals=self.totals,
            receipt_claim_classification=self.receipt_claim_classification,
            provider=self.provider,
            source_path=str(source_path),
            source_type=source_type,
            source_sha256=source_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "source_sha256": self.source_sha256,
            "issue_date": self.issue_date.to_dict(),
            "approval_number": self.approval_number.to_dict(),
            "supplier": self.supplier.to_dict(),
            "buyer": self.buyer.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "totals": self.totals.to_dict(),
            "receipt_claim_classification": (
                self.receipt_claim_classification.to_dict()
            ),
        }


class TaxInvoiceExtractor(Protocol):
    """Provider-neutral OCR/extraction boundary."""

    name: str

    def extract(self, input_path: str | Path) -> RawTaxInvoiceData:
        """Extract raw fields from one inspected tax-invoice document."""
