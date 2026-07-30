# Korean Business Document Generator

Generate a reviewed Korean invoice data set, three RMNTC Excel documents, and
an ordered six-page customer PDF package from one Korean electronic tax
invoice. The project keeps OCR, normalization, business rules, workbook
rendering, PDF conversion, and package assembly behind separate interfaces.

The current implementation is a production-development foundation. Human
review and real-invoice OCR benchmarking are still required before unattended
production use.

## Architecture

```text
Tax invoice PDF/image
        |
        v
OCR provider -> OCRResult
        |
        v
RawTaxInvoiceData -> normalized canonical invoice JSON
        |
        v
Validation and review report
        |
        v
Statement + Quotation + Comparison XLSX
        |
        v
LibreOffice or Microsoft Excel PDF backend
        |
        v
Six-page customer PDF package
```

See [Architecture](docs/architecture.md) for component responsibilities,
validation gates, error handling, logging conventions, and extension points.

## Directory structure

```text
business/             Pricing configuration and document ViewModels
configs/              Canonical JSON Schema and business-rule configuration
document_generator/   Atomic three-workbook orchestration
excel_renderer/       Template-preserving XLSX writers and Excel PDF exporter
extraction/           OCR contracts, providers, normalization, and validation
package/              Pluggable PDF backends, validation, merge, and CLI
pipeline/             OCR-to-workbook Phase D orchestration
renderer/             Existing HTML renderer
reference/rmntc/      Authoritative RMNTC PDF and Excel templates
templates/            HTML/template metadata and assets
docs/                 Architecture and workflow documentation
tests/                Unit, preservation, integration, and package tests
web/                  Next.js upload, review, generation, and download UI
input/                 Local sample/runtime inputs
output/                Generated runtime artifacts
```

Generated files under `output/` and local transient files are excluded by
`.gitignore`. Authoritative files under `reference/` must never be edited by a
generation workflow.

## Requirements and installation

- Python 3.9 or newer
- A virtual environment
- LibreOffice for preferred headless Excel-to-PDF conversion, or Microsoft
  Excel for supported macOS local automation
- PaddleOCR plus a compatible inference engine for real OCR

Create an environment and install the core runtime:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

For development and tests:

```bash
python3 -m pip install -r requirements-dev.txt
```

