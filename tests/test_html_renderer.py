import json
import tempfile
import unittest
from pathlib import Path

from business import BusinessRuleEngine
from renderer import HtmlRenderer, InputDataError, RenderError, TemplateManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HtmlRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = BusinessRuleEngine(
            PROJECT_ROOT / "configs" / "invoice.schema.json",
            PROJECT_ROOT / "configs" / "business_rules.json",
        )
        self.invoice = self.engine.load_invoice(PROJECT_ROOT / "input" / "invoice.json")
        self.renderer = HtmlRenderer(TemplateManager(PROJECT_ROOT / "templates"))

    def test_renders_sample_invoice_as_rmntc_statement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "statement.html"

            rendered_path = self.renderer.render_to_file(
                self.engine.create_statement(self.invoice),
                "rmntc",
                "statement",
                destination,
            )

            html = rendered_path.read_text(encoding="utf-8")
            self.assertIn("<html lang=\"ko\">", html)
            self.assertIn("거래명세서", html)
            self.assertIn("RMNTC-2026-0729-001", html)
            self.assertIn("업무 프로세스 분석", html)
            self.assertIn("₩3,850,000", html)
            self.assertIn("(부가세 포함)", html)
            self.assertIn("수신자:", html)
            self.assertIn("발신자:", html)
            self.assertIn("순 합계", html)
            self.assertIn("세부 정보", html)
            self.assertIn("특이사항:", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertNotIn("{{", html)

    def test_rejects_template_without_html_entrypoint(self) -> None:
        view_model = self.engine.create_quotation(self.invoice)
        template = TemplateManager(PROJECT_ROOT / "templates").load_template(
            "rmntc", "quotation"
        )

        with self.assertRaisesRegex(RenderError, "no HTML entrypoint"):
            self.renderer.render(view_model, template)

    def test_escapes_untrusted_canonical_text(self) -> None:
        invoice = json.loads(
            (PROJECT_ROOT / "input" / "invoice.json").read_text(encoding="utf-8")
        )
        invoice["document"]["buyer"]["name"] = "<script>alert(1)</script>"
        view_model = self.engine.create_statement(invoice)
        template = TemplateManager(PROJECT_ROOT / "templates").load_template(
            "rmntc", "statement"
        )

        html = self.renderer.render(view_model, template)

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_renders_when_optional_remarks_are_absent(self) -> None:
        invoice = json.loads(
            (PROJECT_ROOT / "input" / "invoice.json").read_text(encoding="utf-8")
        )
        del invoice["document"]["remarks"]
        for item in invoice["document"]["items"]:
            item.pop("remarks", None)
        view_model = self.engine.create_statement(invoice)
        template = TemplateManager(PROJECT_ROOT / "templates").load_template(
            "rmntc", "statement"
        )

        html = self.renderer.render(view_model, template)

        self.assertIn("거래명세서", html)
        self.assertNotIn("class=\"remarks\"", html)

    def test_rejects_raw_canonical_dictionary(self) -> None:
        template = TemplateManager(PROJECT_ROOT / "templates").load_template(
            "rmntc", "statement"
        )

        with self.assertRaisesRegex(InputDataError, "must be a ViewModel"):
            self.renderer.render(self.invoice, template)
