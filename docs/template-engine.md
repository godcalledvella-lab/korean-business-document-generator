# Template Engine Foundation

## Purpose

The template engine foundation provides a generic, read-only way to discover and
validate presentation templates. It does not render HTML, generate PDFs, parse
source documents, or contain rules for any company.

`renderer.template_manager.TemplateManager` is the public entry point. It returns
validated `TemplateDefinition` metadata; a future renderer will be responsible
for interpreting template assets.

## Organization

Templates use two directory levels:

```text
templates/
  <company>/
    <document_type>/
      template.json
      ...future presentation assets...
```

The current registry contains:

```text
templates/
  rmntc/
    statement/
    quotation/
    comparison/
  cellclinic/
    invoice/
```

Directory identifiers use lowercase letters, digits, hyphens, and underscores.
The engine treats identifiers as data and contains no branches for `rmntc`,
`cellclinic`, or any other company.

## Template manifest

Every template directory requires `template.json`. Its fields are:

- `manifest_version` is the integer version of the template-manifest contract.
  The manager currently accepts version `1`.
- `company` must match the parent directory name. This catches copied templates
  that were not deliberately re-identified.
- `document_type` must match the template directory name.
- `description` is optional human-readable registry metadata.
- `required_files` lists relative presentation asset paths that must exist before
  the template can load. The initial slots use empty arrays because no HTML or
  other renderable assets have been created yet.
- `locked` is an optional boolean ownership signal. A locked template must not be
  modified without explicit instruction. The manager is read-only regardless of
  this value.

Required paths cannot be absolute, traverse through `..`, escape through a
symlink, or point to a non-file. Duplicate entries are rejected.

## Public API

```python
from renderer import TemplateManager

manager = TemplateManager("templates")
available = manager.discover_templates()
invoice = manager.load_template("cellclinic", "invoice")
```

`discover_templates()` returns validated definitions in deterministic
company/document order. `load_template(company, document_type)` validates one
selection and returns its resolved directory, manifest, required files,
description, and lock status.

Failures use explicit exception types:

- `TemplateNotFoundError` means the root or requested template directory does not
  exist.
- `TemplateValidationError` means a manifest is missing or invalid, its identity
  does not match its directory, or a declared required file is unavailable.
- Both inherit from `TemplateError` for callers that want one template-error
  boundary.

## Adding a company or document type

1. Choose stable lowercase company and document-type identifiers.
2. Create `templates/<company>/<document_type>/template.json`.
3. Set the manifest identity fields to match the directory names.
4. Add presentation assets only when their rendering format has been approved.
5. Declare every asset essential to loading in `required_files`.
6. Load the template with `TemplateManager` to validate it.

No engine change should be necessary. If adding a company requires a conditional
in `TemplateManager`, the concern belongs in structured configuration, canonical
document data, or a separate adapter instead.

## Design principles

### Data is separate from presentation

Canonical JSON is the only document-data source. Templates control layout and
labels; they must not own amounts, party data, calculations, tax policy, or
company workflows.

### Renderers accept structured JSON only

A future renderer must receive an already validated canonical JSON object. It
must not accept OCR text, unstructured strings, database models, or
company-specific objects. OCR and parsing, when implemented, must finish before
the renderer boundary.

### Templates contain no business logic

Template assets may express presentation operations such as field placement,
formatting, and iteration over canonical items. They must not calculate totals,
select tax rules, repair missing data, or decide which business process applies.
Such decisions must be resolved before rendering and represented explicitly in
canonical JSON.

### Templates are isolated and replaceable

Each company/document directory is self-contained. Assets from one template must
not be imported implicitly by another. A future shared presentation library must
be explicit, versioned, and declared as a dependency rather than copied or
silently coupled.

### Validation happens before rendering

Loading checks the manifest and all declared required files. A future renderer
should operate only on a successfully loaded `TemplateDefinition`, so missing
assets fail early with actionable paths.

