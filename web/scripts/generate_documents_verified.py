"""Final web-generation adapter that keeps the ZIP bundle in sync with the PDF.

``generate_documents_fixed`` normalizes the published six-page PDF after the
base generator has already written the download ZIP. Rebuild the bundle once
more so ``RMNTC-final-package.pdf`` inside the ZIP is byte-for-byte the same as
the direct package download.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import generate_documents as base
import generate_documents_fixed as fixed


def _source_invoice(directory: Path) -> Path | None:
    return next(
        (
            directory / f"tax-invoice{suffix}"
            for suffix in (".pdf", ".png", ".jpg", ".jpeg")
            if (directory / f"tax-invoice{suffix}").is_file()
        ),
        None,
    )


def _refresh_bundle(directory: Path) -> None:
    session_path = directory / "session.json"
    if not session_path.is_file():
        return
    session = json.loads(session_path.read_text(encoding="utf-8"))
    bundle_name = session.get("bundleName")
    if not isinstance(bundle_name, str) or not bundle_name:
        return
    generated = directory / "generated"
    base._write_download_bundle(
        directory,
        generated,
        _source_invoice(directory),
        bundle_name,
    )


def main() -> int:
    result = fixed.main()
    _refresh_bundle(Path(sys.argv[1]).resolve())
    return result


if __name__ == "__main__":
    raise SystemExit(main())
