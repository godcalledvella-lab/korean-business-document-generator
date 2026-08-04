"""Populate the RMNTC Quotation workbook without recreating its presentation."""

from __future__ import annotations

import argparse
import copy
import math
import re
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape

from business import BusinessRuleEngine, ViewModel, ViewModelType
from excel_renderer.statement_writer import (
    ExcelRendererError,
    ItemCapacityError,
    TemplateStructureError,
)


QUOTATION_SHEET_PART = "xl/worksheets/sheet1.xml"
ITEM_ROWS = tuple(range(16, 27))
PRESERVED_FORMULA_CELLS = ("F14", "F16", "F17", "F18", "F19", "F20", "F27", "F29")


class InvalidQuotationViewModel(ExcelRendererError):
    """Raised when input is not an existing Quotation ViewModel."""


@dataclass(frozen=True)
class QuotationWriteReport:
    """Immutable audit record for one workbook write."""

    output_path: Path
    modified_cells: tuple[str, ...]
    preserved_formula_cells: tuple[str, ...]


def write_quotation(
    template_path: str | Path,
    output_path: str | Path,
    view_model: ViewModel,
) -> QuotationWriteReport:
    """Duplicate *template_path* and populate mapped Quotation cells only."""

    source = Path(template_path).resolve()
    destination = Path(output_path).resolve()
    _validate_paths(source, destination, "Quotation")
    document = _quotation_document(view_model)
    items = document.get("items")
    if not isinstance(items, list):
        raise InvalidQuotationViewModel("Quotation document.items must be a list.")
    if len(items) > len(ITEM_ROWS):
        raise ItemCapacityError(
            f"Quotation template supports {len(ITEM_ROWS)} styled item rows; "
            f"received {len(items)}."
        )

    try:
        with zipfile.ZipFile(source, "r") as workbook:
            sheet_xml = workbook.read(QUOTATION_SHEET_PART).decode("utf-8")
            updated_xml, modified = _populate_sheet(sheet_xml, document)
            members = [
                (copy.copy(info), workbook.read(info.filename))
                for info in workbook.infolist()
            ]
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise TemplateStructureError(
            f"Quotation template has an invalid OOXML structure: {error}"
        ) from error

    _write_package(destination, members, QUOTATION_SHEET_PART, updated_xml)
    return QuotationWriteReport(
        output_path=destination,
        modified_cells=tuple(modified),
        preserved_formula_cells=PRESERVED_FORMULA_CELLS,
    )


def _quotation_document(view_model: ViewModel) -> dict[str, Any]:
    if not isinstance(view_model, ViewModel) or view_model.type is not ViewModelType.QUOTATION:
        raise InvalidQuotationViewModel(
            "Excel Quotation writer accepts only a Quotation ViewModel."
        )
    document = view_model.data.get("document")
    if not isinstance(document, dict):
        raise InvalidQuotationViewModel(
            "Quotation ViewModel must contain a structured document object."
        )
    return document


