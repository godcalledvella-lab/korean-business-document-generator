"""Headless LibreOffice PDF backend."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Callable, Sequence
from xml.etree import ElementTree

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ContentStream, FloatObject

from package.models import BackendAvailability, RenderResult

from .base import BackendRenderError, PDFBackend


DEFAULT_LIBREOFFICE_PATHS = (
    Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    Path("/opt/homebrew/bin/soffice"),
    Path("/usr/local/bin/soffice"),
    Path("/usr/bin/libreoffice"),
    Path("/usr/bin/soffice"),
    Path("C:/Program Files/LibreOffice/program/soffice.exe"),
    Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
)
WORKSHEETS = {
    "statement": "청구서",
    "quotation": "견적서",
    "comparison": "Sheet1",
}
MISSING_KOREAN_FONTS = {
    "Dotum",
    "Gulim",
    "Gulimche",
    "Malgun Gothic",
    "HY그래픽M",
    "새굴림",
}


def find_libreoffice(
    candidates: Sequence[Path] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    for command in ("soffice", "libreoffice"):
        found = which(command)
        if found:
            return Path(found).resolve()
    paths = candidates if candidates is not None else DEFAULT_LIBREOFFICE_PATHS
    for candidate in paths:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def build_libreoffice_command(
    executable: Path,
    source_copy: Path,
    output_dir: Path,
    profile_dir: Path,
) -> list[str]:
    profile_uri = profile_dir.resolve().as_uri()
    return [
        str(executable),
        "--headless",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile_uri}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir.resolve()),
        str(source_copy.resolve()),
    ]


class LibreOfficeBackend(PDFBackend):
    name = "libreoffice"

    def __init__(
        self,
        executable: Path | None = None,
        *,
        timeout: float = 180,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.executable = executable or find_libreoffice()
        self.timeout = timeout
        self.runner = runner

    def availability(self) -> BackendAvailability:
        if self.executable is None:
            return BackendAvailability(
                self.name,
                False,
                "LibreOffice was not found in PATH or known installation locations.",
            )
        try:
            result = self.runner(
                [str(self.executable), "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return BackendAvailability(self.name, False, str(error))
        version = (result.stdout or result.stderr).strip() or None
        return BackendAvailability(
            self.name,
            result.returncode == 0,
            (
                f"Detected executable at {self.executable}."
                if result.returncode == 0
                else f"Version check failed with exit code {result.returncode}."
            ),
            version,
        )

    def render_xlsx(self, input_path: Path, output_path: Path) -> RenderResult:
        source = input_path.resolve()
        output = output_path.resolve()
        before = _sha256(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="libreoffice-render-", dir=output.parent
        ) as temporary:
            work = Path(temporary)
            profile = work / "profile"
            profile.mkdir()
            copied = work / output.with_suffix(".xlsx").name
            shutil.copy2(source, copied)
            target_worksheet = _target_worksheet(source.stem)
            if target_worksheet is not None:
                _isolate_worksheet(copied, target_worksheet)
                _prepare_bold_korean_font_fallback(copied, target_worksheet)
                if target_worksheet == "청구서":
                    _prepare_statement_render_copy(copied)
                elif target_worksheet == "견적서":
                    _prepare_quotation_render_copy(copied)
            command = build_libreoffice_command(
                self.executable or Path("soffice"), copied, work, profile
            )
            try:
                completed = self.runner(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise BackendRenderError(
                    str(error),
                    step=f"rendering {source.name}",
                    backend=self.name,
                    command=tuple(command),
                    working_path=work,
                    sources_unchanged=_sha256(source) == before,
                ) from error
            converted = work / copied.with_suffix(".pdf").name
            after = _sha256(source)
            if completed.returncode != 0 or not converted.is_file():
                raise BackendRenderError(
                    "LibreOffice did not create the requested PDF.",
                    step=f"rendering {source.name}",
                    backend=self.name,
                    command=tuple(command),
                    exit_code=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    working_path=work,
                    sources_unchanged=after == before,
                )
            _fit_single_page_to_a4_portrait(converted)
            if target_worksheet == "청구서":
                _scale_statement_pdf(converted)
            elif target_worksheet == "견적서":
                _align_quotation_pdf_to_reference(converted)
            elif target_worksheet == "Sheet1":
                _shift_comparison_pdf_right(converted)
                _center_comparison_title(converted)
            shutil.copy2(converted, output)
            return RenderResult(
                self.name,
                source,
                output,
                tuple(command),
                completed.returncode,
                completed.stdout,
                completed.stderr,
                before,
                after,
            )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_bold_korean_font_fallback(
    workbook_path: Path,
    target_worksheet: str,
) -> None:
    """Resolve missing font families while preserving each source style's weight."""
    temporary = workbook_path.with_suffix(".korean-font.xlsx")
    styles_part = "xl/styles.xml"
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ElementTree.register_namespace("", namespace)

    with zipfile.ZipFile(workbook_path, "r") as source:
        members = [
            (deepcopy(entry), source.read(entry.filename))
            for entry in source.infolist()
        ]

    with zipfile.ZipFile(temporary, "w") as destination:
        for entry, payload in members:
            if entry.filename == styles_part:
                root = ElementTree.fromstring(payload)
                fonts = root.find(f"{{{namespace}}}fonts")
                if fonts is None:
                    raise ValueError("Workbook is missing its font style table.")
                for font_id, font in enumerate(fonts):
                    name = font.find(f"{{{namespace}}}name")
                    bold = font.find(f"{{{namespace}}}b")
                    is_bold = bold is not None and bold.get("val", "1") != "0"
                    if name is None:
                        continue
                    source_family = name.get("val")
                    if source_family == "Calibri":
                        name.set("val", "Liberation Sans")
                    elif source_family in MISSING_KOREAN_FONTS:
                        if target_worksheet == "견적서" and font_id == 8:
                            name.set("val", "Apple SD Gothic Neo")
                        elif target_worksheet == "Sheet1" and font_id == 1:
                            name.set("val", "NanumGothic")
                        elif is_bold:
                            name.set("val", "Noto Sans KR")
                        else:
                            name.set("val", "Apple SD Gothic Neo")
                payload = ElementTree.tostring(
                    root,
                    encoding="utf-8",
                    xml_declaration=True,
                )
            destination.writestr(entry, payload)
    temporary.replace(workbook_path)


