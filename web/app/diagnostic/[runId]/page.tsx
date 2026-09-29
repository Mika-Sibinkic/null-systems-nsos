"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { SideBySidePayload, SOWColumn } from "@/lib/engine";

// SOW review + choose surface (P4.T2).
//
// The operator compares the 2-3 scored SOW candidates side-by-side and selects one.
// This page calls our own /api/runs/[runId]/* routes (server-side); the browser never
// holds a connector secret or the engine URL. Every number shown is read from the
// engine's source-traced side-by-side artifact — none is computed in the browser.

type LoadState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: SideBySidePayload };

type SelectState =
  | { status: "idle" }
  | { status: "selecting"; sowId: string }
  | { status: "selected"; sowId: string }
  | { status: "error"; error: string };

const fmtUsd = (n: number) => `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}/yr`;
const fmtPct = (n: number) => `${(n * 100).toFixed(0)}%`;
const fmtPayback = (n: number) =>
  !isFinite(n) || n <= 0 ? "—" : `${n.toFixed(0)} mo`;

export default function DiagnosticReviewPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [sel, setSel] = useState<SelectState>({ status: "idle" });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(runId)}/side-by-side`,
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error(`side-by-side ${res.status}`);
        const data = (await res.json()) as SideBySidePayload;
        if (alive) setLoad({ status: "ready", data });
      } catch (e) {
        if (alive)
          setLoad({
            status: "error",
            error: e instanceof Error ? e.message : "failed",
          });
      }
    })();
    return () => {
      alive = false;
    };
  }, [runId]);

  async function choose(sowId: string) {
    setSel({ status: "selecting", sowId });
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/select`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sow_id: sowId }),
      });
      if (!res.ok) throw new Error(`select ${res.status}`);
      setSel({ status: "selected", sowId });
    } catch (e) {
      setSel({ status: "error", error: e instanceof Error ? e.message : "failed" });
    }
  }

  if (load.status === "loading") {
    return <Shell>Loading your growth options…</Shell>;
  }
  if (load.status === "error") {
    return (
      <Shell>
        <p style={{ color: "#f87171" }}>
          Could not load run <code>{runId}</code>: {load.error}
        </p>
      </Shell>
    );
  }

  const { columns, recommended_sow_id } = load.data;

  return (
    <Shell wide>
      <h1 style={{ fontSize: 34, lineHeight: 1.1, marginBottom: 8 }}>
        Your growth options
      </h1>
      <p style={{ color: "#9aa3ab", marginBottom: 32 }}>
        {columns.length} Statements of Work, scored against your own data. Pick the
        direction you want the business to go.
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${columns.length}, minmax(260px, 1fr))`,
          gap: 16,
        }}
      >
        {columns.map((c) => (
          <SOWCard
            key={c.sow_id}
            col={c}
            recommended={c.sow_id === recommended_sow_id}
            selectedId={sel.status === "selected" ? sel.sowId : undefined}
            selectingId={sel.status === "selecting" ? sel.sowId : undefined}
            onChoose={() => choose(c.sow_id)}
          />
        ))}
      </div>

      {sel.status === "selected" && (
        <p style={{ marginTop: 24, color: "#34d399" }}>
          Selected. The chosen SOW exports as an FDE handoff packet.
        </p>
      )}
      {sel.status === "error" && (
        <p style={{ marginTop: 24, color: "#f87171" }}>
          Selection failed: {sel.error}
        </p>
      )}
    </Shell>
  );
}

function SOWCard({
  col,
  recommended,
  selectedId,
  selectingId,
  onChoose,
}: {
  col: SOWColumn;
  recommended: boolean;
  selectedId?: string;
  selectingId?: string;
  onChoose: () => void;
}) {
  const isSelected = selectedId === col.sow_id;
  const isSelecting = selectingId === col.sow_id;
  return (
    <section
      style={{
        border: `1px solid ${recommended ? "#3b82f6" : "#23272d"}`,
        borderRadius: 12,
        padding: 20,
        background: "#101317",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {recommended && (
        <span
          style={{
            alignSelf: "flex-start",
            fontSize: 12,
            fontWeight: 700,
            color: "#3b82f6",
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Our recommendation
        </span>
      )}
      <h2 style={{ fontSize: 20, margin: 0 }}>{col.title}</h2>
      <p style={{ color: "#9aa3ab", fontSize: 14, margin: 0 }}>{col.objective}</p>

      <dl style={{ margin: "12px 0 0", display: "grid", gap: 6 }}>
        <Metric label="Annual impact" value={fmtUsd(col.impact_usd)} strong />
        <Metric label="EBITDA lift" value={`+${col.ebitda_uplift_pct.toFixed(0)}%`} />
        <Metric label="Payback" value={fmtPayback(col.payback_months)} />
        {col.impact_hours > 0 && (
          <Metric label="Hours freed / yr" value={`${col.impact_hours.toFixed(0)}`} />
        )}
        <Metric label="Consultant conviction" value={fmtPct(col.wwod_score)} />
        <Metric
          label="Deployability"
          value={`${col.grade}${col.blockers.length ? " ⚠" : ""}`}
        />
        <Metric label="Evidence confidence" value={fmtPct(col.confidence)} />
      </dl>

      {col.key_gap && (
        <p style={{ color: "#fbbf24", fontSize: 13, marginTop: 8 }}>
          Confirm first: {col.key_gap}
        </p>
      )}

      <button
        onClick={onChoose}
        disabled={isSelecting || isSelected}
        style={{
          marginTop: "auto",
          background: isSelected ? "#34d399" : "#3b82f6",
          color: "white",
          border: "none",
          padding: "10px 16px",
          borderRadius: 8,
          fontWeight: 600,
          cursor: isSelecting || isSelected ? "default" : "pointer",
          opacity: isSelecting ? 0.7 : 1,
        }}
      >
        {isSelected
          ? "Selected ✓"
          : isSelecting
          ? "Selecting…"
          : "Choose this option"}
      </button>
    </section>
  );
}

function Metric({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
      <dt style={{ color: "#9aa3ab" }}>{label}</dt>
      <dd style={{ margin: 0, fontWeight: strong ? 700 : 500 }}>{value}</dd>
    </div>
  );
}

function Shell({
  children,
  wide,
}: {
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <main
      style={{
        maxWidth: wide ? 1040 : 720,
        margin: "0 auto",
        padding: "64px 24px",
      }}
    >
      {children}
    </main>
  );
}
