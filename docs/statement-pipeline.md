# RMNTC Statement HTML Pipeline

## Scope

The first end-to-end pipeline converts canonical invoice JSON into the RMNTC
Page 2 거래명세서 HTML presentation:

```text
input/invoice.json
  -> configs/invoice.schema.json validation
  -> templates/rmntc/statement/template.json selection
  -> templates/rmntc/statement/statement.html.j2 rendering
  -> output/statement.html
```

It does not perform OCR, source-data interpretation, business calculations, or
PDF generation.

## Run

From the project root:

```bash
python3 -m renderer.cli \
  input/invoice.json \
  rmntc \
  statement \
  output/statement.html
```

The command validates the JSON against its canonical schema before loading the
selected template. It fails without writing a successful document when the JSON,
schema, manifest, entrypoint, or required template asset is invalid.

## Responsibility boundaries

- `input/invoice.json` owns the structured document facts and is the single
  source of truth.
- `configs/invoice.schema.json` owns the canonical input contract.
- `TemplateManager` owns template discovery and asset validation.
- `HtmlRenderer` owns input loading, schema validation, safe template execution,
  display-only filters, and output writing.
- `statement.html.j2` owns RMNTC Statement presentation: Korean labels, layout,
  typography, colors, direct canonical field placement, and line-item iteration.

The renderer does not calculate supply amount, VAT, or totals. It displays the
reviewed values supplied by canonical JSON. Jinja autoescaping protects
user-controlled text. The only custom filters group numeric values, display ISO
dates in Korean form, and preserve line breaks; none changes business meaning.

The template contains no tax, pricing, workflow, or data-repair decisions.

