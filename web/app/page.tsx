import Link from "next/link";

export default function Home() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "64px 24px" }}>
      <h1 style={{ fontSize: 40, lineHeight: 1.1, marginBottom: 16 }}>
        See the dollars your business is leaving on the table.
      </h1>
      <p style={{ fontSize: 18, color: "#9aa3ab", marginBottom: 32 }}>
        This demo runs on a synthetic QuickBooks export. Press connect and the engine
        reads it and returns one quantified finding, with the lines it came from. The
        full run turns findings into 2–3 Statements of Work, each with EBITDA lift,
        hours freed and payback.
      </p>
      <Link
        href="/onboarding"
        style={{
          display: "inline-block",
          background: "#2563eb",
          color: "white",
          padding: "12px 24px",
          borderRadius: 8,
          textDecoration: "none",
          fontWeight: 600,
        }}
      >
        Start the diagnostic
      </Link>
    </main>
  );
}
