import { NextResponse } from "next/server";
import { getTeaser, type ScopedSession, type TeaserFinding } from "@/lib/engine";

// Server-side API route — the first-party backend boundary.
//
// In production this issues/loads the tenant's scoped token (from the server-side
// onboarding flow) and calls the Python engine over HTTP. The browser never sees the
// engine URL or any secret. For the P1 slice, if the engine HTTP service is not
// reachable, we degrade to a clearly-labeled placeholder so the page still renders —
// never a silent failure.

export const runtime = "nodejs";

const DEMO_TENANT = process.env.DEMO_TENANT_ID ?? "synth-acme-services";

export async function POST(): Promise<NextResponse> {
  // The scoped token would come from the onboarding session cookie/store. For the
  // scaffold we synthesize a session object; the real token is minted server-side.
  const session: ScopedSession = {
    tenantId: DEMO_TENANT,
    token: process.env.DEMO_SCOPED_TOKEN ?? "",
  };

  try {
    const finding: TeaserFinding = await getTeaser(session);
    return NextResponse.json(finding);
  } catch {
    // Engine not reachable in this slice — return a labeled placeholder, not a 500,
    // so the onboarding UX is verifiable end-to-end at scaffold stage.
    const placeholder: TeaserFinding = {
      id: "teaser-pending",
      headline: "Connected. Full diagnostic running — first quantified finding shortly.",
      impact_usd: 0,
      impact_hours: 0,
      evidence: ["engine HTTP boundary not wired in this slice"],
      confidence: 0.5,
      method: "scaffold_placeholder",
      team: "teaser",
    };
    return NextResponse.json(placeholder);
  }
}
