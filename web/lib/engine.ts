// Typed HTTP boundary to the Python engine (engine/api, FastAPI).
//
// Security rule enforced here: the web surface holds ONLY a scoped, short-lived token
// (issued by the server-side onboarding flow) — never a connector secret. Every engine
// call carries that token; the engine enforces per-tenant authz on its side.
//
// The engine base URL comes from a server-side env var. It is NOT NEXT_PUBLIC_*, so it
// is never bundled into client JS. All engine calls go through API routes (server-side).

// 127.0.0.1, not localhost: Node 17+ resolves localhost to ::1 first, and the engine
// (uvicorn) listens on IPv4 only, so "localhost" read as engine_unreachable on Node 18.
export const ENGINE_URL: string = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";
export const ENGINE_TIMEOUT_MS: number = parseTimeoutMs(process.env.ENGINE_TIMEOUT_MS);

/** Fail at startup on a bad timeout; Number("5s") is NaN and would abort every call. */
export function parseTimeoutMs(raw: string | undefined): number {
  if (raw === undefined) return 5000;
  if (!/^[1-9]\d*$/.test(raw)) {
    throw new Error("ENGINE_TIMEOUT_MS must be a positive integer (ms)");
  }
  return Number(raw);
}

/** The engine could not be reached at all (connection refused, DNS, timeout). */
export class EngineUnreachableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EngineUnreachableError";
  }
}

/** The engine answered, but with a non-2xx status and a JSON {error} body. */
export class EngineResponseError extends Error {
  readonly status: number;
  readonly path: string;
  constructor(status: number, path: string, message: string) {
    super(message);
    this.name = "EngineResponseError";
    this.status = status;
    this.path = path;
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
