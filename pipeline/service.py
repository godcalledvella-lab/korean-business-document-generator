"""Atomic OCR, validation, workbook, and fixed-asset orchestration."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pypdf import PdfReader, PdfWriter

from document_generator import RmntcDocumentGenerator
from extraction.models import RawTaxInvoiceData
from extraction.providers import OCRProvider, OCRResult
from extraction.service import ExtractionReport, TaxInvoiceExtractionService

from .mapper import OCRInvoiceMapper


class PipelineError(RuntimeError):
    """Raised when the unified pipeline cannot safely publish its outputs."""

    def __init__(
        self,
        message: str,
        *,
        review_report: Path | None = None,
        invoice_draft: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.review_report = review_report
        self.invoice_draft = invoice_draft


@dataclass(frozen=True)
class FixedAsset:
    name: str
    source_path: Path
    page_index: int
    output_name: str


@dataclass(frozen=True)
class PipelineReport:
    source_path: Path
    provider: str
    invoice_draft: Path
    review_report: Path
    workbooks: Mapping[str, Path]
    fixed_assets: Mapping[str, Path]


class _MappedExtractor:
    def __init__(self, provider: OCRProvider, mapper: OCRInvoiceMapper) -> None:
        self.provider = provider
        self.mapper = mapper
        self.name = provider.name
        self.last_result: OCRResult | None = None

    def extract(self, input_path: str | Path) -> RawTaxInvoiceData:
        result = self.provider.extract(Path(input_path).resolve())
        self.last_result = result
        return result.tax_invoice_data or self.mapper.map(result)


class RmntcGenerationPipeline:
    """Generate all Phase D outputs only after OCR validation succeeds."""

    def __init__(
        self,
        provider: OCRProvider,
        *,
        project_root: str | Path | None = None,
        mapper: OCRInvoiceMapper | None = None,
        document_generator: RmntcDocumentGenerator | None = None,
    ) -> None:
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self.provider = provider
        self.mapper = mapper or OCRInvoiceMapper()
        self.document_generator = document_generator or RmntcDocumentGenerator(
            self.project_root
        )
        reference = self.project_root / "reference/rmntc/rmntc_reference.pdf"
        self.fixed_assets = (
            FixedAsset("business_registration", reference, 4, "business_registration.pdf"),
            FixedAsset("bank_account", reference, 5, "bank_account.pdf"),
        )

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path,
    ) -> PipelineReport:
        source = Path(input_path).resolve()
        destination = Path(output_dir).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        published_draft = destination / "invoice_draft.json"
        published_review = destination / "review_report.md"

        with tempfile.TemporaryDirectory(
            prefix=".rmntc-pipeline-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary)
            extraction = TaxInvoiceExtractionService(
                _MappedExtractor(self.provider, self.mapper)
            ).run(
                source,
                staging / "raw_tax_invoice.json",
                staging / "invoice_draft.json",
                staging / "review_report.md",
            )
            if not extraction.validation.safe_to_approve:
                _publish_review_artifacts(
                    extraction, published_draft, published_review
                )
                raise PipelineError(
                    "OCR validation failed; Excel generation was not started. "
                    f"Review {published_review}.",
                    review_report=published_review,
                    invoice_draft=published_draft,
                )
            readiness_issues = _generation_readiness_issues(
                extraction.draft_output
            )
            if readiness_issues:
                _append_review_section(
                    extraction.review_output,
                    "Generation readiness failures",
                    readiness_issues,
                )
                _publish_review_artifacts(
                    extraction, published_draft, published_review
                )
                raise PipelineError(
                    "Validated draft is missing data required by the existing "
                    f"Excel renderers; review {published_review}.",
                    review_report=published_review,
                    invoice_draft=published_draft,
                )

            generated_dir = staging / "generated"
            generation = self.document_generator.generate(
                extraction.draft_output, generated_dir
            )
            staged_assets = self._prepare_fixed_assets(staging / "assets")
            _append_review_section(
                extraction.review_output,
                "Phase D pipeline status",
                (
                    "OCR validation passed.",
                    "Statement, quotation, and comparison workbooks generated.",
                    "Fixed reference assets prepared without PDF merging.",
                ),
            )
            staged_outputs = {
                destination / "invoice_draft.json": extraction.draft_output,
                destination / "review_report.md": extraction.review_output,
                **{
                    destination / result.output_path.name: result.output_path
                    for result in generation.documents
                },
                **{
                    destination / asset.output_name: staged_assets[asset.name]
                    for asset in self.fixed_assets
                },
            }
            _promote(staged_outputs)

        return PipelineReport(
            source_path=source,
            provider=self.provider.name,
            invoice_draft=published_draft,
            review_report=published_review,
            workbooks={
                name: destination / f"{name}.xlsx"
                for name in ("statement", "quotation", "comparison")
            },
            fixed_assets={
                asset.name: destination / asset.output_name
                for asset in self.fixed_assets
            },
        )

    def _prepare_fixed_assets(self, output_dir: Path) -> dict[str, Path]:
        output_dir.mkdir(parents=True)
        results: dict[str, Path] = {}
        source_hashes: dict[Path, str] = {}
        for asset in self.fixed_assets:
            if not asset.source_path.is_file():
                raise PipelineError(
                    f"Missing fixed asset source: {asset.source_path}"
                )
            source_hashes.setdefault(asset.source_path, _sha256(asset.source_path))
            reader = PdfReader(asset.source_path)
            if asset.page_index >= len(reader.pages):
                raise PipelineError(
                    f"Fixed asset page {asset.page_index + 1} is missing from "
                    f"{asset.source_path}."
                )
            output = output_dir / asset.output_name
            writer = PdfWriter()
            writer.add_page(reader.pages[asset.page_index])
            with output.open("wb") as stream:
                writer.write(stream)
            if len(PdfReader(output).pages) != 1:
                raise PipelineError(f"Invalid fixed asset output: {output}")
            results[asset.name] = output
        for source, before in source_hashes.items():
            if _sha256(source) != before:
                raise PipelineError(f"Fixed asset source changed: {source}")
        return results


def _publish_review_artifacts(
    extraction: ExtractionReport,
    draft: Path,
    review: Path,
) -> None:
    _promote(
        {
            draft: extraction.draft_output,
            review: extraction.review_output,
        }
    )


def _promote(outputs: Mapping[Path, Path]) -> None:
    if not outputs:
        return
    destinations = list(outputs)
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".rmntc-publish-", dir=destinations[0].parent
    ) as temporary:
        backup_dir = Path(temporary)
        backups: dict[Path, Path] = {}
        promoted: list[Path] = []
        try:
            for index, destination in enumerate(destinations):
                if destination.exists():
                    backup = backup_dir / f"{index}.backup"
                    destination.replace(backup)
                    backups[destination] = backup
            for destination, source in outputs.items():
                source.replace(destination)
                promoted.append(destination)
        except Exception:
            for destination in promoted:
                if destination.exists():
                    destination.unlink()
            for destination, backup in backups.items():
                if backup.exists():
                    backup.replace(destination)
            raise


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generation_readiness_issues(draft_path: Path) -> tuple[str, ...]:
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    document = payload.get("document", {})
    seller = document.get("seller", {})
    contact = seller.get("contact", {}) if isinstance(seller, dict) else {}
    issues: list[str] = []
    for field in ("phone", "email"):
        if not isinstance(contact.get(field), str) or not contact[field].strip():
            issues.append(
                f"document.seller.contact.{field} is required by the existing "
                "quotation/comparison renderers."
            )
    return tuple(issues)


def _append_review_section(
    review_path: Path,
    title: str,
    messages: tuple[str, ...],
) -> None:
    existing = review_path.read_text(encoding="utf-8").rstrip()
    section = [existing, "", f"## {title}", ""]
    section.extend(f"- {message}" for message in messages)
    review_path.write_text("\n".join(section) + "\n", encoding="utf-8")
