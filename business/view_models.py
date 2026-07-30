"""Create independent renderer view models from canonical invoice JSON."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from .comparison import build_comparison_view_model
from .pricing import PricingConfig


class BusinessRuleError(Exception):
    """Base error for canonical-data business transformations."""


class CanonicalInvoiceError(BusinessRuleError):
    """Raised when canonical invoice input cannot be loaded or validated."""


class ViewModelType(str, Enum):
    """Supported renderer-facing document models."""

    STATEMENT = "statement"
    QUOTATION = "quotation"
    COMPARISON = "comparison"


@dataclass(frozen=True)
class ViewModel:
    """Typed, independent renderer input."""

    type: ViewModelType
    data: dict[str, Any]

    def __post_init__(self) -> None:
        declared_type = self.data.get("view_model_type")
        if declared_type != self.type.value:
            raise ValueError(
                f"View model declares type {declared_type!r}, "
                f"expected {self.type.value!r}."
            )


class BusinessRuleEngine:
    """Validate canonical invoices and produce presentation-ready data."""

    def __init__(
        self,
        invoice_schema_path: str | Path,
        business_config_path: str | Path,
    ) -> None:
        self.invoice_schema_path = Path(invoice_schema_path).resolve()
        self.pricing = PricingConfig.from_file(business_config_path)
        self._validator = self._load_validator(self.invoice_schema_path)

    def load_invoice(self, input_path: str | Path) -> dict[str, Any]:
        """Load and validate a canonical invoice without retaining caller state."""

        path = Path(input_path)
        try:
            with path.open("r", encoding="utf-8") as input_file:
                invoice = json.load(input_file, parse_float=Decimal)
        except OSError as error:
            raise CanonicalInvoiceError(
                f"Could not read canonical invoice {path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise CanonicalInvoiceError(
                f"Canonical invoice is not valid JSON: {path} "
                f"(line {error.lineno}, column {error.colno})"
            ) from error

        return self._validated_copy(invoice)

    def create_statement(self, invoice: Mapping[str, Any]) -> ViewModel:
        """Build a Statement model with canonical values unchanged."""

        canonical = self._validated_copy(invoice)
        return ViewModel(
            ViewModelType.STATEMENT,
            self._copy_document_model(canonical, ViewModelType.STATEMENT),
        )

    def create_quotation(self, invoice: Mapping[str, Any]) -> ViewModel:
        """Build an independent Quotation model with canonical prices."""

        canonical = self._validated_copy(invoice)
        return ViewModel(
            ViewModelType.QUOTATION,
            self._copy_document_model(canonical, ViewModelType.QUOTATION),
        )

    def create_comparison(self, invoice: Mapping[str, Any]) -> ViewModel:
        """Build a comparison model using configured markup and rounding."""

        canonical = self._validated_copy(invoice)
        pricing = self.comparison_pricing(canonical)
        return ViewModel(
            ViewModelType.COMPARISON,
            build_comparison_view_model(canonical, pricing),
        )

    def comparison_pricing(self, invoice: Mapping[str, Any]) -> PricingConfig:
        """Resolve reviewed markup metadata, falling back to configuration."""

        extensions = invoice.get("extensions")
        if not isinstance(extensions, Mapping):
            return self.pricing
        percentage = extensions.get("rmntc.comparison_markup_percentage")
        if percentage is None:
            return self.pricing
        return self.pricing.with_markup_percentage(percentage)

    def create_all(
        self, invoice: Mapping[str, Any]
    ) -> dict[ViewModelType, ViewModel]:
        """Build three independent models from one canonical invoice."""

        canonical = self._validated_copy(invoice)
        return {
            ViewModelType.STATEMENT: self.create_statement(canonical),
            ViewModelType.QUOTATION: self.create_quotation(canonical),
            ViewModelType.COMPARISON: self.create_comparison(canonical),
        }

    def _validated_copy(self, invoice: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(invoice, Mapping):
            raise CanonicalInvoiceError(
                "Canonical invoice must be a structured mapping."
            )
        candidate = deepcopy(dict(invoice))
        errors = sorted(
            self._validator.iter_errors(candidate),
            key=lambda error: [str(part) for part in error.path],
        )
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            raise CanonicalInvoiceError(
                f"Canonical invoice validation failed at {location}: {error.message}"
            )
        return candidate

    @staticmethod
    def _copy_document_model(
        invoice: dict[str, Any],
        model_type: ViewModelType,
    ) -> dict[str, Any]:
        document = invoice["document"]
        return {
            "view_model_version": "1.0",
            "view_model_type": model_type.value,
            "source_document_type": invoice["document_type"],
            "source_invoice_number": document["invoice_number"],
            "document": deepcopy(document),
        }

    @staticmethod
    def _load_validator(schema_path: Path) -> Draft202012Validator:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise CanonicalInvoiceError(
                f"Could not read canonical invoice schema {schema_path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise CanonicalInvoiceError(
                f"Canonical invoice schema is not valid JSON: {schema_path}"
            ) from error

        try:
            return Draft202012Validator(schema, format_checker=FormatChecker())
        except SchemaError as error:
            raise CanonicalInvoiceError(
                f"Canonical invoice schema is invalid: {schema_path}: "
                f"{error.message}"
            ) from error
