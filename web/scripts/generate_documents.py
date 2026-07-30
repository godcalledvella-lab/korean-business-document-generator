"""Thin web transport adapter over existing generation and package APIs."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from document_generator import RmntcDocumentGenerator
from excel_renderer.review_customizer import (
    REVIEW_SETTINGS_KEY,
    apply_review_settings,
)
from package import PDFPackageGenerator
from package.models import PackageError, PackageInputs
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from workbook_preview import render_workbook_preview


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    directory = Path(sys.argv[1]).resolve()
    draft = json.loads(sys.argv[2])
    approved = directory / "approved_invoice.json"
    approved.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    generated = directory / "generated"
    _clear_derived_outputs(generated)
    report = RmntcDocumentGenerator(ROOT).generate(approved, generated)
    review_settings = draft.get("extensions", {}).get(REVIEW_SETTINGS_KEY)
    if review_settings is not None:
        if not isinstance(review_settings, dict):
            raise ValueError(f"{REVIEW_SETTINGS_KEY} must be an object.")
        apply_review_settings(
            generated / "statement.xlsx",
            generated / "quotation.xlsx",
            generated / "comparison.xlsx",
            review_settings,
        )
    comparison_markup_percentage = float(report.comparison_markup * 100)
    previews = {}
    for document, title in (
        ("statement", "Statement"),
        ("quotation", "Quotation"),
        ("comparison", "Comparison Quotation"),
    ):
        render_workbook_preview(
            generated / f"{document}.xlsx",
            generated / f"{document}.html",
            title=title,
        )
        previews[document] = (
            f"/api/preview/{directory.name}/{document}"
        )
    _prepare_fixed_assets(generated)
    previews.update(
        {
            "taxInvoice": f"/api/preview/{directory.name}/tax-invoice",
            "businessRegistration": (
                f"/api/preview/{directory.name}/business-registration"
            ),
            "bankAccount": f"/api/preview/{directory.name}/bank-account",
        }
    )
    downloads = {
        "taxInvoice": f"/api/download/{directory.name}/tax-invoice",
        **{
            result.document: f"/api/download/{directory.name}/{result.document}"
            for result in report.documents
        },
    }
    package_error = None
    source = next(
        (directory / f"tax-invoice{suffix}" for suffix in (".pdf", ".png", ".jpg", ".jpeg")
         if (directory / f"tax-invoice{suffix}").is_file()),
        None,
    )
    business = generated / "business_registration.pdf"
    bank = generated / "bank_account.pdf"
    if source is not None and source.suffix == ".pdf" and business.is_file() and bank.is_file():
        try:
            _generate_package(generated, source, business, bank)
            downloads["package"] = f"/api/download/{directory.name}/package"
            previews["package"] = f"/api/preview/{directory.name}/package"
            _write_exact_package_previews(generated)
            for document in ("statement", "quotation", "comparison"):
                previews[document] = f"/api/preview/{directory.name}/{document}"
        except PackageError as error:
            print(error.diagnostics(), file=sys.stderr)
            package_error = str(error)
        except Exception as error:
            print(f"Unexpected package failure: {error}", file=sys.stderr)
            package_error = str(error)
    elif source is not None and source.suffix != ".pdf" and business.is_file() and bank.is_file():
        try:
            page_one = generated / "page-1-tax-invoice.pdf"
            _image_to_a4_pdf(source, page_one)
            _generate_package(generated, page_one, business, bank)
            downloads["package"] = f"/api/download/{directory.name}/package"
            previews["package"] = f"/api/preview/{directory.name}/package"
            _write_exact_package_previews(generated)
            for document in ("statement", "quotation", "comparison"):
                previews[document] = f"/api/preview/{directory.name}/{document}"
        except PackageError as error:
            print(error.diagnostics(), file=sys.stderr)
            package_error = str(error)
        except Exception as error:
            print(f"Unexpected package failure: {error}", file=sys.stderr)
            package_error = str(error)
    elif source is None:
        package_error = "The original tax invoice is missing."
    else:
        package_error = "One or more fixed PDF assets are unavailable."

    bundle_name = _bundle_filename(draft)
    _write_download_bundle(
        directory,
        generated,
        source,
        bundle_name,
    )
    downloads["bundle"] = f"/api/download/{directory.name}/bundle"

    session_path = directory / "session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    session["draft"] = draft
    session["downloads"] = downloads
    session["previews"] = previews
    session["previewMode"] = "pdf" if "package" in previews else "html"
    session["packageError"] = package_error
    session["bundleName"] = bundle_name
    session["comparisonMarkupPercentage"] = comparison_markup_percentage
    session["reviewSettings"] = review_settings
    session_path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "downloads": downloads,
                "previews": previews,
                "previewMode": session["previewMode"],
                "packageError": package_error,
                "bundleName": bundle_name,
                "comparisonMarkupPercentage": comparison_markup_percentage,
            }
        )
    )
    return 0


def _generate_package(
    generated: Path,
    tax_invoice_pdf: Path,
    business: Path,
    bank: Path,
) -> None:
    PDFPackageGenerator(logger=lambda message: print(message, file=sys.stderr)).generate(
                PackageInputs(
                    tax_invoice_pdf,
                    generated / "statement.xlsx",
                    generated / "quotation.xlsx",
                    generated / "comparison.xlsx",
                    business,
                    bank,
                ),
                generated / "final_package.pdf",
                backend=os.environ.get("PDF_BACKEND", "auto"),
            )


def _write_exact_package_previews(generated: Path) -> None:
    reader = PdfReader(generated / "final_package.pdf")
    if len(reader.pages) != 6:
        raise ValueError("Final package must contain exactly six pages.")
    for page_index, name in (
        (1, "page-2-statement.pdf"),
        (2, "page-3-quotation.pdf"),
        (3, "page-4-comparison.pdf"),
    ):
        writer = PdfWriter()
        writer.add_page(reader.pages[page_index])
        with (generated / name).open("wb") as stream:
            writer.write(stream)


def _image_to_a4_pdf(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        width, height = image.size
        page_width, page_height = A4
        margin = 18
        scale = min(
            (page_width - margin * 2) / width,
            (page_height - margin * 2) / height,
        )
        draw_width = width * scale
        draw_height = height * scale
        output = canvas.Canvas(str(destination), pagesize=A4)
        output.drawImage(
            ImageReader(image.convert("RGB")),
            (page_width - draw_width) / 2,
            (page_height - draw_height) / 2,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
        )
        output.showPage()
        output.save()


def _bundle_filename(draft: dict) -> str:
    invoice_number = str(
        draft.get("document", {}).get("invoice_number") or "invoice"
    )
    safe_number = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in invoice_number
    ).strip("-")
    base = safe_number or "invoice"
    if not base.upper().startswith("RMNTC-"):
        base = f"RMNTC-{base}"
    return f"{base}-documents.zip"


def _write_download_bundle(
    directory: Path,
    generated: Path,
    source: Path | None,
    bundle_name: str,
) -> None:
    entries: list[tuple[Path, str]] = [
        (directory / "approved_invoice.json", "approved-invoice.json"),
        (generated / "statement.xlsx", "02-statement.xlsx"),
        (generated / "quotation.xlsx", "03-quotation.xlsx"),
        (generated / "comparison.xlsx", "04-comparison-quotation.xlsx"),
        (generated / "business_registration.pdf", "05-business-registration.pdf"),
        (generated / "bank_account.pdf", "06-bank-account.pdf"),
        (generated / "statement.html", "previews/02-statement.html"),
        (generated / "quotation.html", "previews/03-quotation.html"),
        (generated / "comparison.html", "previews/04-comparison-quotation.html"),
    ]
    if source is not None:
        entries.insert(
            0,
            (source, f"01-tax-invoice{source.suffix.lower()}"),
        )
    final_package = generated / "final_package.pdf"
    if final_package.is_file():
        entries.append((final_package, "RMNTC-final-package.pdf"))

    destination = generated / bundle_name
    with tempfile.NamedTemporaryFile(
        prefix=".download-bundle-",
        suffix=".zip",
        dir=generated,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for source_path, archive_name in entries:
                if source_path.is_file():
                    archive.write(source_path, archive_name)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare_fixed_assets(generated: Path) -> None:
    reference = ROOT / "reference/rmntc/rmntc_reference.pdf"
    reader = PdfReader(reference)
    for page_index, name in (
        (4, "business_registration.pdf"),
        (5, "bank_account.pdf"),
    ):
        output = generated / name
        writer = PdfWriter()
        writer.add_page(reader.pages[page_index])
        with output.open("wb") as stream:
            writer.write(stream)


def _clear_derived_outputs(generated: Path) -> None:
    """Prevent a failed regeneration from exposing stale package artifacts."""
    for name in (
        "final_package.pdf",
        "page-1-tax-invoice.pdf",
        "page-2-statement.pdf",
        "page-3-quotation.pdf",
        "page-4-comparison.pdf",
    ):
        (generated / name).unlink(missing_ok=True)
    for bundle in generated.glob("RMNTC-*-documents.zip"):
        bundle.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
