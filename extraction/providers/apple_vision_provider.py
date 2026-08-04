"""Apple Vision text-recognition adapter for local macOS extraction."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Protocol, Sequence

from .base import BoundingBox, OCRProvider, OCRResult, OCRTextRegion


class AppleVisionUnavailableError(RuntimeError):
    """Raised when the native Apple Vision runtime cannot be used."""


@dataclass(frozen=True)
class AppleVisionAvailability:
    available: bool
    reason: str
    macos_version: str | None = None


@dataclass(frozen=True)
class AppleVisionObservation:
    """Provider-internal Vision observation using normalized lower-left coordinates."""

    page: int
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float | None = None


class AppleVisionEngine(Protocol):
    def recognize(self, path: Path, languages: Sequence[str]) -> tuple[
        int, Sequence[AppleVisionObservation]
    ]: ...


class AppleVisionProvider(OCRProvider):
    """Return provider-neutral Korean OCR without document/table recognition."""

    provider_name = "apple-vision"
    supported_extensions = frozenset({".pdf", ".png", ".jpg", ".jpeg"})

    def __init__(
        self,
        *,
        engine: AppleVisionEngine | None = None,
        languages: Sequence[str] = ("ko-KR", "en-US"),
    ) -> None:
        self._engine = engine
        self.languages = tuple(languages)
        if not self.languages:
            raise ValueError("Apple Vision requires at least one recognition language.")

    @classmethod
    def availability(cls) -> AppleVisionAvailability:
        if platform.system() != "Darwin":
            return AppleVisionAvailability(
                False, "Apple Vision OCR is available only on macOS."
            )
        version = platform.mac_ver()[0] or None
        if version is not None and _version_tuple(version) < (10, 15):
            return AppleVisionAvailability(
                False,
                "Apple Vision text recognition requires macOS 10.15 or later.",
                version,
            )
        try:
            __import__("Vision")
            __import__("Foundation")
            __import__("Quartz")
        except (ImportError, ModuleNotFoundError) as error:
            return AppleVisionAvailability(
                False,
                "The bundled Apple Vision bridge is unavailable "
                f"({type(error).__name__}: {error}).",
                version,
            )
        return AppleVisionAvailability(True, "Apple Vision OCR is available.", version)

    def extract(self, path: Path) -> OCRResult:
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"OCR input does not exist: {source}")
        if source.suffix.lower() not in self.supported_extensions:
            supported = ", ".join(sorted(self.supported_extensions))
            raise ValueError(
                f"Unsupported Apple Vision input type {source.suffix!r}; "
                f"expected one of: {supported}."
            )

        engine = self._engine
        if engine is None:
            availability = self.availability()
            if not availability.available:
                raise AppleVisionUnavailableError(availability.reason)
            engine = _PyObjCAppleVisionEngine()

        page_count, observations = engine.recognize(source, self.languages)
        if page_count < 1:
            raise ValueError("Apple Vision returned an invalid page count.")

        regions = tuple(
            OCRTextRegion(
                observation.text.strip(),
                _normalized_top_left_box(observation),
                _confidence(observation.confidence),
            )
            for observation in observations
            if observation.text.strip()
        )
        regions = tuple(
            sorted(
                regions,
                key=lambda region: (
                    region.bounding_box.page,
                    region.bounding_box.y,
                    region.bounding_box.x,
                ),
            )
        )
        confidences = [
            region.confidence
            for region in regions
            if region.confidence is not None
        ]
        warnings = (
            ()
            if regions
            else (
                "Apple Vision found no readable text. Manual Review confirmation "
                "is required.",
            )
        )
        return OCRResult(
            page_count=page_count,
            language="ko",
            raw_text="\n".join(region.text for region in regions),
            detected_tables=(),
            text_regions=regions,
            confidence=fmean(confidences) if confidences else None,
            provider_name=self.provider_name,
            provider_metadata={
                "pipeline": "Apple Vision text recognition",
                "languages": self.languages,
                "normalized_bounding_boxes": True,
                "table_recognition": False,
                "warnings": warnings,
            },
        )


class _PyObjCAppleVisionEngine:
    """Small lazy PyObjC bridge; no Apple framework object crosses OCRResult."""

    def recognize(
        self, path: Path, languages: Sequence[str]
    ) -> tuple[int, Sequence[AppleVisionObservation]]:
        from Foundation import NSURL
        from Vision import (
            VNImageRequestHandler,
            VNRecognizeTextRequest,
            VNRequestTextRecognitionLevelAccurate,
        )

        handlers = _vision_handlers(path, NSURL, VNImageRequestHandler)
        observations: list[AppleVisionObservation] = []
        for page, handler in enumerate(handlers, start=1):
            request = VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)
            request.setRecognitionLanguages_(list(languages))
            request.setUsesLanguageCorrection_(True)
            success, error = handler.performRequests_error_([request], None)
            if not success:
                raise RuntimeError(f"Apple Vision request failed: {error}")
            for result in request.results() or ():
                candidates = result.topCandidates_(1)
                if not candidates:
                    continue
                candidate = candidates[0]
                box = result.boundingBox()
                observations.append(
                    AppleVisionObservation(
                        page=page,
                        text=str(candidate.string()),
                        x=float(box.origin.x),
                        y=float(box.origin.y),
                        width=float(box.size.width),
                        height=float(box.size.height),
                        confidence=float(candidate.confidence()),
                    )
                )
        return len(handlers), observations


def _vision_handlers(path: Path, ns_url: Any, handler_class: Any) -> list[Any]:
    url = ns_url.fileURLWithPath_(str(path))
    if path.suffix.lower() != ".pdf":
        return [handler_class.alloc().initWithURL_options_(url, {})]

    try:
        from AppKit import NSMakeSize
        from PDFKit import kPDFDisplayBoxMediaBox, PDFDocument
    except (ImportError, ModuleNotFoundError) as error:
        raise AppleVisionUnavailableError(
            "PDF input requires the bundled PDFKit/AppKit bridge."
        ) from error

    document = PDFDocument.alloc().initWithURL_(url)
    if document is None or document.pageCount() < 1:
        raise ValueError(f"Could not open PDF input: {path}")
    handlers: list[Any] = []
    for index in range(document.pageCount()):
        page = document.pageAtIndex_(index)
        bounds = page.boundsForBox_(kPDFDisplayBoxMediaBox)
        scale = 2.0
        image = page.thumbnailOfSize_forBox_(
            NSMakeSize(bounds.size.width * scale, bounds.size.height * scale),
            kPDFDisplayBoxMediaBox,
        )
        cg_image = image.CGImageForProposedRect_context_hints_(None, None, None)[0]
        handlers.append(handler_class.alloc().initWithCGImage_options_(cg_image, {}))
    return handlers


def _normalized_top_left_box(
    observation: AppleVisionObservation,
) -> BoundingBox:
    values = (
        observation.x,
        observation.y,
        observation.width,
        observation.height,
    )
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("Apple Vision returned a non-normalized bounding box.")
    if observation.x + observation.width > 1.000001:
        raise ValueError("Apple Vision bounding box exceeds the page width.")
    if observation.y + observation.height > 1.000001:
        raise ValueError("Apple Vision bounding box exceeds the page height.")
    return BoundingBox(
        page=observation.page,
        x=observation.x,
        y=1.0 - observation.y - observation.height,
        width=observation.width,
        height=observation.height,
    )


def _confidence(value: float | None) -> float | None:
    if value is None:
        return None
    return min(1.0, max(0.0, float(value)))


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return ()
