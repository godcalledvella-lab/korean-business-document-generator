import invoiceSchema from "../../configs/invoice.schema.json" with { type: "json" };

type SchemaNode = {
  $ref?: string;
  type?: string;
  properties?: Record<string, SchemaNode>;
  required?: string[];
  items?: SchemaNode;
};

export type CanonicalStringField = {
  path: string;
  required: boolean;
  value: unknown;
};

const rootSchema = invoiceSchema as SchemaNode & {
  $defs?: Record<string, SchemaNode>;
};

function resolve(node: SchemaNode): SchemaNode {
  if (!node.$ref) return node;
  const prefix = "#/$defs/";
  if (!node.$ref.startsWith(prefix)) {
    throw new Error(`Unsupported canonical schema reference: ${node.$ref}`);
  }
  const resolved = rootSchema.$defs?.[node.$ref.slice(prefix.length)];
  if (!resolved) {
    throw new Error(`Canonical schema reference was not found: ${node.$ref}`);
  }
  return resolved;
}

function childValue(value: unknown, key: string): unknown {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)[key]
    : undefined;
}

function collectStrings(
  nodeInput: SchemaNode,
  value: unknown,
  path: string,
  required: boolean,
  fields: CanonicalStringField[],
): void {
  const node = resolve(nodeInput);
  if (node.type === "string") {
    fields.push({ path, required, value });
    return;
  }
  if (node.type === "object" && node.properties) {
    const requiredNames = new Set(node.required || []);
    for (const [name, child] of Object.entries(node.properties)) {
      const nextPath = path ? `${path}.${name}` : name;
      collectStrings(
        child,
        childValue(value, name),
        nextPath,
        required && requiredNames.has(name),
        fields,
      );
    }
    return;
  }
  if (node.type === "array" && node.items && Array.isArray(value)) {
    value.forEach((item, index) => {
      collectStrings(node.items!, item, `${path}.${index}`, required, fields);
    });
  }
}

export function canonicalStringFields(draft: unknown): CanonicalStringField[] {
  const fields: CanonicalStringField[] = [];
  collectStrings(rootSchema, draft, "", true, fields);
  return fields;
}

export function canonicalStringField(
  draft: unknown,
  path: string,
): CanonicalStringField | undefined {
  return canonicalStringFields(draft).find((field) => field.path === path);
}
