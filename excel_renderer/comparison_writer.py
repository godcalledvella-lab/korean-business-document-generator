"""Populate the RMNTC Comparison Quotation without recreating its presentation."""

from __future__ import annotations

import argparse
import copy
import sys
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from business import BusinessRuleEngine, ViewModel, ViewModelType
from excel_renderer.quotation_writer import (
    _cell_has_formula,
    _optional_text,
    _required_number,
    _required_text,
    _set_cell,
    _set_formula_cache,
    _validate_paths,
    _write_package,
)
from excel_renderer.statement_writer import (
    ExcelRendererError,
    ItemCapacityError,
    TemplateStructureError,
)


COMPARISON_SHEET_PART = "xl/worksheets/sheet1.xml"
ITEM_ROWS = tuple(range(14, 20))
PRESERVED_FORMULA_CELLS = ("B11", "G14", "G20")


class InvalidComparisonViewModel(ExcelRendererError):
    """Raised when input is not an existing Comparison ViewModel."""


@dataclass(frozen=True)
class ComparisonWriteReport:
    """Immutable audit record for one workbook write."""

    output_path: Path
    modified_cells: tuple[str, ...]
    preserved_formula_cells: tuple[str, ...]


def write_comparison(
    template_path: str | Path,
    output_path: str | Path,
    view_model: ViewModel,
) -> ComparisonWriteReport:
    """Duplicate *template_path* and populate mapped Comparison cells only."""

    source = Path(template_path).resolve()
    destination = Path(output_path).resolve()
    _validate_paths(source, destination, "Comparison")
    document = _comparison_document(view_model)
    items = document.get("items")
    if not isinstance(items, list):
        raise InvalidComparisonViewModel("Comparison document.items must be a list.")
    if len(items) > len(ITEM_ROWS):
        raise ItemCapacityError(
            f"Comparison template supports {len(ITEM_ROWS)} styled item rows; "
            f"received {len(items)}."
        )

    try:
        with zipfile.ZipFile(source, "r") as workbook:
            sheet_xml = workbook.read(COMPARISON_SHEET_PART).decode("utf-8")
            updated_xml, modified = _populate_sheet(sheet_xml, document)
            members = [
                (copy.copy(info), workbook.read(info.filename))
                for info in workbook.infolist()
            ]
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise TemplateStructureError(
            f"Comparison template has an invalid OOXML structure: {error}"
        ) from error

    _write_package(destination, members, COMPARISON_SHEET_PART, updated_xml)
    return ComparisonWriteReport(
        output_path=destination,
        modified_cells=tuple(modified),
        preserved_formula_cells=PRESERVED_FORMULA_CELLS,
    )


def _comparison_document(view_model: ViewModel) -> dict[str, Any]:
    if not isinstance(view_model, ViewModel) or view_model.type is not ViewModelType.COMPARISON:
        raise InvalidComparisonViewModel(
            "Excel Comparison writer accepts only a Comparison ViewModel."
        )
    document = view_model.data.get("document")
    if not isinstance(document, dict):
        raise InvalidComparisonViewModel(
            "Comparison ViewModel must contain a structured document object."
        )
    return document


def _mapping(
    parent: Mapping[str, Any],
    key: str,
    label: str,
) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise InvalidComparisonViewModel(f"{label} must be an object.")
    return value