def _target_worksheet(stem: str) -> str | None:
    normalized = stem.lower()
    return next(
        (
            worksheet
            for document, worksheet in WORKSHEETS.items()
            if normalized == document or normalized.endswith(f"-{document}")
        ),
        None,
    )


def _isolate_worksheet(workbook_path: Path, target_name: str) -> None:
    """Hide non-target sheets in a disposable OOXML copy without loading cells."""
    temporary = workbook_path.with_suffix(".isolated.xlsx")
    workbook_xml = "xl/workbook.xml"
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ElementTree.register_namespace("", namespace)
    found = False
    with zipfile.ZipFile(workbook_path, "r") as source:
        with zipfile.ZipFile(temporary, "w") as destination:
            for entry in source.infolist():
                payload = source.read(entry.filename)
                if entry.filename == workbook_xml:
                    root = ElementTree.fromstring(payload)
                    for sheet in root.findall(f".//{{{namespace}}}sheet"):
                        if sheet.get("name") == target_name:
                            sheet.attrib.pop("state", None)
                            found = True
                        else:
                            sheet.set("state", "hidden")
                    calculation = root.find(f"{{{namespace}}}calcPr")
                    if calculation is None:
                        calculation = ElementTree.SubElement(
                            root,
                            f"{{{namespace}}}calcPr",
                        )
                    calculation.set("calcMode", "auto")
                    calculation.set("fullCalcOnLoad", "1")
                    calculation.set("forceFullCalc", "1")
                    calculation.set("calcId", "0")
                    payload = ElementTree.tostring(
                        root,
                        encoding="utf-8",
                        xml_declaration=True,
                    )
                elif (
                    entry.filename.startswith("xl/worksheets/")
                    and entry.filename.endswith(".xml")
                ):
                    root = ElementTree.fromstring(payload)
                    for cell in root.findall(f".//{{{namespace}}}c"):
                        if cell.find(f"{{{namespace}}}f") is None:
                            continue
                        cached = cell.find(f"{{{namespace}}}v")
                        if cached is not None:
                            cell.remove(cached)
                    payload = ElementTree.tostring(
                        root,
                        encoding="utf-8",
                        xml_declaration=True,
                    )
                elif (
                    entry.filename.startswith("xl/drawings/drawing")
                    and entry.filename.endswith(".xml")
                ):
                    payload = _remove_duplicate_shape_anchors(payload)
                destination.writestr(entry, payload)
    if not found:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            f"Worksheet {target_name!r} was not found in {workbook_path.name}."
        )
    temporary.replace(workbook_path)


