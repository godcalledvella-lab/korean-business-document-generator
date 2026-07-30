# Phase 2A Korean Tax Invoice Extraction Foundation

## Scope

Phase 2A accepts one Korean electronic tax-invoice page as PDF, PNG, JPG, or
JPEG and produces review artifacts. It does not merge PDFs and does not invoke
the unified document generator.

```text
Page 1 image/PDF
        |
document inspection
        |
provider-neutral raw extraction
        |
explicit normalization
        |
arithmetic + schema validation
        |
reviewable draft JSON and review report
        |
mandatory human approval (future workflow)
```

## Current OCR status

No reliable OCR provider is configured in the current environment.

The inspection found:

- no Tesseract executable;
- no `pytesseract`;
- no OpenCV;
- no Poppler command-line tools;
- no configured OCR/cloud credentials;
- Pillow is available for PNG/JPG/JPEG inspection;
- `pypdf` is available for PDF page inspection but is not OCR.

The current executable prototype uses `MockProvider`. It loads explicitly
supplied raw-field JSON while still inspecting and hashing the actual image/PDF
input. It does not claim to recognize the document.

No invoice data is sent outside the machine.

## Provider boundary

All future providers implement:

```python
class TaxInvoiceExtractor(Protocol):
    name: str

    def extract(
        self,
        input_path: str | Path,
    ) -> RawTaxInvoiceData:
        ...
```

`TaxInvoiceExtractionService` depends only on this interface. OCR-specific
responses, credentials, and SDK types must remain inside provider adapters.

## Raw model

`RawTaxInvoiceData` stores:

- issue date and approval number;
- supplier and buyer registration number, company name, representative,
  address, business type, business category, and optional email;
- item date, Korean item name, specification, optional canonical unit,
  quantity, unit price, supply amount, tax amount, and remark;
- total supply amount, VAT, and grand total;
- receipt/claim classification;
- provider name and source document metadata.

Every raw field uses `ExtractedField`, which retains:

- raw value;
- optional confidence from `0` to `1`;
- optional provider source text.

## Normalization

Normalization is explicit and does not overwrite raw output:

- Korean dates become ISO `YYYY-MM-DD`.
- Ten-digit registration numbers become `NNN-NN-NNNNN`.
- KRW values remove commas, whitespace, `₩`, `￦`, and `원`, then become
  whole-won integers.
- Quantities become numeric values.
- Blank strings become null/missing.
- Korean company and item names are preserved.
- Approval number maps to canonical `document.invoice_number`.
- Currency is explicitly set to `KRW` for this workflow.
- Item total is explicitly derived from extracted supply amount plus item tax
  and is recorded as a normalization rule.
- Specification is never silently reused as canonical unit.

The last rule exposes a real boundary with the existing canonical schema:
canonical items require `unit`, whereas many tax invoices expose only
`specification`. The schema has not been changed. Missing unit remains missing
and blocks approval until a human supplies it.

## Validation

The validator checks:

- required supplier, buyer, issue date, approval number, and totals;
- required canonical item values;
- Korean registration-number length;
- quantity multiplied by unit price equals item supply amount;
- total supply equals the item supply sum;
- total VAT equals the item tax sum when all item taxes exist;
- grand total equals supply plus VAT;
- configured field-confidence threshold (currently 80%);
- conformance with `configs/invoice.schema.json`.

Mismatches are reported and never corrected automatically.

Receipt/claim classification remains in raw output because the canonical schema
has no matching field. It is listed for manual confirmation.

## Development command

Until an OCR adapter is approved and configured, run:

```bash
python3 -m extraction.cli \
  input/tax_invoice.pdf \
  --provider mock \
  --mock-json tests/fixtures/tax_invoice/clean_single_item.json \
  --raw-output output/extraction/raw_tax_invoice.json \
  --draft-output output/extraction/invoice_draft.json \
  --review-output output/extraction/review_report.md
```

Omitting a provider stops cleanly and creates no extraction artifacts.
PaddleOCR can run the provider-neutral OCR stage without generating draft
artifacts:

```bash
python3 -m extraction.cli input/tax_invoice.pdf --provider paddle
```

The PaddleOCR invocation prints OCR text and a result summary. Structured
tax-invoice mapping and human-review artifacts remain a later pipeline stage.
The other real provider names still reach explicit `NotImplementedError`
stubs.

## Outputs

```text
output/extraction/
├── raw_tax_invoice.json
├── invoice_draft.json
└── review_report.md
```

`raw_tax_invoice.json` preserves raw values, confidence, source type, resolved
source path, and source SHA-256.

`invoice_draft.json` uses the existing canonical invoice shape where extracted
data permits. It may intentionally fail schema validation when required fields
are missing.

`review_report.md` lists:

- all extracted fields and confidences;
- missing required fields;
- low-confidence fields;
- arithmetic mismatches;
- fields requiring manual confirmation;
- schema status and whether the draft is safe for human approval.

“Safe to approve” does not mean approved. Phase 2A always requires a person to
compare the draft with Page 1. The CLI always reports that document generation
was not triggered.

## Development fixture

`input/tax_invoice.pdf` is a synthetic one-page fixture whose content matches
`tests/fixtures/tax_invoice/clean_single_item.json`. It is labeled inside the
PDF as a manual-provider fixture and is not an OCR benchmark or a real invoice.

## Candidate recognition providers for the next stage

Provider selection requires a separate accuracy, privacy, retention, Korean
language, table-layout, cost, and deployment review.

Local options:

1. Apple Vision text recognition through a native macOS adapter. Data can
   remain local, but table reconstruction and confidence mapping must be built
   and benchmarked.
2. Tesseract with Korean trained data plus image preprocessing and a
   tax-invoice-specific layout parser. It is local, but installation alone does
   not provide reliable structured invoice extraction.
3. A separately approved local vision model, subject to hardware and model
   licensing review.

Cloud candidates, only after explicit approval to transmit invoice data:

- NAVER Cloud CLOVA OCR;
- Google Cloud Document AI;
- Microsoft Azure AI Document Intelligence;
- another vendor with verified Korean tax-invoice/table support.

No cloud provider is selected, configured, or called in Phase 2A.

## Approval and downstream generation

A future approval command should:

1. require a human-reviewed, schema-conformant draft;
2. record who approved it and when;
3. write the approved canonical invoice JSON;
4. call the existing unified document generator explicitly.

That approval/generation bridge and final PDF merging are outside Phase 2A.
