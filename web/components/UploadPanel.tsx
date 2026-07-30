"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const ACCEPTED = [".pdf", ".png", ".jpg", ".jpeg"];
const MAX_BYTES = 20 * 1024 * 1024;

export default function UploadPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<"idle" | "upload" | "ocr" | "draft">("idle");
  const [error, setError] = useState("");

  const choose = useCallback((candidate?: File) => {
    if (!candidate) return;
    const extension = `.${candidate.name.split(".").pop()?.toLowerCase()}`;
    if (!ACCEPTED.includes(extension)) {
      setError("Choose a PDF, PNG, JPG, or JPEG file.");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setError("The maximum upload size is 20 MB.");
      return;
    }
    setError("");
    setFile(candidate);
  }, []);

  async function upload() {
    if (!file) return;
    const progressTimers: number[] = [];
    let responseStatus: number | undefined;
    let responseStatusText: string | undefined;

    setError("");
    setStage("upload");
    const data = new FormData();
    data.append("file", file);
    try {
      const pending = fetch("/api/extract", { method: "POST", body: data });
      progressTimers.push(window.setTimeout(() => setStage("ocr"), 500));
      progressTimers.push(window.setTimeout(() => setStage("draft"), 1400));
      const response = await pending;
      responseStatus = response.status;
      responseStatusText = response.statusText;

      const responseText = await response.text();
      let payload: { error?: unknown; sessionId?: unknown } = {};
      try {
        payload = responseText ? JSON.parse(responseText) : {};
      } catch {
        // A non-JSON response may still contain a useful backend error message.
      }

      if (!response.ok) {
        const backendMessage =
          typeof payload.error === "string" ? payload.error : responseText.trim();
        throw new Error(
          backendMessage ||
            `Extraction failed (${response.status} ${response.statusText}).`,
        );
      }
      if (typeof payload.sessionId !== "string") {
        throw new Error("Extraction succeeded without a review session.");
      }
      router.push(`/review/${payload.sessionId}`);
    } catch (reason) {
      const message =
        reason instanceof Error ? reason.message : "Extraction failed.";
      console.error("[Extraction] POST /api/extract failed", {
        status: responseStatus,
        statusText: responseStatusText,
        message,
      });
      setStage("idle");
      setError(message);
    } finally {
      progressTimers.forEach((timer) => window.clearTimeout(timer));
    }
  }

  if (stage !== "idle") {
    const steps = [
      ["upload", "Uploading securely"],
      ["ocr", "Reading invoice with OCR"],
      ["draft", "Preparing review draft"],
    ] as const;
    const active = steps.findIndex(([key]) => key === stage);
    return (
      <section className="upload-card progress-card" aria-live="polite">
        <div className="loader-orbit"><span /></div>
        <h2>Preparing your invoice</h2>
        <p>{file?.name}</p>
        <div className="progress-steps">
          {steps.map(([key, label], index) => (
            <div className={index <= active ? "progress-step active" : "progress-step"} key={key}>
              <span>{index < active ? "✓" : index + 1}</span>
              {label}
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="upload-card">
      <div
        className={dragging ? "dropzone dragging" : "dropzone"}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (event.currentTarget === event.target) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files[0]);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          hidden
          onChange={(event) => choose(event.target.files?.[0])}
        />
        <span className="upload-icon"><UploadIcon /></span>
        {file ? (
          <>
            <h2>{file.name}</h2>
            <p>{formatBytes(file.size)} · Ready to upload</p>
          </>
        ) : (
          <>
            <h2>Drop your tax invoice here</h2>
            <p>or click to choose a file</p>
          </>
        )}
        <span className="file-types">PDF · PNG · JPG · JPEG &nbsp; up to 20 MB</span>
      </div>
      {error && (
        <div className="upload-error" role="alert">
          <p className="form-error">{error}</p>
          <button className="retry-button" type="button" onClick={upload}>
            Retry
          </button>
        </div>
      )}
      {!error && (
        <button className="primary-button" disabled={!file} onClick={upload}>
          Continue to review
          <ArrowIcon />
        </button>
      )}
    </section>
  );
}

function formatBytes(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.ceil(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function UploadIcon() {
  return <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0L7 9m5-5 5 5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>;
}

function ArrowIcon() {
  return <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6" /></svg>;
}
