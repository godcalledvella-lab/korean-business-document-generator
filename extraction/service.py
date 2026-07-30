"""Local inspection, manual-provider extraction, and review artifact generation."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from .models import RawTaxInvoiceData, TaxInvoiceExtractor
from .normalizer import NormalizationResult, normalize_tax_invoice
from .validator import ExtractionValidationReport, validate_tax_invoice


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


class ExtractionError(RuntimeError):
    """Raised when inspection or extraction cannot complete safely."""


@dataclass(frozen=True)
class DocumentInspection:
    path: Path
    source_type: str
    page_count: int
    sha256: str


@dataclass(frozen=True)
class ExtractionReport:
    inspection: DocumentInspection
    raw_output: Path
    draft_output: Path
    review_output: Path
    validation: ExtractionValidationReport
    provider: str


class ManualJsonTaxInvoiceExtractor:
    """Development provider that reads explicitly supplied reviewed raw JSON."""

    name = "manual-json"

    def __init__(self, raw_json_path: str | Path) -> None:
        self.raw_json_path = Path(raw_json_path).resolve()

    def extract(self, input_path: str | Path) -> RawTaxInvoiceData:
        try:
            payload = json.loads(self.raw_json_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ExtractionError(
                f"Could not read manual extraction JSON {self.raw_json_path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise ExtractionError(
                f"Manual extraction JSON is invalid at line {error.lineno}, "
                f"column {error.colno}: {self.raw_json_path}"
            ) from error
        if not isinstance(payload, dict):
            raise ExtractionError("Manual extraction JSON must be an object.")
        return RawTaxInvoiceData.from_dict(payload, provider=self.name)


class TaxInvoiceExtractionService:
    """Inspect one-page input and produce raw, draft, and review artifacts."""

    def __init__(
        self,
        extractor: TaxInvoiceExtractor,
        *,
        schema_path: str | Path | None = None,
    ) -> None:
        self.extractor = extractor
        self.schema_path = (
            Path(schema_path).resolve()
            if schema_path is not None
            else Path(__file__).resolve().parents[1] / "configs/invoice.schema.json"
        )

    def run(
        self,
        input_path: str | Path,
        raw_output: str | Path,
        draft_output: str | Path,
        review_output: str | Path,
    ) -> ExtractionReport:
        source = Path(input_path).resolve()
        source_hash = _sha256(source)
        inspection = inspect_document(source)
        raw = self.extractor.extract(source).with_source(
            source_path=source,
            source_type=inspection.source_type,
            source_sha256=source_hash,
        )
        normalized = normalize_tax_invoice(raw)
        validation = validate_tax_invoice(raw, normalized, self.schema_path)
        if _sha256(source) != source_hash:
            raise ExtractionError("Source tax-invoice input changed during extraction.")

        raw_path = Path(raw_output).resolve()
        draft_path = Path(draft_output).resolve()
        review_path = Path(review_output).resolve()
        _write_artifacts(
            raw_path,
            raw.to_dict(),
            draft_path,
            normalized.draft,
            review_path,
            _review_markdown(raw, normalized, validation),
        )
        return ExtractionReport(
            inspection=inspection,
            raw_output=raw_path,
            draft_output=draft_path,
            review_output=review_path,
            validation=validation,
            provider=self.extractor.name,
        )


def inspect_document(path: Path) -> DocumentInspection:
    if not path.is_file():
        raise ExtractionError(f"Tax-invoice input does not exist: {path}")
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(
            f"Unsupported tax-invoice input type {extension!r}; "
            "expected PDF, PNG, JPG, or JPEG."
        )
    try:
        if extension == ".pdf":
            page_count = len(PdfReader(path).pages)
            source_type = "pdf"
        else:
            with Image.open(path) as image:
                image.verify()
            page_count = 1
            source_type = extension.lstrip(".").replace("jpeg", "jpg")
    except (OSError, UnidentifiedImageError, Exception) as error:
        if isinstance(error, ExtractionError):
            raise
        raise ExtractionError(f"Could not inspect tax-invoice input {path}: {error}") from error
    if page_count != 1:
        raise ExtractionError(
            f"Tax-invoice input must contain exactly one page; found {page_count}."
        )
    return DocumentInspection(path, source_type, page_count, _sha256(path))


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ExtractionError(f"Could not read tax-invoice input {path}: {error}") from error


def _write_artifacts(
    raw_path: Path,
    raw_payload: dict[str, Any],
    draft_path: Path,
    draft_payload: dict[str, Any],
    review_path: Path,
    review_text: str,
) -> None:
    parents = {path.parent for path in (raw_path, draft_path, review_path)}
    for parent in parents:
        parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".tax-invoice-extraction-",
        dir=raw_path.parent,
    ) as temporary:
        staging = Path(temporary)
        staged = {
            raw_path: staging / "raw.json",
            draft_path: staging / "draft.json",
            review_path: staging / "review.md",
        }
        staged[raw_path].write_text(
            json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staged[draft_path].write_text(
            json.dumps(draft_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staged[review_path].write_text(review_text, encoding="utf-8")
        for destination, source in staged.items():
            source.replace(destination)


def _flatten_raw(raw: RawTaxInvoiceData) -> list[tuple[str, Any, float | None]]:
    rows: list[tuple[str, Any, float | None]] = []
    payload = raw.to_dict()

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict) and "value" in value and "confidence" in value:
            rows.append((prefix, value["value"], value["confidence"]))
        elif isinstance(value, dict):
            for key, item in value.items():
                if key not in {"provider", "source_path", "source_type", "source_sha256"}:
                    walk(f"{prefix}.{key}" if prefix else key, item)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(f"{prefix}[{index}]", item)

    walk("", payload)
    return rows


def _section(title: str, values: tuple[str, ...], empty: str) -> list[str]:
    lines = [f"## {title}", ""]
    lines.extend(f"- `{value}`" for value in values)
    if not values:
        lines.append(f"- {empty}")
    lines.append("")
    return lines


def _review_markdown(
    raw: RawTaxInvoiceData,
    normalized: NormalizationResult,
    report: ExtractionValidationReport,
) -> str:
    lines = [
        "# Korean Tax Invoice Extraction Review",
        "",
        f"- Provider: `{raw.provider}`",
        f"- Source: `{raw.source_path}`",
        f"- Source type: `{raw.source_type}`",
        f"- Source SHA-256: `{raw.source_sha256}`",
        f"- Canonical schema conformant: **{'yes' if report.schema_conformant else 'no'}**",
        f"- Safe to approve after human review: **{'yes' if report.safe_to_approve else 'no'}**",
        "- Human review completed: **no**",
        "",
        "## Extracted fields",
        "",
        "| Field | Raw value | Confidence |",
        "|---|---|---:|",
    ]
    for path, value, confidence in _flatten_raw(raw):
        display = "null" if value is None else str(value).replace("|", "\\|")
        score = "" if confidence is None else f"{confidence:.0%}"
        lines.append(f"| `{path}` | {display} | {score} |")
    lines.append("")
    lines.extend(
        _section(
            "Missing required fields",
            report.missing_required_fields,
            "None detected.",
        )
    )
    lines.extend(
        _section(
            "Low-confidence fields",
            report.low_confidence_fields,
            "None detected.",
        )
    )
    lines.extend(
        _section(
            "Arithmetic mismatches",
            report.arithmetic_mismatches,
            "None detected.",
        )
    )
    lines.extend(
        _section(
            "Fields requiring manual confirmation",
            report.manual_confirmation_fields,
            "No field-specific blocker detected; all fields still require human review.",
        )
    )
    lines.extend(["## Validation details", ""])
    for issue in report.issues:
        detail = f"- **{issue.severity.upper()}** `{issue.field}`: {issue.message}"
        if issue.expected is not None or issue.actual is not None:
            detail += f" Expected `{issue.expected}`, actual `{issue.actual}`."
        lines.append(detail)
    if not report.issues:
        lines.append("- No validation issues detected.")
    lines.extend(["", "## Normalization notes", ""])
    lines.extend(f"- {note}" for note in normalized.normalization_notes)
    lines.extend(
        [
            "",
            "## Approval gate",
            "",
            "This Phase 2A draft has **not** triggered document generation.",
            "A human must compare the draft with Page 1 and explicitly approve a",
            "schema-conformant canonical invoice before downstream generation.",
            "",
        ]
    )
    return "\n".join(lines)
