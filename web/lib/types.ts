export type Contact = { name?: string; email?: string; phone?: string };
export type Party = {
  name?: string;
  business_registration_number?: string;
  representative?: string;
  address?: string;
  business_type?: string;
  business_item?: string;
  contact?: Contact;
};
export type InvoiceItem = {
  line_number: number;
  description?: string;
  quantity?: number;
  unit?: string;
  unit_price?: number;
  supply_amount?: number;
  vat?: number;
  total?: number;
  remarks?: string;
};
export type InvoiceDraft = {
  schema_version: string;
  document_type: string;
  document: {
    invoice_number?: string;
    dates: { issue_date?: string };
    seller: Party;
    buyer: Party;
    currency: string;
    items: InvoiceItem[];
    totals: { supply_amount?: number; vat?: number; total?: number };
  };
  extensions?: Record<string, unknown>;
};
export type SessionPayload = {
  sessionId: string;
  sourceName: string;
  sourceType: string;
  draft: InvoiceDraft;
  confidences: Record<string, number>;
  validation: {
    safeToApprove: boolean;
    schemaConformant: boolean;
    missing: string[];
    lowConfidence: string[];
    arithmeticMismatches: string[];
  };
  downloads?: Record<string, string>;
  previews?: Record<string, string>;
  previewMode?: "pdf" | "html";
  packageError?: string | null;
  bundleName?: string;
  comparisonMarkupPercentage?: number;
  reviewSettings?: import("@/lib/reviewDocuments").ReviewDocumentSettings;
};
