# {{firm_name}} — Diagnostic Summary

*Prepared by Null Systems · {{date}}*

---

## Executive summary

We reviewed your data and identified **three opportunities**. Together they represent **${{total_savings_usd:,}}/year** and **{{total_hours_saved}}** of partner / leadership time per year.

---

## Opportunity 1 — {{op1.headline}}

{{op1.what_we_found}}

- **Costing you today**: {{op1.cost_today}}
- **What changing would save**: {{op1.savings}}
- **Confidence**: {{op1.confidence_sentence}}
- **Suggested next step**: {{op1.next_step}}

---

## Opportunity 2 — {{op2.headline}}

{{op2.what_we_found}}

- **Costing you today**: {{op2.cost_today}}
- **What changing would save**: {{op2.savings}}
- **Confidence**: {{op2.confidence_sentence}}
- **Suggested next step**: {{op2.next_step}}

---

## Opportunity 3 — {{op3.headline}}

{{op3.what_we_found}}

- **Costing you today**: {{op3.cost_today}}
- **What changing would save**: {{op3.savings}}
- **Confidence**: {{op3.confidence_sentence}}
- **Suggested next step**: {{op3.next_step}}

---

{% if side_by_side %}

## Side-by-side — your idea vs. leaner alternative

| | Your scope | Leaner alternative |
|---|---|---|
| Cost | {{sbs.your_cost}} | {{sbs.alt_cost}} |
| Time to value | {{sbs.your_ttv}} | {{sbs.alt_ttv}} |
| Annual savings (year 2+) | {{sbs.your_savings}} | {{sbs.alt_savings}} |
| Payback period | {{sbs.your_payback}} | {{sbs.alt_payback}} |

**Net delta**: {{sbs.delta_summary}}

---

{% endif %}

## Things you already know that we agree with

{{agreed_known}}

---

## What we did NOT cover

{{not_covered}}

---

## How to confirm scope

Reply to this email or schedule a 30-min scope call: **{{cta_link}}**

---

*Appendices A (evidence trail), B (methodology), C (secondary findings) attached.*
