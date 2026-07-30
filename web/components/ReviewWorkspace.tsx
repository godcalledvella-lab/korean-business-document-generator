"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { InvoiceDraft, InvoiceItem, Party, SessionPayload } from "@/lib/types";
import {
  fieldId,
  isRequiredReviewString,
  validateCanonicalDraft,
  type ReviewValidationIssue,
} from "@/lib/reviewValidation";
import {
  comparisonSupplyAmount,
  DEFAULT_COMPARISON_MARKUP_PERCENTAGE,
  QUICK_COMPARISON_MARKUPS,
  validateMarkupPercentage,
} from "@/lib/comparisonMarkup";
import {
  REVIEW_SETTINGS_EXTENSION,
  defaultReviewDocumentSettings,
  mergeReviewDocumentSettings,
  type ReviewDocumentSettings,
  type VisibilityField,
} from "@/lib/reviewDocuments";

type PathValue = string | number | undefined;

export default function ReviewWorkspace({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [draft, setDraft] = useState<InvoiceDraft | null>(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generationStage, setGenerationStage] = useState("");
  const [downloads, setDownloads] = useState<Record<string, string>>({});
  const [serverIssues, setServerIssues] = useState<ReviewValidationIssue[]>([]);
  const [markupInput, setMarkupInput] = useState(
    String(DEFAULT_COMPARISON_MARKUP_PERCENTAGE),
  );
  const [reviewSettings, setReviewSettings] =
    useState<ReviewDocumentSettings | null>(null);

  useEffect(() => {
    fetch(`/api/session/${sessionId}`, { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error);
        setSession(payload);
        setDraft(payload.draft);
        setDownloads(payload.downloads || {});
        const defaults = defaultReviewDocumentSettings(
          payload.draft,
          payload.confidences,
        );
        setReviewSettings(
          mergeReviewDocumentSettings(
            defaults,
            payload.reviewSettings ??
              payload.draft?.extensions?.[REVIEW_SETTINGS_EXTENSION],
          ),
        );
        const storedMarkup =
          payload.comparisonMarkupPercentage ??
          payload.draft?.extensions?.["rmntc.comparison_markup_percentage"] ??
          DEFAULT_COMPARISON_MARKUP_PERCENTAGE;
        setMarkupInput(String(storedMarkup));
      })
      .catch((reason) => setError(reason.message || "Could not load review."));
  }, [sessionId]);

  const requiredIssues = useMemo(
    () => validateCanonicalDraft(draft),
    [draft],
  );
  const issueCount = useMemo(() => {
    if (!session) return 0;
    return new Set([
      ...session.validation.missing,
      ...session.validation.lowConfidence,
      ...session.validation.arithmeticMismatches,
      ...requiredIssues.map((issue) => issue.path),
    ]).size;
  }, [session, requiredIssues]);
  const requiredByPath = useMemo(
    () => new Map(requiredIssues.map((issue) => [issue.path, issue.message])),
    [requiredIssues],
  );
  const markupValidation = useMemo(
    () => validateMarkupPercentage(markupInput),
    [markupInput],
  );
  const comparisonTotal = useMemo(
    () => markupValidation.value === undefined || !draft
      ? undefined
      : comparisonSupplyAmount(draft.document.items, markupValidation.value),
    [draft, markupValidation.value],
  );

  useEffect(() => {
    if (!session || markupValidation.value === undefined) return;
    const timer = window.setTimeout(() => {
      fetch(`/api/session/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          comparisonMarkupPercentage: markupValidation.value,
        }),
      }).catch((reason) => {
        console.warn("[Review] Could not persist comparison markup", reason);
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [markupValidation.value, session, sessionId]);

  useEffect(() => {
    if (!session || !reviewSettings) return;
    const timer = window.setTimeout(() => {
      fetch(`/api/session/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewSettings }),
      }).catch((reason) => {
        console.warn("[Review] Could not persist document settings", reason);
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [reviewSettings, session, sessionId]);

  function focusIssue(path: string) {
    const element = document.getElementById(fieldId(path));
    element?.focus();
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function update(path: string, value: PathValue) {
    setDraft((current) => {
      if (!current) return current;
      const next = structuredClone(current);
      const parts = path.split(".");
      let target: Record<string, unknown> | unknown[] = next as unknown as Record<string, unknown>;
      for (const part of parts.slice(0, -1)) {
        const currentValue = (target as Record<string, unknown>)[part];
        if (
          currentValue === null ||
          typeof currentValue !== "object" ||
          Array.isArray(currentValue)
        ) {
          (target as Record<string, unknown>)[part] = {};
        }
        target = (target as Record<string, unknown>)[part] as Record<string, unknown>;
      }
      (target as Record<string, unknown>)[parts.at(-1)!] = value;
      return next;
    });
    setServerIssues([]);
    setError("");
  }

  function updateItem(index: number, key: keyof InvoiceItem, value: PathValue) {
    setDraft((current) => {
      if (!current) return current;
      const next = structuredClone(current);
      (next.document.items[index] as Record<string, PathValue>)[key] = value;
      return next;
    });
    setServerIssues([]);
    setError("");
  }

  function addItem() {
    setDraft((current) => {
      if (!current) return current;
      const next = structuredClone(current);
      next.document.items.push({
        line_number: next.document.items.length + 1,
        description: "",
        quantity: 1,
        unit: "",
        unit_price: 0,
        supply_amount: 0,
        vat: 0,
        total: 0,
        remarks: "",
      });
      return next;
    });
  }

  function removeItem(index: number) {
    setDraft((current) => {
      if (!current) return current;
      const next = structuredClone(current);
      next.document.items.splice(index, 1);
      next.document.items.forEach((item, itemIndex) => {
        item.line_number = itemIndex + 1;
      });
      return next;
    });
  }

  async function generate() {
    if (!draft || !reviewSettings) return;
    const localIssues = validateCanonicalDraft(draft);
    if (localIssues.length) {
      setServerIssues([]);
      setError("필수 입력값을 확인한 후 다시 시도해 주세요.");
      focusIssue(localIssues[0].path);
      return;
    }
    if (markupValidation.value === undefined) {
      setError(markupValidation.error || "가산율을 확인해 주세요.");
      document.getElementById("comparison-markup-input")?.focus();
      return;
    }
    const progressTimers: number[] = [];
    setGenerating(true);
    setError("");
    setGenerationStage("Validating reviewed invoice…");
    try {
      progressTimers.push(
        window.setTimeout(
          () => setGenerationStage("Generating three workbooks…"),
          700,
        ),
      );
      progressTimers.push(
        window.setTimeout(
          () => setGenerationStage("Preparing previews and downloads…"),
          2400,
        ),
      );
      const approvedDraft = structuredClone(draft);
      approvedDraft.extensions = {
        ...(approvedDraft.extensions || {}),
        "rmntc.comparison_markup_percentage": markupValidation.value,
        [REVIEW_SETTINGS_EXTENSION]: reviewSettings,
      };
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, draft: approvedDraft }),
      });
      const responseText = await response.text();
      let payload: {
        error?: unknown;
        downloads?: Record<string, string>;
      } = {};
      try {
        payload = responseText ? JSON.parse(responseText) : {};
      } catch {
        // Preserve a useful plain-text backend error if JSON is unavailable.
      }
      if (!response.ok) {
        const message =
          (typeof payload.error === "string" && payload.error) ||
          responseText.trim() ||
          `Generation failed (${response.status} ${response.statusText}).`;
        if (response.status === 422) {
          const affected = canonicalIssuesFromMessage(message, draft);
          setServerIssues(affected);
          setError(message);
          if (affected.length) focusIssue(affected[0].path);
          return;
        }
        throw new Error(message);
      }
      if (!payload.downloads) {
        throw new Error("Generation completed without downloadable outputs.");
      }
      setDownloads(payload.downloads);
      router.push(`/preview/${sessionId}`);
    } catch (reason) {
      const message =
        reason instanceof Error ? reason.message : "Generation failed.";
      console.error("[Generation] POST /api/generate failed", {
        sessionId,
        message,
      });
      setError(message);
    } finally {
      progressTimers.forEach((timer) => window.clearTimeout(timer));
      setGenerating(false);
      setGenerationStage("");
    }
  }

  if (error && !draft) {
    return <main className="review-shell"><div className="empty-state"><h1>Review unavailable</h1><p>{error}</p><a href="/">Start again</a></div></main>;
  }
  if (!draft || !session || !reviewSettings) {
    return <main className="review-shell"><div className="review-loading"><span /><p>Loading review draft…</p></div></main>;
  }

  const confidence = (path: string) => session.confidences[path];

  return (
    <main className="review-shell">
      <section className="review-heading">
        <div>
          <a className="back-link" href="/">← New invoice</a>
          <span className="eyebrow">Review before generation</span>
          <h1>Confirm invoice details</h1>
          <p>Every value remains editable. Compare low-confidence fields with the original invoice.</p>
        </div>
        <div className={issueCount ? "review-summary attention" : "review-summary"}>
          <span>{issueCount ? issueCount : "✓"}</span>
          <div>
            <strong>{issueCount ? "Fields need attention" : "Ready for review"}</strong>
            <small>{session.sourceName}</small>
          </div>
        </div>
      </section>

      <div className="review-grid">
        <div className="review-main">
          <Section title="Invoice details" subtitle="Document identity and issue date">
            <div className="field-grid three">
              <Field label="Schema version" path="schema_version" value={draft.schema_version} onChange={update} required={isRequiredReviewString(draft, "schema_version")} error={requiredByPath.get("schema_version")} />
              <Field label="Document type" path="document_type" value={draft.document_type} onChange={update} required={isRequiredReviewString(draft, "document_type")} error={requiredByPath.get("document_type")} />
              <Field label="Approval number" path="document.invoice_number" value={draft.document.invoice_number} confidence={confidence("document.invoice_number")} onChange={update} required={isRequiredReviewString(draft, "document.invoice_number")} error={requiredByPath.get("document.invoice_number")} />
              <Field label="Issue date" path="document.dates.issue_date" value={draft.document.dates.issue_date} confidence={confidence("document.dates.issue_date")} onChange={update} required={isRequiredReviewString(draft, "document.dates.issue_date")} error={requiredByPath.get("document.dates.issue_date")} />
              <Field label="Currency" path="document.currency" value={draft.document.currency} onChange={update} required={isRequiredReviewString(draft, "document.currency")} error={requiredByPath.get("document.currency")} />
            </div>
          </Section>

          <PartySection title="Seller" prefix="document.seller" party={draft.document.seller} draft={draft} confidence={confidence} update={update} errors={requiredByPath} />
          <PartySection title="Buyer" prefix="document.buyer" party={draft.document.buyer} draft={draft} confidence={confidence} update={update} errors={requiredByPath} />

          <Section
            title="Items"
            subtitle={`${draft.document.items.length} line ${draft.document.items.length === 1 ? "item" : "items"}`}
            action={<button className="text-button" onClick={addItem}>＋ Add item</button>}
          >
            <div className="items-list">
              {draft.document.items.map((item, index) => (
                <article className="item-card" key={`${item.line_number}-${index}`}>
                  <div className="item-title">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{item.description || "Untitled item"}</strong>
                    {draft.document.items.length > 1 && (
                      <button aria-label={`Remove item ${index + 1}`} onClick={() => removeItem(index)}>Remove</button>
                    )}
                  </div>
                  <div className="field-grid item-fields">
                    <ItemField label="Description" item={item} index={index} name="description" confidence={confidence(`document.items.${index}.description`)} update={updateItem} wide required={isRequiredReviewString(draft, `document.items.${index}.description`)} error={requiredByPath.get(`document.items.${index}.description`)} />
                    <ItemField label="Quantity" item={item} index={index} name="quantity" confidence={confidence(`document.items.${index}.quantity`)} update={updateItem} numeric required error={requiredByPath.get(`document.items.${index}.quantity`)} />
                    <ItemField label="Unit" item={item} index={index} name="unit" confidence={confidence(`document.items.${index}.unit`)} update={updateItem} required={isRequiredReviewString(draft, `document.items.${index}.unit`)} error={requiredByPath.get(`document.items.${index}.unit`)} />
                    <ItemField label="Unit price" item={item} index={index} name="unit_price" confidence={confidence(`document.items.${index}.unit_price`)} update={updateItem} numeric money required error={requiredByPath.get(`document.items.${index}.unit_price`)} />
                    <ItemField label="Supply" item={item} index={index} name="supply_amount" confidence={confidence(`document.items.${index}.supply_amount`)} update={updateItem} numeric money required error={requiredByPath.get(`document.items.${index}.supply_amount`)} />
                    <ItemField label="VAT" item={item} index={index} name="vat" confidence={confidence(`document.items.${index}.vat`)} update={updateItem} numeric money required error={requiredByPath.get(`document.items.${index}.vat`)} />
                    <ItemField label="Total" item={item} index={index} name="total" confidence={confidence(`document.items.${index}.total`)} update={updateItem} numeric money required error={requiredByPath.get(`document.items.${index}.total`)} />
                    <ItemField label="Remarks" item={item} index={index} name="remarks" confidence={confidence(`document.items.${index}.remarks`)} update={updateItem} wide />
                  </div>
                </article>
              ))}
            </div>
          </Section>

          <Section title="Totals" subtitle="These values are validated by the backend">
            <div className="field-grid three">
              <Field label="Supply amount" path="document.totals.supply_amount" value={draft.document.totals.supply_amount} confidence={confidence("document.totals.supply_amount")} onChange={update} numeric money required error={requiredByPath.get("document.totals.supply_amount")} />
              <Field label="VAT" path="document.totals.vat" value={draft.document.totals.vat} confidence={confidence("document.totals.vat")} onChange={update} numeric money required error={requiredByPath.get("document.totals.vat")} />
              <Field label="Grand total" path="document.totals.total" value={draft.document.totals.total} confidence={confidence("document.totals.total")} onChange={update} numeric money required error={requiredByPath.get("document.totals.total")} />
            </div>
          </Section>

          <Section
            title="Statement"
            subtitle="거래명세서 발신자와 하단 계좌 정보를 확인하세요"
          >
            <div className="field-grid two">
              {([
                ["sender", "발신자"],
                ["companyName", "상호명"],
                ["bank", "은행"],
                ["accountNumber", "계좌번호"],
              ] as const).map(([key, label]) => (
                <DocumentTextField
                  key={key}
                  label={label}
                  value={reviewSettings.statement[key]}
                  onChange={(value) => setReviewSettings((current) => current && ({
                    ...current,
                    statement: { ...current.statement, [key]: value },
                  }))}
                />
              ))}
            </div>
          </Section>

          <Section
            title="Blue quotation"
            subtitle="견적서 표시 항목 — 값만 변경하며 템플릿 구조는 유지됩니다"
          >
            <div className="field-grid two">
              <DocumentTextField
                label="CLIENT"
                value={reviewSettings.blueQuotation.client}
                onChange={(value) => setReviewSettings((current) => current && ({
                  ...current,
                  blueQuotation: { ...current.blueQuotation, client: value },
                }))}
              />
              <DocumentTextField
                label="PRODUCT"
                value={reviewSettings.blueQuotation.product}
                onChange={(value) => setReviewSettings((current) => current && ({
                  ...current,
                  blueQuotation: { ...current.blueQuotation, product: value },
                }))}
              />
            </div>
            <h3 className="settings-subtitle">Black information bar</h3>
            <div className="visibility-grid">
              {([
                ["companyName", "상호"],
                ["businessNumber", "사업자번호"],
                ["address", "주소"],
                ["representative", "대표자"],
              ] as const).map(([key, label]) => (
                <VisibilityEditor
                  key={key}
                  label={label}
                  field={reviewSettings.blueQuotation.informationBar[key]}
                  onChange={(field) => setReviewSettings((current) => current && ({
                    ...current,
                    blueQuotation: {
                      ...current.blueQuotation,
                      informationBar: {
                        ...current.blueQuotation.informationBar,
                        [key]: field,
                      },
                    },
                  }))}
                />
              ))}
            </div>
            <h3 className="settings-subtitle">Footer blue bar</h3>
            <div className="field-grid two">
              {([
                ["telephone", "TEL"],
                ["email", "Email"],
                ["bank", "Bank"],
                ["accountNumber", "Account"],
              ] as const).map(([key, label]) => (
                <DocumentTextField
                  key={key}
                  label={label}
                  value={reviewSettings.blueQuotation.footer[key]}
                  onChange={(value) => setReviewSettings((current) => current && ({
                    ...current,
                    blueQuotation: {
                      ...current.blueQuotation,
                      footer: {
                        ...current.blueQuotation.footer,
                        [key]: value,
                      },
                    },
                  }))}
                />
              ))}
            </div>
            <VisibilityTextEditor
              label="Product Details"
              visible={reviewSettings.blueQuotation.showProductDetails}
              value={reviewSettings.blueQuotation.productDetails}
              onVisible={(visible) => setReviewSettings((current) => current && ({
                ...current,
                blueQuotation: {
                  ...current.blueQuotation,
                  showProductDetails: visible,
                },
              }))}
              onValue={(value) => setReviewSettings((current) => current && ({
                ...current,
                blueQuotation: {
                  ...current.blueQuotation,
                  productDetails: value,
                },
              }))}
            />
            <VisibilityTextEditor
              label="Remark"
              visible={reviewSettings.blueQuotation.showRemark}
              value={reviewSettings.blueQuotation.remark}
              onVisible={(visible) => setReviewSettings((current) => current && ({
                ...current,
                blueQuotation: {
                  ...current.blueQuotation,
                  showRemark: visible,
                },
              }))}
              onValue={(value) => setReviewSettings((current) => current && ({
                ...current,
                blueQuotation: { ...current.blueQuotation, remark: value },
              }))}
            />
          </Section>

          <Section
            title="Green quotation"
            subtitle="비교견적서 기본 회사 정보와 수신 정보를 확인하세요"
          >
            <div className="field-grid two">
              <DocumentTextField
                label="회사명"
                value={reviewSettings.greenQuotation.buyerCompany}
                onChange={(value) => setReviewSettings((current) => current && ({
                  ...current,
                  greenQuotation: {
                    ...current.greenQuotation,
                    buyerCompany: value,
                  },
                }))}
              />
              <DocumentTextField
                label="견적일자"
                value={reviewSettings.greenQuotation.quotationDate}
                type="date"
                onChange={(value) => setReviewSettings((current) => current && ({
                  ...current,
                  greenQuotation: {
                    ...current.greenQuotation,
                    quotationDate: value,
                  },
                }))}
              />
              {([
                ["registrationNumber", "등록번호"],
                ["companyName", "상호(법인명)"],
                ["representative", "성명 / 대표자"],
                ["address", "주소"],
                ["businessType", "업태"],
                ["businessItem", "종목"],
                ["phone", "전화번호"],
                ["hp", "H.P"],
              ] as const).map(([key, label]) => (
                <DocumentTextField
                  key={key}
                  label={label}
                  value={reviewSettings.greenQuotation.companyProfile[key]}
                  onChange={(value) => setReviewSettings((current) => current && ({
                    ...current,
                    greenQuotation: {
                      ...current.greenQuotation,
                      companyProfile: {
                        ...current.greenQuotation.companyProfile,
                        [key]: value,
                      },
                    },
                  }))}
                />
              ))}
            </div>
          </Section>

          <Section
            title="Comparison quotation markup"
            subtitle="비교견적서 가산율"
          >
            <div className="markup-controls">
              <div className="markup-quick-select" aria-label="Quick markup choices">
                {QUICK_COMPARISON_MARKUPS.map((percentage) => (
                  <button
                    type="button"
                    key={percentage}
                    className={Number(markupInput) === percentage ? "selected" : ""}
                    onClick={() => {
                      setMarkupInput(String(percentage));
                      setError("");
                    }}
                  >
                    {percentage}%
                  </button>
                ))}
              </div>
              <div className="markup-editor">
                <div className="markup-slider-heading">
                  <label htmlFor="comparison-markup-slider">Markup percentage</label>
                  <output htmlFor="comparison-markup-slider comparison-markup-input">
                    {markupValidation.value === undefined ? "—" : `${markupValidation.value}%`}
                  </output>
                </div>
                <div className="markup-slider-row">
                  <span>0%</span>
                  <input
                    id="comparison-markup-slider"
                    type="range"
                    min="0"
                    max="100"
                    step="0.1"
                    value={markupValidation.value ?? 0}
                    style={{
                      "--markup-position": `${markupValidation.value ?? 0}%`,
                    } as React.CSSProperties}
                    onChange={(event) => {
                      setMarkupInput(event.target.value);
                      setError("");
                    }}
                  />
                  <span>100%</span>
                </div>
                <label className={markupValidation.error ? "markup-custom invalid" : "markup-custom"} htmlFor="comparison-markup-input">
                  <span>Enter exact value</span>
                  <div>
                    <input
                      id="comparison-markup-input"
                      type="text"
                      inputMode="decimal"
                      value={markupInput}
                      aria-invalid={Boolean(markupValidation.error)}
                      aria-describedby={markupValidation.error ? "comparison-markup-error" : undefined}
                      onChange={(event) => {
                        setMarkupInput(event.target.value);
                        setError("");
                      }}
                    />
                    <i>%</i>
                  </div>
                  {markupValidation.error && (
                    <small id="comparison-markup-error">{markupValidation.error}</small>
                  )}
                </label>
              </div>
            </div>
            <div className="markup-summary" aria-live="polite">
              <div><span>Original supply amount</span><strong>{formatKrw(draft.document.totals.supply_amount)}</strong></div>
              <div><span>Selected markup</span><strong>{markupValidation.value === undefined ? "—" : `${markupValidation.value}%`}</strong></div>
              <div><span>Comparison supply amount</span><strong>{comparisonTotal === undefined ? "—" : formatKrw(comparisonTotal)}</strong></div>
            </div>
          </Section>
        </div>

        <aside className="review-sidebar">
          <div className="sticky-panel">
            <div className="source-card">
              <span className="source-icon">PDF</span>
              <div><strong>Original invoice</strong><small>{session.sourceName}</small></div>
              <a href={`/api/download/${sessionId}/tax-invoice`}>Download</a>
            </div>
            <div className="confidence-legend">
              <h3>Confidence</h3>
              <p><span className="legend-dot high" /> 90–100% High</p>
              <p><span className="legend-dot medium" /> 80–89% Review</p>
              <p><span className="legend-dot low" /> Below 80% Attention</p>
            </div>
            {error && <div className="inline-error">{error}</div>}
            {(requiredIssues.length > 0 || serverIssues.length > 0) && (
              <div className="validation-summary" role="alert">
                <strong>필수 입력값을 확인해 주세요</strong>
                <ul>
                  {(serverIssues.length ? serverIssues : requiredIssues).map((issue) => (
                    <li key={`${issue.path}-${issue.message}`}>
                      <button type="button" onClick={() => focusIssue(issue.path)}>
                        {issue.message}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!Object.keys(downloads).length ? (
              <button className="generate-button" onClick={generate} disabled={generating || requiredIssues.length > 0 || markupValidation.value === undefined}>
                {generating ? <><span className="button-spinner" /> {generationStage}</> : <>Generate documents <span>→</span></>}
              </button>
            ) : (
              <button
                className="generate-button"
                onClick={() => router.push(`/preview/${sessionId}`)}
              >
                Preview generated pages <span>→</span>
              </button>
            )}
            <p className="generation-note">Backend validation runs again before any file is created.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}

function Section({ title, subtitle, action, children }: { title: string; subtitle: string; action?: React.ReactNode; children: React.ReactNode }) {
  return <section className="review-card"><header><div><h2>{title}</h2><p>{subtitle}</p></div>{action}</header>{children}</section>;
}

function PartySection({ title, prefix, party, draft, confidence, update, errors }: {
  title: string; prefix: string; party: Party; draft: InvoiceDraft;
  confidence: (path: string) => number | undefined;
  update: (path: string, value: PathValue) => void;
  errors: Map<string, string>;
}) {
  const fields = [
    ["Company name", "name"],
    ["Business number", "business_registration_number"],
    ["Representative", "representative"],
    ["Address", "address"],
    ["Business type", "business_type"],
    ["Business category", "business_item"],
    ["Email", "contact.email"],
    ["Phone", "contact.phone"],
  ] as const;
  const get = (path: string) => path.split(".").reduce<unknown>((value, key) => (value as Record<string, unknown> | undefined)?.[key], party) as string | undefined;
  return (
    <Section title={title} subtitle={title === "Seller" ? "Supplier information" : "Customer information"}>
      <div className="field-grid two">
        {fields.map(([label, key]) => (
          <Field key={key} label={label} path={`${prefix}.${key}`} value={get(key)} confidence={confidence(`${prefix}.${key}`)} onChange={update} wide={key === "address"} required={isRequiredReviewString(draft, `${prefix}.${key}`)} error={errors.get(`${prefix}.${key}`)} />
        ))}
      </div>
    </Section>
  );
}

function Field({ label, path, value, confidence, onChange, type = "text", numeric, money, wide, required, error }: {
  label: string; path: string; value: unknown; confidence?: number;
  onChange: (path: string, value: PathValue) => void;
  type?: string; numeric?: boolean; money?: boolean; wide?: boolean;
  required?: boolean; error?: string;
}) {
  const confidenceClass = confidence === undefined ? "" : confidence < 0.8 ? "low-confidence" : confidence < 0.9 ? "medium-confidence" : "";
  const inputId = fieldId(path);
  const inputValue = numeric
    ? (typeof value === "number" && Number.isFinite(value) ? value : "")
    : (typeof value === "string" ? value : "");
  return (
    <label className={`field ${wide ? "wide" : ""} ${confidenceClass} ${error ? "required-missing" : ""}`} htmlFor={inputId}>
      <span>{label}{required && <b className="required-mark" aria-hidden="true"> *</b>}<ConfidenceBadge value={confidence} /></span>
      <div className="input-wrap">
        {money && <i>₩</i>}
        <input
          id={inputId}
          type={numeric ? "number" : type}
          value={inputValue}
          required={required}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${inputId}-error` : undefined}
          onChange={(event) => onChange(path, numeric ? (event.target.value === "" ? undefined : Number(event.target.value)) : event.target.value)}
        />
      </div>
      {error && <small className="field-error" id={`${inputId}-error`}>{error}</small>}
    </label>
  );
}

function ItemField({ item, index, name, update, numeric, money, wide, ...rest }: {
  label: string; item: InvoiceItem; index: number; name: keyof InvoiceItem;
  update: (index: number, key: keyof InvoiceItem, value: PathValue) => void;
  confidence?: number; numeric?: boolean; money?: boolean; wide?: boolean;
  required?: boolean; error?: string;
}) {
  return <Field {...rest} label={rest.label} path={`document.items.${index}.${String(name)}`} value={item[name]} numeric={numeric} money={money} wide={wide} onChange={(_, value) => update(index, name, value)} />;
}

function ConfidenceBadge({ value }: { value?: number }) {
  if (value === undefined) return <em className="confidence unknown">Not scored</em>;
  const level = value < 0.8 ? "low" : value < 0.9 ? "medium" : "high";
  return <em className={`confidence ${level}`}>{Math.round(value * 100)}%</em>;
}

function DocumentTextField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="input-wrap">
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    </label>
  );
}

function VisibilityEditor({
  label,
  field,
  onChange,
}: {
  label: string;
  field: VisibilityField;
  onChange: (field: VisibilityField) => void;
}) {
  return (
    <div className="visibility-editor">
      <label className="visibility-toggle">
        <input
          type="checkbox"
          checked={field.visible}
          onChange={(event) => onChange({
            ...field,
            visible: event.target.checked,
          })}
        />
        <span>{label}</span>
        <small>{field.visible ? "Show" : "Hide"}</small>
      </label>
      <input
        type="text"
        value={field.value}
        disabled={!field.visible}
        aria-label={`${label} value`}
        onChange={(event) => onChange({ ...field, value: event.target.value })}
      />
    </div>
  );
}

function VisibilityTextEditor({
  label,
  visible,
  value,
  onVisible,
  onValue,
}: {
  label: string;
  visible: boolean;
  value: string;
  onVisible: (visible: boolean) => void;
  onValue: (value: string) => void;
}) {
  return (
    <div className="visibility-text-editor">
      <label className="visibility-toggle">
        <input
          type="checkbox"
          checked={visible}
          onChange={(event) => onVisible(event.target.checked)}
        />
        <span>{label}</span>
        <small>{visible ? "Show" : "Hide"}</small>
      </label>
      <textarea
        value={value}
        disabled={!visible}
        onChange={(event) => onValue(event.target.value)}
      />
    </div>
  );
}

function formatKrw(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `₩${Math.round(value).toLocaleString("ko-KR")}`
    : "—";
}

function canonicalIssuesFromMessage(
  message: string,
  draft: InvoiceDraft,
): ReviewValidationIssue[] {
  const local = validateCanonicalDraft(draft);
  if (local.length) return local;
  const match = message.match(/document\.items\.(\d+).*['\"]unit['\"]/i);
  if (match) {
    const index = Number(match[1]);
    return [{
      path: `document.items.${index}.unit`,
      message: `품목 ${index + 1}의 단위를 입력해 주세요.`,
    }];
  }
  return [];
}
