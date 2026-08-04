import { NextResponse } from "next/server";
import { readSession, validSession, writeSession } from "@/lib/server";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  const session = await readSession(sessionId);
  if (!session) {
    return NextResponse.json({ error: "Review session not found." }, { status: 404 });
  }
  return NextResponse.json(session);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  if (!validSession(sessionId)) {
    return NextResponse.json({ error: "Review session not found." }, { status: 404 });
  }
  const session = await readSession(sessionId);
  if (!session) {
    return NextResponse.json({ error: "Review session not found." }, { status: 404 });
  }
  const body = await request.json();
  const percentage = body.comparisonMarkupPercentage;
  if (percentage !== undefined) {
    if (
      typeof percentage !== "number" ||
      !Number.isFinite(percentage) ||
      percentage < 0 ||
      percentage > 100
    ) {
      return NextResponse.json(
        { error: "Comparison markup percentage must be between 0 and 100." },
        { status: 422 },
      );
    }
    session.comparisonMarkupPercentage = percentage;
  }
  if (body.reviewSettings !== undefined) {
    if (
      body.reviewSettings === null ||
      typeof body.reviewSettings !== "object" ||
      Array.isArray(body.reviewSettings)
    ) {
      return NextResponse.json(
        { error: "Review document settings must be an object." },
        { status: 422 },
      );
    }
    session.reviewSettings = body.reviewSettings;
  }
  await writeSession(sessionId, session);
  return NextResponse.json({
    comparisonMarkupPercentage: session.comparisonMarkupPercentage,
    reviewSettings: session.reviewSettings,
  });
}
