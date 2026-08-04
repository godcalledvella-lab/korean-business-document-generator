"""Backend-neutral six-page PDF package service."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .backends import BackendRegistry
from .merger import merge_six_pages
from .models import PackageError, PackageInputs, PackageReport, RenderResult
from .validation import PDFValidation, sha256, validate_pdf


class PDFPackageGenerator:
    def __init__(
        self,
        registry: BackendRegistry | None = None,
        *,
        logger: Callable[[str], None] = print,
    ) -> None:
        self.registry = registry or BackendRegistry()
        self.log = logger

    def generate(
        self,
        inputs: PackageInputs,
        output_path: str | Path,
        *,
        backend: str = "auto",
    ) -> PackageReport:
        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        xlsx_inputs = (inputs.statement, inputs.quotation, inputs.comparison)
        original_hashes = {
            path.resolve(): sha256(path.resolve())
            for path in xlsx_inputs
            if path.resolve().is_file()
        }
        with tempfile.TemporaryDirectory(
            prefix=".pdf-package-", dir=output.parent
        ) as temporary:
            work = Path(temporary)
            selected_name: str | None = None
            renders: list[RenderResult] = []
            try:
                self.log("[1/8] Detecting PDF backend...")
                selected, availability = self.registry.select(backend)
                selected_name = selected.name
                version = f" {availability.version}" if availability.version else ""
                self.log(f"✓ Selected {selected.name}{version}: {availability.reason}")

                self.log("[2/8] Validating Page 1 tax invoice...")
                tax_invoice = validate_pdf(
                    inputs.tax_invoice,
                    expected_pages=1,
                    require_a4_portrait=True,
                    step="validating Page 1 tax invoice",
                )
                self.log("✓ Valid one-page A4 portrait PDF")

                generated: list[PDFValidation] = []
                render_jobs = (
                    (3, "Statement", inputs.statement, "page-2-statement.pdf"),
                    (4, "Quotation", inputs.quotation, "page-3-quotation.pdf"),
                    (
                        5,
                        "Comparison",
                        inputs.comparison,
                        "page-4-comparison.pdf",
                    ),
                )
                prepared_jobs = []
                for step_number, label, source, name in render_jobs:
                    self.log(f"[{step_number}/8] Rendering {label} PDF...")
                    source = source.resolve()
                    if not source.is_file():
                        raise PackageError(
                            f"XLSX input is missing: {source}",
                            step=f"rendering {label}",
                            backend=selected.name,
                            working_path=work,
                        )
                    destination = work / name
                    prepared_jobs.append((label, source, destination))

                if selected.name == "libreoffice":
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = [
                            executor.submit(
                                selected.render_xlsx,
                                source,
                                destination,
                            )
                            for _, source, destination in prepared_jobs
                        ]
                        render_results = [future.result() for future in futures]
                else:
                    render_results = [
                        selected.render_xlsx(source, destination)
                        for _, source, destination in prepared_jobs
                    ]

                for (label, source, destination), result in zip(
                    prepared_jobs,
                    render_results,
                ):
                    renders.append(result)
                    if result.source_hash_before != result.source_hash_after:
                        raise PackageError(
                            f"Source XLSX changed during conversion: {source}",
                            step=f"rendering {label}",
                            backend=selected.name,
                            command=result.command,
                            exit_code=result.exit_code,
                            stdout=result.stdout,
                            stderr=result.stderr,
                            working_path=work,
                            sources_unchanged=False,
                        )
                    generated.append(
                        validate_pdf(
                            destination,
                            expected_pages=1,
                            require_a4_portrait=True,
                            step=f"validating {label} PDF",
                        )
                    )
                    self.log(f"✓ Created {destination}")

                self.log("[6/8] Validating fixed PDF assets...")
                business = validate_pdf(
                    inputs.business_registration,
                    expected_pages=1,
                    require_a4_portrait=True,
                    step="validating Business Registration",
                )
                self.log("✓ Business Registration")
                bank = validate_pdf(
                    inputs.bank_account,
                    expected_pages=1,
                    require_a4_portrait=True,
                    step="validating Bank Account Copy",
                )
                self.log("✓ Bank Account Copy")

                self.log("[7/8] Merging six pages...")
                staged_final = work / "final_package.pdf"
                merged = merge_six_pages(
                    (tax_invoice, *generated, business, bank),
                    staged_final,
                )
                self.log("✓ Correct page order")

                self.log("[8/8] Validating final package...")
                if merged.page_count != 6:
                    raise PackageError(
                        f"Final package has {merged.page_count} pages, expected six.",
                        step="validating final package",
                        backend=selected.name,
                        working_path=work,
                    )
                _assert_hashes(original_hashes)
                staged_final.replace(output)
                self.log("✓ Six pages")
                self.log(f"✓ Saved to {output}")
                return PackageReport(
                    output, availability, tuple(renders), merged.page_count
                )
            except PackageError as error:
                if error.backend is None:
                    error.backend = selected_name
                if not error.command and renders:
                    last = renders[-1]
                    error.command = last.command
                    error.exit_code = last.exit_code
                    error.stdout = last.stdout
                    error.stderr = last.stderr
                if error.working_path is None:
                    error.working_path = work
                if error.sources_unchanged is None:
                    error.sources_unchanged = _hashes_unchanged(original_hashes)
                raise
            except Exception as error:
                raise PackageError(
                    str(error),
                    step="unexpected package failure",
                    backend=selected_name,
                    working_path=work,
                    sources_unchanged=_hashes_unchanged(original_hashes),
                ) from error


def _hashes_unchanged(expected: dict[Path, str]) -> bool:
    return all(path.is_file() and sha256(path) == digest for path, digest in expected.items())


def _assert_hashes(expected: dict[Path, str]) -> None:
    if not _hashes_unchanged(expected):
        raise PackageError(
            "One or more source XLSX files changed during package generation.",
            step="validating final package",
            sources_unchanged=False,
        )
