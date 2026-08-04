import { randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { ensureSessionRoot, runExtraction, sessionRoot } from "@/lib/server";

export const runtime = "nodejs";
export const maxDuration = 600;

const extensions = new Set([".pdf", ".png", ".jpg", ".jpeg"]);
const maxBytes = 20 * 1024 * 1024;

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const upload = form.get("file");
    if (!(upload instanceof File)) {
      return NextResponse.json({ error: "Choose an invoice file." }, { status: 400 });
    }
    const extension = path.extname(upload.name).toLowerCase();
    if (!extensions.has(extension)) {
      return NextResponse.json(
        { error: "Only PDF, PNG, JPG, and JPEG files are supported." },
        { status: 415 },
      );
    }
    if (upload.size > maxBytes) {
      return NextResponse.json({ error: "The maximum upload size is 20 MB." }, { status: 413 });
    }
    await ensureSessionRoot();
    const sessionId = randomBytes(16).toString("hex");
    const directory = path.join(sessionRoot, sessionId);
    await mkdir(directory);
    const source = path.join(directory, `tax-invoice${extension}`);
    await writeFile(source, Buffer.from(await upload.arrayBuffer()), { flag: "wx" });
    const payload = await runExtraction({
      source,
      directory,
      original_name: upload.name,
    });
    return NextResponse.json(payload);
  } catch (reason) {
    const message =
      reason instanceof Error ? reason.message : "Extraction failed.";
    console.error("[Extraction API] POST /api/extract failed", {
      provider: process.env.OCR_PROVIDER || "paddle",
      message,
      error: reason,
    });
    return NextResponse.json(
      { error: message },
      { status: 500 },
    );
  }
}
