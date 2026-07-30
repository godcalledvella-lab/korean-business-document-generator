# RMNTC Excel Template Analysis

## Scope and inspection method

This report covers the three workbooks under `reference/rmntc/templates/`.
They were inspected read-only as OOXML ZIP packages and rendered to temporary
thumbnails for visual confirmation. No workbook was recalculated, saved, or
modified.

The filenames have duplicated `.xlsx.xlsx` extensions; mappings should use the
actual filenames until a separately approved migration renames them.

None of the workbooks defines an `_xlnm.Print_Area` name. The print areas below
therefore distinguish between the explicit setting (none) and the visually
intended range inferred from populated/formatted cells.

## Workbook inventory

| Document | Workbook filename | Worksheets |
|---|---|---|
| Statement | `TalkFile_거래명세서(로맨틱어스 용) (1).xlsx.xlsx` | `청구서`, `Sheet1` |
| Quotation | `TalkFile_견적서(로맨틱어스 용) (1).xlsx.xlsx` | `견적서` |
| Comparison quotation | `TalkFile_비교견적서.xlsx.xlsx` | `Sheet1` |

## 1. Statement workbook

### Workbook

**Filename:** `TalkFile_거래명세서(로맨틱어스 용) (1).xlsx.xlsx`

The workbook has no VBA project. It contains one embedded PNG and two visible
worksheets. `청구서` is the printable Statement. `Sheet1` is a small internal
purchase/sales/profit calculation sheet and is not part of the customer-facing
statement.

The workbook also contains 25 legacy defined names. Many reference deleted
ranges or sheets through `#REF!`, including `송장합계`, `제목2`, and most
`회사설정_*` names. These names must not be used as integration targets without
a separate cleanup decision. The surviving names that point to cells include
`송장번호표시 -> '청구서'!$C$1`, `행제목영역1..C3 -> '청구서'!$B$3`,
`열제목영역1..B7.1 -> '청구서'!$B$4`, and
`열제목영역2..D6.1 -> '청구서'!$D$4`; their semantics no longer match all of
their names.

### Worksheet `청구서`

**Purpose:** printable RMNTC 거래명세서.

**Print area:** no explicit print area. The intended document body is
approximately `B1:E24`. Cell `J17` contains a stray backtick and expands the
technical used extent; it should not be treated as document data.

**Page setup:**

- Paper size: `9` (A4).
- Orientation: portrait.
- Fit to height: `0` (automatic/unbounded rather than one-page-tall).
- Horizontal centering: enabled.
- Margins in inches: left `0.25`, right `0.25`, top `0.5`, bottom `0.5`.
- Header and footer margins: `0.0`.
- Gridlines are hidden in the worksheet view.

**Merged cells:**

- `D2:E2` — headline total.
- `D3:E3` — VAT note.
- `B18:D18` — “순 합계” label area.
- `B24:E24` — blank remarks/content area below “특이사항:”.

**Formulas:**

| Cell | Formula | Purpose and caution |
|---|---|---|
| `E7` | `=(D7*B7)` | Line amount for the first populated item row. Equivalent formulas are not currently filled through all reserved rows. |
| `E18` | `=SUM(E7:E17)` | Sum of up to 11 line-item amounts. |
| `D2` | `=E17+E18` | Headline total. This double-counts row 17 if `E17` is populated; it is safe only while `E17` is blank. A future implementation must preserve the template until formula correction is explicitly authorized. |

**Images:**

- One embedded `xl/media/image1.png`.
- Drawing name: `image1.png`.
- One-cell anchor starts at zero-based column `3`, row `0` (cell `D1`) with
  offsets of 390,525 and 295,275 EMU.
- Extent: 1,200,150 × 523,875 EMU, approximately 126 × 55 pixels.
- Visually this is the RMNTC logo area. It is static presentation content and
  must not be replaced from JSON.

### Worksheet `Sheet1`

**Purpose:** internal profit calculation, not a printed Statement data sheet.

**Print area:** no explicit print area. Populated range is `A1:D4`.

**Page setup:**

