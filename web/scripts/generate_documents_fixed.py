"""RMNTC web-generation fixes layered over the stable document generator.

This adapter keeps the core template writers untouched while applying the reviewed
business/document rules used by the web app:
- blank optional contact fields are omitted before canonical validation;
- the blue quotation uses VAT-included line totals as its commercial quote base;
- the blue quotation does not display a separate VAT row;
- final package pages are normalized to one page size without stretching content.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

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


def _patch_quotation_writer() -> None:
    import excel_renderer.quotation_writer as quotation_writer

    original = quotation_writer._populate_sheet

    def fixed_populate(xml, document):
        quoted = deepcopy(document)
        items = quoted.get("items")
        totals = quoted.get("totals")
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
        # F28 is the template VAT display row. The approved RMNTC quotation
        # keeps that row's space/borders but intentionally shows no VAT amount.
        updated, changed = quotation_writer._set_cell(
            updated, "F28", "blank", "", "Quotation"
        )
        if changed and "F28" not in modified:
            modified.append("F28")
        return updated, modified

    quotation_writer._populate_sheet = fixed_populate


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

    _patch_quotation_writer()

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