def _populate_sheet(
    xml: str,
    document: Mapping[str, Any],
) -> tuple[str, list[str]]:
    dates = _mapping(document, "dates")
    seller = _mapping(document, "seller")
    buyer = _mapping(document, "buyer")
    totals = _mapping(document, "totals")
    items = document["items"]

    issue_date = _required_text(dates, "issue_date", "document.dates.issue_date")
    try:
        issue_serial = (date.fromisoformat(issue_date) - date(1899, 12, 30)).days
    except ValueError as error:
        raise InvalidQuotationViewModel(
            "document.dates.issue_date must be an ISO date."
        ) from error

    seller_name = _required_text(seller, "name", "document.seller.name")
    seller_registration = _required_text(
        seller,
        "business_registration_number",
        "document.seller.business_registration_number",
    )
    seller_address = _required_text(seller, "address", "document.seller.address")
    seller_representative = _required_text(
        seller, "representative", "document.seller.representative"
    )
    seller_business_type = _optional_text(
        seller, "business_type", "document.seller.business_type"
    )
    seller_business_item = _optional_text(
        seller, "business_item", "document.seller.business_item"
    )
    buyer_name = _required_text(buyer, "name", "document.buyer.name")
    contact = _mapping(seller, "contact")
    phone = _optional_text(contact, "phone", "document.seller.contact.phone")
    email = _required_text(contact, "email", "document.seller.contact.email")
    supply_amount = _required_number(
        totals, "supply_amount", "document.totals.supply_amount"
    )
    vat = _required_number(totals, "vat", "document.totals.vat")
    remarks = document.get("remarks", "")
    if not isinstance(remarks, str):
        raise InvalidQuotationViewModel("document.remarks must be text.")
    product_descriptions: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise InvalidQuotationViewModel(
                f"document.items.{index} must be an object."
            )
        product_descriptions.append(
            _required_text(
                item,
                "description",
                f"document.items.{index}.description",
            )
        )
    product_names = ", ".join(product_descriptions)
    product_label = (
        product_names
        if len(product_names) <= 24
        else f"{product_descriptions[0]} 외 {len(product_descriptions) - 1}건"
    )
    footer_contact = (
        f"TEL : {phone} / E-mail : {email}" if phone else f"E-mail : {email}"
    )

    changes: list[tuple[str, str, Any]] = [
        ("H2", "number", issue_serial),
        ("H3", "text", f"{buyer_name}\u00a0귀하"),
        ("H4", "text", product_label),
        (
            "A6",
            "text",
            f"■ 상호 : {seller_name}    ■ 사업자번호 : {seller_registration}"
            f"    ■ 업종 : {seller_business_type}    ■ 업태 : {seller_business_item}"
            f"\n■ 주소 : {seller_address}    ■ 대표자 : {seller_representative}    ",
        ),
        ("B8", "text", product_names),
        ("C14", "text", f"{korean_amount_words(supply_amount)} 원 정"),
        ("F28", "number", vat),
        ("B30", "text", remarks),
        ("A35", "text", footer_contact),
    ]

    for index, row in enumerate(ITEM_ROWS):
        if index < len(items):
            item = items[index]
            if not isinstance(item, Mapping):
                raise InvalidQuotationViewModel(
                    "Every quotation item must be an object."
                )
            changes.extend(
                (
                    (
                        f"A{row}",
                        "number",
                        _required_number(
                            item, "line_number", f"item row {row} line_number"
                        ),
                    ),
                    (
                        f"B{row}",
                        "text",
                        _required_text(
                            item, "description", f"item row {row} description"
                        ),
                    ),
                    (
                        f"D{row}",
                        "number",
                        _required_number(item, "quantity", f"item row {row} quantity"),
                    ),
                    (
                        f"E{row}",
                        "number",
                        _required_number(
                            item, "unit_price", f"item row {row} unit_price"
                        ),
                    ),
                    (
                        f"H{row}",
                        "text",
                        _optional_text(item, "remarks", f"item row {row} remarks"),
                    ),
                )
            )
            if not _cell_has_formula(xml, f"F{row}"):
                changes.append(
                    (
                        f"F{row}",
                        "number",
                        _required_number(
                            item, "supply_amount", f"item row {row} supply_amount"
                        ),
                    )
                )
        else:
            changes.extend(
                (f"{column}{row}", "blank", "")
                for column in ("A", "B", "D", "E", "H")
            )
            if not _cell_has_formula(xml, f"F{row}"):
                changes.append((f"F{row}", "blank", ""))

    updated = xml
    modified: list[str] = []
    for reference, kind, value in changes:
        updated, changed = _set_cell(updated, reference, kind, value, "Quotation")
        if changed:
            modified.append(reference)

    formula_caches: list[tuple[str, Any | None]] = []
    for index, row in enumerate(ITEM_ROWS):
        if _cell_has_formula(xml, f"F{row}"):
            cached_value = (
                _required_number(
                    items[index],
                    "supply_amount",
                    f"item row {row} supply_amount",
                )
                if index < len(items)
                else None
            )
            formula_caches.append((f"F{row}", cached_value))
    formula_caches.extend(
        (
            ("F14", supply_amount),
            ("F27", supply_amount),
            (
                "F29",
                _required_number(totals, "total", "document.totals.total"),
            ),
        )
    )
    for reference, value in formula_caches:
        updated, changed = _set_formula_cache(
            updated, reference, value, "Quotation"
        )
        if changed and reference not in modified:
            modified.append(reference)
    return updated, modified


