import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RMNTC Document Studio",
  description: "Review Korean tax invoices and generate customer documents.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <header className="site-header">
          <a className="brand" href="/" aria-label="RMNTC Document Studio home">
            <span className="brand-mark" aria-hidden="true">R</span>
            <span>
              <strong>RMNTC</strong>
              <small>Document Studio</small>
            </span>
          </a>
          <span className="header-status">
            <span className="status-dot" />
            Secure local processing
          </span>
        </header>
        {children}
      </body>
    </html>
  );
}
