"""Populate the RMNTC Statement workbook without recreating its presentation.

The writer edits only individual cell records in the Statement worksheet XML.
Every other OOXML package part is copied byte-for-byte from the source workbook.
This deliberately avoids loading and saving the workbook through an object model,
which can normalize or discard unsupported drawings and legacy workbook metadata.
"""

from __future__ import annotations

import copy
import math
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from xml.sax.saxutils import escape

from business import ViewModel, ViewModelType


STATEMENT_SHEET_PART = "xl/worksheets/sheet1.xml"
ITEM_ROWS = (7, 8, 10, 11, 12, 13, 14, 15, 16, 17)
PRESERVED_FORMULA_CELLS = ("E7",)


class ExcelRendererError(Exception):
    """Base error for the Excel rendering pipeline."""


class InvalidStatementViewModel(ExcelRendererError):
    """Raised when input is not an existing Statement ViewModel."""


class TemplateStructureError(ExcelRendererError):
    """Raised when the workbook does not match the approved template structure."""


class ItemCapacityError(ExcelRendererError):
    """Raised when statement items exceed the template's styled row capacity."""


@dataclass(frozen=True)
class StatementWriteReport:
    """Immutable audit record for one workbook write."""

    output_path: Path
    modified_cells: tuple[str, ...]
    created_formula_cells: tuple[str, ...]
    preserved_formula_cells: tuple[str, ...]


def write_statement(
    template_path: str | Path,
    output_path: str | Path,
    view_model: ViewModel,
) -> StatementWriteReport:
    """Duplicate *template_path* and populate mapped Statement cells only."""

    source = Path(template_path).resolve()
    destination = Path(output_path).resolve()
    if source == destination:
        raise ExcelRendererError("Output workbook must not overwrite the template.")
    if not source.is_file():
        raise ExcelRendererError(f"Statement template does not exist: {source}")
    if not zipfile.is_zipfile(source):
        raise ExcelRendererError(f"Statement template is not a valid XLSX file: {source}")

    document = _statement_document(view_model)
    items = document.get("items")
    if not isinstance(items, list):
        raise InvalidStatementViewModel("Statement document.items must be a list.")
    if len(items) > len(ITEM_ROWS):
        raise ItemCapacityError(
            f"Statement template supports {len(ITEM_ROWS)} styled item rows; "
            f"received {len(items)}."
        )

    try:
        with zipfile.ZipFile(source, "r") as workbook:
            sheet_xml = workbook.read(STATEMENT_SHEET_PART).decode("utf-8")
            updated_xml, modified, created = _populate_sheet(sheet_xml, document)
            members = [(copy.copy(info), workbook.read(info.filename)) for info in workbook.infolist()]
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise TemplateStructureError(
            f"Statement template has an invalid OOXML structure: {error}"
        ) from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name

        with zipfile.ZipFile(temporary_name, "w") as output:
            for info, payload in members:
                if info.filename == STATEMENT_SHEET_PART:
                    payload = updated_xml.encode("utf-8")
                output.writestr(info, payload)
        Path(temporary_name).replace(destination)
    except OSError as error:
        raise ExcelRendererError(
            f"Could not write Statement workbook {destination}: {error}"
        ) from error
    finally:
        if temporary_name:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()

    return StatementWriteReport(
        output_path=destination,
        modified_cells=tuple(modified),
        created_formula_cells=tuple(created),
        preserved_formula_cells=PRESERVED_FORMULA_CELLS,
    )


def _statement_document(view_model: ViewModel) -> dict[str, Any]:
    if not isinstance(view_model, ViewModel) or view_model.type is not ViewModelType.STATEMENT:
        raise InvalidStatementViewModel(
            "Excel Statement writer accepts only a Statement ViewModel."
        )
    document = view_model.data.get("document")
    if not isinstance(document, dict):
        raise InvalidStatementViewModel(
            "Statement ViewModel must contain a structured document object."
        )
    return document


