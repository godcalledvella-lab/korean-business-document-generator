# Canonical JSON Data Model

## Purpose

The canonical JSON document is the single source of truth for document data.
Inputs may eventually be entered manually, imported, or extracted, but downstream
templates and renderers must read this model rather than their own copies of the
data. A rendered document must never become the authoritative data source.

The invoice contract is defined by
[`configs/invoice.schema.json`](../configs/invoice.schema.json) using JSON Schema
Draft 2020-12. The schema describes data only; it contains no OCR, rendering, PDF,
or company-specific rules.

## Compatibility strategy

Every canonical document uses a small versioned envelope:

- `schema_version` identifies the contract version. Version `1.0` is fixed by this
  invoice schema. Additive, compatible revisions may use a new minor version in a
  future schema; incompatible changes require a new major version and migration.
- `document_type` is the stable payload discriminator. It is `invoice` here.
  Future types such as `quotation` or `purchase_order` can receive their own
  schemas while retaining the same envelope.
- `document` contains the type-specific canonical payload. This separation keeps
  invoice fields from leaking into other document types.
- `extensions` is an optional escape hatch for namespaced data that is not part of
  the stable core. Keys must resemble `vendor.feature` to prevent collisions.
  Consumers must not require an extension unless they explicitly support it.

Unknown fields are rejected throughout the core model. This prevents misspellings
or template-only values from silently becoming competing sources of truth.
Controlled additions belong in `extensions` until intentionally promoted into a
versioned core schema.

## Invoice fields

The `document` object contains:

- `invoice_number` (required string) is the identifier assigned by the issuer. It
  is a string because identifiers can contain letters, separators, or leading
  zeroes and must not be treated as arithmetic values.
- `dates` (required object) groups dates so their meanings remain explicit:
  - `issue_date` (required ISO `YYYY-MM-DD` date) records when the invoice was
    issued.
  - `supply_date` (optional ISO date) records when goods or services were supplied.
  - `due_date` (optional ISO date) records the payment deadline.
- `seller` (required party) identifies the supplier and uses the shared party
  structure described below.
- `buyer` (required party) identifies the customer and uses the same structure,
  avoiding separate company-specific models.
- `currency` (required string) is a three-letter uppercase ISO 4217 code such as
  `KRW`, `USD`, or `EUR`. One invoice currency applies to all monetary fields,
  eliminating ambiguous mixed-currency values.
- `items` (required non-empty array) preserves the ordered invoice line items.
- `totals` (required object) holds the authoritative invoice-wide monetary totals.
- `remarks` (optional string) stores free-form invoice notes, special conditions,
  or payment information without embedding them in a template.
- `extensions` (optional object) holds namespaced invoice-specific additions that
  do not belong in the stable model.

## Seller and buyer fields

Both `seller` and `buyer` use the same reusable party model:

- `name` (required non-empty string) is the legal or trading name and is the
  minimum identity required for either party.
- `business_registration_number` (optional string) preserves the identifier as
  data. The schema deliberately does not impose one company's formatting rules.
- `representative` (optional string) names the registered or acting representative.
- `address` (optional string) stores the postal or registered business address as
  content, leaving line wrapping to presentation templates.
- `business_type` (optional string) represents the registered business category
  commonly shown on Korean business documents.
- `business_item` (optional string) represents the registered industry, activity,
  or business item commonly shown alongside the business type.
- `contact` (optional object) separates operational contact details from legal
  identity:
  - `name` is the contact person's name.
  - `email` is a syntactically valid email address.
  - `phone` is a string so country codes, spaces, and punctuation are preserved.
- `extensions` stores optional namespaced party data without hardcoding fields for
  a particular company.

## Item fields

Every object in `items` contains:

- `line_number` (optional positive integer) provides a stable display or reference
  number when array position alone is insufficient.
- `description` (required non-empty string) identifies the good or service.
- `quantity` (required positive number) supports both whole and fractional
  quantities. Zero or negative quantities require a future explicit adjustment
  model rather than an ambiguous normal item.
- `unit` (required non-empty string) keeps the unit of measure independent from
  the numeric quantity and permits Korean or international unit labels.
- `unit_price` (required number) is the per-unit amount before VAT.
- `supply_amount` (required number) is the canonical line amount before VAT after
  any adjustments represented by the source system.
- `vat` (required non-negative number) is the VAT amount for the line. It remains
  explicit so tax-exempt and zero-VAT lines can use `0` without inference.
- `total` (required number) is the canonical final line amount including VAT.
- `remarks` (optional string) stores a note that applies only to that line.
- `extensions` stores namespaced line-level data outside the stable contract.

The schema records supplied monetary values but does not prescribe calculation or
rounding rules. Those rules vary by jurisdiction, source system, and business
policy and must not be hidden inside the data contract. Future validation may
compare arithmetic relationships, but it must never silently rewrite canonical
values.

## Total fields

The `totals` object contains:

- `supply_amount` (required number) is the authoritative invoice-wide amount
  before VAT.
- `vat` (required non-negative number) is the authoritative invoice-wide VAT.
- `total` (required number) is the authoritative amount payable including VAT.

Totals are stored explicitly instead of being presentation-time calculations.
This ensures all future outputs use the same reviewed values and makes differences
caused by source rounding visible.

## Numeric representation

Amounts and quantities are JSON numbers, never localized strings. For example,
use `1250000`, not `"₩1,250,000"`. Currency symbols, thousands separators, decimal
places, and Korean labels are presentation concerns owned by templates.

Systems that cannot safely preserve decimal precision must use a decimal-capable
parser when reading and writing canonical JSON. They must not round through binary
floating-point operations.

## Example

```json
{
  "schema_version": "1.0",
  "document_type": "invoice",
  "document": {
    "invoice_number": "INV-2026-0001",
    "dates": {
      "issue_date": "2026-07-29",
      "supply_date": "2026-07-29",
      "due_date": "2026-08-28"
    },
    "seller": {
      "name": "예시공급자 주식회사",
      "business_registration_number": "000-00-00000",
      "representative": "홍길동",
      "address": "서울특별시 예시구 예시로 1",
      "business_type": "서비스업",
      "business_item": "소프트웨어 개발"
    },
    "buyer": {
      "name": "예시구매자 주식회사"
    },
    "currency": "KRW",
    "items": [
      {
        "line_number": 1,
        "description": "예시 서비스",
        "quantity": 1,
        "unit": "건",
        "unit_price": 100000,
        "supply_amount": 100000,
        "vat": 10000,
        "total": 110000
      }
    ],
    "totals": {
      "supply_amount": 100000,
      "vat": 10000,
      "total": 110000
    },
    "remarks": "예시 데이터이며 실제 회사 정보가 아닙니다."
  }
}
```

