"""Provider-neutral Korean tax-invoice extraction foundation."""

from .models import (
    ExtractedField,
    RawTaxInvoiceData,
    TaxInvoiceExtractor,
)
from .providers import (
    DEFAULT_PROVIDER_REGISTRY,
    OCRProvider,
    OCRResult,
    OCRTaxInvoiceExtractor,
    ProviderRegistry,
)
from .service import (
    ExtractionReport,
    ManualJsonTaxInvoiceExtractor,
    TaxInvoiceExtractionService,
)

__all__ = [
    "ExtractedField",
    "ExtractionReport",
    "ManualJsonTaxInvoiceExtractor",
    "DEFAULT_PROVIDER_REGISTRY",
    "OCRProvider",
    "OCRResult",
    "OCRTaxInvoiceExtractor",
    "ProviderRegistry",
    "RawTaxInvoiceData",
    "TaxInvoiceExtractionService",
    "TaxInvoiceExtractor",
]
