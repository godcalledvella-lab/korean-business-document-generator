"""Backend-neutral Excel-to-PDF interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from package.models import BackendAvailability, PackageError, RenderResult


class BackendRenderError(PackageError):
    """A selected backend failed to render one workbook."""


class PDFBackend(ABC):
    name: str

    @abstractmethod
    def availability(self) -> BackendAvailability:
        """Return availability and a human-readable reason."""

    @abstractmethod
    def render_xlsx(self, input_path: Path, output_path: Path) -> RenderResult:
        """Render one copied workbook to one PDF."""
