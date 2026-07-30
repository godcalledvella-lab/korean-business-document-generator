"""Build comparison-quotation data from canonical invoice values."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any, Mapping

from .pricing import PricingConfig, apply_markup


_TOTAL_FIELDS = ("supply_amount", "vat", "total")


def build_comparison_view_model(
    invoice: Mapping[str, Any],
    pricing: PricingConfig,
) -> dict[str, Any]:
    """Create an independent base-versus-marked-up comparison view model."""

    source_document = invoice["document"]
    comparison_items: list[dict[str, Any]] = []
    for source_item in source_document["items"]:
        base_prices = {
            field: deepcopy(source_item[field])
            for field in ("unit_price", "supply_amount", "vat", "total")
        }
        unit_price = apply_markup(source_item["unit_price"], pricing)
        quantity = Decimal(str(source_item["quantity"]))
        quantum = Decimal(1).scaleb(-pricing.decimal_places)
        supply_amount = (Decimal(str(unit_price)) * quantity).quantize(
            quantum,
            rounding=pricing.rounding_mode,
        )
        if pricing.decimal_places == 0:
            supply_amount = int(supply_amount)
        vat = apply_markup(source_item["vat"], pricing)
        total = Decimal(str(supply_amount)) + Decimal(str(vat))
        if pricing.decimal_places == 0:
            total = int(total)
        comparison_prices = {
            "unit_price": unit_price,
            "supply_amount": supply_amount,
            "vat": vat,
            "total": total,
        }
        comparison_items.append(
            {
                "line_number": deepcopy(source_item.get("line_number")),
                "description": deepcopy(source_item["description"]),
                "quantity": deepcopy(source_item["quantity"]),
                "unit": deepcopy(source_item["unit"]),
                "base": base_prices,
                "comparison": comparison_prices,
                "remarks": deepcopy(source_item.get("remarks")),
            }
        )

    base_totals = {
        field: deepcopy(source_document["totals"][field]) for field in _TOTAL_FIELDS
    }
    comparison_totals = {
        field: sum(
            Decimal(str(item["comparison"][field]))
            for item in comparison_items
        )
        for field in _TOTAL_FIELDS
    }
    if pricing.decimal_places == 0:
        comparison_totals = {
            field: int(value) for field, value in comparison_totals.items()
        }

    return {
        "view_model_version": "1.0",
        "view_model_type": "comparison",
        "source_document_type": invoice["document_type"],
        "source_invoice_number": source_document["invoice_number"],
        "document": {
            "invoice_number": deepcopy(source_document["invoice_number"]),
            "dates": deepcopy(source_document["dates"]),
            "seller": deepcopy(source_document["seller"]),
            "buyer": deepcopy(source_document["buyer"]),
            "currency": deepcopy(source_document["currency"]),
            "markup": {
                "rate": pricing.comparison_markup_rate,
                "percentage": pricing.comparison_markup_rate * Decimal(100),
            },
            "items": comparison_items,
            "totals": {
                "base": base_totals,
                "comparison": comparison_totals,
            },
            "remarks": deepcopy(source_document.get("remarks")),
        },
    }
