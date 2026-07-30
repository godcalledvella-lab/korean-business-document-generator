"""Strict PDF and source-workbook validation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from .models import PackageError


A4_WIDTH = 595.2756
A4_HEIGHT = 841.8898
A4_TOLERANCE = 5.0


@dataclass(frozen=True)
class PDFValidation:
    path: Path
    page_count: int
    page_fingerprints: tuple[str, ...]


def validate_pdf(
    path: Path,
    *,
    expected_pages: int,
    require_a4_portrait: bool,
    require_nonblank: bool = True,
    step: str,
) -> PDFValidation:
    source = path.resolve()
    if not source.is_file():
        raise PackageError(f"PDF is missing: {source}", step=step)
    data = source.read_bytes()
    if len(data) < 100 or not data.startswith(b"%PDF-"):
        raise PackageError(f"PDF is blank or has an invalid header: {source}", step=step)
    try:
        reader = PdfReader(source, strict=True)
        if reader.is_encrypted:
            raise PackageError(f"Encrypted PDF is unsupported: {source}", step=step)
        pages = tuple(reader.pages)
    except PackageError:
        raise
    except Exception as error:
        raise PackageError(f"Corrupt PDF {source}: {error}", step=step) from error
    if len(pages) != expected_pages:
        raise PackageError(
            f"Expected {expected_pages} page(s), found {len(pages)} in {source}.",
            step=step,
        )
    fingerprints: list[str] = []
    for number, page in enumerate(pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if require_a4_portrait and (
            width >= height
            or abs(width - A4_WIDTH) > A4_TOLERANCE
            or abs(height - A4_HEIGHT) > A4_TOLERANCE
        ):
            raise PackageError(
                f"Page {number} is not A4 portrait ({width:.2f} x {height:.2f} pt): "
                f"{source}",
                step=step,
            )
        content = _page_content(page)
        if require_nonblank and not _has_visible_content(page, content):
            raise PackageError(f"Page {number} appears blank: {source}", step=step)
        fingerprints.append(_fingerprint(page, content))
    return PDFValidation(source, len(pages), tuple(fingerprints))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _page_content(page: object) -> bytes:
    contents = page.get_contents()
    if contents is None:
        return b""
    try:
        return contents.get_data()
    except AttributeError:
        return b""


def _has_visible_content(page: object, content: bytes) -> bool:
    if (page.extract_text() or "").strip():
        return True
    resources = page.get("/Resources") or {}
    if resources.get("/XObject"):
        return True
    visible_operators = (b" Tj", b" TJ", b" Do", b" re", b" m", b" l", b"BI")
    return any(operator in content for operator in visible_operators)


def _fingerprint(page: object, content: bytes) -> str:
    dimensions = (
        f"{float(page.mediabox.width):.4f}:"
        f"{float(page.mediabox.height):.4f}:"
        f"{int(page.get('/Rotate', 0) or 0)}"
    ).encode()
    text = (page.extract_text() or "").encode("utf-8")
    return hashlib.sha256(dimensions + b"\0" + content + b"\0" + text).hexdigest()
