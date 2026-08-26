import path from "node:path";
import { NextResponse } from "next/server";
import { readSession, runPython, sessionRoot, validSession } from "@/lib/server";

export const runtime = "nodejs";
export const maxDuration = 900;

export async function POST(request: Request) {
  try {
    const body = await request.json();
    if (!validSession(body.sessionId) || !(await readSession(body.sessionId))) {
      return NextResponse.json({ error: "Review session not found." }, { status: 404 });
    }
    if (!body.draft || typeof body.draft !== "object") {
      return NextResponse.json({ error: "Reviewed invoice JSON is required." }, { status: 400 });
    }
    const result = await runPython("generate_documents_verified.py", [
      path.join(sessionRoot, body.sessionId),
      JSON.stringify(body.draft),
    ]);
    return NextResponse.json(result);
  } catch (reason) {
    const message =
      reason instanceof Error ? reason.message : "Generation failed.";
    console.error("[Generation API] POST /api/generate failed", {
      message,
      error: reason,
    });
    return NextResponse.json(
      { error: message },
      { status: 422 },
    );
  }
}
