# Excel Renderer Byte-Level Verification Report

## Scope

This report compares the original RMNTC Statement workbook with the generated
workbook at the level of uncompressed OOXML package parts.

- Original:
  `reference/rmntc/templates/TalkFile_거래명세서(로맨틱어스 용) (1).xlsx.xlsx`
- Generated: `output/statement_test.xlsx`
- Comparison date: 2026-07-29
- Digest algorithm: SHA-256

| Package | Size | SHA-256 |
|---|---:|---|
| Original workbook | 44,824 bytes | `ed2ba9cbbdc147cb3aa08a4aff8f7ee38af6fa28a90bc2fddc2873b42230b0b8` |
| Generated workbook | 44,900 bytes | `4938fe96d35dfe807c12cc716bdb28c6da4fadd91b40fdcee7e94b8aa2477ec1` |

Both packages contain 19 members, with identical member names and ordering.
The generated package passes a complete ZIP CRC/integrity check.

The complete `.xlsx` files are not byte-identical because one worksheet part
contains the intended dynamic values. A different whole-package checksum is
therefore expected.

## OOXML parts that differ

Exactly one OOXML part differs:

| Part | Original size | Generated size | Original SHA-256 | Generated SHA-256 |
|---|---:|---:|---|---|
| `xl/worksheets/sheet1.xml` | 108,905 bytes | 109,403 bytes | `9fe5404afcd38dd8be09825bf0cf1c03a1898aafe6960c2af3a57848b85fe16d` | `a1cd4fcd338a72ad708bccbc06725eec2b0a60931ac396b8874afd44a4fc3f9f` |

`sheet1.xml` is the `청구서` worksheet. It changed because it is the only
worksheet into which Statement ViewModel values are written.

The differences are expected. They affect displayed document content—date,
party names, line items, seller name, remarks, and calculated line amounts—but
do not change the worksheet's visual design. Cell style identifiers remain on
the edited cells, and no row, column, merge, drawing, page setup, print option,
or other presentation record changed.

### Changed cell records

| Cell | Change | Expected | Visual effect |
|---|---|---|---|
| `B2` | Replaced template date with Excel serial `46232` (`2026-07-29`) | Yes | Displayed date changes; existing date style/format remains |
| `B3` | Replaced shared-string reference with inline buyer display text | Yes | Buyer text changes; layout/style remains |
| `B4` | Replaced shared-string reference with inline seller display text | Yes | Seller text changes; layout/style remains |
| `B7` | Quantity changed from `50` to `1` | Yes | First quantity changes |
| `C7` | Description changed to `업무 프로세스 분석` | Yes | First description changes |
| `D7` | Unit price changed from `8,800` to `1,500,000` | Yes | First unit price changes |
| `B8` | Blank cell populated with quantity `2` | Yes | Second quantity appears |
| `C8` | Blank cell populated with `문서 자동화 시스템 설계` | Yes | Second description appears |
| `D8` | Blank cell populated with unit price `750,000` | Yes | Second unit price appears |
| `E8` | Blank cell populated with formula `=(D8*B8)` | Yes | Second line amount appears after spreadsheet calculation |
| `B10` | Blank cell populated with quantity `4` | Yes | Third quantity appears |
| `C10` | Blank cell populated with `운영 교육` | Yes | Third description appears |
| `D10` | Blank cell populated with unit price `125,000` | Yes | Third unit price appears |
| `E10` | Blank cell populated with formula `=(D10*B10)` | Yes | Third line amount appears after spreadsheet calculation |
| `C20` | Replaced shared-string reference with seller name | Yes | Seller name changes |
| `B24` | Blank cell populated with Statement remarks | Yes | Remarks appear in the existing merged remarks area |

The string cells use OOXML inline strings. This avoids modifying
`xl/sharedStrings.xml`, so the change is confined to each intended cell record.

## Required byte-identity verification

All existing parts in the requested categories are byte-identical after
decompression from the two `.xlsx` packages.

### Styles

| Part | Result | SHA-256 in both workbooks |
|---|---|---|
| `xl/styles.xml` | Byte-identical | `d7e7b4e3709064dde0be3dc4dfd5f0a945eba584959af22b4b154c963b36ae8e` |

This confirms that fonts, fills, borders, alignments, protection settings, and
number-format definitions were not changed.

### Themes

| Part | Result | SHA-256 in both workbooks |
|---|---|---|
| `xl/theme/theme1.xml` | Byte-identical | `583f091f83dabccf51906942710cb2b84f3215f288327cc9a7b9502e3d25be75` |

### Drawings

