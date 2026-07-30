"""CLI for the six-page customer PDF package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .models import PackageError, PackageInputs
from .service import PDFPackageGenerator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the six-page PDF package.")
    parser.add_argument("--tax-invoice", required=True, type=Path)
    parser.add_argument("--statement", required=True, type=Path)
    parser.add_argument("--quotation", required=True, type=Path)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--business-registration", required=True, type=Path)
    parser.add_argument("--bank-account", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--backend",
        choices=("auto", "libreoffice", "excel"),
        default="auto",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = PackageInputs(
        args.tax_invoice,
        args.statement,
        args.quotation,
        args.comparison,
        args.business_registration,
        args.bank_account,
    )
    try:
        PDFPackageGenerator().generate(
            inputs, args.output, backend=args.backend
        )
    except PackageError as error:
        print(error.diagnostics(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
