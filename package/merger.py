"""Exact-order PDF merging."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from pypdf import PdfReader, PdfWriter

from .models import PackageError
from .validation import PDFValidation, validate_pdf


def merge_six_pages(
    ordered_inputs: Sequence[PDFValidation],
    output_path: Path,
) -> PDFValidation:
    if len(ordered_inputs) != 6 or any(item.page_count != 1 for item in ordered_inputs):
        raise PackageError(
            "Merge requires exactly six validated one-page inputs.",
            step="merging six pages",
        )
    writer = PdfWriter()
    for item in ordered_inputs:
        writer.add_page(PdfReader(item.path, strict=True).pages[0])
    with output_path.open("wb") as stream:
        writer.write(stream)
    merged = validate_pdf(
        output_path,
        expected_pages=6,
        require_a4_portrait=True,
        step="validating final package",
    )
    expected = tuple(item.page_fingerprints[0] for item in ordered_inputs)
    if merged.page_fingerprints != expected:
        raise PackageError(
            "Final PDF page order or page content differs from the validated inputs.",
            step="merging six pages",
        )
    return merged
