# Exposure is not impact (2026-11-11, Tier 2, needs Mika's confirm)

- **Change:** vendor concentration, customer concentration and overdue AR now put their dollars in `exposure_usd` and set `impact_usd` to 0.
- **Why:** they were booked as annual savings. Subcontractor Group's $8.4M spend became an $8.4M/yr SOW and a +273% EBITDA lift on synthetic-client-a. A dependency is a risk, not a saving, and overdue AR is one-time cash, not a yearly number.
- **Customer share:** the denominator is `profit_and_loss.TotalIncome` when present. Before, it was 7 invoices, so Northwind read as 31% of revenue. Against $28M it is 1.6%, so the finding no longer fires. With no P&L the share reads "of invoiced sample (n invoices)".
- **Render:** report, side-by-side and handoff packet show exposure as "at risk". It never enters annual impact, EBITDA lift or payback.
- **Effect on the synthetic run:** the supply-resilience SOW goes from $8.4M/yr to $0/yr with $8.4M at risk, and its WWOD conviction drops with it.
- **Overdue AR at risk** is the open overdue balance ($235,000 on synthetic-client-a). The 80% recovery assumption is gone; nothing used it once AR stopped counting as impact.
- **Not changed:** the concentration thresholds and the council weights.
- **Check:** `python -m pytest -q tests/test_e2e_synthetic.py`.
- **Rollback:** revert the commit. No schema migration. `exposure_usd` is a new field that older readers ignore.
