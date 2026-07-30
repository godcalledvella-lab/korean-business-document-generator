import UploadPanel from "@/components/UploadPanel";

export default function Home() {
  return (
    <main className="landing-shell">
      <section className="hero">
        <span className="eyebrow">Korean business documents, simplified</span>
        <h1>From tax invoice<br />to a complete package.</h1>
        <p>
          Upload one Korean electronic tax invoice. Review every extracted
          detail before generating your RMNTC documents.
        </p>
      </section>
      <UploadPanel />
      <section className="privacy-note">
        <ShieldIcon />
        <div>
          <strong>Your document stays in your environment.</strong>
          <span>Files are processed by your configured local OCR provider.</span>
        </div>
      </section>
    </main>
  );
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3 5 6v5c0 4.6 2.9 8.2 7 10 4.1-1.8 7-5.4 7-10V6l-7-3Z" />
      <path d="m9 12 2 2 4-5" />
    </svg>
  );
}
