import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { existingFile, readSession, sessionRoot, validSession } from "@/lib/server";

export const runtime = "nodejs";

const allowed: Record<string, { name: string; type: string }> = {
  "tax-invoice": { name: "tax-invoice", type: "application/octet-stream" },
  statement: { name: "statement.xlsx", type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  quotation: { name: "quotation.xlsx", type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  comparison: { name: "comparison.xlsx", type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  package: { name: "final_package.pdf", type: "application/pdf" },
  bundle: { name: "documents.zip", type: "application/zip" },
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ sessionId: string; file: string }> },
) {
  const { sessionId, file } = await context.params;
  const descriptor = allowed[file];
  if (!validSession(sessionId) || !descriptor) {
    return NextResponse.json({ error: "Download not found." }, { status: 404 });
  }
  const directory = path.join(sessionRoot, sessionId);
  const session = await readSession(sessionId);
  let configuredName = descriptor.name;
  let source: string;
  if (file === "tax-invoice") {
    const matches = [".pdf", ".png", ".jpg", ".jpeg"]
      .map((extension) => path.join(directory, `tax-invoice${extension}`));
    source = (await Promise.all(matches.map(async (candidate) => (
      (await existingFile(candidate)) ? candidate : ""
    )))).find(Boolean) || "";
  } else if (file === "package") {
    source = path.join(directory, "generated", "final_package.pdf");
  } else if (file === "bundle") {
    const bundleName = typeof session?.bundleName === "string"
      ? session.bundleName
      : descriptor.name;
    source = path.join(directory, "generated", bundleName);
    configuredName = bundleName;
  } else {
    source = path.join(directory, "generated", `${file}.xlsx`);
  }
  if (!source || !(await existingFile(source))) {
    return NextResponse.json({ error: "Download is not available." }, { status: 404 });
  }
  const extension = path.extname(source);
  const invoiceNumber = String(
    session?.draft?.document?.invoice_number || "invoice",
  ).replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "invoice";
  const downloadBase = invoiceNumber.toUpperCase().startsWith("RMNTC-")
    ? invoiceNumber
    : `RMNTC-${invoiceNumber}`;
  const names: Record<string, string> = {
    statement: `${downloadBase}-statement.xlsx`,
    quotation: `${downloadBase}-quotation.xlsx`,
    comparison: `${downloadBase}-comparison-quotation.xlsx`,
    package: `${downloadBase}-final-package.pdf`,
  };
  const downloadName = file === "tax-invoice"
    ? `${downloadBase}-tax-invoice${extension}`
    : names[file] || configuredName;
  return new NextResponse(await readFile(source), {
    headers: {
      "Content-Type": descriptor.type === "application/octet-stream"
        ? (extension === ".pdf" ? "application/pdf" : `image/${extension.slice(1).replace("jpg", "jpeg")}`)
        : descriptor.type,
      "Content-Disposition": `attachment; filename="${downloadName}"`,
      "Cache-Control": "private, no-store",
    },
  });
}