| Part | Result | SHA-256 in both workbooks |
|---|---|---|
| `xl/drawings/drawing1.xml` | Byte-identical | `d90be1b42c961ebbf8a6f0183c7c495c6605ba60a68c3c24db7058e814794e5b` |
| `xl/drawings/drawing2.xml` | Byte-identical | `394373ea7e1b1dfd8633980cf12b48a29def82f40be77ecb084131e50739dc4b` |
| `xl/drawings/_rels/drawing1.xml.rels` | Byte-identical | `cd31aba7c923e69aa0742c49b9c0f6300a45a049873c409773576170d7ce08c1` |

Drawing anchors, dimensions, references, and relationships were not changed.

### Media and image checksums

The workbook contains one image. Its payload and checksum are identical.

| Image | Original SHA-256 | Generated SHA-256 | Result |
|---|---|---|---|
| `xl/media/image1.png` | `fba7407e237ca72be6da101166d638c7783f0a43d1270e4f7da0bfc110c02aaf` | `fba7407e237ca72be6da101166d638c7783f0a43d1270e4f7da0bfc110c02aaf` | Byte-identical |

No images were added, removed, replaced, recompressed, or altered.

### Printer settings

Neither workbook contains an `xl/printerSettings/` part. The part sets are
identical and empty. Page setup and print options are stored in
`xl/worksheets/sheet1.xml`; comparison after excluding only the 16 changed cell
records confirms those records are unchanged.

### Worksheet relationships

| Part | Result | SHA-256 in both workbooks |
|---|---|---|
| `xl/worksheets/_rels/sheet1.xml.rels` | Byte-identical | `4211b0867e1f9f8ab69aa64d9c23d96187fa3213862175352d5699bf0203dad0` |
| `xl/worksheets/_rels/sheet2.xml.rels` | Byte-identical | `eace0cae9b4278f2954e555cfc3944b18802739a2d6d5930bb473590e18ed4fd` |

Image, drawing, table, and worksheet relationship targets are unchanged.

### Document properties

| Part | Result | SHA-256 in both workbooks |
|---|---|---|
| `docProps/core.xml` | Byte-identical | `1acca57b8744bd914adce196b69fc41adc85d682312497835b23d13358f74dc3` |
| `docProps/custom.xml` | Byte-identical | `07967530fc7e65347722e626baea3b4294152ae6a80305b24576f1e8bf9bc1a5` |

No creator, timestamp, application, or custom-property metadata was changed.

## Other unchanged OOXML parts

Every other package member is also byte-identical:

| Part | SHA-256 in both workbooks |
|---|---|
| `[Content_Types].xml` | `a5dd50976230c3fe5f9fdc7006ab81e5e3e9ff4581e2a4af0c49126a1d3b8d98` |
| `_rels/.rels` | `f86dbde45232cef623df9a71066a83862cdeb9a8f538a46843d32599d03ef9dc` |
| `xl/_rels/workbook.xml.rels` | `62c5d3908b64c4280e307eb7b4d87b2fbef17ddb1fc1b590e62398d7e3e83a01` |
| `xl/metadata` | `a275a49d4488910e272f37f732e65c96c88c9cc7ab64bacb752df1014d715b02` |
| `xl/sharedStrings.xml` | `3e18f97e04bd6c4eed64baa47ef502c90289d9bc191e3f0706a8a307c8ec50e0` |
| `xl/tables/table1.xml` | `157aeeffafa1139790861ae43ebffde45c28501327d98e8abc70c9575283b5c4` |
| `xl/workbook.xml` | `3a0e5dd7b4d22be298aea995b1558aa1dc466d20532824f6e035f41ac8927cf0` |
| `xl/worksheets/sheet2.xml` | `9c5bfec4ee74184d8d5147e338b0cbdc428b0c73a2ebb53ecb0f264ec8201887` |

`sheet2.xml` contains the internal calculation sheet, including its existing
formulas. Its byte identity confirms that the renderer did not touch that sheet.

## ZIP container metadata note

OOXML part payloads and ZIP container metadata are separate layers. Rebuilding
the package normalized two non-content ZIP directory fields on all 19 members:

- General-purpose flag bits changed from `2056` to `0`.
- External file attributes changed from `0` to `25165824`.

These fields describe ZIP transport/host metadata; they are not OOXML workbook
content and do not affect Excel rendering. Member names, ordering, compression
method, timestamps, comments, extra fields, platform/version fields, and
uncompressed bytes were otherwise preserved. The only OOXML payload difference
is the expected `xl/worksheets/sheet1.xml` change documented above.

## Conclusion

The verification passed:

- 18 of 19 OOXML parts are byte-identical.
- The sole changed part is the intended Statement worksheet.
- Its differences are limited to 16 mapped dynamic cell records.
- All existing formulas remain unchanged; formulas were added only to blank
  amount cells `E8` and `E10`.
- Styles, themes, drawings, media, worksheet relationships, document
  properties, page setup, print settings, merges, row heights, and column widths
  are unchanged.
- Every embedded image checksum is identical.

