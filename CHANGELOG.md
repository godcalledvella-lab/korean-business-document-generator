# Changelog

## v1.0

### OCR pipeline

- Added persistent PaddleOCR PP-Structure processing with Korean text and table recognition.
- Added provider-neutral OCR results with text, confidence, source text, and bounding-box evidence.
- Preserved Korean, English, numbers, whitespace, and meaningful punctuation during reconstruction and mapping.
- Improved approval-number, organization, address, item-row, quantity, unit-price, supply-amount, and tax extraction.
- Excluded payment-method labels from invoice item descriptions.

### Review UI

- Added the Upload → OCR → Review → Generate workflow.
- Added editable extracted fields, confidence indicators, validation, document settings, and comparison-markup controls.
- Added safe session persistence and generation from approved Review data.
- Kept optional seller phone values blank without blocking approval or generation.

### Seller defaults

- Added stable RMNTC seller defaults for 로맨틱어스, including registration, representative, address, business type, business category, and email.
- Kept seller defaults separate from OCR-extracted buyer data and preserved user edits within each Review session.
- Added fixed quotation information-bar and footer defaults with individual visibility controls.

### RMNTC document generation

- Added generation and packaging of the complete six-page RMNTC PDF set.
- Preserved authoritative workbook templates, formulas, cell geometry, styles, drawings, print settings, and fixed PDF assets.
- Added LibreOffice rendering accommodations for accepted page placement, typography, and quotation fidelity.

### Transaction Statement

- Added the VAT-included transaction statement using the final payable amount.
- Preserved the approved statement layout, item table, page scale, and RMNTC account information.

### Blue Quotation

- Added the original quotation with reviewed item prices, supply amount, VAT, and VAT-included total.
- Preserved CLIENT, PRODUCT, product-details, company-bar, amount wording, accounting formatting, blank item rows, remark, and footer presentation.

### Green Comparison Quotation

- Added the comparison quotation using marked-up Page 3 unit prices.
- Recalculated every displayed unit price and line supply amount so the final comparison total reconciles with its item rows.
- Preserved the approved green template, title placement, table geometry, and company profile.

### Fixed supporting documents

- Included the RMNTC Business Registration PDF as Page 5.
- Included the RMNTC Bank Certificate PDF as Page 6.

### Comparison markup

- Added user-selectable comparison markup percentages with session persistence.
- Applied markup per item using the approved rounding behavior without hardcoding a percentage.
- Kept the web Review calculation, generated workbook, and final PDF totals consistent.

### OCR stability and performance

- Reused one initialized PaddleOCR provider across consecutive uploads.
- Disabled unused chart, formula, seal, orientation, unwarping, and region models while retaining Korean OCR and table recognition.
- Avoided PaddleX's unnecessary chart-model load and reduced persistent-worker memory usage.
- Added a narrowly scoped low-resolution text fallback for uncertain buyer organization and address fields.
- Parallelized independent LibreOffice workbook conversions while preserving generated output and source files.

### Production validation

- Validated representative single-item, multi-item, Korean, mixed-language, long-address, and comparison-quotation invoices.
- Verified Upload → OCR → Review → Generate through the localhost web application with HTTP 200 responses.
- Verified six-page package order, calculations, VAT, seller defaults, comparison markup, fonts, spacing, layout, and worker reuse.
- Passed the complete Python regression suite, TypeScript checks, and Next.js production build for the v1.0 release.
