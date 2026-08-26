"""RMNTC web-generation fixes layered over the stable document generator.

The web app follows the approved RMNTC document behavior without mutating source
invoice evidence or template files:
- blank optional contact fields are omitted before canonical validation;
- Statement currency values render as compact "₩ 1,500" text rather than the
  template's stretched Accounting display;
- the blue quotation uses VAT-included line totals as its commercial quote base;
- the blue quotation keeps the VAT row space but displays no VAT amount;
- quotation/comparison generation tolerates omitted optional contact data;
- final package pages are normalized to one page size without stretching content.
"""

from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PageObject, PdfReader, PdfWriter, Transformation


def _sanitize_optional_contacts(draft: dict) -> dict:
    cleaned = deepcopy(draft)
    document = cleaned.get("document")
    if not isinstance(document, dict):
        return cleaned
    for side in ("seller", "buyer"):
        party = document.get(side)
        if not isinstance(party, dict):
            continue
        contact = party.get("contact")
        if not isinstance(contact, dict):
            continue
        for key in ("name", "email", "phone"):
            value = contact.get(key)
            if isinstance(value, str):
                value = value.strip()
                if value:
                    contact[key] = value
                else:
                    contact.pop(key, None)
        if not contact:
            party.pop("contact", None)
    return cleaned


def _compact_money(value) -> str:
    decimal = Decimal(str(value))
    if decimal == decimal.to_integral_value():
        return f"₩ {int(decimal):,}"
    return f"₩ {decimal:,}"


def _replace_cell_with_inline_text(module, xml: str, reference: str, text: str) -> tuple[str, bool]:
    pattern = module._cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        return xml, False
    attrs = match.group("attrs") or match.group("attrs_full")
    attrs = re.sub(r'\s+t="[^"]*"', "", attrs) + ' t="inlineStr"'
    replacement = f"<c{attrs}><is><t>{escape(text)}</t></is></c>"
    if replacement == match.group(0):
        return xml, False
    return xml[: match.start()] + replacement + xml[match.end() :], True


def _patch_statement_writer() -> None:
    import excel_renderer.statement_writer as statement_writer

    original = statement_writer._populate_sheet

    def fixed_populate(xml, document):
        updated, modified, created_formulas = original(xml, document)
        items = document.get("items") if isinstance(document, dict) else None
        if isinstance(items, list):
            replaced_formula_refs: set[str] = set()
            for row, item in zip(statement_writer.ITEM_ROWS, items):
                if not isinstance(item, dict):
                    continue
                unit_price = item.get("unit_price")
                supply_amount = item.get("supply_amount")
                if isinstance(unit_price, (int, float, Decimal)) and not isinstance(unit_price, bool):
                    updated, changed = _replace_cell_with_inline_text(
                        statement_writer,
                        updated,
                        f"D{row}",
                        _compact_money(unit_price),
                    )
                    if changed and f"D{row}" not in modified:
                        modified.append(f"D{row}")
                if isinstance(supply_amount, (int, float, Decimal)) and not isinstance(supply_amount, bool):
                    reference = f"E{row}"
                    updated, changed = _replace_cell_with_inline_text(
                        statement_writer,
                        updated,
                        reference,
                        _compact_money(supply_amount),
                    )
                    if changed:
                        replaced_formula_refs.add(reference)
                        if reference not in modified:
                            modified.append(reference)
            created_formulas = [
                reference
                for reference in created_formulas
                if reference not in replaced_formula_refs
            ]
        return updated, modified, created_formulas

    statement_writer._populate_sheet = fixed_populate


