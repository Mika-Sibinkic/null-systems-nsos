// Typed HTTP boundary to the Python engine (engine/api, FastAPI).
//
// Engineering-bar pillar 1: the web surface holds ONLY a scoped, short-lived token
// (issued by the server-side onboarding flow) — never a connector secret. Every engine
// call carries that token; the engine enforces per-tenant authz on its side.
//
// The engine base URL comes from a server-side env var. It is NOT NEXT_PUBLIC_*, so it
// is never bundled into client JS. All engine calls go through API routes (server-side).

export const ENGINE_URL: string = process.env.ENGINE_URL ?? "http://localhost:8000";
export const ENGINE_TIMEOUT_MS: number = Number(process.env.ENGINE_TIMEOUT_MS ?? 5000);

/** The engine could not be reached at all (connection refused, DNS, timeout). */
export class EngineUnreachableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EngineUnreachableError";
  }
}

/** The engine answered, but with a non-2xx status and a JSON {error} body. */
export class EngineResponseError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
    message: string
  ) {
    super(message);
    this.name = "EngineResponseError";
  }
}

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
  let res: Response;
  try {
    res = await fetch(`${ENGINE_URL}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        // scoped token, not a secret — engine verifies signature + tenant + scope
        authorization: `Bearer ${session.token}`,
        "x-tenant-id": session.tenantId,
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(ENGINE_TIMEOUT_MS),
    });
  } catch (e) {
    const reason = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    throw new EngineUnreachableError(`${ENGINE_URL}${path} (${reason})`);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body?.error) detail = `${detail}: ${body.error}`;
    } catch {
      // non-JSON error body; keep the status-only detail
    }
    throw new EngineResponseError(res.status, path, `engine ${path} -> ${detail}`);
  }
  return (await res.json()) as T;
}

export interface DevScopedToken {
  token: string;
  tenant_id: string;
  scopes: string[];
  expires_in: number;
}

/**
 * Dev-only: ask the engine to mint a read-scoped token for a tenant. The engine only
 * serves this while it runs on its dev signing secret (VINNY_TOKEN_SECRET unset); with
 * a production secret configured it returns 404 and the web layer must be given a
 * token minted by the onboarding flow (DEMO_SCOPED_TOKEN for the scaffold).
 */
export async function getDevScopedToken(tenantId: string): Promise<DevScopedToken> {
  return engineFetch<DevScopedToken>(
    "/dev/scoped-token",
    { tenantId, token: "" },
    { method: "POST", body: JSON.stringify({ tenant_id: tenantId }) }
  );
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
