"""Reusable business rules that produce renderer-ready view models."""

from .comparison import build_comparison_view_model
from .pricing import PricingConfig, PricingConfigurationError, apply_markup
from .view_models import (
    BusinessRuleEngine,
    BusinessRuleError,
    CanonicalInvoiceError,
    ViewModel,
    ViewModelType,
)

__all__ = [
    "BusinessRuleEngine",
    "BusinessRuleError",
    "CanonicalInvoiceError",
    "PricingConfig",
    "PricingConfigurationError",
    "ViewModel",
    "ViewModelType",
    "apply_markup",
    "build_comparison_view_model",
]

