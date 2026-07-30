# OCR Roadmap

## Phase C - First real provider

The PaddleOCR adapter now runs PP-StructureV3 with Korean recognition and
table extraction for PDF, PNG, JPG, and JPEG input. It maps OCR text, boxes,
table cells, and confidence into `OCRResult`; it does not yet map OCR output
into structured tax-invoice fields. Accuracy and confidence calibration still
require the Phase 2C benchmark.

## Phase 2B - Provider framework

Current phase.

Deliverables:

- abstract `OCRProvider` interface;
- provider-neutral `OCRResult`;
- bounding-box, text-region, table, and table-cell models;
- registry and CLI provider selection;
- deterministic `MockProvider`;
- compiling stubs for Tesseract, EasyOCR, Google Document AI,
  Azure Document Intelligence, OpenAI vision, and Claude vision;
- `OCRTaxInvoiceExtractor` compatibility bridge into the existing
  `RawTaxInvoiceData` pipeline;
- provider registration, lookup, mock-output, stub, and downstream
  compatibility tests.

Exit criteria:

- downstream normalizer and validator do not import provider adapters;
- provider-specific SDK objects cannot cross the `OCRResult` boundary;
- mock and PaddleOCR perform extraction;
- no real invoice data is transmitted externally.

## Phase 2C - Provider benchmark

Build and approve an anonymized real Korean tax-invoice corpus and ground
truth. Implement candidate adapters one at a time behind feature/configuration
gates.

Measure:

- Korean field accuracy;
- numeric accuracy;
- table reconstruction;
- missing and hallucinated fields;
- confidence calibration;
- latency, cost, and operational failure rates;
- schema-conformant draft production;
- human-review workload.

All unknowns in `docs/ocr-provider-evaluation.md` remain “Requires
measurement” until this phase supplies evidence.

Cloud candidates require explicit data-transmission approval before testing
with real invoices.

## Phase 2D - Production provider selection

Select a provider using Phase 2C evidence.

Production readiness includes:

- approved privacy/security posture;
- credential and secret management;
- request timeouts, retries, and rate limits;
- provider version/model pinning;
- monitoring, audit logs, and cost controls;
- confidence thresholds by field;
- fallback and manual-entry behavior;
- regression corpus and release gates;
- documented provider outage behavior.

Selection may choose different providers for local/offline and approved cloud
deployments, provided both emit the same `OCRResult`.

## Phase 2E - Human approval integration

Add an explicit approval boundary after reviewable draft generation.

The approval workflow should:

- display source page and extracted fields side by side;
- highlight missing, low-confidence, and mismatched values;
- allow authorized corrections without losing raw provenance;
- record reviewer, timestamp, changes, and approval decision;
- validate the corrected canonical invoice;
- prevent downstream generation until approval;
- invoke the existing unified document generator only after approval.

Final PDF assembly remains a separate later-stage concern.
