"use client";

import { useEffect, useState } from "react";
import type { SessionPayload } from "@/lib/types";

const pages = [
  ["taxInvoice", "Tax Invoice", "Supplied source document"],
  ["statement", "Statement", "Generated workbook preview"],
  ["quotation", "Quotation", "Generated workbook preview"],
  ["comparison", "Comparison Quotation", "Generated workbook preview"],
  ["businessRegistration", "Business Registration", "Fixed reference document"],
  ["bankAccount", "Bank Account Copy", "Fixed reference document"],
] as const;

export default function PreviewWorkspace({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`/api/session/${sessionId}`, { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error);
        if (!payload.previews) throw new Error("Generated previews are not ready.");
        setSession(payload);
      })
      .catch((reason) => setError(reason.message || "Could not load previews."));
  }, [sessionId]);

  if (error) {
    return <main className="preview-shell"><div className="empty-state"><h1>Preview unavailable</h1><p>{error}</p><a href={`/review/${sessionId}`}>Return to review</a></div></main>;
  }
  if (!session?.previews) {
    return <main className="preview-shell"><div className="review-loading"><span /><p>Loading generated pages…</p></div></main>;
  }

  const hasPackage = Boolean(session.previews.package && session.downloads?.package);
  return (
    <main className="preview-shell">
      <section className="preview-heading">
        <div>
          <a className="back-link" href={`/review/${sessionId}`}>← Back to review</a>
          <span className="eyebrow">Visual approval</span>
          <h1>Inspect every page</h1>
          <p>Review all six pages in order before downloading the customer package.</p>
          {session.comparisonMarkupPercentage !== undefined && (
            <span className="markup-metadata">
              비교견적서 가산율 {session.comparisonMarkupPercentage}%
            </span>
          )}
        </div>
        <div className="preview-actions">
          {session.downloads?.bundle && (
            <a className="secondary-button" href={session.downloads.bundle}>
              Download all files <span>↓</span>
            </a>
          )}
          {hasPackage ? (
            <a className="final-download-button" href={session.downloads!.package}>
              Download final PDF <span>↓</span>
            </a>
          ) : (
            <button className="final-download-button disabled" disabled>
              Final PDF unavailable
            </button>
          )}
        </div>
      </section>

      {!hasPackage && (
        <section className="fallback-banner">
          <span>HTML</span>
          <div>
            <strong>PDF rendering is unavailable, so HTML previews are active.</strong>
            <p>{session.packageError || "No supported PDF backend is currently available."}</p>
          </div>
        </section>
      )}

      <section className="package-sequence">
        <header>
          <div>
            <span className="eyebrow">Final package preview</span>
            <h2>{hasPackage ? "Validated six-page PDF" : "Six-page HTML proof"}</h2>
          </div>
          <span className="page-count">6 pages · A4 portrait</span>
        </header>
        {hasPackage ? (
          <iframe
            className="package-frame"
            src={session.previews.package}
            title="Final six-page package"
          />
        ) : (
          <div className="sequence-strip">
            {pages.map(([key, label], index) => (
              <a href={`#page-${index + 1}`} key={key}>
                <span>{index + 1}</span>
                <iframe src={session.previews![key]} title={`${label} thumbnail`} tabIndex={-1} />
                <strong>{label}</strong>
              </a>
            ))}
          </div>
        )}
      </section>

      <section className="page-previews">
        {pages.map(([key, label, description], index) => (
          <article className="page-preview-card" id={`page-${index + 1}`} key={key}>
            <header>
              <span className="page-number">{String(index + 1).padStart(2, "0")}</span>
              <div><h2>{label}</h2><p>{description}</p></div>
              <a href={session.previews![key]} target="_blank" rel="noreferrer">Open full size ↗</a>
            </header>
            <div className="preview-frame-wrap">
              <iframe src={session.previews![key]} title={`${label} preview`} />
            </div>
          </article>
        ))}
      </section>

      <footer className="preview-footer">
        <div>
          <strong>Finished reviewing?</strong>
          <span>
            {hasPackage
              ? "Download the validated PDF or the complete source bundle."
              : "Download the complete workbook and preview bundle."}
          </span>
        </div>
        {hasPackage ? (
          <a className="final-download-button" href={session.downloads!.package}>Download final PDF <span>↓</span></a>
        ) : session.downloads?.bundle ? (
          <a className="final-download-button" href={session.downloads.bundle}>Download all files <span>↓</span></a>
        ) : (
          <a className="secondary-button" href={`/review/${sessionId}`}>Return to review</a>
        )}
      </footer>
    </main>
  );
}
