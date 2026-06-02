import Link from "next/link";

export default function Home() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "64px 24px" }}>
      <h1 style={{ fontSize: 40, lineHeight: 1.1, marginBottom: 16 }}>
        See the dollars your business is leaving on the table.
      </h1>
      <p style={{ fontSize: 18, color: "#9aa3ab", marginBottom: 32 }}>
        Connect your stack. In under an hour you get your first quantified finding;
        within the run window, 2–3 Statements of Work — each with EBITDA %, hours
        reclaimed, and payback — to choose between.
      </p>
      <Link
        href="/onboarding"
        style={{
          display: "inline-block",
          background: "#3b82f6",
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
