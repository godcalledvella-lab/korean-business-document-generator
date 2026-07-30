from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from excel_renderer.pdf_exporter import (
    DEFAULT_WORKSHEET,
    EXCEL_BUNDLE_ID,
    EXCEL_PDF_APPLESCRIPT,
    EXCEL_PRINT_PDF_APPLESCRIPT,
    ExcelNotInstalledError,
    ExcelPdfExportError,
    build_osascript_command,
    export_excel_pdf,
    find_excel_application,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_excel_installation_detection(tmp_path):
    missing = tmp_path / "Missing Excel.app"
    installed = tmp_path / "Microsoft Excel.app"
    installed.mkdir()

    assert find_excel_application((missing, installed)) == installed.resolve()
    assert find_excel_application((missing,)) is None


def test_applescript_command_construction_handles_paths_as_arguments(tmp_path):
    source = tmp_path / '입력 "statement".xlsx'
    output = tmp_path / "PDF 결과.pdf"

    command = build_osascript_command(source, output)

    assert command[:3] == ["/usr/bin/osascript", "-e", EXCEL_PDF_APPLESCRIPT]
    assert command[3:] == [
        str(source.resolve()),
        str(output.resolve()),
        DEFAULT_WORKSHEET,
    ]
    assert EXCEL_BUNDLE_ID == "com.microsoft.Excel"
    assert 'tell application "Microsoft Excel"' in EXCEL_PDF_APPLESCRIPT
    assert "activate" in EXCEL_PDF_APPLESCRIPT
    assert "workbook file name sourcePath" in EXCEL_PDF_APPLESCRIPT
    assert "set targetWorksheet to worksheet worksheetName of openedWorkbook" in (
        EXCEL_PDF_APPLESCRIPT
    )
    assert (
        "save as targetWorksheet filename outputPath file format PDF file format"
        in EXCEL_PDF_APPLESCRIPT
    )
    assert 'do shell script "/usr/bin/test -s "' in EXCEL_PDF_APPLESCRIPT
    assert "set display alerts to true" in EXCEL_PDF_APPLESCRIPT
    assert "file format PDF file format" in EXCEL_PDF_APPLESCRIPT
    assert "close openedWorkbook saving no" in EXCEL_PDF_APPLESCRIPT
    assert "DEBUG workbook name Excel opened:" in EXCEL_PDF_APPLESCRIPT
    assert "DEBUG worksheet name:" in EXCEL_PDF_APPLESCRIPT
    assert "DEBUG workbook became active:" in EXCEL_PDF_APPLESCRIPT
    assert "DEBUG PDF export command returned:" in EXCEL_PDF_APPLESCRIPT
    assert "DEBUG output file exists immediately afterward:" in EXCEL_PDF_APPLESCRIPT


def test_print_strategy_constructs_native_print_workflow(tmp_path):
    source = tmp_path / "statement.xlsx"
    output = tmp_path / "statement.pdf"

    command = build_osascript_command(source, output, strategy="print")

    assert command[:3] == [
        "/usr/bin/osascript",
        "-e",
        EXCEL_PRINT_PDF_APPLESCRIPT,
    ]
    assert command[3:] == [
        str(source.resolve()),
        str(output.resolve()),
        DEFAULT_WORKSHEET,
    ]
    assert 'keystroke "p" using command down' in EXCEL_PRINT_PDF_APPLESCRIPT
    assert "UI elements enabled" in EXCEL_PRINT_PDF_APPLESCRIPT
    assert "Save as PDF" in EXCEL_PRINT_PDF_APPLESCRIPT
    assert "close openedWorkbook saving no" in EXCEL_PRINT_PDF_APPLESCRIPT
    assert "DEBUG workbook name Excel opened:" in EXCEL_PRINT_PDF_APPLESCRIPT
    assert "DEBUG PDF print workflow returned:" in EXCEL_PRINT_PDF_APPLESCRIPT


def test_source_hash_is_unchanged_after_export(tmp_path, monkeypatch):
    excel = tmp_path / "Microsoft Excel.app"
    excel.mkdir()
    source = tmp_path / "statement.xlsx"
    source.write_bytes(b"unchanged workbook bytes")
    output = tmp_path / "statement.pdf"
    original_hash = _digest(source)

    monkeypatch.setattr(
        "excel_renderer.pdf_exporter.find_excel_application", lambda: excel
    )

    def fake_run(command, **kwargs):
        if command[0] == "/usr/bin/osacompile":
            return subprocess.CompletedProcess(command, 0, "", "")
        Path(command[4]).write_bytes(b"%PDF-1.7\nmock\n%%EOF\n")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("excel_renderer.pdf_exporter.subprocess.run", fake_run)

    assert export_excel_pdf(source, output) == output.resolve()
    assert _digest(source) == original_hash
    assert output.read_bytes().startswith(b"%PDF-")


def test_print_strategy_preserves_source_hash(tmp_path, monkeypatch):
    excel = tmp_path / "Microsoft Excel.app"
    excel.mkdir()
    source = tmp_path / "statement.xlsx"
    source.write_bytes(b"unchanged workbook bytes")
    output = tmp_path / "statement.pdf"
    original_hash = _digest(source)
    monkeypatch.setattr(
        "excel_renderer.pdf_exporter.find_excel_application", lambda: excel
    )

    def fake_run(command, **kwargs):
        if command[0] == "/usr/bin/osacompile":
            return subprocess.CompletedProcess(command, 0, "", "")
        assert command[2] == EXCEL_PRINT_PDF_APPLESCRIPT
        Path(command[4]).write_bytes(b"%PDF-1.7\nmock\n%%EOF\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("excel_renderer.pdf_exporter.subprocess.run", fake_run)

    assert export_excel_pdf(source, output, strategy="print") == output.resolve()
    assert _digest(source) == original_hash


def test_print_strategy_failure_includes_permission_steps(tmp_path, monkeypatch):
    excel = tmp_path / "Microsoft Excel.app"
    excel.mkdir()
    source = tmp_path / "statement.xlsx"
    source.write_bytes(b"xlsx")
    monkeypatch.setattr(
        "excel_renderer.pdf_exporter.find_excel_application", lambda: excel
    )
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0 if command[0] == "/usr/bin/osacompile" else 1,
            "",
            "",
        )

    monkeypatch.setattr("excel_renderer.pdf_exporter.subprocess.run", fake_run)

    with pytest.raises(ExcelPdfExportError, match="Privacy & Security > Accessibility"):
        export_excel_pdf(source, tmp_path / "out.pdf", strategy="print")


def test_clear_failure_when_excel_is_unavailable(tmp_path, monkeypatch):
    source = tmp_path / "statement.xlsx"
    source.write_bytes(b"xlsx")
    output = tmp_path / "statement.pdf"
    monkeypatch.setattr(
        "excel_renderer.pdf_exporter.find_excel_application", lambda: None
    )

    with pytest.raises(ExcelNotInstalledError, match="No fallback was used"):
        export_excel_pdf(source, output)
    assert not output.exists()
