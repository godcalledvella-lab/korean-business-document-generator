"""Conservative mapping from provider-neutral OCR output to raw invoice fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from extraction.models import RawTaxInvoiceData
from extraction.providers import OCRResult, OCRTextRegion


PAYMENT_METHOD_LABELS = frozenset({"현금", "수표", "어음", "외상미수금", "의상미수금"})
PARTY_LABELS = (
    "등록번호",
    "사업자등록번호",
    "상호",
    "상혼",
    "법인명",
    "성명",
    "대표자",
    "사업장",
    "주소",
    "업태",
    "업대",
    "종목",
    "이메일",
    "전자우편",
    "전화번호",
    "전화",
)
_KRW_TOKEN = re.compile(r"^[+\-]?\s*[₩￦]?\s*\d[\d,\s]*\s*원?$")


@dataclass(frozen=True)
class OCRInvoiceMapper:
    """Map explicit Korean labels without fabricating absent values."""

    def map(self, result: OCRResult) -> RawTaxInvoiceData:
        lines = _lines(result)
        payload = {
            "issue_date": _field(
                result,
                lines,
                ("작성일자", "발행일자"),
                value_pattern=re.compile(r"\d{4}\s*[-./년]\s*\d{1,2}"),
            ),
            "approval_number": _approval_number(result, lines),
            "supplier": _party(result, lines, "공급자"),
            "buyer": _party(result, lines, "공급받는자"),
            "items": _items(result),
            "totals": {
                "supply_amount": _field(
                    result,
                    lines,
                    ("합계 공급가액", "공급가액 합계", "공급가액"),
                    monetary=True,
                ),
                "vat": _field(
                    result,
                    lines,
                    ("합계 세액", "세액 합계", "세액", "세역"),
                    monetary=True,
                ),
                "grand_total": _field(
                    result,
                    lines,
                    ("합계금액", "총금액"),
                    monetary=True,
                ),
            },
            "receipt_claim_classification": _classification(result, lines),
            "provider": result.provider_name,
        }
        return RawTaxInvoiceData.from_dict(payload, provider=result.provider_name)


def _lines(result: OCRResult) -> list[str]:
    values = [line.strip() for line in result.raw_text.splitlines() if line.strip()]
    for table in result.detected_tables:
        values.extend(cell.text.strip() for cell in table.cells if cell.text.strip())
    return values


def _labeled(lines: Iterable[str], labels: tuple[str, ...]) -> str | None:
    escaped = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"(?:{escaped})\s*[:：]?\s*(.+)$")
    for line in lines:
        match = pattern.search(line)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def _field(
    result: OCRResult,
    lines: list[str],
    labels: tuple[str, ...],
    *,
    monetary: bool = False,
    value_pattern: re.Pattern[str] | None = None,
) -> dict[str, object] | None:
    spatial = _spatial_field(
        result,
        labels,
        monetary=monetary,
        value_pattern=value_pattern,
    )
    if spatial is not None:
        return spatial

    value = _labeled(lines, labels)
    if value is None:
        return None
    if monetary and not _is_krw_token(value):
        return None
    if value_pattern is not None and value_pattern.search(value) is None:
        return None
    source = next(
        (
            line
            for line in lines
            if any(label in line for label in labels) and value in line
        ),
        value,
    )
    return {
        "value": value,
        "confidence": _text_confidence(result, source),
        "source_text": source,
    }


def _party(
    result: OCRResult, lines: list[str], side: str
) -> dict[str, dict[str, object] | None]:
    aliases = {
        "business_registration_number": ("등록번호", "사업자등록번호"),
        "company_name": ("상호", "법인명"),
        "representative": ("성명", "대표자"),
        "address": ("사업장주소", "주소"),
        "business_type": ("업태",),
        "business_category": ("종목",),
        "email": ("이메일", "전자우편"),
        "phone": ("전화번호", "전화"),
    }
    regions = _regions(result)
    if regions:
        xs = [
            region.bounding_box.x + region.bounding_box.width
            for region in regions
        ]
        midpoint = max(xs, default=0) / 2
        bounds = (0.0, midpoint) if side == "공급자" else (midpoint, float("inf"))
        spatial = {
            field: _party_spatial_field(result, labels, bounds)
            for field, labels in aliases.items()
        }
        spatial["business_registration_number"] = _registration_number(
            result, bounds
        )
        if spatial["company_name"] is None:
            spatial["company_name"] = _company_name(result, bounds)
        spatial["address"] = _party_address(result, bounds) or spatial["address"]
        for field, field_labels in aliases.items():
            if spatial[field] is None:
                spatial[field] = _field(
                    result,
                    lines,
                    tuple(
                        variant
                        for label in field_labels
                        for variant in (
                            f"{side} {label}",
                            f"{side}.{label}",
                            f"{side}_{label}",
                        )
                    ),
                )
        spatial["company_name"] = _preserve_legal_entity_spacing(
            spatial["company_name"]
        )
        spatial["email"] = _review_invalid_email(spatial["email"])
        return spatial

    mapped = {
        field: _field(
            result,
            lines,
            tuple(
                variant
                for label in labels
                for variant in (
                    f"{side} {label}",
                    f"{side}.{label}",
                    f"{side}_{label}",
                )
            ),
        )
        for field, labels in aliases.items()
    }
    mapped["company_name"] = _preserve_legal_entity_spacing(
        mapped["company_name"]
    )
    mapped["email"] = _review_invalid_email(mapped["email"])
    return mapped


def _items(result: OCRResult) -> list[dict[str, str | None]]:
    spatial_items = _spatial_items(result)
    if spatial_items:
        return spatial_items

    for table in result.detected_tables:
        rows: dict[int, dict[int, object]] = {}
        for cell in table.cells:
            rows.setdefault(cell.row, {})[cell.column] = cell
        ordered = [
            [columns[index] for index in sorted(columns)]
            for _, columns in sorted(rows.items())
        ]
        header_index = next(
            (
                index
                for index, row in enumerate(ordered)
                if any("품목" in cell.text for cell in row)
                and any("공급가액" in cell.text for cell in row)
            ),
            None,
        )
        if header_index is None:
            continue
        headers = [_header(cell.text) for cell in ordered[header_index]]
        items: list[dict[str, str | None]] = []
        for row in ordered[header_index + 1 :]:
            mapped = {
                field: {
                    "value": row[index].text.strip() or None,
                    "confidence": row[index].confidence,
                    "source_text": row[index].text,
                }
                for index, field in enumerate(headers)
                if field is not None and index < len(row)
            }
            if mapped.get("item_name", {}).get("value"):
                mapped.setdefault("unit", None)
                items.append(mapped)
        if items:
            return items
    return []


def _header(value: str) -> str | None:
    compact = re.sub(r"\s", "", value)
    aliases = (
        ("작성일", "date"),
        ("일자", "date"),
        ("품목", "item_name"),
        ("규격", "specification"),
        ("단위", "unit"),
        ("수량", "quantity"),
        ("수랑", "quantity"),
        ("단가", "unit_price"),
        ("공급가액", "supply_amount"),
        ("세액", "tax_amount"),
        ("세역", "tax_amount"),
        ("비고", "remark"),
    )
    return next((field for label, field in aliases if label in compact), None)


def _approval_number(
    result: OCRResult,
    lines: list[str],
) -> dict[str, object] | None:
    """Preserve OCR evidence while normalizing spaces inside approval digits."""
    candidates: list[tuple[float, str, float | None, str]] = []
    for region in _regions(result):
        normalized = re.sub(r"\s", "", region.text).replace("–", "-")
        match = re.search(r"\d{8}-\d{8}-\d+", normalized)
        if match is not None:
            candidates.append(
                (
                    region.bounding_box.y,
                    match.group(0),
                    region.confidence,
                    region.text,
                )
            )
    if candidates:
        _, value, confidence, source_text = min(candidates, key=lambda item: item[0])
        return {
            "value": value,
            "confidence": confidence,
            "source_text": source_text,
        }
    return _field(
        result,
        lines,
        ("승인번호",),
        value_pattern=re.compile(r"\d{8}\s*-\s*\d{8}\s*-\s*\d+"),
    )


def _classification(
    result: OCRResult, lines: Iterable[str]
) -> dict[str, object] | None:
    for line in lines:
        compact = re.sub(r"\s", "", line)
        if "영수" in compact and ("구분" in compact or "청구" in compact):
            return {
                "value": "영수",
                "confidence": _text_confidence(result, line),
                "source_text": line,
            }
        if "청구" in compact and "구분" in compact:
            return {
                "value": "청구",
                "confidence": _text_confidence(result, line),
                "source_text": line,
            }
    return None


def _text_confidence(result: OCRResult, source: str) -> float | None:
    scores = [
        region.confidence
        for region in result.text_regions
        if region.confidence is not None
        and (region.text in source or source in region.text)
    ]
    scores.extend(
        cell.confidence
        for table in result.detected_tables
        for cell in table.cells
        if cell.confidence is not None
        and (cell.text in source or source in cell.text)
    )
    return min(scores) if scores else None


def _regions(result: OCRResult) -> list[OCRTextRegion]:
    """Use geometrically reliable OCR regions, falling back to table cells."""
    if result.text_regions:
        return sorted(
            result.text_regions,
            key=lambda region: (
                region.bounding_box.page,
                region.bounding_box.y,
                region.bounding_box.x,
            ),
        )
    return sorted(
        (
            OCRTextRegion(cell.text, cell.bounding_box, cell.confidence)
            for table in result.detected_tables
            for cell in table.cells
            if cell.text.strip() and cell.bounding_box is not None
        ),
        key=lambda region: (
            region.bounding_box.page,
            region.bounding_box.y,
            region.bounding_box.x,
        ),
    )


def _compact(value: str) -> str:
    return re.sub(r"\s", "", value)


def _matches_label(value: str, labels: tuple[str, ...]) -> bool:
    compact = _compact(value)
    return any(_compact(label) in compact for label in labels)


def _is_krw_token(value: str) -> bool:
    return (
        _compact(value) not in PAYMENT_METHOD_LABELS
        and _KRW_TOKEN.fullmatch(value.strip()) is not None
    )


def _spatial_field(
    result: OCRResult,
    labels: tuple[str, ...],
    *,
    monetary: bool,
    value_pattern: re.Pattern[str] | None,
) -> dict[str, object] | None:
    regions = _regions(result)
    anchors = [
        region for region in regions if _matches_label(region.text, labels)
    ]
    if monetary and anchors:
        # The invoice summary precedes the item-table headers in this layout.
        # Restrict repeated labels such as 공급가액/세액 to their first row.
        first_y = min(anchor.bounding_box.y for anchor in anchors)
        anchors = [
            anchor for anchor in anchors if anchor.bounding_box.y <= first_y + 5
        ]
    best: tuple[float, OCRTextRegion, OCRTextRegion] | None = None
    for anchor in anchors:
        box = anchor.bounding_box
        for candidate in regions:
            if candidate is anchor or candidate.bounding_box.page != box.page:
                continue
            text = candidate.text.strip()
            if not text or _matches_label(text, labels):
                continue
            if monetary and not _is_krw_token(text):
                continue
            if value_pattern is not None and value_pattern.search(text) is None:
                continue
            other = candidate.bounding_box
            vertical_gap = other.y - (box.y + box.height)
            center_delta = abs(
                (other.x + other.width / 2) - (box.x + box.width / 2)
            )
            same_row = abs(
                (other.y + other.height / 2) - (box.y + box.height / 2)
            ) <= max(box.height, other.height) * 0.75
            right = other.x >= box.x + box.width - 2
            below = -3 <= vertical_gap <= max(35.0, box.height * 2.5)
            aligned_below = center_delta <= max(65.0, box.width * 2)
            if same_row and right:
                score = (other.x - box.x - box.width) + center_delta * 0.15
            elif below and aligned_below:
                score = 20 + max(vertical_gap, 0) + center_delta * 0.25
            else:
                continue
            choice = (score, anchor, candidate)
            if best is None or score < best[0]:
                best = choice
    if best is None:
        return None
    _, anchor, candidate = best
    return {
        "value": candidate.text.strip(),
        "confidence": candidate.confidence,
        "source_text": f"{anchor.text} {candidate.text}".strip(),
    }


def _in_bounds(region: OCRTextRegion, bounds: tuple[float, float]) -> bool:
    center = region.bounding_box.x + region.bounding_box.width / 2
    return bounds[0] <= center < bounds[1]


def _party_spatial_field(
    result: OCRResult,
    labels: tuple[str, ...],
    bounds: tuple[float, float],
) -> dict[str, object] | None:
    regions = [region for region in _regions(result) if _in_bounds(region, bounds)]
    aliases = labels + (("업대",) if labels == ("업태",) else ())
    anchors = [region for region in regions if _matches_label(region.text, aliases)]
    best: tuple[float, OCRTextRegion, OCRTextRegion] | None = None
    for anchor in anchors:
        box = anchor.bounding_box
        for candidate in regions:
            if candidate is anchor or _matches_label(candidate.text, aliases):
                continue
            if _matches_label(candidate.text, PARTY_LABELS):
                continue
            other = candidate.bounding_box
            row_delta = abs(
                (other.y + other.height / 2) - (box.y + box.height / 2)
            )
            if other.x < box.x + box.width - 2 or row_delta > max(
                box.height, other.height
            ):
                continue
            score = other.x - (box.x + box.width) + row_delta
            if best is None or score < best[0]:
                best = (score, anchor, candidate)
    if best is None:
        return None
    _, anchor, candidate = best
    return {
        "value": candidate.text.strip(),
        "confidence": candidate.confidence,
        "source_text": f"{anchor.text} {candidate.text}".strip(),
    }


def _registration_number(
    result: OCRResult, bounds: tuple[float, float]
) -> dict[str, object] | None:
    normalized = _normalized_geometry(result)
    candidates = [
        region
        for region in _regions(result)
        if _in_bounds(region, bounds)
        and region.bounding_box.y < (0.25 if normalized else 100)
        and re.fullmatch(
            r"\s*\d\s*\d\s*\d\s*-\s*\d\s*\d\s*-\s*"
            r"\d\s*\d\s*\d\s*\d\s*\d\s*",
            region.text,
        )
    ]
    if not candidates:
        return None
    candidate = min(candidates, key=lambda region: region.bounding_box.y)
    digits = re.sub(r"\D", "", candidate.text)
    return {
        "value": f"{digits[:3]}-{digits[3:5]}-{digits[5:]}",
        "confidence": candidate.confidence,
        "source_text": candidate.text,
    }


def _company_name(
    result: OCRResult, bounds: tuple[float, float]
) -> dict[str, object] | None:
    excluded = ("상호", "법인명", "성명", "대표자", "사업장", "주소")
    normalized = _normalized_geometry(result)
    y_min, y_max = (0.10, 0.22) if normalized else (45, 78)
    x_offset = 0.05 if normalized else 70
    candidates = [
        region
        for region in _regions(result)
        if _in_bounds(region, bounds)
        and y_min <= region.bounding_box.y <= y_max
        and not _matches_label(region.text, excluded)
        and not re.search(r"\d{3}\s*-\s*\d{2}\s*-\s*\d{5}", region.text)
        and len(region.text.strip()) >= 3
        and not region.text.strip().startswith("(")
        and region.bounding_box.x >= bounds[0] + x_offset
    ]
    if not candidates:
        return None
    candidate = min(candidates, key=lambda region: region.bounding_box.x)
    return {
        "value": candidate.text.strip(),
        "confidence": candidate.confidence,
        "source_text": candidate.text,
    }


def _party_address(
    result: OCRResult, bounds: tuple[float, float]
) -> dict[str, object] | None:
    regions = [region for region in _regions(result) if _in_bounds(region, bounds)]
    anchors = [
        region
        for region in regions
        if _compact(region.text) in {"사업장", "사업장주소", "사업성"}
    ]
    if not anchors:
        if _normalized_geometry(result):
            candidates = [
                region
                for region in regions
                if 0.19 <= region.bounding_box.y <= 0.26
                and re.search(r"\d", region.text)
                and re.search(
                    r"(?:특별시|광역시|도|시|군|구|로|길|동|읍|면)",
                    region.text,
                )
            ]
            if candidates:
                candidate = max(candidates, key=lambda region: len(region.text))
                return {
                    "value": candidate.text.strip(),
                    "confidence": candidate.confidence,
                    "source_text": candidate.text,
                }
        return None
    anchor = min(anchors, key=lambda region: region.bounding_box.y)
    box = anchor.bounding_box
    next_section_y = min(
        (
            region.bounding_box.y
            for region in regions
            if region.bounding_box.y > box.y
            and _matches_label(
                region.text,
                ("업태", "업대", "종목", "이메일", "전자우편", "전화"),
            )
        ),
        default=float("inf"),
    )
    values = [
        region
        for region in regions
        if region is not anchor
        and region.bounding_box.x >= box.x + box.width - 3
        and box.y - 3 <= region.bounding_box.y <= box.y + max(28.0, box.height * 2.2)
        and region.bounding_box.y < next_section_y - max(5.0, box.height * 0.5)
        and not _matches_label(region.text, PARTY_LABELS)
    ]
    if not values:
        return None
    values.sort(key=lambda region: (region.bounding_box.y, region.bounding_box.x))
    return {
        "value": _join_spatial_text(values),
        "confidence": min(
            (
                region.confidence
                for region in values
                if region.confidence is not None
            ),
            default=None,
        ),
        "source_text": _join_spatial_text(values),
    }


def _normalized_geometry(result: OCRResult) -> bool:
    regions = _regions(result)
    return bool(regions) and max(
        max(
            region.bounding_box.x + region.bounding_box.width,
            region.bounding_box.y + region.bounding_box.height,
        )
        for region in regions
    ) <= 1.000001


def _review_invalid_email(
    field: dict[str, object] | None,
) -> dict[str, object] | None:
    """Keep imperfect OCR email text, but force visible human review."""
    if field is None:
        return None
    value = field.get("value")
    if not isinstance(value, str) or "@" not in value:
        return field
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        return field
    confidence = field.get("confidence")
    field = dict(field)
    field["confidence"] = min(float(confidence), 0.79) if confidence is not None else 0.79
    return field


def _preserve_legal_entity_spacing(
    field: dict[str, object] | None,
) -> dict[str, object] | None:
    if field is None or not isinstance(field.get("value"), str):
        return field
    value = re.sub(r"^(사단법인|재단법인)(?=\S)", r"\1 ", field["value"])
    if value == field["value"]:
        return field
    normalized = dict(field)
    normalized["value"] = value
    return normalized


def _spatial_items(result: OCRResult) -> list[dict[str, object | None]]:
    regions = _regions(result)
    item_headers = [
        region for region in regions if "품목" in _compact(region.text)
    ]
    if not item_headers:
        return []
    header = item_headers[0]
    header_center_y = header.bounding_box.y + header.bounding_box.height / 2
    header_regions = [
        region
        for region in regions
        if abs(
            region.bounding_box.y
            + region.bounding_box.height / 2
            - header_center_y
        )
        <= 10
        and _header(region.text) is not None
    ]
    columns = sorted(
        (
            (
                region.bounding_box.x + region.bounding_box.width / 2,
                _header(region.text),
            )
            for region in header_regions
            if _header(region.text) is not None
        ),
        key=lambda value: value[0],
    )
    item_header = min(
        (
            region
            for region in header_regions
            if _header(region.text) == "item_name"
        ),
        key=lambda region: region.bounding_box.x,
    )
    item_center = item_header.bounding_box.x + item_header.bounding_box.width / 2
    item_left = max(
        (
            region.bounding_box.x + region.bounding_box.width
            for region in header_regions
            if _header(region.text) == "date"
        ),
        default=0.0,
    )
    item_right = min(
        (
            (item_center + center) / 2
            for center, field in columns
            if center > item_center and field != "item_name"
        ),
        default=float("inf"),
    )
    required = {"item_name", "quantity", "unit_price", "supply_amount", "tax_amount"}
    if not required.issubset({field for _, field in columns}):
        return []

    totals_y = min(
        (
            region.bounding_box.y
            for region in regions
            if _matches_label(region.text, ("합계금액", "총금액"))
            and region.bounding_box.y > header_center_y
        ),
        default=float("inf"),
    )
    body = [
        region
        for region in regions
        if region.bounding_box.y > header.bounding_box.y + header.bounding_box.height
        and region.bounding_box.y < totals_y
    ]
    row_centers: list[float] = []
    rows: list[list[OCRTextRegion]] = []
    for region in sorted(
        body,
        key=lambda value: (
            value.bounding_box.y + value.bounding_box.height / 2,
            value.bounding_box.x,
        ),
    ):
        center_y = region.bounding_box.y + region.bounding_box.height / 2
        if not rows or abs(center_y - row_centers[-1]) > 9:
            rows.append([region])
            row_centers.append(center_y)
        else:
            rows[-1].append(region)
            row_centers[-1] = median(
                value.bounding_box.y + value.bounding_box.height / 2
                for value in rows[-1]
            )

    centers = [center for center, _ in columns]
    boundaries = [
        (centers[index] + centers[index + 1]) / 2
        for index in range(len(centers) - 1)
    ]

    def column_for(region: OCRTextRegion) -> str | None:
        x = region.bounding_box.x + region.bounding_box.width / 2
        index = next(
            (index for index, boundary in enumerate(boundaries) if x < boundary),
            len(columns) - 1,
        )
        return columns[index][1]

    items: list[dict[str, object | None]] = []
    for row in rows:
        values: dict[str, list[OCRTextRegion]] = {}
        date_parts: list[OCRTextRegion] = []
        for region in row:
            field = column_for(region)
            if field == "date":
                date_parts.append(region)
            elif field is not None:
                values.setdefault(field, []).append(region)
        item_regions = [
            region
            for region in row
            if item_left
            < region.bounding_box.x + region.bounding_box.width / 2
            < item_right
            and not re.fullmatch(r"\d{1,2}", region.text.strip())
        ]
        if item_regions:
            values["item_name"] = item_regions
        item_text = _join_spatial_text(values.get("item_name", ()))
        numeric_fields = ("quantity", "unit_price", "supply_amount", "tax_amount")
        if (
            not item_text
            or _compact(item_text) in PAYMENT_METHOD_LABELS
            or not any(
                any(_is_krw_token(region.text) for region in values.get(field, ()))
                for field in numeric_fields
            )
        ):
            continue
        mapped: dict[str, object | None] = {}
        for field, field_regions in values.items():
            text = _join_spatial_text(field_regions)
            mapped[field] = {
                "value": text or None,
                "confidence": min(
                    (
                        region.confidence
                        for region in field_regions
                        if region.confidence is not None
                    ),
                    default=None,
                ),
                "source_text": text,
            }
        if date_parts:
            ordered = sorted(date_parts, key=lambda value: value.bounding_box.x)
            mapped["date"] = {
                "value": "-".join(part.text.strip() for part in ordered),
                "confidence": min(
                    (
                        part.confidence
                        for part in ordered
                        if part.confidence is not None
                    ),
                    default=None,
                ),
                "source_text": " ".join(part.text for part in ordered),
            }
        mapped.setdefault("unit", None)
        items.append(mapped)
    return items


def _join_spatial_text(regions: Iterable[OCRTextRegion]) -> str:
    ordered = sorted(
        regions,
        key=lambda region: (region.bounding_box.y, region.bounding_box.x),
    )
    text = ""
    previous: OCRTextRegion | None = None
    closing = ".,:;!?)]}，。：；！？）］｝"
    opening = "([{（［｛"
    for region in ordered:
        value = region.text.strip()
        if not value:
            continue
        if previous is None:
            text = value
        else:
            same_line = abs(
                (region.bounding_box.y + region.bounding_box.height / 2)
                - (previous.bounding_box.y + previous.bounding_box.height / 2)
            ) <= max(region.bounding_box.height, previous.bounding_box.height) * 0.6
            unmatched_parenthesis = (
                text.count("(") + text.count("（")
                > text.count(")") + text.count("）")
            )
            attach = (
                value[0] in closing
                or text[-1] in opening
                or (not same_line and unmatched_parenthesis)
            )
            text += ("" if attach else " ") + value
        previous = region
    return text
