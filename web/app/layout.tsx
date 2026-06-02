import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Null Systems — Diagnostic",
  description:
    "Run the diagnostic yourself. Connect your stack, get 2–3 scored SOWs in time/cost language.",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
          background: "#0b0d10",
          color: "#e6e8ea",
        }}
      >
        {children}
      </body>
    </html>
  );
}
