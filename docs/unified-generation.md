# Unified RMNTC Excel Generation

## Purpose

The unified generator reads one canonical invoice JSON document and produces
the complete RMNTC Excel document set:

- `statement.xlsx`
- `quotation.xlsx`
- `comparison.xlsx`

PDF generation is a separate workflow and is not invoked.

## Command

Run from the repository root:

```bash
python3 -m document_generator.cli \
  input/invoice.json \
  --company rmntc \
  --output-dir output
```

The command reports the resolved input path, selected company, all selected
template paths, configured comparison markup, per-document status, output
paths, and totals.

Example totals for the repository fixture:

```text
Statement: 3850000
Quotation: 3850000
Comparison: 3780000
```

The Comparison total is the VAT-exclusive amount displayed by the current
Comparison template. Its markup comes from `configs/business_rules.json`.

## Architecture

`document_generator.cli` handles argument parsing and user-facing reporting.

`document_generator.service.RmntcDocumentGenerator` owns orchestration:

1. Resolve and validate the three authoritative templates.
2. Load and JSON-Schema-validate the canonical invoice.
3. Verify declared invoice totals equal the line-item sums.
4. Build the existing Statement, Quotation, and Comparison ViewModels through
   `BusinessRuleEngine`.
5. Enforce each existing template's item capacity.
6. Generate all workbooks into a temporary staging directory through the
   existing Excel renderers.
7. Validate every staged workbook and source-template checksum.
8. Move all three staged files into the output directory only after the full
   set passes.

The service does not recreate or save the source workbooks. Each renderer
continues to copy its authoritative template and edit only mapped worksheet
cell records.

## Templates

The RMNTC template set is:

```text
reference/rmntc/templates/statement.xlsx
reference/rmntc/templates/quotation.xlsx
reference/rmntc/templates/comparison.xlsx
```

These files are immutable source masters for generation. The unified service
captures their SHA-256 digests before rendering and verifies the digests again
before publication.

## Validation

Before publication, every staged workbook must:

- exist and pass ZIP/OOXML integrity checks;
- contain the same OOXML member set as its template;
- open successfully through an independent Excel-compatible workbook parser;
- contain its required worksheet (`청구서`, `견적서`, or `Sheet1`);
- retain every original template formula;
- retain merged ranges and cell style identifiers;
- retain row heights, column widths, worksheet dimensions, sheet views,
  page setup, margins, and print settings;
- retain styles, fonts, fills, borders, themes, images, drawings, media,
  relationships, metadata, and all other non-target worksheet parts
  byte-for-byte;
- contain the expected rendered item values and total formulas;
- use the Business Rule Engine's configured Comparison prices and total.

## Atomic failure behavior

Generation takes place under a temporary directory beside the final output
directory. A renderer or validation failure removes that temporary directory
and does not publish any staged workbook.

If final files already exist, they remain untouched during generation and
validation. During publication they are moved to temporary backups first. If
any final move fails, newly promoted files are removed and all backups are
restored.

The CLI exits with status `1`, identifies the failure, and reports each
document as `failed`, `validated` but unpublished, or `not run`.

## Input example

```json
{
  "schema_version": "1.0",
  "document_type": "invoice",
  "document": {
    "invoice_number": "RMNTC-2026-0729-001",
    "dates": {"issue_date": "2026-07-29"},
    "seller": {"name": "알엠엔티씨 주식회사"},
    "buyer": {"name": "주식회사 한빛상사"},
    "currency": "KRW",
    "items": [],
    "totals": {
      "supply_amount": 0,
      "vat": 0,
      "total": 0
    }
  }
}
```

The abbreviated example illustrates the envelope only. Actual input must
satisfy all required party and line-item fields in
`configs/invoice.schema.json`, and at least one item is required.

## Output example

```text
output/
├── statement.xlsx
├── quotation.xlsx
└── comparison.xlsx
```

## Current capacities

The source templates define fixed styled item areas:

| Document | Maximum items |
|---|---:|
| Statement | 10 |
| Quotation | 11 |
| Comparison | 6 |

The generator stops before rendering if the invoice exceeds any relevant
capacity. It does not insert rows or redesign a template.

## Adding another company

Add another company as a separate configuration rather than branching inside
the RMNTC renderers:

1. Add immutable company templates under
   `reference/<company>/templates/`.
2. Add or reuse renderer adapters that accept the existing ViewModels.
3. Define a company template specification containing document names,
   template paths, output filenames, worksheet names, and worksheet OOXML
   parts.
4. Register the company in the CLI's allowed company choices and select the
   corresponding generator/service implementation.
5. Define template capacities explicitly.
6. Add company-specific mapping, preservation, atomic-failure, and workbook
   integration tests.

Business pricing remains in the Business Rule Engine configuration. Company
services must consume its ViewModels and must not duplicate or hardcode markup
logic.