For PaddleOCR, first follow the official
[PaddlePaddle inference-engine installation](https://www.paddleocr.ai/main/en/version3.x/paddlepaddle_installation.html)
for the target CPU/GPU platform, then run:

```bash
python3 -m pip install -r requirements-ocr.txt
```

The optional `doc-parser` dependency group is required for PP-StructureV3;
see the official [PaddleOCR installation guide](https://www.paddleocr.ai/main/en/version3.x/installation.html).
Do not install OCR dependencies automatically in application code.

### LibreOffice

- macOS: install the [official LibreOffice application](https://www.libreoffice.org/download/download-libreoffice/)
  in `/Applications`, or use
  `brew install --cask libreoffice`.
- Debian/Ubuntu: `sudo apt-get install libreoffice`.
- Windows: install LibreOffice from its official installer and ensure
  `soffice.exe` is in the standard Program Files location or on `PATH`.

The package generator also checks common Homebrew, Linux, Windows, and PATH
locations.

### Platform notes

- macOS: the Excel backend requires Microsoft Excel and permission for
  AppleScript automation. It uses save-as PDF, not print-dialog UI automation.
- Linux: use LibreOffice headless mode. Microsoft Excel automation is not
  supported.
- Windows: LibreOffice is the implemented backend. The current Microsoft Excel
  adapter is macOS-only.

## Development

Run the complete suite:

```bash
python3 -m pytest -q
```

Run focused suites while developing:

```bash
python3 -m pytest tests/test_ocr_providers.py -q
python3 -m pytest tests/test_pipeline.py -q
python3 -m pytest tests/test_pdf_package.py -q
```

Library modules return reports or raise typed errors. CLI modules own
user-facing stdout/stderr. The PDF package service emits numbered progress
events through an injectable logger callback.

## CLI usage

### OCR extraction

Run real provider-neutral PaddleOCR:

```bash
python3 -m extraction.cli \
  input/tax_invoice.pdf \
  --provider paddle
```

Run deterministic fixture extraction for development:

```bash
python3 -m extraction.cli \
  input/tax_invoice.pdf \
  --provider mock \
  --mock-json tests/fixtures/tax_invoice/clean_single_item.json \
  --raw-output output/extraction/raw_tax_invoice.json \
  --draft-output output/extraction/invoice_draft.json
```

OCR normalization never silently invents missing invoice values. Validation
reports missing fields, low confidence, malformed identifiers, and arithmetic
mismatches.

### Canonical document generation

Generate all three workbooks from approved canonical JSON:

```bash
python3 -m document_generator.cli \
  input/invoice.json \
  --company rmntc \
  --output-dir output
```

Outputs:

```text
output/statement.xlsx
output/quotation.xlsx
output/comparison.xlsx
```

Generation occurs in staging and publishes only after all three template-
preservation checks succeed.

### Unified OCR-to-workbook pipeline

```bash
python3 -m pipeline.cli \
  input/tax_invoice.pdf \
  --provider paddle \
  --output output
```

Invalid or renderer-incomplete drafts publish a review report but do not start
Excel generation.

### PDF package

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

`auto` prefers LibreOffice, selects Excel only when LibreOffice is unavailable,
and fails clearly when neither backend is usable. The final package is
validated as six A4 portrait pages in the required order before atomic
publication.

## Review web application

The Next.js App Router application under `web/` provides drag-and-drop upload,
OCR progress, editable seller/buyer/item/totals review, confidence badges,
generation, six-page visual approval, and session-scoped downloads. Its Route
Handlers are thin transport adapters over the existing Python APIs and contain
no pricing, normalization, or generation rules.

After generation, each workbook receives a read-only HTML preview that
preserves the worksheet's cells, merges, dimensions, fills, borders,
alignment, number display, and embedded images. When a PDF backend is usable,
the validated final package is also shown inline. Otherwise the UI
automatically presents the original invoice, three workbook previews, Business
Registration, and Bank Account Copy as an ordered six-page HTML proof.

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`. The server uses `python3` by default; set
`PYTHON_BIN` to select another interpreter and `OCR_PROVIDER` to select a
registered provider. Production OCR defaults to `paddle`.

## Configuration

Runtime configuration is centralized under `configs/`:

- `invoice.schema.json`: canonical invoice contract
- `business_rules.json`: comparison pricing configuration

No secrets belong in repository configuration. Backend executable discovery
is platform-specific adapter behavior rather than business configuration.

## Current limitations

- PaddleOCR is optional and is not installed by the application.
- OCR accuracy, table reconstruction, and confidence calibration require a
  representative Korean tax-invoice benchmark.
- Human approval is not yet represented as a durable workflow state.
- The OCR mapper is conservative and may require manual confirmation.
- Existing Excel renderers require a supplier phone and email.
- LibreOffice output may differ visually from Microsoft Excel.
- The Excel PDF backend is macOS-only and requires a licensed local Excel.
- Fixed RMNTC assets currently come from known pages in the authoritative
  reference PDF; adding companies needs a formal asset manifest.
- There is no authentication, durable database, job queue, or deployment
  configuration. Review sessions currently use local filesystem storage.

## Roadmap

1. Benchmark PaddleOCR on approved, anonymized Korean tax invoices.
2. Add durable human review and approval state.
3. Introduce a company/template/fixed-asset manifest without changing current
   document mappings.
4. Perform visual PDF fidelity approval for LibreOffice and Excel.
5. Add authentication, durable review-session persistence, and authorization.
6. Add deployment, secrets, observability, and retention policies.

## Production handoff

This section is the operational runbook for a clean workstation or
self-hosted production machine. Run all Python components from the same virtual
environment: the web process invokes the OCR, workbook, preview, and packaging
modules through `PYTHON_BIN`.

### Prerequisites

- Python 3.9 or newer
- Node.js 20.9 or newer and npm
- LibreOffice in a standard installation location or on `PATH` for the
  preferred PDF backend
- PaddlePaddle and PaddleOCR for real Korean invoice recognition
- Sufficient local storage for PaddleOCR models, uploaded invoices, generated
  workbooks, previews, PDFs, and ZIP packages
- On macOS, AppleScript Automation permission if the optional Microsoft Excel
  backend will be used

LibreOffice is strongly recommended in production. The application continues
to generate XLSX files, HTML previews, and the ZIP bundle when no usable PDF
backend is available, but it cannot publish the six-page final PDF.

### Installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Install the PaddlePaddle inference engine appropriate for the deployment CPU,
GPU, operating system, and Python version by following the official
[PaddlePaddle installation instructions](https://www.paddlepaddle.org.cn/install/quick).
Then install the repository OCR dependencies into the same environment:

```bash
python3 -m pip install -r requirements-ocr.txt
```

Install frontend dependencies using the committed lockfile:

```bash
cd web
npm ci
cd ..
```

For development and test execution:

```bash
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
```

Install LibreOffice separately; the application never installs system
software automatically:

```bash
# macOS with Homebrew
brew install --cask libreoffice

# Debian or Ubuntu
sudo apt-get update
sudo apt-get install libreoffice
```

On Windows, use the official LibreOffice installer. The backend searches
standard Program Files locations and `PATH`.

### Required dependencies

Core Python dependencies are pinned in `requirements.txt`:

- Jinja2
- jsonschema
- openpyxl
- Pillow
- pypdf
- ReportLab

`requirements-ocr.txt` adds PaddleOCR document parsing and includes the core
requirements. PaddlePaddle itself must be installed separately because the
correct wheel depends on the deployment platform. `requirements-dev.txt` adds
pytest.

The web application uses Next.js and React. Exact JavaScript dependencies are
recorded in `web/package-lock.json`.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PYTHON_BIN` | `python3` | Python executable used by Next.js Route Handlers. In production, set this to the absolute `.venv/bin/python` path. |
| `OCR_PROVIDER` | `paddle` | OCR provider selected by the web upload flow. |
| `OCR_MOCK_JSON` | `tests/fixtures/tax_invoice/clean_single_item.json` | Fixture used only when `OCR_PROVIDER=mock`. |
| `PDF_BACKEND` | `auto` | PDF backend: `auto`, `libreoffice`, or `excel`. `auto` prefers LibreOffice. |
| `NODE_ENV` | Set by Next.js | Use `production` through `npm run start`; do not manually override it during builds. |
| `PORT` | `3000` | Port used by `next start`. |
| `HOSTNAME` | `0.0.0.0` in typical deployments | Address used by `next start`; restrict it or place the service behind a reverse proxy as appropriate. |

Example local production environment:

```bash
export PYTHON_BIN="$(pwd)/.venv/bin/python"
export OCR_PROVIDER=paddle
export PDF_BACKEND=auto
```

Do not place invoice data, credentials, or provider secrets in committed
configuration files.

### Running the backend

The Python backend is a set of library and CLI modules; it is not a separate
HTTP daemon. The Next.js Route Handlers invoke these modules using
`PYTHON_BIN`.

Verify OCR independently:

```bash
source .venv/bin/activate
python3 -m extraction.cli input/tax_invoice.pdf --provider paddle
```

Generate approved canonical documents independently:

```bash
python3 -m document_generator.cli \
  input/invoice.json \
  --company rmntc \
  --output-dir output
```

Generate a final PDF package independently:

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

### Running the web application

For local development:

```bash
export PYTHON_BIN="$(pwd)/.venv/bin/python"
export OCR_PROVIDER=paddle
export PDF_BACKEND=auto
cd web
npm run dev
```

Open `http://localhost:3000`. Runtime upload and review data is written beneath
the repository-level `.web-data/` directory.

### Switching OCR providers

For the web application, set `OCR_PROVIDER` before starting Next.js:

```bash
OCR_PROVIDER=paddle npm run dev
```

For deterministic development without real OCR:

```bash
OCR_PROVIDER=mock \
OCR_MOCK_JSON=tests/fixtures/tax_invoice/clean_single_item.json \
npm run dev
```

For the extraction CLI, use `--provider`:

```bash
python3 -m extraction.cli input/tax_invoice.pdf --provider paddle
```

Registered provider names are `mock`, `paddle`, `tesseract`, `easyocr`,
`google`, `azure`, `openai`, and `claude`. Only `paddle` and `mock` are
implemented. Selecting another registered adapter currently raises
`NotImplementedError`; no document is sent to a cloud provider.

### Production build

Run the complete verification gates from the repository root:

```bash
source .venv/bin/activate
python3 -m pytest -q
cd web
npm run typecheck
npm run build
```

Start the optimized application:

```bash
export PYTHON_BIN="$(cd .. && pwd)/.venv/bin/python"
export OCR_PROVIDER=paddle
export PDF_BACKEND=auto
npm run start
```

When running the command from `web/`, the `PYTHON_BIN` expression above
resolves the repository virtual environment.

### Deployment instructions

The supported handoff target is a persistent, self-hosted Node.js process on a
machine capable of running Python, PaddleOCR, and LibreOffice:

1. Provision a non-root service account and clone or copy the repository.
2. Install Python, Node.js, PaddlePaddle/PaddleOCR, and LibreOffice.
3. Create one repository virtual environment and install both
   `requirements.txt` and `requirements-ocr.txt`.
4. Run the Python suite, frontend typecheck, and production build.
5. Set `PYTHON_BIN` to the absolute virtual-environment interpreter and set
   `OCR_PROVIDER` and `PDF_BACKEND`.
6. Ensure the service account can write `.web-data/` and can execute
   LibreOffice headlessly.
7. Run `npm run start` from `web/` under a process supervisor such as systemd,
   launchd, or an equivalent container supervisor.
8. Place the service behind a TLS-terminating reverse proxy and enforce request
   size and timeout policies compatible with the application's 20 MB upload
   limit and long-running OCR requests.
9. Back up or expire `.web-data/` according to the organization's invoice-data
   retention policy.
10. Monitor process failures, disk use, OCR duration, and PDF backend errors.

Do not deploy this application to a stateless or short-duration serverless
runtime without redesigning session storage and background execution.
PaddleOCR model initialization, LibreOffice subprocesses, local filesystem
sessions, and generation requests of several minutes require a persistent
runtime.

### Known limitations

- Human review remains mandatory; OCR output is never the final source of
  truth.
- PaddleOCR model downloads and first startup can be large and slow.
- OCR results vary with scan resolution, rotation, compression, and invoice
  layout.
- The review workflow uses local `.web-data/` files rather than a durable
  database and currently has no authentication or multi-user authorization.
- Uploaded invoices and generated artifacts require an external retention and
  deletion policy.
- LibreOffice has been accepted for the current RMNTC templates, but future
  templates require another visual-fidelity acceptance pass.
- Microsoft Excel 16.111.2 on the tested macOS environment did not produce a
  PDF through its AppleScript save-as API; `auto` therefore uses LibreOffice
  when available.
- The fixed Business Registration and Bank Account PDFs are RMNTC-specific.
- Only RMNTC templates and mappings are implemented.
- OCR provider adapters other than PaddleOCR and Mock are placeholders.
- There is no bundled reverse proxy, container image, database, queue,
  monitoring stack, or automatic dependency installation.
