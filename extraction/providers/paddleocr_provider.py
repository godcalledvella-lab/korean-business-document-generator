"""PaddleOCR PP-StructureV3 adapter."""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Iterable, Mapping, Sequence
from html.parser import HTMLParser
from pathlib import Path
from statistics import fmean
from typing import Any

from .base import (
    BoundingBox,
    DetectedTable,
    OCRProvider,
    OCRResult,
    OCRTableCell,
    OCRTextRegion,
)


class PaddleOCRDependencyError(RuntimeError):
    """Raised when the optional PaddleOCR runtime is unavailable."""


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cells: list[dict[str, Any]] = []
        self.row = -1
        self.column = 0
        self._cell: dict[str, Any] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "tr":
            self.row += 1
            self.column = 0
        elif tag in {"td", "th"}:
            values = dict(attrs)
            row_span = _positive_int(values.get("rowspan"), 1)
            column_span = _positive_int(values.get("colspan"), 1)
            self._cell = {
                "row": max(self.row, 0),
                "column": self.column,
                "row_span": row_span,
                "column_span": column_span,
                "parts": [],
            }
            self.column += column_span

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            self._cell["text"] = "".join(self._cell.pop("parts")).strip()
            self.cells.append(self._cell)
            self._cell = None


class PaddleOCRProvider(OCRProvider):
    """Run Korean OCR and table recognition through PP-StructureV3."""

    provider_name = "paddle"
    supported_extensions = frozenset({".pdf", ".png", ".jpg", ".jpeg"})

    def __init__(
        self,
        *,
        pipeline: Any | None = None,
        language: str = "korean",
    ) -> None:
        self._pipeline = pipeline
        self.language = language

    def extract(self, path: Path) -> OCRResult:
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"OCR input does not exist: {source}")
        if source.suffix.lower() not in self.supported_extensions:
            supported = ", ".join(sorted(self.supported_extensions))
            raise ValueError(
                f"Unsupported PaddleOCR input type {source.suffix!r}; "
                f"expected one of: {supported}."
            )

        pipeline = self._pipeline or self._build_pipeline()
        pages = list(pipeline.predict(str(source)))
        if not pages:
            raise ValueError(f"PaddleOCR returned no results for {source}.")
        return self._convert_results(pages)

    def _build_pipeline(self) -> Any:
        try:
            from paddleocr import PPStructureV3
        except (ImportError, ModuleNotFoundError) as error:
            raise PaddleOCRDependencyError(
                "PaddleOCR is not installed. Install PaddlePaddle for your "
                "platform, then install document parsing support with "
                '`python3 -m pip install "paddleocr[doc-parser]"`.'
            ) from error

        return PPStructureV3(
            lang=self.language,
            use_table_recognition=True,
        )

    def _convert_results(self, results: Sequence[Any]) -> OCRResult:
        page_maps = [_result_mapping(result) for result in results]
        regions: list[OCRTextRegion] = []
        tables: list[DetectedTable] = []
        page_text: list[str] = []
        confidences: list[float] = []

        for ordinal, result in enumerate(page_maps, start=1):
            page = _page_number(result, ordinal)
            ocr = _mapping(result.get("overall_ocr_res"))
            texts = _sequence(ocr.get("rec_texts"))
            scores = _sequence(ocr.get("rec_scores"))
            polygons = _sequence(
                _first_present(ocr, "rec_polys", "rec_boxes")
            )
            clean_texts = [str(text).strip() for text in texts]
            ordered_blocks = [
                str(_mapping(block).get("block_content") or "").strip()
                for block in _sequence(result.get("parsing_res_list"))
            ]
            ordered_text = [text for text in ordered_blocks if text]
            page_text.extend(
                ordered_text or [text for text in clean_texts if text]
            )

            for index, text in enumerate(clean_texts):
                box = _box(polygons[index], page) if index < len(polygons) else None
                if not text or box is None:
                    continue
                score = _confidence(scores[index]) if index < len(scores) else None
                regions.append(OCRTextRegion(text, box, score))
                if score is not None:
                    confidences.append(score)

            for table_data in _sequence(result.get("table_res_list")):
                table = _convert_table(_mapping(table_data), page)
                tables.append(table)
                if table.confidence is not None:
                    confidences.append(table.confidence)

        declared_counts = [
            _positive_int(result.get("page_count"), 0) for result in page_maps
        ]
        page_count = max([len(page_maps), *declared_counts])
        return OCRResult(
            page_count=page_count,
            language="ko",
            raw_text="\n".join(page_text),
            detected_tables=tuple(tables),
            text_regions=tuple(regions),
            confidence=fmean(confidences) if confidences else None,
            provider_name=self.provider_name,
            provider_metadata={
                "pipeline": "PP-StructureV3",
                "language": self.language,
                "table_recognition": True,
                "paddleocr_version": _package_version("paddleocr"),
            },
        )


