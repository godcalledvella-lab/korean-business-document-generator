"""CLI for the unified OCR-to-RMNTC generation pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from extraction.providers import DEFAULT_PROVIDER_REGISTRY

from .service import PipelineError, RmntcGenerationPipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract and validate one tax invoice, then generate RMNTC files."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--provider",
        required=True,
        choices=DEFAULT_PROVIDER_REGISTRY.names(),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--mock-json",
        type=Path,
        help="Structured fixture required when --provider mock is selected",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.provider == "mock" and args.mock_json is None:
        print("error: --provider mock requires --mock-json.", file=sys.stderr)
        return 2
    try:
        provider = (
            DEFAULT_PROVIDER_REGISTRY.create(
                "mock", fixture_path=args.mock_json
            )
            if args.provider == "mock"
            else DEFAULT_PROVIDER_REGISTRY.create(args.provider)
        )
        report = RmntcGenerationPipeline(provider).run(args.input, args.output)
    except (PipelineError, RuntimeError, ValueError, OSError) as error:
        print(f"Pipeline failed: {error}", file=sys.stderr)
        return 1

    print(f"Source: {report.source_path}")
    print(f"OCR provider: {report.provider}")
    print(f"Invoice draft: {report.invoice_draft}")
    print(f"Review report: {report.review_report}")
    for name, path in report.workbooks.items():
        print(f"{name.capitalize()}: {path}")
    for name, path in report.fixed_assets.items():
        print(f"{name.replace('_', ' ').title()}: {path}")
    print("Pipeline succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
