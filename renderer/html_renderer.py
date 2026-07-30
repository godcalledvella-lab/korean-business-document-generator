"""Render business-rule view models through selected HTML templates."""

from __future__ import annotations

import base64
import mimetypes
from decimal import Decimal
from html import escape
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError as JinjaTemplateError,
    select_autoescape,
)

from business import ViewModel
from .template_manager import TemplateDefinition, TemplateManager


class RendererError(Exception):
    """Base error for canonical JSON to presentation rendering."""


class InputDataError(RendererError):
    """Raised when renderer input is not a business-rule view model."""


class RenderError(RendererError):
    """Raised when a template cannot produce an HTML document."""


class HtmlRenderer:
    """Render canonical structured JSON without applying business rules."""

    def __init__(
        self,
        template_manager: TemplateManager,
    ) -> None:
        self.template_manager = template_manager

    def render_to_file(
        self,
        view_model: ViewModel,
        company: str,
        template_document_type: str,
        output_path: str | Path,
    ) -> Path:
        """Render one business-rule view model to an HTML file."""

        template = self.template_manager.load_template(
            company, template_document_type
        )
        html = self.render(view_model, template)

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.write_text(html, encoding="utf-8")
        except OSError as error:
            raise RenderError(
                f"Could not write rendered HTML to {destination}: {error}"
            ) from error
        return destination.resolve()

    def render(
        self,
        view_model: ViewModel,
        template: TemplateDefinition,
    ) -> str:
        """Render a structured view model with a loaded template."""

        if not isinstance(view_model, ViewModel):
            raise InputDataError(
                "Renderer input must be a ViewModel produced by BusinessRuleEngine."
            )
        if view_model.type.value != template.document_type:
            raise InputDataError(
                f"View model type {view_model.type.value!r} does not match "
                f"template document type {template.document_type!r}."
            )
        if template.entrypoint is None:
            raise RenderError(
                "Selected template has no HTML entrypoint: "
                f"company={template.company!r}, "
                f"document_type={template.document_type!r}"
            )

        environment = Environment(
            loader=FileSystemLoader(str(template.path)),
            autoescape=select_autoescape(enabled_extensions=("html", "j2")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        environment.filters["amount"] = _format_amount
        environment.filters["date_ko"] = _format_korean_date
        environment.filters["multiline"] = _format_multiline
        environment.globals["template_asset"] = (
            lambda relative_path: _template_asset_data_uri(
                template, relative_path
            )
        )

        try:
            jinja_template = environment.get_template(template.entrypoint.name)
            return jinja_template.render(view_model.data)
        except JinjaTemplateError as error:
            raise RenderError(
                f"Failed to render template {template.entrypoint}: {error}"
            ) from error

def _format_amount(value: int | float | Decimal) -> str:
    """Apply display-only grouping without changing the canonical value."""

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError("The 'amount' filter requires a JSON number.")
    decimal_value = Decimal(str(value))
    formatted = f"{decimal_value:,.12f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _format_korean_date(value: str) -> str:
    """Convert an ISO date to a Korean display form without date arithmetic."""

    parts = value.split("-")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("The 'date_ko' filter requires an ISO YYYY-MM-DD date.")
    year, month, day = (int(part) for part in parts)
    return f"{year}년 {month}월 {day}일"


def _format_multiline(value: str) -> str:
    """Escape user text and preserve explicit newlines for HTML display."""

    return escape(value).replace("\n", "<br>\n")


def _template_asset_data_uri(
    template: TemplateDefinition,
    relative_path: str,
) -> str:
    """Embed a validated static template asset in the HTML preview."""

    asset_path = (template.path / relative_path).resolve()
    if asset_path not in template.required_files:
        raise RenderError(
            f"Template asset is not declared in 'required_files': {relative_path!r}"
        )
    media_type = mimetypes.guess_type(asset_path.name)[0]
    if media_type is None:
        raise RenderError(
            f"Template asset has an unsupported media type: {asset_path}"
        )
    encoded = base64.b64encode(asset_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
