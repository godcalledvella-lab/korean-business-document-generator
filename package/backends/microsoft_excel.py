"""Native Microsoft Excel backend for supported macOS automation."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from excel_renderer.pdf_exporter import (
    EXCEL_PDF_APPLESCRIPT,
    build_osascript_command,
    find_excel_application,
)
from package.models import BackendAvailability, RenderResult

from .base import BackendRenderError, PDFBackend


WORKSHEETS = {
    "statement": "청구서",
    "quotation": "견적서",
    "comparison": "Sheet1",
}


class MicrosoftExcelBackend(PDFBackend):
    name = "excel"

    def __init__(self, *, timeout: float = 180) -> None:
        self.timeout = timeout

    def availability(self) -> BackendAvailability:
        application = find_excel_application()
        if application is None:
            return BackendAvailability(
                self.name,
                False,
                "Microsoft Excel for macOS was not found.",
            )
        for executable in (Path("/usr/bin/osascript"), Path("/usr/bin/osacompile")):
            if not executable.is_file():
                return BackendAvailability(
                    self.name,
                    False,
                    f"Required local automation executable is missing: {executable}",
                )
        return BackendAvailability(
            self.name,
            True,
            f"Detected Microsoft Excel at {application}; native save-as PDF automation is available.",
        )

    def render_xlsx(self, input_path: Path, output_path: Path) -> RenderResult:
        source = input_path.resolve()
        output = output_path.resolve()
        worksheet = WORKSHEETS.get(source.stem.lower())
        if worksheet is None:
            raise BackendRenderError(
                f"No worksheet mapping is registered for {source.name}.",
                step=f"rendering {source.name}",
                backend=self.name,
            )
        before = _sha256(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="excel-render-", dir=output.parent
        ) as temporary:
            work = Path(temporary)
            copied = work / source.name
            shutil.copy2(source, copied)
            command = tuple(
                build_osascript_command(copied, output, worksheet, "save-as")
            )
            script_path = work / "export.applescript"
            compiled_path = work / "export.scpt"
            script_path.write_text(EXCEL_PDF_APPLESCRIPT, encoding="utf-8")
            compile_command = (
                "/usr/bin/osacompile",
                "-o",
                str(compiled_path),
                str(script_path),
            )
            try:
                compiled = subprocess.run(
                    compile_command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if compiled.returncode != 0:
                    raise BackendRenderError(
                        "Microsoft Excel AppleScript failed syntax validation.",
                        step=f"rendering {source.name}",
                        backend=self.name,
                        command=compile_command,
                        exit_code=compiled.returncode,
                        stdout=compiled.stdout,
                        stderr=compiled.stderr,
                        working_path=work,
                        sources_unchanged=_sha256(source) == before,
                    )
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except BackendRenderError:
                raise
            except (OSError, subprocess.TimeoutExpired) as error:
                raise BackendRenderError(
                    str(error),
                    step=f"rendering {source.name}",
                    backend=self.name,
                    command=command,
                    working_path=work,
                    sources_unchanged=_sha256(source) == before,
                ) from error
            if completed.returncode != 0 or not output.is_file():
                raise BackendRenderError(
                    "Microsoft Excel PDF export failed. Excel may be unavailable, "
                    "unlicensed, or PDF export may be unsupported.",
                    step=f"rendering {source.name}",
                    backend=self.name,
                    command=command,
                    exit_code=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    working_path=work,
                    sources_unchanged=_sha256(source) == before,
                )
        after = _sha256(source)
        return RenderResult(
            self.name,
            source,
            output,
            command,
            0,
            completed.stdout,
            completed.stderr,
            before,
            after,
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