def _convert_table(data: Mapping[str, Any], page: int) -> DetectedTable:
    table_ocr = _mapping(data.get("table_ocr_pred"))
    texts = [str(value).strip() for value in _sequence(table_ocr.get("rec_texts"))]
    scores = _sequence(table_ocr.get("rec_scores"))
    boxes = _sequence(data.get("cell_box_list"))
    if not boxes:
        boxes = _sequence(_first_present(table_ocr, "rec_boxes", "rec_polys"))

    layout = _html_cells(str(data.get("pred_html") or ""))
    count = max(len(layout), len(texts), len(boxes))
    if not layout:
        layout = [
            {
                "row": 0,
                "column": index,
                "row_span": 1,
                "column_span": 1,
                "text": texts[index] if index < len(texts) else "",
            }
            for index in range(count)
        ]

    cells: list[OCRTableCell] = []
    cell_scores: list[float] = []
    for index, layout_cell in enumerate(layout):
        score = _confidence(scores[index]) if index < len(scores) else None
        if score is not None:
            cell_scores.append(score)
        text = (
            texts[index]
            if index < len(texts) and texts[index]
            else str(layout_cell.get("text") or "")
        )
        cells.append(
            OCRTableCell(
                row=int(layout_cell["row"]),
                column=int(layout_cell["column"]),
                text=text,
                bounding_box=_box(boxes[index], page) if index < len(boxes) else None,
                confidence=score,
                row_span=int(layout_cell["row_span"]),
                column_span=int(layout_cell["column_span"]),
            )
        )

    row_count = max(
        (cell.row + cell.row_span for cell in cells),
        default=_positive_int(data.get("row_count"), 0),
    )
    column_count = max(
        (cell.column + cell.column_span for cell in cells),
        default=_positive_int(data.get("column_count"), 0),
    )
    table_box = _union_boxes(
        [cell.bounding_box for cell in cells if cell.bounding_box is not None],
        page,
    )
    return DetectedTable(
        page=page,
        row_count=row_count,
        column_count=column_count,
        cells=tuple(cells),
        bounding_box=table_box,
        confidence=fmean(cell_scores) if cell_scores else None,
    )


def _html_cells(html: str) -> list[dict[str, Any]]:
    if not html:
        return []
    parser = _TableHTMLParser()
    parser.feed(html)
    return parser.cells


def _result_mapping(result: Any) -> Mapping[str, Any]:
    if isinstance(result, Mapping):
        return result
    for attribute in ("json", "to_dict"):
        value = getattr(result, attribute, None)
        if value is None:
            continue
        value = value() if callable(value) else value
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, Mapping):
            return value
    raise TypeError(
        f"Unsupported PaddleOCR result object: {type(result).__name__}."
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _sequence(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return []
    if isinstance(value, Sequence):
        return list(value)
    if isinstance(value, Iterable):
        return list(value)
    return []


def _page_number(result: Mapping[str, Any], ordinal: int) -> int:
    index = result.get("page_index")
    return int(index) + 1 if index is not None else ordinal


def _box(value: Any, page: int) -> BoundingBox | None:
    points = _sequence(value)
    if not points:
        return None
    if len(points) == 4 and all(isinstance(item, (int, float)) for item in points):
        x1, y1, x2, y2 = (float(item) for item in points)
    else:
        pairs = [_sequence(point) for point in points]
        pairs = [pair for pair in pairs if len(pair) >= 2]
        if not pairs:
            return None
        xs = [float(pair[0]) for pair in pairs]
        ys = [float(pair[1]) for pair in pairs]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    return BoundingBox(page, x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))


def _union_boxes(boxes: Sequence[BoundingBox], page: int) -> BoundingBox | None:
    if not boxes:
        return None
    x1 = min(box.x for box in boxes)
    y1 = min(box.y for box in boxes)
    x2 = max(box.x + box.width for box in boxes)
    y2 = max(box.y + box.height for box in boxes)
    return BoundingBox(page, x1, y1, x2 - x1, y2 - y1)


def _confidence(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, score))


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None
