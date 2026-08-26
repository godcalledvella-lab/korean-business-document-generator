from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "web" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import generate_documents_fixed as fixed  # noqa: E402
import generate_documents_verified as verified  # noqa: E402


def test_blank_optional_contacts_are_removed_without_touching_real_values():
    draft = {
        "document": {
            "seller": {
                "contact": {
                    "name": "  ",
                    "email": " seller@example.com ",
                    "phone": " 010-1234-5678 ",
                }
            },
            "buyer": {
                "contact": {
                    "name": "",
                    "email": "",
                    "phone": "",
                }
            },
        }
    }

    cleaned = fixed._sanitize_optional_contacts(draft)

    assert cleaned["document"]["seller"]["contact"] == {
        "email": "seller@example.com",
        "phone": "010-1234-5678",
    }
    assert "contact" not in cleaned["document"]["buyer"]
    assert draft["document"]["seller"]["contact"]["email"] == " seller@example.com "


def test_compact_money_format_matches_statement_display_rule():
    assert fixed._compact_money(1500) == "₩ 1,500"
    assert fixed._compact_money(109091) == "₩ 109,091"


def test_pdf_normalization_preserves_first_page_size_for_every_page(tmp_path):
    package = tmp_path / "final_package.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=500, height=746)
    writer.add_blank_page(width=595.276, height=841.89)
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=500, height=746)
    writer.add_blank_page(width=595.276, height=841.89)
    writer.add_blank_page(width=500, height=746)
    with package.open("wb") as stream:
        writer.write(stream)

    fixed._normalize_package_pages(package)

    reader = PdfReader(package)
    assert len(reader.pages) == 6
    for page in reader.pages:
        assert abs(float(page.mediabox.width) - 500) < 0.01
        assert abs(float(page.mediabox.height) - 746) < 0.01


def test_refreshed_zip_contains_the_current_normalized_package(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    bundle_name = "RMNTC-test-documents.zip"
    (tmp_path / "session.json").write_text(
        json.dumps({"bundleName": bundle_name}), encoding="utf-8"
    )
    (tmp_path / "approved_invoice.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tax-invoice.pdf").write_bytes(b"invoice-source")
    current_package = b"normalized-package-bytes"
    (generated / "final_package.pdf").write_bytes(current_package)

    verified._refresh_bundle(tmp_path)

    with zipfile.ZipFile(generated / bundle_name) as archive:
        assert archive.read("RMNTC-final-package.pdf") == current_package
        assert archive.read("01-tax-invoice.pdf") == b"invoice-source"
