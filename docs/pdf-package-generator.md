# PDF Package Generator

## Architecture

The `package` module turns three generated workbooks and three supplied PDFs
into one validated six-page customer package:

```text
PackageInputs
  -> BackendRegistry
  -> PDFBackend
  -> three temporary workbook PDFs
  -> PDF validation
  -> exact-order merger
  -> six-page validation
  -> atomic publication
```

Backend-specific commands live under `package/backends/`. The package service
depends only on the `PDFBackend` interface and provider-neutral result models.

## Backend selection

`--backend auto` detects both supported local backends and chooses:

1. LibreOffice when its executable and version check are available.
2. Microsoft Excel only when LibreOffice is unavailable and supported macOS
   AppleScript automation is present.
3. A clear failure when neither is available.

An explicitly requested unavailable backend fails; it never silently switches
to another implementation. A selected backend that fails during rendering
also does not trigger automatic fallback.

LibreOffice detection covers PATH plus common macOS, Homebrew, Linux, and
Windows installation paths. Each conversion uses a copied workbook and an
isolated temporary user profile.

The Excel backend uses native macOS Excel AppleScript export, compiles the
script before execution, and closes the copied workbook without saving. It
does not use print-dialog UI automation.

## CLI

```bash
python3 -m package.cli \
  --tax-invoice input/tax_invoice.pdf \
  --statement output/statement.xlsx \
  --quotation output/quotation.xlsx \
  --comparison output/comparison.xlsx \
  --business-registration output/business_registration.pdf \
  --bank-account output/bank_account.pdf \
  --output output/final_package.pdf \
  --backend auto
```

Use `--backend libreoffice` or `--backend excel` for an explicit selection.

## Required inputs and output

The tax invoice, Business Registration, and Bank Account Copy must each be a
valid, nonblank, one-page A4 portrait PDF. Each workbook must exist and remain
byte-identical throughout conversion.

The published output is:

```text
output/final_package.pdf
```

Its exact order is tax invoice, Statement, Quotation, Comparison Quotation,
Business Registration, then Bank Account Copy.

## Validation and logging

The command prints eight numbered stages covering backend detection, Page 1,
each workbook render, fixed assets, merge, and final validation. Validation
rejects missing, corrupt, blank, non-A4, landscape, or incorrectly paginated
PDFs. The merged page fingerprints are compared with the six ordered inputs.

On failure, diagnostics include the failed step, backend, exact command, exit
code, stdout, stderr, temporary working path, and source-hash status.

All intermediate files live in a temporary directory beside the destination.
The final file is moved into place only after every check succeeds. Temporary
files are cleaned on success and failure, and an existing final package is
preserved when generation fails.

## Fidelity and backend limitations

LibreOffice may differ from Microsoft Excel in font substitution, print-area
interpretation, formula recalculation, image placement, and pagination. It
must remain visually benchmarked against authoritative RMNTC examples before
production approval.

The Microsoft Excel backend is macOS-only. Application presence cannot prove
that Office is licensed or that PDF export works; those conditions are tested
during the selected export and reported as failures. It uses save-as PDF
automation only, never silent UI automation.

## Adding another backend

Implement `PDFBackend.availability()` and `PDFBackend.render_xlsx()`, returning
`BackendAvailability` and `RenderResult`. Register the adapter in
`BackendRegistry`, define its selection priority explicitly, and add detection,
command, source-hash, failure-diagnostic, and integration tests. No package
service changes should be necessary.
