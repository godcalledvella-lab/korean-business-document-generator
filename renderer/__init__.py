"""Presentation-layer foundations for canonical business documents."""

from .template_manager import (
    TemplateDefinition,
    TemplateError,
    TemplateManager,
    TemplateNotFoundError,
    TemplateValidationError,
)
from .html_renderer import (
    HtmlRenderer,
    InputDataError,
    RenderError,
    RendererError,
)

__all__ = [
    "TemplateDefinition",
    "TemplateError",
    "TemplateManager",
    "TemplateNotFoundError",
    "TemplateValidationError",
    "HtmlRenderer",
    "InputDataError",
    "RenderError",
    "RendererError",
]
