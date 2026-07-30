# RMNTC Comparison Quotation OOXML Verification

Compared `reference/rmntc/templates/comparison.xlsx` with
`output/comparison.xlsx` after rendering `input/invoice.json`.

| Package | Bytes | SHA-256 |
|---|---:|---|
| Source | 54,078 | `aaf8a7c837aab6c769b923d3258ad8f1f70e880e3c3c7816721a41cb0a0f5848` |
| Output | 54,543 | `397ab30e8be146c6e1c82ba2077bda71ae6f3d075e8d423d0c6e69d79a14c482` |

The ZIP integrity check passed. Both packages contain the same 12 OOXML
members. Exactly one member differs: `xl/worksheets/sheet1.xml`.

| Worksheet part | Bytes | SHA-256 |
|---|---:|---|
| Source | 541,543 | `6fabbbd6c48549e8fd4c617a81bac9eb11c154b88b9ae33c6428b64cdbf7d3be` |
| Output | 542,492 | `5458caa90ff8580f3b56048b52724c71a12435d1564e3d1d5d15d2a4474e007b` |

The changed worksheet records are limited to these mapped dynamic cells:

`B6`, `B7`, `F5`, `F6`, `I6`, `F7`, `F8`, `I8`, `F9`, `I9`, `A21`,
`A14`, `C14`, `D14`, `E14`, `I14`,
`A15`, `C15`, `D15`, `E15`, `I15`, `G15`,
`A16`, `C16`, `D16`, `E16`, `I16`, `G16`,
`G14`, `G20`, `B11`.

The formula cells retain identical formula elements; only their cached results
were updated so previews display the recalculated comparison amounts before
Excel recalculates the workbook.

All 11 other OOXML members are byte-identical. In particular:

- `xl/styles.xml` is byte-identical, SHA-256
  `f144d951230877a7727a0ca2ab8fdb44b84f8124591d49e40f7cbcf21a974bcb`.
- The source and output both contain no embedded media or drawing layer.
- Worksheet relationships, theme, workbook, workbook relationships, shared
  strings, metadata, properties, and content types are byte-identical.
- Formula text and attributes in `B11`, `G14`, and `G20` are unchanged.
- Merge ranges, cell style identifiers, row attributes/heights, column
  definitions/widths, sheet views, print options, margins, and page setup are
  unchanged.

The generated workbook was loaded successfully by openpyxl and opened and
closed successfully by Microsoft Excel without saving.
