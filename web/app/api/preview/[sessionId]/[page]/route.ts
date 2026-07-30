import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { existingFile, sessionRoot, validSession } from "@/lib/server";

export const runtime = "nodejs";

const generatedPages: Record<string, Array<{ file: string; type: string }>> = {
  statement: [
    { file: "page-2-statement.pdf", type: "application/pdf" },
    { file: "statement.html", type: "text/html; charset=utf-8" },
  ],
  quotation: [
    { file: "page-3-quotation.pdf", type: "application/pdf" },
    { file: "quotation.html", type: "text/html; charset=utf-8" },
  ],
  comparison: [
    { file: "page-4-comparison.pdf", type: "application/pdf" },
    { file: "comparison.html", type: "text/html; charset=utf-8" },
  ],
  "business-registration": [
    { file: "business_registration.pdf", type: "application/pdf" },
  ],
  "bank-account": [{ file: "bank_account.pdf", type: "application/pdf" }],
  package: [{ file: "final_package.pdf", type: "application/pdf" }],
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ sessionId: string; page: string }> },
) {
  const { sessionId, page } = await context.params;
  if (!validSession(sessionId)) {
    return NextResponse.json({ error: "Preview not found." }, { status: 404 });
  }
  const directory = path.join(sessionRoot, sessionId);
  let source = "";
  let type = "";
  if (page === "tax-invoice") {
    for (const extension of [".pdf", ".png", ".jpg", ".jpeg"]) {
      const candidate = path.join(directory, `tax-invoice${extension}`);
      if (await existingFile(candidate)) {
        source = candidate;
        type = extension === ".pdf"
          ? "application/pdf"
          : `image/${extension.slice(1).replace("jpg", "jpeg")}`;
        break;
      }
    }
  } else {
    const descriptors = generatedPages[page] || [];
    for (const descriptor of descriptors) {
      const candidate = path.join(directory, "generated", descriptor.file);
      if (await existingFile(candidate)) {
        source = candidate;
        type = descriptor.type;
        break;
      }
    }
  }
  if (!source || !(await existingFile(source))) {
    return NextResponse.json({ error: "Preview is not available." }, { status: 404 });
  }
  return new NextResponse(await readFile(source), {
    headers: {
      "Content-Type": type,
      "Content-Disposition": "inline",
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
