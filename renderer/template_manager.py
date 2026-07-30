"""Discover and validate presentation templates without rendering them."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MANIFEST_NAME = "template.json"
_SUPPORTED_MANIFEST_VERSION = 1


class TemplateError(Exception):
    """Base error for template discovery and loading."""


class TemplateNotFoundError(TemplateError):
    """Raised when a requested company or document template does not exist."""


class TemplateValidationError(TemplateError):
    """Raised when a template manifest or required asset is invalid."""


@dataclass(frozen=True)
class TemplateDefinition:
    """Validated metadata describing one template directory."""

    company: str
    document_type: str
    path: Path
    manifest_path: Path
    required_files: tuple[Path, ...]
    entrypoint: Path | None = None
    description: str | None = None
    locked: bool = False


class TemplateManager:
    """Read-only registry for company and document-type templates.

    The manager understands directory structure and manifest metadata only. It
    does not interpret template assets, transform document data, or apply
    company-specific rules.
    """

    def __init__(self, templates_root: str | Path) -> None:
        self.templates_root = Path(templates_root).expanduser().resolve()
        if not self.templates_root.exists():
            raise TemplateNotFoundError(
                f"Templates root does not exist: {self.templates_root}"
            )
        if not self.templates_root.is_dir():
            raise TemplateValidationError(
                f"Templates root is not a directory: {self.templates_root}"
            )

    def discover_templates(self) -> tuple[TemplateDefinition, ...]:
        """Return all valid templates in deterministic company/type order."""

        templates: list[TemplateDefinition] = []
        for company_dir in self._visible_directories(self.templates_root):
            for document_dir in self._visible_directories(company_dir):
                templates.append(
                    self.load_template(company_dir.name, document_dir.name)
                )
        return tuple(templates)

    def load_template(
        self, company: str, document_type: str
    ) -> TemplateDefinition:
        """Load and validate a template by company and document type."""

        self._validate_identifier(company, "company")
        self._validate_identifier(document_type, "document type")

        template_path = self.templates_root / company / document_type
        if not template_path.exists() or not template_path.is_dir():
            raise TemplateNotFoundError(
                "Template not found for "
                f"company={company!r}, document_type={document_type!r}: "
                f"{template_path}"
            )

        manifest_path = template_path / _MANIFEST_NAME
        if not manifest_path.is_file():
            raise TemplateValidationError(
                f"Required template manifest is missing: {manifest_path}"
            )

        manifest = self._read_manifest(manifest_path)
        self._validate_manifest_identity(
            manifest, company, document_type, manifest_path
        )
        required_files = self._validate_required_files(
            manifest, template_path, manifest_path
        )
        entrypoint = self._validate_entrypoint(
            manifest, template_path, required_files, manifest_path
        )

        description = manifest.get("description")
        if description is not None and not isinstance(description, str):
            raise TemplateValidationError(
                f"'description' must be a string in {manifest_path}"
            )

        locked = manifest.get("locked", False)
        if not isinstance(locked, bool):
            raise TemplateValidationError(
                f"'locked' must be a boolean in {manifest_path}"
            )

        return TemplateDefinition(
            company=company,
            document_type=document_type,
            path=template_path.resolve(),
            manifest_path=manifest_path.resolve(),
            required_files=required_files,
            entrypoint=entrypoint,
            description=description,
            locked=locked,
        )

    @staticmethod
    def _visible_directories(parent: Path) -> list[Path]:
        return sorted(
            (
                path
                for path in parent.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            ),
            key=lambda path: path.name,
        )

    @staticmethod
    def _validate_identifier(value: str, label: str) -> None:
        if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
            raise TemplateValidationError(
                f"Invalid {label} identifier {value!r}; use lowercase letters, "
                "digits, hyphens, or underscores."
            )

    @staticmethod
    def _read_manifest(manifest_path: Path) -> dict[str, Any]:
        try:
            content = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(content)
        except OSError as error:
            raise TemplateValidationError(
                f"Could not read template manifest {manifest_path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise TemplateValidationError(
                f"Template manifest is not valid JSON: {manifest_path} "
                f"(line {error.lineno}, column {error.colno})"
            ) from error

        if not isinstance(manifest, dict):
            raise TemplateValidationError(
                f"Template manifest must contain a JSON object: {manifest_path}"
            )
        return manifest

    @staticmethod
    def _validate_manifest_identity(
        manifest: dict[str, Any],
        company: str,
        document_type: str,
        manifest_path: Path,
    ) -> None:
        required = ("manifest_version", "company", "document_type", "required_files")
        missing = [field for field in required if field not in manifest]
        if missing:
            raise TemplateValidationError(
                f"Template manifest {manifest_path} is missing required field(s): "
                f"{', '.join(missing)}"
            )

        version = manifest["manifest_version"]
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != _SUPPORTED_MANIFEST_VERSION
        ):
            raise TemplateValidationError(
                f"Unsupported 'manifest_version' in {manifest_path}: {version!r}; "
                f"expected {_SUPPORTED_MANIFEST_VERSION}."
            )
        if manifest["company"] != company:
            raise TemplateValidationError(
                f"Manifest company {manifest['company']!r} does not match "
                f"directory {company!r}: {manifest_path}"
            )
        if manifest["document_type"] != document_type:
            raise TemplateValidationError(
                f"Manifest document_type {manifest['document_type']!r} does not "
                f"match directory {document_type!r}: {manifest_path}"
            )

    @staticmethod
    def _validate_required_files(
        manifest: dict[str, Any],
        template_path: Path,
        manifest_path: Path,
    ) -> tuple[Path, ...]:
        entries = manifest["required_files"]
        if not isinstance(entries, list) or any(
            not isinstance(entry, str) or not entry for entry in entries
        ):
            raise TemplateValidationError(
                f"'required_files' must be an array of non-empty strings in "
                f"{manifest_path}"
            )
        if len(entries) != len(set(entries)):
            raise TemplateValidationError(
                f"'required_files' contains duplicate paths in {manifest_path}"
            )

        template_root = template_path.resolve()
        validated: list[Path] = []
        for entry in entries:
            relative_path = Path(entry)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise TemplateValidationError(
                    f"Required file path must stay inside its template directory: "
                    f"{entry!r} in {manifest_path}"
                )

            asset_path = (template_path / relative_path).resolve()
            if not asset_path.is_relative_to(template_root):
                raise TemplateValidationError(
                    f"Required file resolves outside its template directory: "
                    f"{entry!r} in {manifest_path}"
                )
            if not asset_path.is_file():
                raise TemplateValidationError(
                    f"Required template file is missing: {asset_path} "
                    f"(declared by {manifest_path})"
                )
            validated.append(asset_path)

        return tuple(validated)

    @staticmethod
    def _validate_entrypoint(
        manifest: dict[str, Any],
        template_path: Path,
        required_files: tuple[Path, ...],
        manifest_path: Path,
    ) -> Path | None:
        entry = manifest.get("entrypoint")
        if entry is None:
            return None
        if not isinstance(entry, str) or not entry:
            raise TemplateValidationError(
                f"'entrypoint' must be a non-empty string in {manifest_path}"
            )

        relative_path = Path(entry)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise TemplateValidationError(
                f"Template entrypoint must stay inside its template directory: "
                f"{entry!r} in {manifest_path}"
            )

        entrypoint = (template_path / relative_path).resolve()
        if entrypoint not in required_files:
            raise TemplateValidationError(
                f"Template entrypoint must also appear in 'required_files': "
                f"{entry!r} in {manifest_path}"
            )
        return entrypoint
