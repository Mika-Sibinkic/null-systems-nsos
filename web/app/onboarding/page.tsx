"use client";

import { useState } from "react";
import type { TeaserFinding } from "@/lib/engine";

// Onboarding surface. The OAuth connect handshake (not simulated here) sends the
// connector secret to the SERVER-SIDE flow; the browser only ever receives a scoped,
// short-lived token. This page calls our own /api/teaser route (server-side), which
// holds that token and talks to the engine — the browser never touches the engine or
// any secret directly.

interface TeaserState {
  status: "idle" | "connecting" | "ready" | "error";
  finding?: TeaserFinding;
  error?: string;
}

const SOURCES = [
  { id: "quickbooks", label: "QuickBooks", kind: "Accounting" },
  { id: "hubspot", label: "HubSpot", kind: "CRM" },
  { id: "slack", label: "Slack", kind: "Comms" },
];

export default function OnboardingPage() {
  const [state, setState] = useState<TeaserState>({ status: "idle" });

  async function connect() {
    setState({ status: "connecting" });
    try {
      const res = await fetch("/api/teaser", { method: "POST" });
      if (!res.ok) throw new Error(`teaser ${res.status}`);
      const finding = (await res.json()) as TeaserFinding;
      setState({ status: "ready", finding });
    } catch (e) {
      setState({ status: "error", error: e instanceof Error ? e.message : "failed" });
    }
  }

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "64px 24px" }}>
      <h1 style={{ fontSize: 32, marginBottom: 8 }}>Connect your stack</h1>
      <p style={{ color: "#9aa3ab", marginBottom: 32 }}>
        Read-only. Your credentials stay server-side — this browser only holds a
        short-lived access token.
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
              <div style={{ fontSize: 13, color: "#6b7480" }}>{s.kind}</div>
            </div>
            <span style={{ fontSize: 13, color: "#6b7480" }}>read-only</span>
          </div>
        ))}
      </div>

      <button
        onClick={connect}
        disabled={state.status === "connecting"}
        style={{
          background: "#3b82f6",
          color: "white",
          border: "none",
          padding: "12px 24px",
          borderRadius: 8,
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        {state.status === "connecting" ? "Reading your data…" : "Connect & get first finding"}
      </button>

      {state.status === "ready" && state.finding ? (
        <section
          style={{
            marginTop: 32,
            border: "1px solid #1f3a2a",
            background: "#0f1a13",
            borderRadius: 12,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 13, color: "#4ade80", marginBottom: 8 }}>
            First finding (full diagnostic still running)
          </div>
          <h2 style={{ fontSize: 22, margin: "0 0 12px" }}>{state.finding.headline}</h2>
          <div style={{ fontSize: 28, fontWeight: 700, color: "#4ade80" }}>
            ${state.finding.impact_usd.toLocaleString()}/yr
          </div>
          <ul style={{ color: "#9aa3ab", fontSize: 14, marginTop: 16 }}>
            {state.finding.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
          <div style={{ fontSize: 12, color: "#6b7480", marginTop: 12 }}>
            confidence {Math.round(state.finding.confidence * 100)}%
          </div>
        </section>
      ) : null}

      {state.status === "error" ? (
        <p style={{ color: "#f87171", marginTop: 24 }}>Could not connect: {state.error}</p>
      ) : null}
    </main>
  );
}
