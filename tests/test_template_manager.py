import json
import tempfile
import unittest
from pathlib import Path

from renderer import (
    TemplateManager,
    TemplateNotFoundError,
    TemplateValidationError,
)


class TemplateManagerTests(unittest.TestCase):
    def test_discovers_repository_templates(self) -> None:
        root = Path(__file__).resolve().parents[1] / "templates"
        discovered = TemplateManager(root).discover_templates()

        identities = {
            (template.company, template.document_type) for template in discovered
        }
        self.assertEqual(
            identities,
            {
                ("rmntc", "statement"),
                ("rmntc", "quotation"),
                ("rmntc", "comparison"),
                ("cellclinic", "invoice"),
            },
        )

    def test_loads_template_by_company_and_document_type(self) -> None:
        root = Path(__file__).resolve().parents[1] / "templates"

        template = TemplateManager(root).load_template("cellclinic", "invoice")

        self.assertEqual(template.company, "cellclinic")
        self.assertEqual(template.document_type, "invoice")
        self.assertEqual(template.required_files, ())
        self.assertIsNone(template.entrypoint)

    def test_loads_declared_html_entrypoint(self) -> None:
        root = Path(__file__).resolve().parents[1] / "templates"

        template = TemplateManager(root).load_template("rmntc", "statement")

        self.assertEqual(template.entrypoint.name, "statement.html.j2")
        self.assertIn(template.entrypoint, template.required_files)

    def test_missing_template_has_clear_error(self) -> None:
        root = Path(__file__).resolve().parents[1] / "templates"

        with self.assertRaisesRegex(
            TemplateNotFoundError,
            "company='unknown'.*document_type='invoice'",
        ):
            TemplateManager(root).load_template("unknown", "invoice")

    def test_missing_manifest_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "company" / "invoice").mkdir(parents=True)

            with self.assertRaisesRegex(
                TemplateValidationError, "manifest is missing"
            ):
                TemplateManager(root).load_template("company", "invoice")

    def test_missing_required_file_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_path = root / "company" / "invoice"
            template_path.mkdir(parents=True)
            manifest = {
                "manifest_version": 1,
                "company": "company",
                "document_type": "invoice",
                "required_files": ["layout.asset"],
            }
            (template_path / "template.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                TemplateValidationError, "Required template file is missing"
            ):
                TemplateManager(root).load_template("company", "invoice")

    def test_rejects_path_traversal_in_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_path = root / "company" / "invoice"
            template_path.mkdir(parents=True)
            manifest = {
                "manifest_version": 1,
                "company": "company",
                "document_type": "invoice",
                "required_files": ["../shared.asset"],
            }
            (template_path / "template.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                TemplateValidationError, "stay inside"
            ):
                TemplateManager(root).load_template("company", "invoice")


if __name__ == "__main__":
    unittest.main()
