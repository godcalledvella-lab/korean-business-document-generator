from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from business import BusinessRuleEngine, PricingConfig, PricingConfigurationError


ROOT = Path(__file__).resolve().parents[1]
MARKUP_MODULE = ROOT / "web/lib/comparisonMarkup.ts"


def _engine() -> BusinessRuleEngine:
    return BusinessRuleEngine(
        ROOT / "configs/invoice.schema.json",
        ROOT / "configs/business_rules.json",
    )


def _current_invoice() -> dict:
    invoice = json.loads((ROOT / "input/invoice.json").read_text(encoding="utf-8"))
    prices = (200_000, 150_000, 70_000)
    quantities = (6, 1, 1)
    vats = (120_000, 15_000, 7_000)
    for item, price, quantity, vat in zip(
        invoice["document"]["items"], prices, quantities, vats
    ):
        supply = price * quantity
        item.update(
            {
                "quantity": quantity,
                "unit_price": price,
                "supply_amount": supply,
                "vat": vat,
                "total": supply + vat,
            }
        )
    invoice["document"]["totals"] = {
        "supply_amount": 1_420_000,
        "vat": 142_000,
        "total": 1_562_000,
    }
    return invoice


def _comparison(percentage: int | float | str | None = None) -> dict:
    invoice = _current_invoice()
    if percentage is not None:
        invoice["extensions"] = {
            "rmntc.comparison_markup_percentage": percentage,
        }
    return _engine().create_comparison(invoice).data["document"]


def _run_markup_javascript(expression: str):
    script = (
        f"import * as markup from {json.dumps(MARKUP_MODULE.as_uri())};"
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    completed = subprocess.run(
        [
            "node",
            "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_default_and_quick_select_markup_values():
    assert _run_markup_javascript(
        "({defaultValue:markup.DEFAULT_COMPARISON_MARKUP_PERCENTAGE,"
        "quick:[...markup.QUICK_COMPARISON_MARKUPS]})"
    ) == {"defaultValue": 8, "quick": [5, 6, 7, 8, 9, 10]}
    comparison = _comparison()
    assert comparison["markup"]["percentage"] == Decimal("8.00")
    assert [
        item["comparison"]["unit_price"] for item in comparison["items"]
    ] == [216_000, 162_000, 75_600]
    assert comparison["totals"]["comparison"]["supply_amount"] == 1_533_600


def test_review_uses_live_slider_exact_input_and_session_persistence():
    source = (
        ROOT / "web/components/ReviewWorkspace.tsx"
    ).read_text(encoding="utf-8")
    assert 'type="range"' in source
    assert 'min="0"' in source
    assert 'max="100"' in source
    assert 'step="0.1"' in source
    assert 'inputMode="decimal"' in source
    assert "setMarkupInput(event.target.value)" in source
    assert "comparisonSupplyAmount(" in source
    assert 'method: "PATCH"' in source
    assert "comparisonMarkupPercentage: markupValidation.value" in source


@pytest.mark.parametrize(
    ("percentage", "prices", "total"),
    (
        (0, [200_000, 150_000, 70_000], 1_420_000),
        (7.5, [215_000, 161_250, 75_250], 1_526_500),
        (100, [400_000, 300_000, 140_000], 2_840_000),
    ),
)
def test_custom_markup_reconciles_item_prices_amounts_and_total(
    percentage, prices, total
):
    comparison = _comparison(percentage)
    items = comparison["items"]
    assert [item["comparison"]["unit_price"] for item in items] == prices
    for item in items:
        assert item["comparison"]["supply_amount"] == (
            item["comparison"]["unit_price"] * item["quantity"]
        )
        assert isinstance(item["comparison"]["unit_price"], int)
        assert isinstance(item["comparison"]["supply_amount"], int)
    assert comparison["totals"]["comparison"]["supply_amount"] == total
    assert total == sum(
        item["comparison"]["supply_amount"] for item in items
    )


@pytest.mark.parametrize("percentage", (-1, 100.01, "NaN", None))
def test_invalid_markup_is_rejected(percentage):
    config = PricingConfig.from_file(ROOT / "configs/business_rules.json")
    with pytest.raises(PricingConfigurationError):
        config.with_markup_percentage(percentage)


def test_review_markup_validation_rejects_out_of_range_and_non_numeric_values():
    results = _run_markup_javascript(
        "[-1,101,'NaN',null,'',0,7.5,100].map("
        "value=>markup.validateMarkupPercentage(value))"
    )
    assert all("error" in result for result in results[:5])
    assert [result["value"] for result in results[5:]] == [0, 7.5, 100]


def test_markup_metadata_does_not_change_statement_quotation_or_vat():
    invoice = _current_invoice()
    reviewed = deepcopy(invoice)
    reviewed["extensions"] = {"rmntc.comparison_markup_percentage": 7.5}
    engine = _engine()

    assert (
        engine.create_statement(reviewed).data["document"]
        == engine.create_statement(invoice).data["document"]
    )
    assert (
        engine.create_quotation(reviewed).data["document"]
        == engine.create_quotation(invoice).data["document"]
    )
    comparison = engine.create_comparison(reviewed).data["document"]
    assert comparison["totals"]["base"]["vat"] == 142_000