- Orientation: landscape.
- Paper size is not explicitly recorded.
- Margins in inches: left/right `0.7`, top/bottom `0.75`.
- Header and footer margins: `0.0`.
- No print centering option is recorded.

**Merged cells:** none.

**Formulas:**

| Cell | Formula | Meaning |
|---|---|---|
| `D3` | `=C3*D1-B3*D1` | VAT-inclusive unit margin × total quantity. |
| `D4` | `=C4*D1-B4*D1` | VAT-exclusive unit margin × total quantity. |

**Images:** none on this worksheet.

This internal sheet requires purchase price and sales-price assumptions that are
not part of the canonical invoice or Statement ViewModel. It should remain
untouched by the JSON population workflow.

### Recommended Statement cell mapping

The recommended item capacity is 11 rows (`7:17`). Values should come from the
existing Statement ViewModel. Static Korean labels, formatting, logo, and formulas
are template-owned.

| Target | Statement ViewModel field | Notes |
|---|---|---|
| `청구서!B2` | `document.dates.issue_date` | Write as a real Excel date and retain the existing date number format. |
| `청구서!B3` | `document.buyer.name` | Cell currently contains the full display string `수신자: …`; integration should compose that display value outside the workbook without changing its style. |
| `청구서!B4` | `document.seller.name` | Cell currently contains `발신자: …`. |
| `청구서!B7:B17` | `document.items[*].quantity` | One item per row; clear unused values only, preserving styles. |
| `청구서!C7:C17` | `document.items[*].description` | One item per row. |
| `청구서!D7:D17` | `document.items[*].unit_price` | Numeric value; retain the existing currency format. |
| `청구서!E7:E17` | line amount | Prefer template formulas `=B[row]*D[row]` if formula repair/fill is later authorized. Until then, the Statement ViewModel’s explicit line amount is safer than inventing calculations in the workbook writer. |
| `청구서!E18` | `document.totals.total` or formula result | The visible reference calls this “순 합계” while the headline says VAT included. Confirm whether this target should represent `total` or `supply_amount` before implementation. |
| `청구서!D2:E2` | `document.totals.total` | Merged headline amount. Existing formula is structurally unsafe when row 17 is used; do not silently change it. |
| `청구서!C20` | `document.seller.name` | Seller/company display name. |
| `청구서!C21` | not available | Bank name is absent from the current Statement ViewModel. Do not parse it from remarks. |
| `청구서!C22` | not available | Bank account is absent from the current Statement ViewModel. Do not parse it from remarks. |
| `청구서!B24:E24` | `document.remarks` | Merged remarks body below the static `B23` label. |

`invoice_number`, buyer/seller registration numbers, addresses, and contacts have
no visible cells in this Statement template and should not be inserted into
unrelated blank cells.

## 2. Quotation workbook

### Workbook and worksheet

**Filename:** `TalkFile_견적서(로맨틱어스 용) (1).xlsx.xlsx`

**Worksheet:** `견적서`.

The workbook has no VBA project and no defined names.

**Print area:** no explicit print area. The intended formatted document range is
`A1:H36`.

**Page setup:**

- Paper size: `9` (A4).
- Orientation: portrait.
- Scale: `85%`.
- Horizontal and vertical centering: enabled.
- Margins in inches: left/right `0.3543307087` (9 mm),
  top/bottom `0.3937007874` (10 mm).
- Header and footer margins: `0.0`.

**Merged cells:**

`A1:H1`, `C2:E4`, `A6:H6`, `A7:H7`, `A8:A11`, `B8:H11`,
`A12:H12`, `C14:E14`, `F14:H14`, `A15:C15`, `F15:G15`,
`B16:C16`, `F16:G16`, `B17:C17`, `F17:G17`, `B18:C18`,
`F18:G18`, `B19:C19`, `F19:G19`, `B20:C20`, `F20:G20`,
`B21:C21`, `F21:G21`, `B22:C22`, `F22:G22`, `B23:C23`,
`F23:G23`, `B24:C24`, `F24:G24`, `B25:C25`, `F25:G25`,
`B26:C26`, `F26:G26`, `A27:C27`, `F27:G27`, `A28:C28`,
`F28:G28`, `A29:C29`, `F29:G29`, `A30:A34`, `B30:H34`,
`A35:H35`, `A36:H36`.

