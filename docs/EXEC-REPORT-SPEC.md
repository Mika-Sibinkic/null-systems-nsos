# Executive Report — Specification

> What the CEO actually receives. Authoritative spec.

## Format

3–5 page markdown document. PDF rendering (Pandoc) and publishing to a docs tool are planned, not built.

## Required sections (in order)

1. **Cover** — Firm name. Date. "Prepared by Vinny · A Null Systems product."
2. **Executive summary (1 paragraph)** — The 1-line headline of each top-3 opportunity, totaled in $/hours saved per year.
3. **The three opportunities, ranked** — One section each. Per opportunity:
   - **Headline** — verb-led, 12-word max, time/cost framing.
   - **What we found** — 3-5 sentences. Plain language. No technical detail.
   - **What it costs you today** — quantified. $ and/or hours.
   - **What changing would save** — quantified. $ and/or hours, per quarter or per year.
   - **Confidence** — single sentence: "We're highly / moderately / suggestively confident because [evidence summary]."
   - **Suggested next step** — the FDE engagement scope (1 paragraph).
4. **Side-by-side (only if client supplied an idea)** — table of "Your scope" vs "Leaner alternative" with cost / time-to-value / payback delta.
5. **Things you already know that we agree with** — 2-3 sentences. Reinforces credibility, doesn't pad.
6. **What we did NOT cover** — explicit limitations. Sources we couldn't access; signals that need more time.
7. **How to confirm scope** — single CTA. Email + form link.

## Voice rules

- Cold. Hard. Time/cost first. Never "could", "might", "potentially" without a quantified bound.
- No jargon. No ML terminology. No "AI". Just outcomes.
- One number per sentence in the impact lines. Never compound.
- Every quantified claim has its source listed in an appendix (not inline).

## Appendices

A. **Evidence trail** — per finding, the underlying signals (Slack thread refs, invoice IDs, transcript timestamps).
B. **Methodology** — one paragraph: "Six diagnostic teams reviewed your data over X hours and ran Y questions. Findings were ranked by [composite score] and reviewed in council."
C. **What we'd recommend reviewing in 6 months** — list of secondary findings that didn't make the top 3 but should be revisited.

## Anti-patterns (will be flagged in QA)

❌ Using "AI" or "ML" or "NLP" in the body.
❌ Long evidence quotes inline.
❌ Showing more than 3 opportunities in the main report (they go in Appendix C).
❌ Recommending Null Systems by name in the body (it's implicit — this is a Null Systems report).
❌ Hedging language without a bound ("could improve" → state the range).

## Templates

See `presentation/exec-report/template.md` for the markdown template.
See `presentation/side-by-side/template.md` for the comparison table.
