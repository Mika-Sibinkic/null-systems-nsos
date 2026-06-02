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
