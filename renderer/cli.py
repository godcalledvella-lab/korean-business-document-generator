"""Command-line entry point for canonical JSON to HTML rendering."""

from __future__ import annotations

import argparse
from pathlib import Path

from business import BusinessRuleEngine, ViewModelType
from .html_renderer import HtmlRenderer
from .template_manager import TemplateManager


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render canonical business-document JSON to HTML."
    )
    parser.add_argument("input", type=Path, help="Canonical JSON input file")
    parser.add_argument("company", help="Template company identifier")
    parser.add_argument("document_type", help="Template document-type identifier")
    parser.add_argument("output", type=Path, help="Generated HTML output file")
    parser.add_argument(
        "--templates-root",
        type=Path,
        default=Path("templates"),
        help="Template registry root (default: templates)",
    )
    parser.add_argument(
        "--schemas-root",
        type=Path,
        default=Path("configs"),
        help="Canonical schema root (default: configs)",
    )
    arguments = parser.parse_args()

    engine = BusinessRuleEngine(
        arguments.schemas_root / "invoice.schema.json",
        arguments.schemas_root / "business_rules.json",
    )
    invoice = engine.load_invoice(arguments.input)
    view_models = engine.create_all(invoice)
    try:
        view_model_type = ViewModelType(arguments.document_type)
    except ValueError as error:
        supported = ", ".join(model_type.value for model_type in ViewModelType)
        parser.error(
            f"unsupported document type {arguments.document_type!r}; "
            f"choose one of: {supported}"
        )
        raise error

    renderer = HtmlRenderer(TemplateManager(arguments.templates_root))
    destination = renderer.render_to_file(
        view_models[view_model_type],
        arguments.company,
        arguments.document_type,
        arguments.output,
    )
    print(destination)


if __name__ == "__main__":
    main()
