"""PDF backend registration, detection, and selection."""

from __future__ import annotations

from collections.abc import Iterable

from package.models import BackendAvailability, PackageError

from .base import PDFBackend
from .libreoffice import LibreOfficeBackend
from .microsoft_excel import MicrosoftExcelBackend


class BackendRegistry:
    def __init__(self, backends: Iterable[PDFBackend] | None = None) -> None:
        configured = backends or (LibreOfficeBackend(), MicrosoftExcelBackend())
        self.backends = {backend.name: backend for backend in configured}

    def detect(self) -> tuple[BackendAvailability, ...]:
        return tuple(backend.availability() for backend in self.backends.values())

    def select(
        self, requested: str = "auto"
    ) -> tuple[PDFBackend, BackendAvailability]:
        if requested not in {"auto", *self.backends}:
            raise PackageError(
                f"Unsupported PDF backend {requested!r}.",
                step="detecting PDF backend",
            )
        if requested != "auto":
            backend = self.backends[requested]
            availability = backend.availability()
            if not availability.available:
                raise PackageError(
                    f"Requested backend {requested!r} is unavailable: "
                    f"{availability.reason}",
                    step="detecting PDF backend",
                    backend=requested,
                )
            return backend, availability
        detected = {item.name: item for item in self.detect()}
        for name in ("libreoffice", "excel"):
            availability = detected.get(name)
            if availability and availability.available:
                return self.backends[name], availability
        reasons = "; ".join(
            f"{item.name}: {item.reason}" for item in detected.values()
        )
        raise PackageError(
            f"No supported PDF backend is available. {reasons}",
            step="detecting PDF backend",
        )