def _fit_single_page_to_a4_portrait(pdf_path: Path) -> None:
    """Place one rendered page on an A4 portrait canvas without rasterizing it."""
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 1:
        return
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    a4_width, a4_height = 595.2756, 841.8898
    tolerance = 3.0
    if (
        abs(width - a4_width) <= tolerance
        and abs(height - a4_height) <= tolerance
    ):
        return
    scale = min(a4_width / width, a4_height / height)
    offset_x = (a4_width - width * scale) / 2
    offset_y = (a4_height - height * scale) / 2
    canvas = PdfWriter()
    target = canvas.add_blank_page(width=a4_width, height=a4_height)
    target.merge_transformed_page(
        page,
        Transformation().scale(scale).translate(offset_x, offset_y),
    )
    temporary = pdf_path.with_suffix(".a4.pdf")
    with temporary.open("wb") as stream:
        canvas.write(stream)
    temporary.replace(pdf_path)


def _scale_statement_pdf(pdf_path: Path) -> None:
    """Reduce the complete statement page by 2.5% around the page center."""
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 1:
        return
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    scale = 0.95
    canvas = PdfWriter()
    target = canvas.add_blank_page(width=width, height=height)
    target.merge_transformed_page(
        page,
        Transformation().scale(scale).translate(
            width * (1 - scale) / 2,
            height * (1 - scale) / 2,
        ),
    )
    temporary = pdf_path.with_suffix(".statement-scaled.pdf")
    with temporary.open("wb") as stream:
        canvas.write(stream)
    temporary.replace(pdf_path)


def _shift_comparison_pdf_right(pdf_path: Path) -> None:
    """Move the complete comparison page right by 1.5 mm without resizing."""
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 1:
        return
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    canvas = PdfWriter()
    target = canvas.add_blank_page(width=width, height=height)
    target.merge_transformed_page(page, Transformation().translate(4.252, 0))
    temporary = pdf_path.with_suffix(".comparison-shifted.pdf")
    with temporary.open("wb") as stream:
        canvas.write(stream)
    temporary.replace(pdf_path)


