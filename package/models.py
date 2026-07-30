"""Shared package and backend result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackendAvailability:
    name: str
    available: bool
    reason: str
    version: str | None = None


@dataclass(frozen=True)
class RenderResult:
    backend: str
    source: Path
    output: Path
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    source_hash_before: str
    source_hash_after: str


@dataclass(frozen=True)
class PackageInputs:
    tax_invoice: Path
    statement: Path
    quotation: Path
    comparison: Path
    business_registration: Path
    bank_account: Path


@dataclass(frozen=True)
class PackageReport:
    output: Path
    backend: BackendAvailability
    renders: tuple[RenderResult, ...]
    page_count: int


class PackageError(RuntimeError):
    """Failure with execution diagnostics suitable for CLI reporting."""

    def __init__(
        self,
        message: str,
        *,
        step: str,
        backend: str | None = None,
        command: tuple[str, ...] = (),
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        working_path: Path | None = None,
        sources_unchanged: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.step = step
        self.backend = backend
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.working_path = working_path
        self.sources_unchanged = sources_unchanged

    def diagnostics(self) -> str:
        command = " ".join(self.command) if self.command else "<not executed>"
        unchanged = (
            "unknown"
            if self.sources_unchanged is None
            else ("yes" if self.sources_unchanged else "no")
        )
        return "\n".join(
            (
                f"Failed step: {self.step}",
                f"Backend: {self.backend or '<not selected>'}",
                f"Command: {command}",
                f"Exit code: {self.exit_code if self.exit_code is not None else '<none>'}",
                f"Stdout: {self.stdout or '<empty>'}",
                f"Stderr: {self.stderr or '<empty>'}",
                f"Temporary working path: {self.working_path or '<none>'}",
                f"Source files unchanged: {unchanged}",
                f"Error: {self}",
            )
        )
