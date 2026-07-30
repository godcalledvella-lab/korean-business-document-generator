"""Command-line interface for unified RMNTC workbook generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .service import GenerationError, RmntcDocumentGenerator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate all Excel documents for one canonical invoice."
    )
    parser.add_argument("input", type=Path, help="Canonical invoice JSON")
    parser.add_argument(
        "--company",
        required=True,
        choices=("rmntc",),
        help="Company template set",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Final workbook directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    generator = RmntcDocumentGenerator()
    source = args.input.resolve()
    markup, templates = generator.configuration()

    print(f"Source JSON: {source}", flush=True)
    print(f"Company: {args.company}", flush=True)
    for spec in templates:
        print(f"Template ({spec.document}): {spec.template_path}", flush=True)
    print(f"Comparison markup: {markup} ({markup * 100}%)", flush=True)

    try:
        report = generator.generate(source, args.output_dir)
    except GenerationError as error:
        for spec in templates:
            status = error.statuses.get(spec.document, "not run")
            print(f"{spec.document.capitalize()}: {status}")
        print(f"Generation failed: {error}", file=sys.stderr)
        return 1

    for result in report.documents:
        print(f"{result.document.capitalize()}: {result.status}")
        print(f"  Output: {result.output_path}")
        print(f"  Total: {result.total}")
    print("Generation succeeded: all RMNTC workbooks were published atomically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
