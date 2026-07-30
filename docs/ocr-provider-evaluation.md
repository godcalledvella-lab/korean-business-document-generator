# OCR Provider Evaluation Framework

## Status

This document defines the Phase 2C benchmark matrix. It does not select a
production provider and does not contain invented accuracy, latency, or cost
figures.

`mock` and the local PaddleOCR PP-StructureV3 adapter are implemented. The
remaining adapters are compiling stubs that raise `NotImplementedError`.
PaddleOCR's real-world quality remains unmeasured pending an approved Korean
tax-invoice benchmark corpus.

## Common output contract

Every provider must return `OCRResult`, containing:

- page count;
- language;
- raw text;
- detected tables and cells;
- text-region bounding boxes;
- provider-neutral confidence;
- generic provider metadata;
- optional structured `RawTaxInvoiceData`.

Provider SDK response objects must not leave the adapter.

## Preliminary comparison

| Provider | Korean accuracy | Table extraction | Tax-invoice suitability | Offline capability | Privacy model | Cost | Speed | API dependency | Ease of deployment | Expected confidence quality |
|---|---|---|---|---|---|---|---|---|---|---|
| Mock | Not applicable; deterministic fixture | Deterministic fixture only | Development/tests only | Yes | Local fixture data | No OCR usage cost | Requires measurement | None | Implemented for tests | Deterministic fixture confidence; not an OCR benchmark |
| Tesseract | Requires measurement | Requires measurement; layout parser needed | Requires measurement | Designed for local execution | Can remain local | Software/runtime cost requires measurement | Requires measurement | No hosted API required | Requires measurement | Requires measurement and calibration |
| PaddleOCR | Requires measurement | Requires measurement | Requires measurement | Designed for local execution | Can remain local | Software/runtime cost requires measurement | Requires measurement | No hosted API required | Requires measurement | Requires measurement and calibration |
| EasyOCR | Requires measurement | Requires measurement; layout parser needed | Requires measurement | Designed for local execution | Can remain local | Software/runtime cost requires measurement | Requires measurement | No hosted API required | Requires measurement | Requires measurement and calibration |
| Google Document AI | Requires measurement | Requires measurement | Requires measurement | No for hosted adapter | Invoice data leaves the local machine; approval required | Requires current pricing measurement | Requires measurement | Google Cloud API and credentials | Requires measurement | Requires measurement and adapter normalization |
| Azure Document Intelligence | Requires measurement | Requires measurement | Requires measurement | No for hosted adapter | Invoice data leaves the local machine; approval required | Requires current pricing measurement | Requires measurement | Azure API and credentials | Requires measurement | Requires measurement and adapter normalization |
| OpenAI vision | Requires measurement | Requires measurement | Requires measurement | No for hosted adapter | Invoice data leaves the local machine; approval required | Requires current pricing measurement | Requires measurement | OpenAI API and credentials | Requires measurement | Requires measurement; field confidence strategy must be designed |
| Claude vision | Requires measurement | Requires measurement | Requires measurement | No for hosted adapter | Invoice data leaves the local machine; approval required | Requires current pricing measurement | Requires measurement | Anthropic API and credentials | Requires measurement | Requires measurement; field confidence strategy must be designed |

The offline descriptions reflect the intended adapter deployment model, not a
measured guarantee. Model downloads, runtime dependencies, hardware, and
licensing must be evaluated before implementation.

## Benchmark corpus

Phase 2C needs an approved, anonymized corpus that covers:

- clean born-digital tax invoices;
- scanned invoices;
- PNG, JPG/JPEG, and one-page PDF inputs;
- low resolution, skew, rotation, shadows, compression, and noisy backgrounds;
- multiple Korean fonts and font sizes;
- single-item and multi-item tables;
- blank optional fields;
- merged cells and irregular row heights;
- receipt and claim classifications;
- intentionally malformed and arithmetically inconsistent documents.

Ground truth must be human-entered and independently reviewed.

## Metrics to measure

No benchmark number should be published until the corpus and scoring rules are
frozen.

Required measurements:

- field exact-match rate;
- Korean character error rate for free text;
- numeric exact-match rate;
- business-number and date exact-match rate;
- item row detection precision/recall;
- table cell assignment accuracy;
- missing-field and hallucinated-field rates;
- confidence calibration by field type;
- arithmetic-validation pass/failure accuracy;
- end-to-end schema-conformant draft rate;
- latency distribution by input type and resolution;
- compute or API cost per page;
- retry and failure rate.

## Privacy gate

Cloud-provider implementation requires explicit approval before any real
invoice is transmitted. The approval must define:

- permitted provider and region;
- credentials and secret storage;
- retention and training/data-use settings;
- logging and redaction rules;
- approved test corpus;
- deletion and incident procedures.

Until that gate is satisfied, cloud adapters remain stubs.

## Selection rule

Production selection must be based on measured Korean tax-invoice performance,
not general OCR marketing claims. A provider advances only if:

1. structured output maps cleanly into `OCRResult`;
2. field confidence can be calibrated or explicitly marked unavailable;
3. privacy and deployment requirements pass review;
4. numeric and table errors are reliably caught by downstream validation;
5. human review remains effective for unresolved fields.