def _populate_sheet(
    xml: str,
    document: Mapping[str, Any],
) -> tuple[str, list[str]]:
    dates = _mapping(document, "dates", "document.dates")
    seller = _mapping(document, "seller", "document.seller")
    buyer = _mapping(document, "buyer", "document.buyer")
    totals = _mapping(document, "totals", "document.totals")
    comparison_totals = _mapping(
        totals, "comparison", "document.totals.comparison"
    )
    contact = _mapping(seller, "contact", "document.seller.contact")
    items = document["items"]

    issue_date = _required_text(dates, "issue_date", "document.dates.issue_date")
    try:
        formatted_issue_date = issue_date.replace("-", ".")
        if len(formatted_issue_date) != 10:
            raise ValueError
    except (AttributeError, ValueError) as error:
        raise InvalidComparisonViewModel(
            "document.dates.issue_date must be an ISO date."
        ) from error

    changes: list[tuple[str, str, Any]] = [
        ("B6", "text", formatted_issue_date),
        (
            "B7",
            "text",
            _required_text(buyer, "name", "document.buyer.name"),
        ),
        (
            "F5",
            "text",
            _required_text(
                seller,
                "business_registration_number",
                "document.seller.business_registration_number",
            ),
        ),
        (
            "F6",
            "text",
            _required_text(seller, "name", "document.seller.name"),
        ),
        (
            "I6",
            "text",
            _required_text(
                seller, "representative", "document.seller.representative"
            ),
        ),
        (
            "F7",
            "text",
            _required_text(seller, "address", "document.seller.address"),
        ),
        (
            "F8",
            "text",
            _required_text(
                seller, "business_type", "document.seller.business_type"
            ),
        ),
        (
            "I8",
            "text",
            _required_text(
                seller, "business_item", "document.seller.business_item"
            ),
        ),
        (
            "F9",
            "text",
            _optional_text(contact, "phone", "document.seller.contact.phone"),
        ),
        (
            "I9",
            "text",
            _optional_text(contact, "phone", "document.seller.contact.phone"),
        ),
        (
            "A21",
            "text",
            document.get("remarks", "")
            if isinstance(document.get("remarks", ""), str)
            else "",
        ),
    ]

    for index, row in enumerate(ITEM_ROWS):
        if index < len(items):
            item = items[index]
            if not isinstance(item, Mapping):
                raise InvalidComparisonViewModel(
                    "Every comparison item must be an object."
                )
            comparison = _mapping(
                item, "comparison", f"item row {row} comparison"
            )
            changes.extend(
                (
                    (
                        f"A{row}",
                        "text",
                        _required_text(
                            item, "description", f"item row {row} description"
                        ),
                    ),
                    (
                        f"C{row}",
                        "number",
                        _required_number(item, "quantity", f"item row {row} quantity"),
                    ),
                    (
                        f"D{row}",
                        "text",
                        _required_text(item, "unit", f"item row {row} unit"),
                    ),
                    (
                        f"E{row}",
                        "number",
                        _required_number(
                            comparison,
                            "unit_price",
                            f"item row {row} comparison.unit_price",
                        ),
                    ),
                    (
                        f"I{row}",
                        "text",
                        _optional_text(item, "remarks", f"item row {row} remarks"),
                    ),
                )
            )
            if not _cell_has_formula(xml, f"G{row}"):
                changes.append(
                    (
                        f"G{row}",
                        "number",
                        _required_number(
                            comparison,
                            "supply_amount",
                            f"item row {row} comparison.supply_amount",
                        ),
                    )
                )
        else:
            changes.extend(
                (f"{column}{row}", "blank", "")
                for column in ("A", "C", "D", "E", "I")
            )
            if not _cell_has_formula(xml, f"G{row}"):
                changes.append((f"G{row}", "blank", ""))

    expected_total = _required_number(
        comparison_totals,
        "supply_amount",
        "document.totals.comparison.supply_amount",
    )
    line_total = sum(
        Decimal(str(_mapping(item, "comparison", "item comparison")["supply_amount"]))
        for item in items
    )
    if Decimal(str(expected_total)) != line_total:
        raise InvalidComparisonViewModel(
            "Comparison total must equal its marked-up line amounts."
        )

    updated = xml
    modified: list[str] = []
    for reference, kind, value in changes:
        updated, changed = _set_cell(updated, reference, kind, value, "Comparison")
        if changed:
            modified.append(reference)
    for reference, value in (
        (
            "G14",
            _required_number(
                _mapping(items[0], "comparison", "item row 14 comparison"),
                "supply_amount",
                "item row 14 comparison.supply_amount",
            ),
        ),
        ("G20", expected_total),
        ("B11", expected_total),
    ):
        updated, changed = _set_formula_cache(
            updated, reference, value, "Comparison"
        )
        if changed and reference not in modified:
            modified.append(reference)
    return updated, modified


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Populate an RMNTC Comparison Quotation workbook from canonical invoice JSON."
        )
    )
    parser.add_argument("input", type=Path, help="Canonical invoice JSON")
    parser.add_argument("template", type=Path, help="Comparison template workbook")
    parser.add_argument("output", type=Path, help="Destination .xlsx workbook")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        engine = BusinessRuleEngine(
            root / "configs/invoice.schema.json",
            root / "configs/business_rules.json",
        )
        invoice = engine.load_invoice(args.input)
        report = write_comparison(
            args.template, args.output, engine.create_comparison(invoice)
        )
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(report.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
