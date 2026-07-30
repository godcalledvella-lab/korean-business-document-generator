"""CLI for local Phase 2A tax-invoice extraction artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .providers import (
    DEFAULT_PROVIDER_REGISTRY,
    OCRTaxInvoiceExtractor,
)
from .service import (
    ExtractionError,
    TaxInvoiceExtractionService,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect one Korean tax invoice and create reviewable extraction artifacts. "
            "No downstream document generation is performed."
        )
    )
    parser.add_argument("input", type=Path, help="One-page PDF, PNG, JPG, or JPEG")
    parser.add_argument(
        "--raw-output",
        type=Path,
        help="Structured raw extraction JSON (requires --draft-output)",
    )
    parser.add_argument(
        "--draft-output",
        type=Path,
        help="Canonical draft JSON (requires --raw-output)",
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=Path("output/extraction/review_report.md"),
    )
    parser.add_argument(
        "--provider",
        choices=DEFAULT_PROVIDER_REGISTRY.names(),
        help="Configured local extraction provider",
    )
    parser.add_argument(
        "--mock-json",
        type=Path,
        help="Deterministic structured JSON fixture required by --provider mock",
    )
    parser.add_argument(
        "--manual-json",
        type=Path,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.provider is None:
        print(
            "error: no OCR provider selected. Choose --provider mock for "
            "development or another registered provider stub.",
            file=sys.stderr,
        )
        return 2
    if (args.raw_output is None) != (args.draft_output is None):
        print(
            "error: --raw-output and --draft-output must be supplied together.",
            file=sys.stderr,
        )
        return 2
    mock_json = args.mock_json or args.manual_json
    if args.provider == "mock" and mock_json is None:
        print(
            "error: --provider mock requires --mock-json <fixture.json>.",
            file=sys.stderr,
        )
        return 2
    try:
        provider = (
            DEFAULT_PROVIDER_REGISTRY.create(
                args.provider,
                fixture_path=mock_json,
            )
            if args.provider == "mock"
            else DEFAULT_PROVIDER_REGISTRY.create(args.provider)
        )
        if args.raw_output is None:
            result = provider.extract(args.input)
            print(f"Provider: {result.provider_name}")
            print(f"Source: {args.input.resolve()}")
            print(f"Pages: {result.page_count}")
            print(f"Language: {result.language or 'unknown'}")
            print(
                "Confidence: "
                + (
                    f"{result.confidence:.6f}"
                    if result.confidence is not None
                    else "unavailable"
                )
            )
            print(f"Text regions: {len(result.text_regions)}")
            print(f"Tables: {len(result.detected_tables)}")
            print("Raw text:")
            print(result.raw_text)
            print("Document generation triggered: no")
            return 0

        report = TaxInvoiceExtractionService(OCRTaxInvoiceExtractor(provider)).run(
            args.input,
            args.raw_output,
            args.draft_output,
            args.review_output,
        )
    except (
        ExtractionError,
        FileNotFoundError,
        NotImplementedError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Provider: {report.provider}")
    print(f"Source: {report.inspection.path}")
    print(f"Source SHA-256: {report.inspection.sha256}")
    print(f"Raw output: {report.raw_output}")
    print(f"Draft output: {report.draft_output}")
    print(f"Review report: {report.review_output}")
    print(f"Schema conformant: {report.validation.schema_conformant}")
    print(f"Safe to approve after human review: {report.validation.safe_to_approve}")
    print("Document generation triggered: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
