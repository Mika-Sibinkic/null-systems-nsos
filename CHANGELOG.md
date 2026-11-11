# Changelog

## [0.1.0] - 2026-11-11

First public version, an internal prototype. It runs end to end on one fabricated client. No real
firm's books have been through it yet. `git log` holds the history before this.

- `python scripts/run_synthetic.py` turns a QuickBooks-like export into an owner-facing report with
  three scored options. CI reruns it and fails if the output differs from `examples/synthetic-client-a/report.md`.
- Every dollar in the output carries a source trace and a confidence. The engine raises on one that
  does not. Each assumed rate is named next to the number it drives, and the recommended option's
  assumption is the first thing to firm up.
- Supplier concentration, customer concentration and overdue receivables show as dollars at risk.
  They stay out of annual impact, EBITDA lift and payback. Before this, an $8.4M supplier dependency
  was booked as $8.4M a year of savings and a +273% EBITDA lift.
- Findings under 0.65 confidence are listed as pending review and left out of every total.
- Options rank by annual impact. The council layer was removed because it did not change the output.
- 171 tests run offline with no API key and make no network call.