def korean_amount_words(value: int | float | Decimal) -> str:
    """Return a Korean large-number expression for a non-negative won amount."""

    decimal_value = Decimal(str(value))
    if not decimal_value.is_finite() or decimal_value < 0:
        raise InvalidQuotationViewModel(
            "Korean amount-in-words value must be finite and non-negative."
        )
    if decimal_value != decimal_value.to_integral_value():
        raise InvalidQuotationViewModel(
            "Korean amount-in-words value must be a whole won amount."
        )
    amount = int(decimal_value)
    if amount == 0:
        return "영"

    digits = ("", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
    small_units = ("", "십", "백", "천")
    large_units = ("", "만", "억", "조", "경")
    groups: list[str] = []
    group_index = 0
    while amount:
        group = amount % 10000
        if group:
            text = ""
            for position in range(3, -1, -1):
                digit = (group // (10**position)) % 10
                if digit:
                    if digit != 1 or position == 0:
                        text += digits[digit]
                    text += small_units[position]
            groups.append(text + large_units[group_index])
        amount //= 10000
        group_index += 1
    return "".join(reversed(groups))


def _validate_paths(source: Path, destination: Path, label: str) -> None:
    if source == destination:
        raise ExcelRendererError("Output workbook must not overwrite the template.")
    if not source.is_file():
        raise ExcelRendererError(f"{label} template does not exist: {source}")
    if not zipfile.is_zipfile(source):
        raise ExcelRendererError(f"{label} template is not a valid XLSX file: {source}")


def _write_package(
    destination: Path,
    members: list[tuple[zipfile.ZipInfo, bytes]],
    sheet_part: str,
    updated_xml: str,
) -> None:
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
                if info.filename == sheet_part:
                    payload = updated_xml.encode("utf-8")
                output.writestr(info, payload)
        Path(temporary_name).replace(destination)
    except OSError as error:
        raise ExcelRendererError(
            f"Could not write workbook {destination}: {error}"
        ) from error
    finally:
        if temporary_name:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise InvalidQuotationViewModel(f"document.{key} must be an object.")
    return value


def _required_text(parent: Mapping[str, Any], key: str, label: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str):
        raise InvalidQuotationViewModel(f"{label} must be text.")
    return value


def _optional_text(parent: Mapping[str, Any], key: str, label: str) -> str:
    value = parent.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidQuotationViewModel(f"{label} must be text or null.")
    return value


def _wrap_template_text(value: str, *, line_width: int = 24) -> str:
    """Add a single controlled break without changing the template cell style."""
    if _display_width(value) <= line_width or "\n" in value:
        return value
    break_at = 0
    width = 0
    for index, character in enumerate(value):
        width += 2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
        if width > line_width:
            break_at = index
            break
    whitespace = value.rfind(" ", 0, break_at + 1)
    if whitespace >= 0:
        break_at = whitespace
    if break_at <= 0:
        break_at = min(len(value), line_width)
    return f"{value[:break_at].rstrip()}\n{value[break_at:].lstrip()}"


def _display_width(value: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
        for character in value
    )


def _required_number(
    parent: Mapping[str, Any], key: str, label: str
) -> int | float | Decimal:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise InvalidQuotationViewModel(f"{label} must be numeric.")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidQuotationViewModel(f"{label} must be finite.")
    return value


def _cell_pattern(reference: str) -> re.Pattern[str]:
    escaped = re.escape(reference)
    return re.compile(
        rf'<c(?P<attrs>\s[^>]*\br="{escaped}"[^>]*?)(?P<self>/>)|'
        rf'<c(?P<attrs_full>\s[^>]*\br="{escaped}"[^>]*)>'
        rf'(?P<body>.*?)</c>',
        re.DOTALL,
    )


def _cell_has_formula(xml: str, reference: str) -> bool:
    match = _cell_pattern(reference).search(xml)
    if not match:
        raise TemplateStructureError(f"Required mapped cell {reference} is missing.")
    body = "" if match.group("self") else (match.group("body") or "")
    return re.search(r"<f(?:\s|>)", body) is not None


def _set_cell(
    xml: str,
    reference: str,
    kind: str,
    value: Any,
    template_name: str,
) -> tuple[str, bool]:
    match = _cell_pattern(reference).search(xml)
    if not match:
        raise TemplateStructureError(
            f"Required mapped cell {reference} is missing from {template_name} template."
        )
    attrs = match.group("attrs") or match.group("attrs_full")
    body = "" if match.group("self") else (match.group("body") or "")
    if re.search(r"<f(?:\s|>)", body):
        raise TemplateStructureError(
            f"Mapped value cell {reference} contains a protected formula."
        )

    attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
    if kind == "blank":
        replacement = f"<c{attrs}/>"
    elif kind == "number":
        replacement = f"<c{attrs}><v>{_number_text(value)}</v></c>"
    else:
        text_value = str(value)
        text = escape(text_value)
        space = (
            ' xml:space="preserve"'
            if text_value[:1].isspace() or text_value[-1:].isspace()
            else ""
        )
        replacement = f'<c{attrs} t="inlineStr"><is><t{space}>{text}</t></is></c>'
    if match.group(0) == replacement:
        return xml, False
    return xml[: match.start()] + replacement + xml[match.end() :], True


def _set_formula_cache(
    xml: str,
    reference: str,
    value: Any | None,
    template_name: str,
) -> tuple[str, bool]:
    match = _cell_pattern(reference).search(xml)
    if not match or match.group("self"):
        raise TemplateStructureError(
            f"Required formula cell {reference} is missing from {template_name} template."
        )
    attrs = match.group("attrs_full")
    body = match.group("body") or ""
    if re.search(r"<f(?:\s|>)", body) is None:
        raise TemplateStructureError(
            f"Required formula cell {reference} has no formula."
        )
    new_body = re.sub(r"<v>.*?</v>", "", body, count=1, flags=re.DOTALL)
    if value is not None:
        new_body += f"<v>{_number_text(value)}</v>"
    replacement = f"<c{attrs}>{new_body}</c>"
    if match.group(0) == replacement:
        return xml, False
    return xml[: match.start()] + replacement + xml[match.end() :], True


def _number_text(value: int | float | Decimal) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate an RMNTC Quotation workbook from canonical invoice JSON."
    )
    parser.add_argument("input", type=Path, help="Canonical invoice JSON")
    parser.add_argument("template", type=Path, help="Quotation template workbook")
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
        report = write_quotation(
            args.template, args.output, engine.create_quotation(invoice)
        )
    except (ExcelRendererError, Exception) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(report.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
