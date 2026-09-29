// Typed HTTP boundary to the Python engine.
//
// Engineering-bar pillar 1: the web surface holds ONLY a scoped, short-lived token
// (issued by the server-side onboarding flow) — never a connector secret. Every engine
// call carries that token; the engine enforces per-tenant authz on its side.
//
// The engine base URL comes from a server-side env var. It is NOT NEXT_PUBLIC_*, so it
// is never bundled into client JS. All engine calls go through API routes (server-side),
// keeping the boundary first-party.

export const ENGINE_BASE_URL: string =
  process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:8000";

export interface TeaserFinding {
  id: string;
  headline: string;
  impact_usd: number;
  impact_hours: number;
  evidence: string[];
  confidence: number;
  method: string;
  team: string;
}

export interface ScopedSession {
  tenantId: string;
  token: string; // scoped, short-lived — safe for the web layer to hold
}

async function engineFetch<T>(
  path: string,
  session: ScopedSession,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${ENGINE_BASE_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      // scoped token, not a secret — engine verifies signature + tenant + scope
      authorization: `Bearer ${session.token}`,
      "x-tenant-id": session.tenantId,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`engine ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function getTeaser(session: ScopedSession): Promise<TeaserFinding> {
  return engineFetch<TeaserFinding>(
    `/teaser?tenant=${encodeURIComponent(session.tenantId)}`,
    session
  );
}

// ── SOW review surface (P4.T2) ────────────────────────────────────────────────
// The diagnostic run produces 2-3 scored SOW candidates rendered side-by-side.
// The web layer holds only the scoped token; the engine enforces per-tenant authz
// on the run_id <-> tenant binding. No dollar number is minted here — every value
// is read from the engine's side-by-side artifact, which carries source[] traces.

export interface SOWColumn {
  sow_id: string;
  title: string;
  objective: string;
  impact_usd: number;
  impact_hours: number;
  confidence: number;
  ebitda_uplift_pct: number;
  payback_months: number;
  wwod_score: number;
  wwod_confidence: number;
  grade: string;
  pillar_aggregate: number;
  blockers: string[];
  gaps: string[];
  key_gap: string;
  source: string[];
}

export interface SideBySidePayload {
  columns: SOWColumn[];
  recommended_sow_id: string | null;
  rows: { key: string; label: string }[];
}

export interface SelectionResult {
  run_id: string;
  selected_sow_id: string;
  status: "selected";
}

export async function getSideBySide(
  session: ScopedSession,
  runId: string
): Promise<SideBySidePayload> {
  return engineFetch<SideBySidePayload>(
    `/runs/${encodeURIComponent(runId)}/side-by-side?tenant=${encodeURIComponent(
      session.tenantId
    )}`,
    session
  );
}

export async function selectSOW(
  session: ScopedSession,
  runId: string,
  sowId: string
): Promise<SelectionResult> {
  return engineFetch<SelectionResult>(
    `/runs/${encodeURIComponent(runId)}/select`,
    session,
    { method: "POST", body: JSON.stringify({ sow_id: sowId }) }
  );
}
