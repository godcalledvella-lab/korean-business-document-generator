"""Apply reviewed presentation values without changing workbook geometry."""

from __future__ import annotations

import copy
import re
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from xml.sax.saxutils import escape

from excel_renderer.quotation_writer import (
    QUOTATION_SHEET_PART,
    _cell_pattern,
    _set_cell,
    _wrap_template_text,
    _write_package,
    korean_amount_words,
)
from excel_renderer.comparison_writer import COMPARISON_SHEET_PART
from excel_renderer.statement_writer import STATEMENT_SHEET_PART


REVIEW_SETTINGS_KEY = "rmntc.review_settings"


def apply_review_settings(
    statement_path: Path,
    quotation_path: Path,
    comparison_path: Path,
    settings: Mapping[str, Any],
) -> None:
    """Apply Review UI values to mapped cells in generated workbook copies."""

    blue = _mapping(settings, "blueQuotation")
    green = _mapping(settings, "greenQuotation")
    statement = _mapping(settings, "statement")
    _customize_statement(statement_path, statement)
    _customize_blue_quotation(quotation_path, blue)
    _customize_green_quotation(comparison_path, green)


def _customize_statement(
    workbook_path: Path,
    settings: Mapping[str, Any],
) -> None:
    changes = (
        ("B4", "text", f"발신자: {_text(settings, 'sender')}"),
        ("C20", "text", _text(settings, "companyName")),
        ("C21", "text", _text(settings, "bank")),
        ("C22", "text", _text(settings, "accountNumber")),
    )
    _update_sheet(workbook_path, STATEMENT_SHEET_PART, changes, "Statement")


def _customize_blue_quotation(
    workbook_path: Path,
    settings: Mapping[str, Any],
) -> None:
    information = _mapping(settings, "informationBar")
    existing_information = _cell_text(
        workbook_path,
        QUOTATION_SHEET_PART,
        "A6",
    )
    information_text = (
        f"■ 상호 : {_visible_value(information, 'companyName')}"
        f"    ■ 사업자번호 : {_visible_value(information, 'businessNumber')}"
        f"    ■ 업종 : {_labeled_value(existing_information, '업종')}"
        f"    ■ 업태 : {_labeled_value(existing_information, '업태')}"
        f"\n■ 주소 : {_visible_value(information, 'address')}"
        f"    ■ 대표자 : {_visible_value(information, 'representative')}    "
    )
    footer = _mapping(settings, "footer")
    footer_text = (
        f"TEL : {_text(footer, 'telephone')} / E-mail : {_text(footer, 'email')}"
        f" / 계좌번호 : {_text(footer, 'bank')} {_text(footer, 'accountNumber')}"
    )
    client_text = _text(settings, "client").replace(" 귀하", "\u00a0귀하")
    changes = (
        ("H3", "text", client_text),
        ("H4", "text", _wrap_template_text(_text(settings, "product"))),
        ("A6", "text", information_text),
        (
            "B8",
            "text" if _boolean(settings, "showProductDetails") else "blank",
            _text(settings, "productDetails"),
        ),
        (
            "B30",
            "text" if _boolean(settings, "showRemark") else "blank",
            _text(settings, "remark"),
        ),
        ("A35", "text", footer_text),
    )
    _update_sheet(workbook_path, QUOTATION_SHEET_PART, changes, "Quotation")


def _customize_green_quotation(
    workbook_path: Path,
    settings: Mapping[str, Any],
) -> None:
    profile = _mapping(settings, "companyProfile")
    issue_date = _text(settings, "quotationDate").replace("-", ".")
    comparison_total = _formula_cache(workbook_path, COMPARISON_SHEET_PART, "G20")
    changes = (
        ("B6", "text", issue_date),
        ("B7", "text", _text(settings, "buyerCompany")),
        ("F5", "text", _text(profile, "registrationNumber")),
        ("F6", "text", _text(profile, "companyName")),
        ("I6", "text", _text(profile, "representative")),
        ("F7", "text", _text(profile, "address")),
        ("F8", "text", _text(profile, "businessType")),
        ("I8", "text", _text(profile, "businessItem")),
        ("F9", "text", _text(profile, "phone")),
        ("I9", "text", _text(profile, "hp")),
        ("B11", "display-text", korean_amount_words(comparison_total)),
    )
    _update_sheet(workbook_path, COMPARISON_SHEET_PART, changes, "Comparison")


def _update_sheet(
    workbook_path: Path,
    sheet_part: str,
    changes: tuple[tuple[str, str, str], ...],
    template_name: str,
) -> None:
    with zipfile.ZipFile(workbook_path, "r") as workbook:
        xml = workbook.read(sheet_part).decode("utf-8")
        members = [
            (copy.copy(info), workbook.read(info.filename))
            for info in workbook.infolist()
        ]
    updated = xml
    for reference, kind, value in changes:
        if kind == "display-text":
            updated = _replace_display_formula(updated, reference, value)
        else:
            updated, _ = _set_cell(
                updated,
                reference,
                kind,
                value,
                template_name,
            )
    _write_package(workbook_path, members, sheet_part, updated)


def _visible_value(parent: Mapping[str, Any], key: str) -> str:
    field = _mapping(parent, key)
    return _text(field, "value") if _boolean(field, "visible") else ""


def _cell_text(workbook_path: Path, sheet_part: str, reference: str) -> str:
    with zipfile.ZipFile(workbook_path, "r") as workbook:
        xml = workbook.read(sheet_part).decode("utf-8")
    cell = _cell_pattern(reference).search(xml)
    if not cell or cell.group("self"):
        raise ValueError(f"Mapped text cell {reference} is missing.")
    text = re.search(r"<t(?:\s[^>]*)?>(.*?)</t>", cell.group("body") or "", re.DOTALL)
    if text is None:
        raise ValueError(f"Mapped text cell {reference} has no text value.")
    return text.group(1)


def _labeled_value(value: str, label: str) -> str:
    match = re.search(
        rf"■\s*{re.escape(label)}\s*:\s*(.*?)(?=\s+■|\n|$)",
        value,
    )
    if match is None:
        raise ValueError(f"Quotation information bar is missing {label}.")
    return match.group(1).strip()


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Review setting {key} must be an object.")
    return value


def _text(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Review setting {key} must be text.")
    return value


def _boolean(parent: Mapping[str, Any], key: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Review setting {key} must be true or false.")
    return value


def _formula_cache(
    workbook_path: Path,
    sheet_part: str,
    reference: str,
) -> Decimal:
    with zipfile.ZipFile(workbook_path, "r") as workbook:
        xml = workbook.read(sheet_part).decode("utf-8")
    cell = _cell_pattern(reference).search(xml)
    if not cell or cell.group("self"):
        raise ValueError(f"Formula cache {reference} is missing.")
    value = re.search(r"<v>([^<]+)</v>", cell.group("body") or "")
    if value is None:
        raise ValueError(f"Formula cache {reference} is missing.")
    return Decimal(value.group(1))


def _replace_display_formula(xml: str, reference: str, value: str) -> str:
    """Replace only the green template's amount-display formula, never totals."""
    cell = _cell_pattern(reference).search(xml)
    if not cell or cell.group("self"):
        raise ValueError(f"Display cell {reference} is missing.")
    body = cell.group("body") or ""
    if "<f>(G20)</f>" not in body:
        raise ValueError(f"Display cell {reference} no longer mirrors G20.")
    attrs = cell.group("attrs_full") or ""
    attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
    replacement = (
        f'<c{attrs} t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    )
    return xml[: cell.start()] + replacement + xml[cell.end() :]