def _populate_sheet(
    xml: str,
    document: Mapping[str, Any],
) -> tuple[str, list[str], list[str]]:
    dates = _mapping(document, "dates")
    seller = _mapping(document, "seller")
    buyer = _mapping(document, "buyer")
    issue_date = dates.get("issue_date")
    if not isinstance(issue_date, str):
        raise InvalidStatementViewModel("document.dates.issue_date must be an ISO date.")
    try:
        issue_serial = (date.fromisoformat(issue_date) - date(1899, 12, 30)).days
    except ValueError as error:
        raise InvalidStatementViewModel(
            "document.dates.issue_date must be an ISO date."
        ) from error

    seller_name = _required_text(seller, "name", "document.seller.name")
    buyer_name = _required_text(buyer, "name", "document.buyer.name")
    remarks = document.get("remarks", "")
    if not isinstance(remarks, str):
        raise InvalidStatementViewModel("document.remarks must be text.")
    totals = _mapping(document, "totals")
    vat_included_total = _required_number(
        totals, "total", "document.totals.total"
    )

    changes: list[tuple[str, str, Any]] = [
        ("D2", "display_total", vat_included_total),
        ("B2", "number", issue_serial),
        ("B3", "text", f"수신자: {buyer_name}"),
        ("B4", "text", f"발신자: {seller_name}"),
        ("C20", "text", seller_name),
        ("E18", "display_total", vat_included_total),
        ("B24", "text", remarks),
    ]
    items = document["items"]
    for row, item in zip(ITEM_ROWS, items):
        if not isinstance(item, Mapping):
            raise InvalidStatementViewModel("Every statement item must be an object.")
        changes.extend(
            (
                (f"B{row}", "number", _required_number(item, "quantity", row)),
                (
                    f"C{row}",
                    "text",
                    _required_text(item, "description", f"item row {row} description"),
                ),
                (f"D{row}", "number", _required_number(item, "unit_price", row)),
            )
        )

    updated = xml
    modified: list[str] = []
    created_formulas: list[str] = []
    for reference, kind, value in changes:
        if kind == "display_total":
            updated, changed = _set_display_total(updated, reference, value)
        else:
            updated, changed = _set_cell(updated, reference, kind, value)
        if changed:
            modified.append(reference)

    for row in ITEM_ROWS[: len(items)]:
        reference = f"E{row}"
        updated, created = _create_formula_if_blank(
            updated, reference, f"(D{row}*B{row})"
        )
        if created:
            modified.append(reference)
            created_formulas.append(reference)

    return updated, modified, created_formulas


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise InvalidStatementViewModel(f"document.{key} must be an object.")
    return value


def _required_text(parent: Mapping[str, Any], key: str, label: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str):
        raise InvalidStatementViewModel(f"{label} must be text.")
    return value


def _required_number(parent: Mapping[str, Any], key: str, label: int | str) -> int | float | Decimal:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise InvalidStatementViewModel(f"{label} {key} must be numeric.")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidStatementViewModel(f"{label} {key} must be finite.")
    return value


def _set_display_total(
    xml: str,
    reference: str,
    value: int | float | Decimal,
) -> tuple[str, bool]:
    """Replace a template total formula while retaining the cell's style."""

    pattern = _cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        raise TemplateStructureError(
            f"Required Statement total cell {reference} is missing."
        )
    attrs = match.group("attrs") or match.group("attrs_full")
    attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
    replacement = f"<c{attrs}><v>{_number_text(value)}</v></c>"
    if match.group(0) == replacement:
        return xml, False
    return xml[: match.start()] + replacement + xml[match.end() :], True


def _cell_pattern(reference: str) -> re.Pattern[str]:
    escaped = re.escape(reference)
    return re.compile(
        rf'<c(?P<attrs>\s[^>]*\br="{escaped}"[^>]*?)'
        rf'(?P<self>/>)|'
        rf'<c(?P<attrs_full>\s[^>]*\br="{escaped}"[^>]*)>'
        rf'(?P<body>.*?)</c>',
        re.DOTALL,
    )


def _set_cell(
    xml: str,
    reference: str,
    kind: str,
    value: Any,
) -> tuple[str, bool]:
    pattern = _cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        raise TemplateStructureError(
            f"Required mapped cell {reference} is missing from Statement template."
        )
    attrs = match.group("attrs") or match.group("attrs_full")
    body = "" if match.group("self") else (match.group("body") or "")
    if re.search(r"<f(?:\s|>)", body):
        raise TemplateStructureError(
            f"Mapped value cell {reference} contains a protected formula."
        )

    if kind == "number":
        attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
        new_body = f"<v>{_number_text(value)}</v>"
    else:
        attrs = re.sub(r'\s+t="[^"]*"', "", attrs) + ' t="inlineStr"'
        text = escape(str(value))
        space = ' xml:space="preserve"' if str(value)[:1].isspace() or str(value)[-1:].isspace() else ""
        new_body = f"<is><t{space}>{text}</t></is>"

    replacement = f"<c{attrs}>{new_body}</c>"
    if match.group(0) == replacement:
        return xml, False
    return xml[: match.start()] + replacement + xml[match.end() :], True


def _create_formula_if_blank(
    xml: str,
    reference: str,
    formula: str,
) -> tuple[str, bool]:
    pattern = _cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        raise TemplateStructureError(
            f"Required amount cell {reference} is missing from Statement template."
        )
    body = "" if match.group("self") else (match.group("body") or "")
    if re.search(r"<f(?:\s|>)", body):
        return xml, False
    if re.search(r"<(?:v|is)(?:\s|>)", body):
        raise TemplateStructureError(
            f"Amount cell {reference} is not blank; refusing to overwrite it."
        )
    attrs = match.group("attrs") or match.group("attrs_full")
    replacement = f"<c{attrs}><f>{escape(formula)}</f></c>"
    return xml[: match.start()] + replacement + xml[match.end() :], True


def _number_text(value: int | float | Decimal) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
