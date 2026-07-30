# RMNTC Quotation OOXML Verification

Compared `reference/rmntc/templates/quotation.xlsx` with
`output/quotation.xlsx` after rendering `input/invoice.json`.

| Package | Bytes | SHA-256 |
|---|---:|---|
| Source | 80,637 | `dc2de5b339192a4ea24c1e650c61023f26fd74deb0d754ad14c6dcfffd1c5297` |
| Output | 81,051 | `829903fd265ea410edeeef0b45030a5dee90ddb1df3ace1b579b1f181c0df7fb` |

The ZIP integrity check passed. Both packages contain the same 14 OOXML
members. Exactly one member differs: `xl/worksheets/sheet1.xml`.

| Worksheet part | Bytes | SHA-256 |
|---|---:|---|
| Source | 540,626 | `07e729e7416dff1b5a887a07c3a7ba6d550913c627ca95aee1590d1c6f1fa6be` |
| Output | 541,181 | `0146c3e20f1cc290a870e2b8b7bb01d7e001ba60f835823face3e8b4ca14ddfd` |

The changed worksheet records are limited to these mapped dynamic cells:

`H2`, `H3`, `A6`, `B8`, `C14`, `F28`, `B30`, `A35`,
`A16`, `B16`, `D16`, `E16`, `H16`,
`A17`, `B17`, `D17`, `E17`, `H17`,
`A18`, `B18`, `D18`, `E18`, `H18`,
`A19`, `B19`, `D19`, `E19`,
`A20`, `B20`, `D20`, `E20`, `F25`,
`F16`, `F17`, `F18`, `F19`, `F20`, `F14`, `F27`, `F29`.

The unused item cells clear template examples while retaining their existing
cell records and style identifiers. The listed formula cells retain byte-for-
byte identical formula elements; only their cached results were updated or
cleared so previews display the generated values before recalculation.

All 13 other OOXML members are byte-identical. In particular:

- `xl/styles.xml` is byte-identical, SHA-256
  `771ee20abd6812691ec556b01a3dd56aaea551a196a2e74a8f151f06631e0de3`.
- `xl/media/image1.png` is byte-identical, SHA-256
  `33731fa57d896afe6c7f40f766a1534c092a4d72453d242e13d9e425d3e108c1`.
- Drawing XML, drawing relationships, worksheet relationships, theme,
  workbook, workbook relationships, shared strings, metadata, properties, and
  content types are byte-identical.
- Formula text and shared-formula attributes are unchanged.
- Merge ranges, cell style identifiers, row attributes/heights, column
  definitions/widths, sheet views, print options, margins, and page setup are
  unchanged.

The generated workbook was loaded successfully by openpyxl and opened and
closed successfully by Microsoft Excel without saving.