def _patch_quotation_writer() -> None:
    import excel_renderer.quotation_writer as quotation_writer

    original = quotation_writer._populate_sheet

    def fixed_populate(xml, document):
        quoted = deepcopy(document)
        items = quoted.get("items")
        totals = quoted.get("totals")
        seller = quoted.get("seller")
        original_contact = {}
        if isinstance(seller, dict):
            contact = seller.get("contact")
            if isinstance(contact, dict):
                original_contact = deepcopy(contact)
            else:
                contact = {}
                seller["contact"] = contact
            # The legacy writer expects an email string. Empty is acceptable for
            # rendering; we replace the footer afterward using only real values.
            contact.setdefault("email", "")

        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                quantity = item.get("quantity")
                line_total = item.get("total")
                if (
                    isinstance(quantity, (int, float, Decimal))
                    and not isinstance(quantity, bool)
                    and Decimal(str(quantity)) != 0
                    and isinstance(line_total, (int, float, Decimal))
                    and not isinstance(line_total, bool)
                ):
                    unit_price = Decimal(str(line_total)) / Decimal(str(quantity))
                    if unit_price == unit_price.to_integral_value():
                        item["unit_price"] = int(unit_price)
                        item["supply_amount"] = line_total
        if isinstance(totals, dict):
            total = totals.get("total")
            if isinstance(total, (int, float, Decimal)) and not isinstance(total, bool):
                totals["supply_amount"] = total

        updated, modified = original(xml, quoted)

        # F28 is the template VAT display row. Keep its row/borders but remove
        # the amount entirely.
        updated, changed = quotation_writer._set_cell(
            updated, "F28", "blank", "", "Quotation"
        )
        if changed and "F28" not in modified:
            modified.append("F28")

        phone = original_contact.get("phone")
        email = original_contact.get("email")
        phone = phone.strip() if isinstance(phone, str) else ""
        email = email.strip() if isinstance(email, str) else ""
        if phone and email:
            footer = f"TEL : {phone} / E-mail : {email}"
        elif phone:
            footer = f"TEL : {phone}"
        elif email:
            footer = f"E-mail : {email}"
        else:
            footer = ""
        updated, changed = quotation_writer._set_cell(
            updated, "A35", "text", footer, "Quotation"
        )
        if changed and "A35" not in modified:
            modified.append("A35")
        return updated, modified

    quotation_writer._populate_sheet = fixed_populate


def _patch_comparison_writer() -> None:
    import excel_renderer.comparison_writer as comparison_writer

    original = comparison_writer._populate_sheet

    def fixed_populate(xml, document):
        compared = deepcopy(document)
        seller = compared.get("seller")
        if isinstance(seller, dict) and not isinstance(seller.get("contact"), dict):
            seller["contact"] = {}
        return original(xml, compared)

    comparison_writer._populate_sheet = fixed_populate


def _normalize_package_pages(package_path: Path) -> None:
    if not package_path.is_file():
        return
    reader = PdfReader(package_path)
    if not reader.pages:
        return
    first = reader.pages[0]
    target_width = float(first.mediabox.width)
    target_height = float(first.mediabox.height)
    writer = PdfWriter()

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if abs(width - target_width) < 0.01 and abs(height - target_height) < 0.01:
            writer.add_page(page)
            continue
        scale = min(target_width / width, target_height / height)
        draw_width = width * scale
        draw_height = height * scale
        tx = (target_width - draw_width) / 2
        ty = (target_height - draw_height) / 2
        canvas = PageObject.create_blank_page(width=target_width, height=target_height)
        canvas.merge_transformed_page(
            page,
            Transformation().scale(scale).translate(tx, ty),
        )
        writer.add_page(canvas)

    temporary = package_path.with_suffix(".normalized.tmp.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(package_path)


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: generate_documents_fixed.py SESSION_DIR DRAFT_JSON")

    draft = json.loads(sys.argv[2])
    sys.argv[2] = json.dumps(
        _sanitize_optional_contacts(draft), ensure_ascii=False, separators=(",", ":")
    )

    _patch_statement_writer()
    _patch_quotation_writer()
    _patch_comparison_writer()

    import generate_documents as base

    result = base.main()
    directory = Path(sys.argv[1]).resolve()
    generated = directory / "generated"
    package_path = generated / "final_package.pdf"
    _normalize_package_pages(package_path)
    if package_path.is_file():
        base._write_exact_package_previews(generated)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
