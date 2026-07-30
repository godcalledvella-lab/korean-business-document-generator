import json
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from business import (
    BusinessRuleEngine,
    CanonicalInvoiceError,
    PricingConfig,
    PricingConfigurationError,
    ViewModelType,
    apply_markup,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BusinessRuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = BusinessRuleEngine(
            PROJECT_ROOT / "configs" / "invoice.schema.json",
            PROJECT_ROOT / "configs" / "business_rules.json",
        )
        self.invoice = json.loads(
            (PROJECT_ROOT / "input" / "invoice.json").read_text(encoding="utf-8")
        )

    def test_creates_three_independent_view_models(self) -> None:
        original = deepcopy(self.invoice)

        models = self.engine.create_all(self.invoice)

        self.assertEqual(
            set(models),
            {
                ViewModelType.STATEMENT,
                ViewModelType.QUOTATION,
                ViewModelType.COMPARISON,
            },
        )
        self.assertEqual(self.invoice, original)

        models[ViewModelType.STATEMENT].data["document"]["buyer"]["name"] = "변경"
        self.assertNotEqual(
            models[ViewModelType.QUOTATION].data["document"]["buyer"]["name"],
            "변경",
        )
        self.assertNotEqual(
            models[ViewModelType.COMPARISON].data["document"]["buyer"]["name"],
            "변경",
        )
        self.assertEqual(self.invoice, original)

    def test_statement_preserves_canonical_document_values(self) -> None:
        statement = self.engine.create_statement(self.invoice)

        self.assertEqual(statement.type, ViewModelType.STATEMENT)
        self.assertEqual(statement.data["document"], self.invoice["document"])
        self.assertIsNot(statement.data["document"], self.invoice["document"])

    def test_quotation_is_an_independent_model(self) -> None:
        quotation = self.engine.create_quotation(self.invoice)

        self.assertEqual(quotation.type, ViewModelType.QUOTATION)
        self.assertEqual(
            quotation.data["source_invoice_number"],
            self.invoice["document"]["invoice_number"],
        )
        self.assertIsNot(quotation.data["document"], self.invoice["document"])

    def test_comparison_uses_markup_from_configuration(self) -> None:
        comparison = self.engine.create_comparison(self.invoice)
        first_item = comparison.data["document"]["items"][0]

        self.assertEqual(
            comparison.data["document"]["markup"]["rate"],
            Decimal("0.08"),
        )
        self.assertEqual(first_item["base"]["unit_price"], 1500000)
        self.assertEqual(first_item["comparison"]["unit_price"], 1620000)
        self.assertEqual(
            comparison.data["document"]["totals"]["comparison"]["total"],
            4158000,
        )

    def test_custom_markup_changes_comparison_without_code_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "business_rules.json"
            config_path.write_text(
                json.dumps(
                    {
                        "pricing": {
                            "comparison_markup_rate": "0.125",
                            "decimal_places": 0,
                            "rounding": "ROUND_HALF_UP",
                        }
                    }
                ),
                encoding="utf-8",
            )
            engine = BusinessRuleEngine(
                PROJECT_ROOT / "configs" / "invoice.schema.json",
                config_path,
            )

            comparison = engine.create_comparison(self.invoice)

            self.assertEqual(
                comparison.data["document"]["markup"]["rate"],
                Decimal("0.125"),
            )
            self.assertEqual(
                comparison.data["document"]["items"][0]["comparison"][
                    "unit_price"
                ],
                1687500,
            )

    def test_decimal_safe_rounding_is_configurable(self) -> None:
        config = PricingConfig.from_mapping(
            {
                "comparison_markup_rate": "0.08",
                "decimal_places": 0,
                "rounding": "ROUND_HALF_UP",
            }
        )

        self.assertEqual(apply_markup(12.5, config), 14)

    def test_invalid_invoice_is_rejected(self) -> None:
        invalid = deepcopy(self.invoice)
        del invalid["document"]["totals"]

        with self.assertRaisesRegex(
            CanonicalInvoiceError, "validation failed at document"
        ):
            self.engine.create_statement(invalid)

    def test_missing_markup_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            PricingConfigurationError, "comparison_markup_rate"
        ):
            PricingConfig.from_mapping(
                {
                    "decimal_places": 0,
                    "rounding": "ROUND_HALF_UP",
                }
            )


if __name__ == "__main__":
    unittest.main()
