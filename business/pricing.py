"""Configuration and decimal-safe pricing transformations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    InvalidOperation,
)
from pathlib import Path
from typing import Any


class PricingConfigurationError(ValueError):
    """Raised when pricing configuration is missing or invalid."""


_ROUNDING_MODES = {
    "ROUND_CEILING": ROUND_CEILING,
    "ROUND_DOWN": ROUND_DOWN,
    "ROUND_FLOOR": ROUND_FLOOR,
    "ROUND_HALF_DOWN": ROUND_HALF_DOWN,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_UP": ROUND_UP,
}


@dataclass(frozen=True)
class PricingConfig:
    """Validated pricing rules used by comparison view models."""

    comparison_markup_rate: Decimal
    decimal_places: int
    rounding: str

    @classmethod
    def from_file(cls, config_path: str | Path) -> "PricingConfig":
        path = Path(config_path)
        try:
            configuration = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise PricingConfigurationError(
                f"Could not read business-rule configuration {path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise PricingConfigurationError(
                f"Business-rule configuration is not valid JSON: {path} "
                f"(line {error.lineno}, column {error.colno})"
            ) from error

        if not isinstance(configuration, dict):
            raise PricingConfigurationError(
                f"Business-rule configuration must be a JSON object: {path}"
            )
        pricing = configuration.get("pricing")
        if not isinstance(pricing, dict):
            raise PricingConfigurationError(
                f"Missing object 'pricing' in business-rule configuration: {path}"
            )
        return cls.from_mapping(pricing)

    @classmethod
    def from_mapping(cls, pricing: dict[str, Any]) -> "PricingConfig":
        required = ("comparison_markup_rate", "decimal_places", "rounding")
        missing = [field for field in required if field not in pricing]
        if missing:
            raise PricingConfigurationError(
                "Pricing configuration is missing required field(s): "
                f"{', '.join(missing)}"
            )

        raw_rate = pricing["comparison_markup_rate"]
        if not isinstance(raw_rate, (str, int, float)) or isinstance(raw_rate, bool):
            raise PricingConfigurationError(
                "'comparison_markup_rate' must be a decimal string or number."
            )
        try:
            rate = Decimal(str(raw_rate))
        except InvalidOperation as error:
            raise PricingConfigurationError(
                "'comparison_markup_rate' is not a valid decimal."
            ) from error
        if not rate.is_finite() or rate < 0:
            raise PricingConfigurationError(
                "'comparison_markup_rate' must be a finite, non-negative decimal."
            )

        decimal_places = pricing["decimal_places"]
        if (
            not isinstance(decimal_places, int)
            or isinstance(decimal_places, bool)
            or decimal_places < 0
        ):
            raise PricingConfigurationError(
                "'decimal_places' must be a non-negative integer."
            )

        rounding = pricing["rounding"]
        if rounding not in _ROUNDING_MODES:
            supported = ", ".join(sorted(_ROUNDING_MODES))
            raise PricingConfigurationError(
                f"Unsupported rounding mode {rounding!r}; choose one of: {supported}."
            )

        return cls(
            comparison_markup_rate=rate,
            decimal_places=decimal_places,
            rounding=rounding,
        )

    @property
    def rounding_mode(self) -> str:
        return _ROUNDING_MODES[self.rounding]

    def with_markup_percentage(
        self,
        percentage: int | float | Decimal | str,
    ) -> "PricingConfig":
        """Return an equivalent configuration with a reviewed percentage."""

        if isinstance(percentage, bool) or not isinstance(
            percentage, (str, int, float, Decimal)
        ):
            raise PricingConfigurationError(
                "Comparison markup percentage must be numeric."
            )
        try:
            reviewed = Decimal(str(percentage))
        except InvalidOperation as error:
            raise PricingConfigurationError(
                "Comparison markup percentage is not a valid number."
            ) from error
        if not reviewed.is_finite() or reviewed < 0 or reviewed > 100:
            raise PricingConfigurationError(
                "Comparison markup percentage must be between 0 and 100."
            )
        return PricingConfig(
            comparison_markup_rate=reviewed / Decimal(100),
            decimal_places=self.decimal_places,
            rounding=self.rounding,
        )


def apply_markup(
    amount: int | float | Decimal,
    config: PricingConfig,
) -> int | Decimal:
    """Return a marked-up, configured-rounded amount without mutating input."""

    if isinstance(amount, bool) or not isinstance(amount, (int, float, Decimal)):
        raise TypeError("Markup can only be applied to a numeric amount.")
    decimal_amount = Decimal(str(amount))
    quantum = Decimal(1).scaleb(-config.decimal_places)
    result = (decimal_amount * (Decimal(1) + config.comparison_markup_rate)).quantize(
        quantum,
        rounding=config.rounding_mode,
    )
    if config.decimal_places == 0:
        return int(result)
    return result
