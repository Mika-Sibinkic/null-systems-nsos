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
  | { status: "not_built" }
  | { status: "error"; error: string }
  | { status: "ready"; data: SideBySidePayload };

type SelectState =
  | { status: "idle" }
  | { status: "selecting"; sowId: string }
  | { status: "selected"; sowId: string }
  | { status: "error"; error: string };

const usd = (n: number) => `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const fmtPct = (n: number) => `${(n * 100).toFixed(0)}%`;
const fmtPayback = (n: number | null) =>
  n === null ? "—" : n < 1 ? "<1 mo" : `${n.toFixed(0)} mo`;
const fmtEbitda = (n: number | null) => (n === null ? "— (base not positive)" : `+${n.toFixed(0)}%`);
const fmtGrade = (grade: string, blockers: number) =>
  blockers ? `${grade} · ${blockers} ${blockers === 1 ? "blocker" : "blockers"}` : grade;

const PRIMARY = "#2563eb";
const MUTED = "#9aa3ab";

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
        if (res.status === 404) {
          if (alive) setLoad({ status: "not_built" });
          return;
        }
        if (!res.ok) throw new Error(`the server answered ${res.status}`);
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
    if (sel.status === "selecting" || (sel.status === "selected" && sel.sowId === sowId)) return;
    setSel({ status: "selecting", sowId });
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/select`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sow_id: sowId }),
      });
      if (!res.ok) throw new Error(`the server answered ${res.status}`);
      setSel({ status: "selected", sowId });
    } catch (e) {
      setSel({ status: "error", error: e instanceof Error ? e.message : "failed" });
    }
  }

  const columns = load.status === "ready" ? load.data.columns : [];

  return (
    <Shell wide>
      <h1 style={{ fontSize: 34, lineHeight: 1.1, marginBottom: 8 }}>
        Your growth options
      </h1>

      {load.status === "loading" && <p style={{ color: MUTED }}>Loading your growth options…</p>}
      {load.status === "not_built" && (
        <p style={{ color: MUTED }}>
          Run review is not available yet (see README: What is not built).
        </p>
      )}
      {load.status === "error" && (
        <p role="alert" style={{ color: "#f87171" }}>
          Could not load run <code>{runId}</code>: {load.error}.
        </p>
      )}

      {load.status === "ready" && (
        <>
          <p style={{ color: MUTED, marginBottom: 32 }}>
            {columns.length} Statements of Work, scored against your own data. Pick the
            direction you want the business to go.
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 16,
            }}
          >
            {columns.map((c) => (
              <SOWCard
                key={c.sow_id}
                col={c}
                recommended={c.sow_id === load.data.recommended_sow_id}
                selectedId={sel.status === "selected" ? sel.sowId : undefined}
                selectingId={sel.status === "selecting" ? sel.sowId : undefined}
                onChoose={() => choose(c.sow_id)}
              />
            ))}
          </div>
        </>
      )}

      <div role="status" style={{ marginTop: 24 }}>
        {sel.status === "selected" && (
          <p style={{ color: "#34d399" }}>
            Selected. The chosen SOW exports as an FDE handoff packet.
          </p>
        )}
        {sel.status === "error" && (
          <p style={{ color: "#f87171" }}>Selection failed: {sel.error}.</p>
        )}
      </div>
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
        border: `1px solid ${recommended ? PRIMARY : "#23272d"}`,
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
            color: "#60a5fa",
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Our recommendation
        </span>
      )}
      <h2 style={{ fontSize: 20, margin: 0 }}>{col.title}</h2>
      <p style={{ color: MUTED, fontSize: 14, margin: 0 }}>{col.objective}</p>

      <dl style={{ margin: "12px 0 0", display: "grid", gap: 6 }}>
        <Metric label="Annual impact" value={`${usd(col.impact_usd)}/yr`} strong />
        {col.exposure_usd > 0 && <Metric label="At risk (not in totals)" value={usd(col.exposure_usd)} />}
        <Metric label="EBITDA lift" value={fmtEbitda(col.ebitda_uplift_pct)} />
        <Metric label="Payback" value={fmtPayback(col.payback_months)} />
        {col.impact_hours > 0 && (
          <Metric label="Hours freed / yr" value={`${col.impact_hours.toFixed(0)}`} />
        )}
        <Metric label="Consultant conviction" value={fmtPct(col.wwod_score)} />
        <Metric label="Deployability" value={fmtGrade(col.grade, col.blockers.length)} />
        <Metric label="Evidence confidence" value={fmtPct(col.confidence)} />
      </dl>

      {col.key_gap && (
        <p style={{ color: "#fbbf24", fontSize: 13, marginTop: 8 }}>
          Confirm first: {col.key_gap}
        </p>
      )}

      <button
        type="button"
        onClick={onChoose}
        aria-disabled={isSelecting || isSelected}
        style={{
          font: "inherit",
          marginTop: "auto",
          background: isSelected ? "#34d399" : PRIMARY,
          color: isSelected ? "#0b0d10" : "white",
          border: "none",
          padding: "10px 16px",
          borderRadius: 8,
          fontWeight: 600,
          cursor: isSelecting || isSelected ? "default" : "pointer",
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
      <dt style={{ color: MUTED }}>{label}</dt>
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
