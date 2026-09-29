import { NextResponse } from "next/server";
import {
  ENGINE_URL,
  EngineResponseError,
  EngineUnreachableError,
  getDevScopedToken,
  getTeaser,
  type ScopedSession,
  type TeaserFinding,
} from "@/lib/engine";

// Server-side API route — the first-party backend boundary.
//
// Calls the Python engine (engine/api) over HTTP with a scoped token. The browser
// never sees the engine URL or any secret. Three outcomes:
//   - engine answered 2xx        -> the engine's finding, untouched
//   - engine answered non-2xx    -> 502 with the engine's JSON error (no fallback)
//   - engine unreachable/timeout -> a finding labeled "engine unreachable", never a
//                                   silent failure and never a fabricated number

export const runtime = "nodejs";

const DEMO_TENANT = process.env.DEMO_TENANT_ID ?? "synth-acme-services";

function engineUnreachableFallback(e: EngineUnreachableError): TeaserFinding {
  return {
    id: "teaser-engine-unreachable",
    headline: "Engine unreachable. No finding could be read.",
    impact_usd: 0,
    impact_hours: 0,
    evidence: [`engine unreachable at ${ENGINE_URL}: ${e.message}`],
    confidence: 0,
    method: "engine_unreachable",
    team: "teaser",
  };
}

export async function POST(): Promise<NextResponse> {
  // The scoped token comes from the onboarding session (DEMO_SCOPED_TOKEN for the
  // scaffold). Without one, ask the engine's dev-only minting endpoint; that endpoint
  // exists only while the engine runs on its dev signing secret.
  const session: ScopedSession = {
    tenantId: DEMO_TENANT,
    token: process.env.DEMO_SCOPED_TOKEN ?? "",
  };

  try {
    if (!session.token) {
      session.token = (await getDevScopedToken(DEMO_TENANT)).token;
    }
    const finding: TeaserFinding = await getTeaser(session);
    return NextResponse.json(finding);
  } catch (e) {
    if (e instanceof EngineUnreachableError) {
      return NextResponse.json(engineUnreachableFallback(e));
    }
    if (e instanceof EngineResponseError) {
      return NextResponse.json(
        { error: e.message, engine_status: e.status },
        { status: 502 }
      );
    }
    throw e;
  }
}