**Formulas:**

| Cell/range | Formula | Purpose |
|---|---|---|
| `F16:F20` | Shared formula based on `F16 = D16*E16` | Item line amount. Shared descendants translate to their respective rows. |
| `F14` | `=F27` | Headline VAT-exclusive quotation amount. |
| `F27` | `=SUM(F16:G26)` | Subtotal over the 11 reserved item rows. Because each `F:G` row is merged, values reside in column F. |
| `F29` | `=F27+F28` | Grand total, allowing row 28 to hold VAT or another adjustment. |

Rows `21:26` are reserved item rows but do not currently contain shared formulas.

**Images and drawings:**

- One embedded `xl/media/image1.png`, drawing name `image1.png`.
- Anchor begins at zero-based column `0`, row `0` (cell `A1`) with offsets
  57,150 and 152,400 EMU.
- Extent: 1,476,375 × 752,475 EMU, approximately 155 × 79 pixels.
- The drawing XML contains 110 one-cell anchors in total: one actual embedded
  image plus 109 shape anchors. These shapes are part of the existing workbook
  presentation and must not be deleted or rebuilt during value population.

### Recommended Quotation cell mapping

The existing quotation design supports 11 item rows (`16:26`).

| Target | Quotation ViewModel field | Notes |
|---|---|---|
| `H2` | `document.dates.issue_date` | Real Excel date; retain formatting. |
| `H3` | `document.buyer.name` | Existing display includes `귀하`; compose only the display string. |
| `H4` | item/product summary | Intended value cell beside `PRODUCT :`; use a prebuilt view-model summary when one exists, otherwise leave blank. |
| `A6:H6` | seller summary | Existing single-line block combines seller name, registration number, address, and representative. Populate only from structured seller fields. |
| `B8:H11` | item-description summary | Existing large merged “제품상세” body; use a prebuilt summary or leave unchanged. Do not duplicate calculations here. |
| `A16:A26` | sequential display line number | Use `item.line_number` where present. |
| `B16:C26` | `document.items[*].description` | Merged description cells. |
| `D16:D26` | `document.items[*].quantity` | Numeric quantity. |
| `E16:E26` | `document.items[*].unit_price` | Numeric unit price. |
| `F16:G26` | `document.items[*].supply_amount` | Preserve existing formulas where present; do not calculate in the renderer. |
| `H16:H26` | `document.items[*].remarks` | Per-item remarks. |
| `F14:H14` | `document.totals.supply_amount` | Headline marked VAT-exclusive in this design. Existing `F14=F27` may remain if subtotal formulas are complete. |
| `F27:G27` | `document.totals.supply_amount` | Subtotal. |
| `F28:G28` | `document.totals.vat` | Reserved adjustment/VAT row. The neighboring merged label is blank in the source template; adding a label would be a design change and is not recommended during population. |
| `F29:G29` | `document.totals.total` | Grand total. |
| `B30:H34` | `document.remarks` | Large merged remark body. |
| `A35:H35` | seller contact/footer data | Existing text combines phone, email, and bank account. Phone/email are structured; bank data is not currently available and must not be parsed from remarks. |

## 3. Comparison quotation workbook

### Workbook and worksheet

**Filename:** `TalkFile_비교견적서.xlsx.xlsx`

**Worksheet:** `Sheet1`.

The workbook has no VBA project, defined names, images, or drawing layer.

**Print area:** no explicit print area. The visually intended range is `A1:I21`.

**Page setup:**

- Orientation: landscape.
- Paper size and scale are not explicitly recorded.
- Margins in inches: left/right `0.7`, top/bottom `0.75`.
- Header and footer margins: `0.0`.
- No horizontal or vertical centering option is recorded.

**Merged cells:**

