# Business Rule Engine

## Architecture

```text
canonical invoice.json
  -> schema validation
  -> BusinessRuleEngine
       -> Statement ViewModel
       -> Quotation ViewModel
       -> Comparison ViewModel
  -> renderer
  -> selected presentation template
```

The canonical invoice remains the single source of truth. The business layer
creates independent, renderer-facing projections without changing the input.
Templates remain presentation-only and the renderer performs no pricing,
taxation, total, or markup calculations.

## Package responsibilities

- `business/view_models.py` validates canonical invoices and exposes
  `BusinessRuleEngine`, `ViewModel`, and `ViewModelType`.
- `business/pricing.py` loads and validates pricing configuration and performs
  decimal-safe markup with explicit rounding.
- `business/comparison.py` constructs the base-versus-marked-up comparison
  structure.
- `business/__init__.py` defines the package's public API.
- `configs/business_rules.json` owns configurable pricing policy. The default
  comparison markup is expressed there as `0.08`, not in Python code.

## View models

All models have:

- `view_model_version` for evolution of the renderer contract.
- `view_model_type` as a renderer/template discriminator.
- `source_document_type` to record the canonical source type.
- `source_invoice_number` for traceability.
- `document` containing presentation-ready structured data.

### Statement

The Statement model carries an independent deep copy of the canonical invoice
document. Amounts and totals are preserved exactly.

### Quotation

The Quotation model is a separate deep copy with a `quotation` discriminator.
It currently preserves canonical prices because no additional quotation pricing
policy has been specified.

### Comparison Quotation

The Comparison model contains each item's shared identity and two price groups:

- `base` preserves `unit_price`, `supply_amount`, `vat`, and `total`.
- `comparison` contains those fields after configured markup and rounding.

Invoice totals are represented with matching `base` and `comparison` groups.
The applied decimal `rate` and display-oriented `percentage` are included in the
view model so the renderer never needs to derive them.

## Configuration

`configs/business_rules.json` contains:

- `comparison_markup_rate`: non-negative decimal rate. It is stored as a string
  to preserve exact decimal meaning.
- `decimal_places`: number of fractional currency places retained after markup.
- `rounding`: explicit Python Decimal rounding mode.

This project currently uses zero decimal places and `ROUND_HALF_UP`, which suit
the sample KRW data. A future currency-aware policy can select a different
configuration before the engine runs; that decision must not move into a
template or renderer.

## Immutability boundary

Every engine method validates and deep-copies its input. The three returned
models have no shared nested document structures. Changing one model cannot
change the canonical invoice or either sibling model.

`ViewModel` is a typed envelope. `HtmlRenderer` rejects raw canonical dictionaries
and rejects a view model whose type does not match the selected template. This
enforces the business-layer boundary at runtime.

