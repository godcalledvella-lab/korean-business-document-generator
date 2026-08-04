"""Export one worksheet to PDF through native Microsoft Excel for macOS."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


EXCEL_BUNDLE_ID = "com.microsoft.Excel"
DEFAULT_WORKSHEET = "청구서"
DEFAULT_EXCEL_PATHS = (
    Path("/Applications/Microsoft Excel.app"),
    Path.home() / "Applications/Microsoft Excel.app",
)

# Arguments are passed through argv, rather than interpolated into AppleScript.
# This makes spaces, quotes, and non-ASCII filenames safe.
EXCEL_PDF_APPLESCRIPT = r'''
on run argv
    set sourcePath to item 1 of argv
    set outputPath to item 2 of argv
    set worksheetName to item 3 of argv
    set openedWorkbook to missing value
    set currentStep to "starting Excel"

    tell application "Microsoft Excel"
        activate
        set previousAlerts to display alerts
        set display alerts to true
        try
            set currentStep to "opening workbook"
            set openedWorkbook to open workbook workbook file name sourcePath
            set openedWorkbookName to name of openedWorkbook as text
            log "DEBUG workbook name Excel opened: " & openedWorkbookName

            set currentStep to "resolving worksheet"
            set targetWorksheet to worksheet worksheetName of openedWorkbook
            set openedWorksheetName to name of targetWorksheet as text
            log "DEBUG worksheet name: " & openedWorksheetName

            set currentStep to "activating worksheet"
            activate object targetWorksheet
            set activeWorkbookName to name of active workbook as text
            set workbookIsActive to (activeWorkbookName is openedWorkbookName)
            log "DEBUG workbook became active: " & (workbookIsActive as text)

            delay 1
            log "DEBUG output path: " & outputPath
            set currentStep to "executing PDF export"
            save as targetWorksheet filename outputPath file format PDF file format
            log "DEBUG PDF export command returned: true"

            set currentStep to "checking output file"
            set outputExists to false
            repeat with attemptNumber from 1 to 300
                try
                    do shell script "/usr/bin/test -s " & quoted form of outputPath
                    set outputExists to true
                    exit repeat
                end try
                delay 0.1
            end repeat
            log "DEBUG output file exists immediately afterward: " & (outputExists as text)
            if outputExists is false then
                error "Excel returned from PDF export but did not create the requested file." number -1728
            end if

            set currentStep to "closing workbook without saving"
            close openedWorkbook saving no
            set openedWorkbook to missing value
            set display alerts to previousAlerts
        on error errorMessage number errorNumber
            log "DEBUG failure step: " & currentStep
            log "DEBUG AppleScript error " & (errorNumber as text) & ": " & errorMessage
            if openedWorkbook is not missing value then
                close openedWorkbook saving no
            end if
            set display alerts to previousAlerts
            error errorMessage number errorNumber
        end try
    end tell
end run
'''.strip()

EXCEL_PRINT_PDF_APPLESCRIPT = r'''
on waitForSheet(excelProcess, maximumAttempts)
    tell application "System Events"
        repeat with attemptNumber from 1 to maximumAttempts
            if exists sheet 1 of window 1 of excelProcess then
                return sheet 1 of window 1 of excelProcess
            end if
            delay 0.1
        end repeat
    end tell
    error "Timed out waiting for a macOS dialog sheet." number -1712
end waitForSheet

on run argv
    set sourcePath to item 1 of argv
    set outputPath to item 2 of argv
    set worksheetName to item 3 of argv
    set outputDirectory to do shell script "/usr/bin/dirname -- " & quoted form of outputPath
    set outputName to do shell script "/usr/bin/basename -- " & quoted form of outputPath
    set openedWorkbook to missing value
    set currentStep to "checking UI automation permission"

    tell application "System Events"
        if UI elements enabled is false then
            error "Accessibility permission is disabled for the process running osascript." number -1719
        end if
    end tell

    tell application "Microsoft Excel"
        activate
        set previousAlerts to display alerts
        set display alerts to true
        try
            set currentStep to "opening workbook"
            set openedWorkbook to open workbook workbook file name sourcePath
            set openedWorkbookName to name of openedWorkbook as text
            log "DEBUG workbook name Excel opened: " & openedWorkbookName

            set currentStep to "resolving worksheet"
            set targetWorksheet to worksheet worksheetName of openedWorkbook
            set openedWorksheetName to name of targetWorksheet as text
            log "DEBUG worksheet name: " & openedWorksheetName

            set currentStep to "activating worksheet"
            activate object targetWorksheet
            set activeWorkbookName to name of active workbook as text
            set workbookIsActive to (activeWorkbookName is openedWorkbookName)
            log "DEBUG workbook became active: " & (workbookIsActive as text)
            log "DEBUG output path: " & outputPath

            set currentStep to "opening macOS print dialog"
            tell application "System Events"
                tell process "Microsoft Excel"
                    set frontmost to true
                    keystroke "p" using command down
                end tell
                set excelProcess to process "Microsoft Excel"
            end tell
            set printDialog to my waitForSheet(excelProcess, 200)
            log "DEBUG print command returned: true"

            set currentStep to "opening PDF menu"
            tell application "System Events"
                tell process "Microsoft Excel"
                    set pdfMenuButton to missing value
                    repeat with candidateButton in menu buttons of printDialog
                        try
                            set candidateName to name of candidateButton as text
                            set candidateValue to value of candidateButton as text
                            if candidateName contains "PDF" or candidateValue contains "PDF" then
                                set pdfMenuButton to candidateButton
                                exit repeat
                            end if
                        end try
                    end repeat
                    if pdfMenuButton is missing value then
                        error "Could not find the PDF menu in the macOS print dialog." number -1728
                    end if
                    click pdfMenuButton
                    delay 0.5

                    set savePdfItem to missing value
                    repeat with candidateItem in menu items of menu 1 of pdfMenuButton
                        set candidateName to name of candidateItem as text
                        if candidateName contains "PDF" and (candidateName contains "Save" or candidateName contains "저장") then
                            set savePdfItem to candidateItem
                            exit repeat
                        end if
                    end repeat
                    if savePdfItem is missing value then
                        error "Could not find Save as PDF in the macOS PDF menu." number -1728
                    end if
                    click savePdfItem
                end tell
            end tell

            set currentStep to "saving PDF in macOS save dialog"
            delay 0.8
            tell application "System Events"
                tell process "Microsoft Excel"
                    keystroke "g" using {command down, shift down}
                    delay 0.5
                    keystroke outputDirectory
                    key code 36
                    delay 0.8
                    keystroke "a" using command down
                    keystroke outputName
                    key code 36
                end tell
            end tell
            log "DEBUG PDF print workflow returned: true"

            set currentStep to "checking output file"
            set outputExists to false
            repeat with attemptNumber from 1 to 200
                try
                    do shell script "/usr/bin/test -s " & quoted form of outputPath
                    set outputExists to true
                    exit repeat
                end try
                delay 0.1
            end repeat
            log "DEBUG output file exists immediately afterward: " & (outputExists as text)

            set currentStep to "closing workbook without saving"
            close openedWorkbook saving no
            set openedWorkbook to missing value
            set display alerts to previousAlerts
        on error errorMessage number errorNumber
            log "DEBUG failure step: " & currentStep
            log "DEBUG AppleScript error " & (errorNumber as text) & ": " & errorMessage
            if openedWorkbook is not missing value then
                close openedWorkbook saving no
            end if
            set display alerts to previousAlerts
            error errorMessage number errorNumber
        end try
    end tell
end run
'''.strip()


class ExcelPdfExportError(RuntimeError):
    """Base error for native Excel PDF export."""


class ExcelNotInstalledError(ExcelPdfExportError):
    """Raised when Microsoft Excel cannot be found on this Mac."""


def find_excel_application(
    candidates: Sequence[Path] | None = None,
) -> Path | None:
    """Return the first installed Microsoft Excel application bundle."""

    paths = tuple(candidates) if candidates is not None else DEFAULT_EXCEL_PATHS
    for candidate in paths:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def build_osascript_command(
    source: str | Path,
    output: str | Path,
    worksheet: str = DEFAULT_WORKSHEET,
    strategy: str = "save-as",
) -> list[str]:
    """Build the native export command without executing it."""

    script = _script_for_strategy(strategy)
    return [
        "/usr/bin/osascript",
        "-e",
        script,
        str(Path(source).resolve()),
        str(Path(output).resolve()),
        worksheet,
    ]


def export_excel_pdf(
    source: str | Path,
    output: str | Path,
    worksheet: str = DEFAULT_WORKSHEET,
    *,
    timeout: float = 120,
    strategy: str = "save-as",
) -> Path:
    """Export *worksheet* through Excel and prove the workbook was not saved."""

    excel = find_excel_application()
    if excel is None:
        raise ExcelNotInstalledError(
            "Microsoft Excel is not installed. Expected "
            "'/Applications/Microsoft Excel.app' or "
            "'~/Applications/Microsoft Excel.app'. No fallback was used."
        )

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if not source_path.is_file():
        raise ExcelPdfExportError(f"Source workbook does not exist: {source_path}")
    if source_path == output_path:
        raise ExcelPdfExportError("PDF output must not overwrite the source workbook.")
    if output_path.suffix.lower() != ".pdf":
        raise ExcelPdfExportError(f"PDF output must use a .pdf extension: {output_path}")
    if not worksheet:
        raise ExcelPdfExportError("Worksheet name must not be empty.")

    source_hash = _sha256(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    script = _script_for_strategy(strategy)
    command = build_osascript_command(source_path, output_path, worksheet, strategy)
    with tempfile.TemporaryDirectory(prefix="excel-pdf-applescript-") as temp_dir:
        script_path = Path(temp_dir) / "export.applescript"
        compiled_path = Path(temp_dir) / "export.scpt"
        script_path.write_text(script, encoding="utf-8")
        try:
            compile_result = subprocess.run(
                [
                    "/usr/bin/osacompile",
                    "-o",
                    str(compiled_path),
                    str(script_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExcelPdfExportError(
                f"Could not compile generated AppleScript: {error}"
            ) from error
        if compile_result.stdout:
            print(compile_result.stdout, end="", flush=True)
        if compile_result.stderr:
            print(compile_result.stderr, end="", file=sys.stderr, flush=True)
        if compile_result.returncode != 0:
            diagnostic = re.search(
                r":(\d+): error: (.+)",
                compile_result.stderr,
            )
            if diagnostic:
                line_number, message = diagnostic.groups()
                raise ExcelPdfExportError(
                    f"AppleScript syntax error at line {line_number}: {message}"
                )
            raise ExcelPdfExportError(
                "AppleScript compilation failed with osacompile exit code "
                f"{compile_result.returncode}."
            )
    try:
        completed = subprocess.run(
            command,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExcelPdfExportError(f"Could not run Microsoft Excel export: {error}") from error

    if completed.returncode != 0:
        permission_help = ""
        if strategy == "print":
            permission_help = (
                " Enable System Settings > Privacy & Security > Accessibility for "
                "the terminal or application running Python. Also enable System "
                "Settings > Privacy & Security > Automation so that application "
                "may control Microsoft Excel and System Events."
            )
        raise ExcelPdfExportError(
            f"Microsoft Excel PDF export failed with osascript exit code "
            f"{completed.returncode}. AppleScript output was streamed above."
            f"{permission_help}"
        )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ExcelPdfExportError(
            f"Microsoft Excel reported success but did not create a PDF: {output_path}"
        )
    if _sha256(source_path) != source_hash:
        raise ExcelPdfExportError(
            "Source workbook changed during export; Excel was instructed to close "
            "without saving."
        )
    return output_path


def _script_for_strategy(strategy: str) -> str:
    if strategy == "save-as":
        return EXCEL_PDF_APPLESCRIPT
    if strategy == "print":
        return EXCEL_PRINT_PDF_APPLESCRIPT
    raise ExcelPdfExportError(
        f"Unknown PDF export strategy {strategy!r}; expected 'save-as' or 'print'."
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export an Excel worksheet to PDF using Microsoft Excel for macOS."
    )
    parser.add_argument("source", type=Path, help="Existing .xlsx workbook")
    parser.add_argument("output", type=Path, help="Destination .pdf file")
    parser.add_argument(
        "--worksheet",
        default=DEFAULT_WORKSHEET,
        help=f"Worksheet to export (default: {DEFAULT_WORKSHEET})",
    )
    parser.add_argument(
        "--strategy",
        choices=("save-as", "print"),
        default="save-as",
        help="PDF export strategy (default: save-as)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = export_excel_pdf(
            args.source,
            args.output,
            args.worksheet,
            strategy=args.strategy,
        )
    except ExcelPdfExportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
