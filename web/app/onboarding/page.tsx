"use client";

import { useState } from "react";
import type { TeaserFinding } from "@/lib/engine";

// Onboarding demo. Nothing connects yet: the engine reads a committed synthetic
// QuickBooks export. This page calls our own /api/teaser route (server-side), which
// holds a scoped, short-lived token and talks to the engine. The browser never
// touches the engine or any secret directly.

interface TeaserState {
  status: "idle" | "connecting" | "ready" | "error";
  finding?: TeaserFinding;
  error?: string;
}

const SOURCES = [
  { id: "quickbooks", label: "QuickBooks", kind: "Accounting", note: "synthetic export" },
  { id: "hubspot", label: "HubSpot", kind: "CRM", note: "not connected in this demo" },
  { id: "slack", label: "Slack", kind: "Comms", note: "not connected in this demo" },
];

const MUTED = "#9aa3ab";

export default function OnboardingPage() {
  const [state, setState] = useState<TeaserState>({ status: "idle" });
  const busy = state.status === "connecting";

  async function connect() {
    if (busy) return; // aria-disabled, not disabled, so focus stays on the button
    setState({ status: "connecting" });
    try {
      const res = await fetch("/api/teaser", { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `the server answered ${res.status}`);
      }
      const finding = (await res.json()) as TeaserFinding;
      setState({ status: "ready", finding });
    } catch (e) {
      setState({ status: "error", error: e instanceof Error ? e.message : String(e) });
    }
  }

  const f = state.status === "ready" ? state.finding : undefined;
  const unreachable = f?.method === "engine_unreachable";

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "64px 24px" }}>
      <h1 style={{ fontSize: 32, marginBottom: 8 }}>Sample diagnostic</h1>
      <p style={{ color: MUTED, marginBottom: 32 }}>
        This demo reads a synthetic QuickBooks export, not your books. The engine
        reads it server-side; this browser only holds a short-lived access token.
      </p>

      <div style={{ display: "grid", gap: 12, marginBottom: 32 }}>
        {SOURCES.map((s) => (
          <div
            key={s.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              border: "1px solid #1f2630",
              borderRadius: 10,
              padding: "16px 20px",
            }}
          >
            <div>
              <div style={{ fontWeight: 600 }}>{s.label}</div>
              <div style={{ fontSize: 13, color: MUTED }}>{s.kind}</div>
            </div>
            <span style={{ fontSize: 13, color: MUTED }}>{s.note}</span>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={connect}
        aria-disabled={busy}
        style={{
          font: "inherit",
          background: "#2563eb",
          color: "white",
          border: "none",
          padding: "12px 24px",
          borderRadius: 8,
          fontWeight: 600,
          cursor: busy ? "progress" : "pointer",
        }}
      >
        {busy ? "Reading the export…" : "Read the sample export"}
      </button>

      <div role="status" style={{ marginTop: 32 }}>
        {f && unreachable ? (
          <section
            style={{
              border: "1px solid #5c4813",
              background: "#1a1508",
              borderRadius: 12,
              padding: 24,
            }}
          >
            <div style={{ fontSize: 13, color: "#fbbf24", marginBottom: 8 }}>
              Engine unreachable
            </div>
            <h2 style={{ fontSize: 22, margin: "0 0 12px" }}>No finding could be read.</h2>
            <p style={{ color: MUTED, fontSize: 14, margin: 0 }}>{f.evidence[0]}</p>
          </section>
        ) : f ? (
          <section
            style={{
              border: "1px solid #1f3a2a",
              background: "#0f1a13",
              borderRadius: 12,
              padding: 24,
            }}
          >
            <div style={{ fontSize: 13, color: "#4ade80", marginBottom: 8 }}>
              Sample finding from the synthetic export
            </div>
            <h2 style={{ fontSize: 22, margin: "0 0 12px" }}>{f.headline}</h2>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#4ade80" }}>
              ${f.impact_usd.toLocaleString("en-US")}/yr
            </div>
            <ul style={{ color: MUTED, fontSize: 14, marginTop: 16 }}>
              {f.evidence.map((e, i) => (
                <li key={i}>{e.endsWith(" [LIKELY]") ? `Assumes: ${e.slice(0, -9)}` : e}</li>
              ))}
            </ul>
            <div style={{ fontSize: 12, color: MUTED, marginTop: 12 }}>
              confidence {Math.round(f.confidence * 100)}%
            </div>
          </section>
        ) : null}
      </div>

      {state.status === "error" ? (
        <p role="alert" style={{ color: "#f87171", marginTop: 24 }}>
          Could not get a finding: {state.error}.
        </p>
      ) : null}
    </main>
  );
}