`A1:I3`, `F5:I5`, `B6:D6`, `F6:G6`, `B7:D7`, `F7:I7`,
`B8:D8`, `F8:G8`, `F9:G9`, `B11:F11`, `H11:I11`,
`A13:B13`, `E13:F13`, `G13:H13`, `A14:B14`, `E14:F14`,
`G14:H14`, `A15:B15`, `E15:F15`, `G15:H15`, `A16:B16`,
`E16:F16`, `G16:H16`, `A17:B17`, `E17:F17`, `G17:H17`,
`A18:B18`, `E18:F18`, `G18:H18`, `A19:B19`, `E19:F19`,
`G19:H19`, `A20:B20`, `E20:F20`, `G20:H20`, `A21:I21`.

**Formulas:**

| Cell | Formula | Purpose |
|---|---|---|
| `G14` | `=C14*E14` | First item supply amount. Rows 15:19 are reserved but do not contain formulas. |
| `G20` | `=SUM(G14:G19)` | Total supply amount across six reserved rows. |
| `B11` | `=(G20)` | Headline amount. |

**Images:** none.

### Recommended Comparison cell mapping

This workbook is visually a single supplier quotation, not a side-by-side
base-versus-comparison table. It can represent the Comparison ViewModel’s
`comparison` prices, but there is no place for the corresponding `base` prices
without redesigning the template. Since redesign is out of scope, base amounts
should not be inserted.

The existing table supports six item rows (`14:19`).

| Target | Comparison ViewModel field | Notes |
|---|---|---|
| `B6:D6` | `document.dates.issue_date` | Existing example is a formatted text date; a real Excel date is preferable if its number format is preserved. |
| `B7:D7` | `document.buyer.name` | Customer/company receiving the quotation. |
| `F5:I5` | seller business registration number | Available only if the Comparison ViewModel exposes it through its copied seller object. |
| `F6:G6` | `document.seller.name` | Supplier legal/company name. |
| `I6` | `document.seller.representative` | Supplier representative. |
| `F7:I7` | `document.seller.address` | Supplier address. |
| `F8:G8` | `document.seller.business_type` | 업태. |
| `I8` | `document.seller.business_item` | 종목. |
| `F9:G9` | `document.seller.contact.phone` | Main phone. |
| `I9` | `document.seller.contact.phone` | Existing template repeats the same phone as H.P.; use only if that duplication is intentional. |
| `A14:B19` | `document.items[*].description` | Up to six item descriptions. |
| `C14:C19` | `document.items[*].quantity` | Quantity. |
| `D14:D19` | `document.items[*].unit` | 규격/unit. |
| `E14:F19` | `document.items[*].comparison.unit_price` | Marked-up unit price from the Business Rule Engine. |
| `G14:H19` | `document.items[*].comparison.supply_amount` | Marked-up supply amount; preserve formulas only if all rows are intentionally filled with formulas. |
| `I14:I19` | `document.items[*].remarks` | Item content/remarks. |
| `G20:H20` | `document.totals.comparison.supply_amount` | Marked-up supply total. |
| `B11:F11` | `document.totals.comparison.supply_amount` | Headline amount; existing formula points to `G20`. |
| `A21:I21` | `document.remarks` | Full-width footer/notes row. |

The current Comparison ViewModel copies the canonical seller. If this workbook
is meant to portray an independent comparison vendor, that vendor identity is
not represented in the current data model. It must not be fabricated or
hardcoded during Excel population.

## Cross-template recommendations

1. **Treat cells, not legacy defined names, as the integration contract.** The
   Statement workbook’s broken names make named-range population unsafe.
2. **Populate values without changing styles, merges, row heights, column
   widths, drawings, print settings, or workbook names.**
3. **Use typed Excel dates and numbers.** Keep identifiers such as registration
   numbers and bank accounts as strings.
4. **Enforce template capacities before writing:** 11 Statement rows,
   11 Quotation rows, and 6 Comparison rows. Overflow policy requires a later
   architecture decision; silently adding rows would redesign the templates.
5. **Do not calculate in the renderer.** Use explicit values already present in
   the relevant ViewModel, or preserve audited workbook formulas after a
   separately approved formula-repair step.
6. **Do not infer missing bank or alternate-vendor fields from remarks.**
7. **Open copies for future population.** The three files under
   `reference/rmntc/templates/` should remain immutable reference masters.