def _center_comparison_title(pdf_path: Path) -> None:
    """Center only the comparison title text without moving other content."""
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 1:
        return
    page = reader.pages[0]
    content = ContentStream(page.get_contents(), reader)
    in_first_text_object = False
    adjusted = False
    for operands, operator in content.operations:
        if operator == b"BT" and not adjusted:
            in_first_text_object = True
        elif operator == b"ET" and in_first_text_object:
            break
        elif operator == b"Td" and in_first_text_object:
            operands[0] = FloatObject(float(operands[0]) + 4.66)
            adjusted = True
    if not adjusted:
        raise ValueError("Comparison PDF is missing its title text position.")
    page.replace_contents(content)
    writer = PdfWriter()
    writer.add_page(page)
    temporary = pdf_path.with_suffix(".comparison-title-centered.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(pdf_path)


def _prepare_quotation_render_copy(workbook_path: Path) -> None:
    """Match the authoritative Excel quotation print placement in LibreOffice."""
    temporary = workbook_path.with_suffix(".quotation-layout.xlsx")
    sheet_part = "xl/worksheets/sheet1.xml"
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ElementTree.register_namespace("", namespace)

    with zipfile.ZipFile(workbook_path, "r") as source:
        members = [
            (deepcopy(entry), source.read(entry.filename))
            for entry in source.infolist()
        ]

    with zipfile.ZipFile(temporary, "w") as destination:
        for entry, payload in members:
            if entry.filename == sheet_part:
                root = ElementTree.fromstring(payload)
                row_heights = {
                    5: 20.4,
                    7: 5.6,
                    **{row: 29.15 for row in range(8, 12)},
                    **{row: 21.65 for row in range(16, 27)},
                    **{row: 27.18 for row in range(27, 30)},
                    **{row: 26.72 for row in range(30, 35)},
                }
                for row in root.findall(f".//{{{namespace}}}row"):
                    row_number = int(row.get("r", "0"))
                    if row_number in row_heights:
                        row.set("ht", str(row_heights[row_number]))
                        row.set("customHeight", "1")
                for row_number in range(16, 27):
                    description = root.find(
                        f".//{{{namespace}}}c[@r='B{row_number}']"
                    )
                    has_item = description is not None and (
                        description.find(f"{{{namespace}}}is") is not None
                        or description.find(f"{{{namespace}}}v") is not None
                    )
                    if has_item:
                        continue
                    amount = root.find(
                        f".//{{{namespace}}}c[@r='F{row_number}']"
                    )
                    if amount is None:
                        continue
                    formula = amount.find(f"{{{namespace}}}f")
                    if formula is not None:
                        amount.remove(formula)
                    cached = amount.find(f"{{{namespace}}}v")
                    if cached is not None:
                        amount.remove(cached)
                for reference, label in (
                    ("G2", "DATE :\u00a0"),
                    ("G3", "CLIENT :\u00a0"),
                    ("G4", "PRODUCT :\u00a0"),
                ):
                    cell = root.find(
                        f".//{{{namespace}}}c[@r='{reference}']"
                    )
                    if cell is None:
                        raise ValueError(
                            f"Quotation workbook is missing label cell {reference}."
                        )
                    for child in list(cell):
                        cell.remove(child)
                    cell.set("t", "inlineStr")
                    inline = ElementTree.SubElement(
                        cell,
                        f"{{{namespace}}}is",
                    )
                    text = ElementTree.SubElement(
                        inline,
                        f"{{{namespace}}}t",
                    )
                    text.set(
                        "{http://www.w3.org/XML/1998/namespace}space",
                        "preserve",
                    )
                    text.text = label
                print_options = root.find(f"{{{namespace}}}printOptions")
                if print_options is None:
                    raise ValueError("Quotation workbook is missing print options.")
                print_options.attrib.pop("verticalCentered", None)
                page_setup = root.find(f"{{{namespace}}}pageSetup")
                if page_setup is None:
                    raise ValueError("Quotation workbook is missing page setup.")
                page_setup.set("scale", "90")
                payload = ElementTree.tostring(
                    root,
                    encoding="utf-8",
                    xml_declaration=True,
                )
            destination.writestr(entry, payload)
    temporary.replace(workbook_path)


def _align_quotation_pdf_to_reference(pdf_path: Path) -> None:
    """Correct LibreOffice's quotation-only vertical compression as vectors."""
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 1:
        return
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    canvas = PdfWriter()
    target = canvas.add_blank_page(width=width, height=height)
    target.merge_transformed_page(
        page,
        Transformation().scale(1.0, 1.09).translate(-5.1, -88.2),
    )
    temporary = pdf_path.with_suffix(".quotation-aligned.pdf")
    with temporary.open("wb") as stream:
        canvas.write(stream)
    temporary.replace(pdf_path)


def _prepare_statement_render_copy(workbook_path: Path) -> None:
    """Materialize Excel-only table stripes and remove a stray print-range cell."""
    temporary = workbook_path.with_suffix(".statement-layout.xlsx")
    sheet_part = "xl/worksheets/sheet1.xml"
    styles_part = "xl/styles.xml"
    workbook_part = "xl/workbook.xml"
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ElementTree.register_namespace("", namespace)

    with zipfile.ZipFile(workbook_path, "r") as source:
        members = {
            entry.filename: (entry, source.read(entry.filename))
            for entry in source.infolist()
        }

    styles_root = ElementTree.fromstring(members[styles_part][1])
    fills = styles_root.find(f"{{{namespace}}}fills")
    cell_xfs = styles_root.find(f"{{{namespace}}}cellXfs")
    if fills is None or cell_xfs is None:
        raise ValueError("Statement workbook is missing required style tables.")
    beige_fill_id = next(
        (
            index
            for index, fill in enumerate(list(fills))
            if any(
                (node.get("rgb") or "").upper() == "FFF8F5EE"
                for node in fill.iter()
            )
        ),
        None,
    )
    if beige_fill_id is None:
        return

    sheet_root = ElementTree.fromstring(members[sheet_part][1])
    style_variants: dict[tuple[int, int], int] = {}
    statement_rows = (7, 8, 10, 11, 12, 13, 14, 15, 16, 17)
    for index, row_number in enumerate(statement_rows):
        fill_id = beige_fill_id if index % 2 == 0 else 0
        for column in ("B", "C", "D", "E"):
            cell = sheet_root.find(
                f".//{{{namespace}}}c[@r='{column}{row_number}']"
            )
            if cell is None:
                continue
            style_id = int(cell.get("s", "0"))
            key = (style_id, fill_id)
            if key not in style_variants:
                variant = deepcopy(list(cell_xfs)[style_id])
                variant.set("fillId", str(fill_id))
                variant.set("applyFill", "1")
                cell_xfs.append(variant)
                style_variants[key] = len(list(cell_xfs)) - 1
            cell.set("s", str(style_variants[key]))
    cell_xfs.set("count", str(len(list(cell_xfs))))

    stray = sheet_root.find(f".//{{{namespace}}}c[@r='J17']")
    if stray is not None:
        for row in sheet_root.findall(f".//{{{namespace}}}row"):
            if stray in list(row):
                row.remove(stray)
                break
    page_setup = sheet_root.find(f"{{{namespace}}}pageSetup")
    if page_setup is None:
        raise ValueError("Statement workbook is missing page setup.")
    # LibreOffice recalculates fit-to-page scaling from populated cell content,
    # which made an otherwise identical generated sheet render slightly smaller
    # than the authoritative template. A fixed print scale keeps the template
    # geometry stable while retaining the full one-page Statement print area.
    page_setup.attrib.pop("fitToWidth", None)
    page_setup.attrib.pop("fitToHeight", None)
    page_setup.set("scale", "95")
    sheet_properties = sheet_root.find(f"{{{namespace}}}sheetPr")
    if sheet_properties is not None:
        page_setup_properties = sheet_properties.find(
            f"{{{namespace}}}pageSetUpPr"
        )
        if page_setup_properties is not None:
            page_setup_properties.attrib.pop("fitToPage", None)

    workbook_root = ElementTree.fromstring(members[workbook_part][1])
    defined_names = workbook_root.find(f"{{{namespace}}}definedNames")
    if defined_names is None:
        defined_names = ElementTree.Element(f"{{{namespace}}}definedNames")
        calculation = workbook_root.find(f"{{{namespace}}}calcPr")
        if calculation is None:
            workbook_root.append(defined_names)
        else:
            workbook_root.insert(list(workbook_root).index(calculation), defined_names)
    print_area = next(
        (
            node
            for node in defined_names.findall(f"{{{namespace}}}definedName")
            if node.get("name") == "_xlnm.Print_Area"
            and node.get("localSheetId") == "0"
        ),
        None,
    )
    if print_area is None:
        print_area = ElementTree.SubElement(
            defined_names,
            f"{{{namespace}}}definedName",
            {"name": "_xlnm.Print_Area", "localSheetId": "0"},
        )
    print_area.text = "'청구서'!$B$1:$E$24"

    replacements = {
        styles_part: ElementTree.tostring(
            styles_root, encoding="utf-8", xml_declaration=True
        ),
        sheet_part: ElementTree.tostring(
            sheet_root, encoding="utf-8", xml_declaration=True
        ),
        workbook_part: ElementTree.tostring(
            workbook_root, encoding="utf-8", xml_declaration=True
        ),
    }
    with zipfile.ZipFile(temporary, "w") as destination:
        for name, (entry, payload) in members.items():
            destination.writestr(entry, replacements.get(name, payload))
    temporary.replace(workbook_path)


def _remove_duplicate_shape_anchors(payload: bytes) -> bytes:
    """Drop only pathological repeated text shapes from a conversion copy."""
    drawing_namespace = (
        "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
    )
    text_namespace = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ElementTree.register_namespace("xdr", drawing_namespace)
    ElementTree.register_namespace("a", text_namespace)
    root = ElementTree.fromstring(payload)
    anchors: list[tuple[ElementTree.Element, str]] = []
    for anchor in list(root):
        shape = anchor.find(f".//{{{drawing_namespace}}}sp")
        if shape is None:
            continue
        text = "".join(
            node.text or ""
            for node in shape.findall(f".//{{{text_namespace}}}t")
        )
        compact = "".join(text.split())
        if compact:
            anchors.append((anchor, compact))
    repeated = {
        text
        for text, count in Counter(text for _, text in anchors).items()
        if count >= 10
    }
    if not repeated:
        return payload
    for anchor, text in anchors:
        if text in repeated:
            root.remove(anchor)
    return ElementTree.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
