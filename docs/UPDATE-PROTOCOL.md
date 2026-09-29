# UPDATE-PROTOCOL — keep docs/viz recursive to state

> The "recursive" requirement: docs and the mind map must never drift from code. Every milestone that
> changes what's built updates the docs **in the same change**, gated by CI.

## The rule

A change that moves a component between states (🔴→🟡→🟢) **must, in the same PR/commit**:

1. **STATE.md** — update the component's row (state emoji + notes + `Last verified` date).
2. **ROADMAP.md** — tick the checkbox(es) it completes; if scope shifted, edit the phase.
3. **Mind map** (`docs/site/index.html`) — recolor the touched node(s) to match STATE
   (`:::built` / `:::partial` / `:::planned`) and add a `click` link if a new doc anchor exists.
4. **PRODUCT.md changelog** — append a dated line **only if the product description changed** (not for
   pure implementation progress).

## CI check

`.github/workflows/ci.yml` can run `scripts/check_docs_sync.py`. It fails the
build when engine/client/web/learning source changed in a commit but none of STATE.md / ROADMAP.md /
`docs/site/index.html` did — forcing the doc update. Override only with a `[skip-docs-sync]` tag in
the commit message (logged, not silent).

## Why

STATE = where we are. ROADMAP = where we're going. They reconcile at every merge. The mind map is the
visual of STATE. If any of the three lags the code, the recursion is broken and the visualization
lies. This protocol is the cheapest enforcement that keeps them honest.

## Quick reference

| You changed… | Update |
|---|---|
| A component's build state | STATE row + ROADMAP checkbox + mind-map node color |
| What the product *is/does* | PRODUCT.md flow + changelog line |
| A phase's plan/scope | ROADMAP phase |
| A Tier-2 architecture choice | new `docs/decisions/YYYY-MM-DD-<slug>.md` + link from ROADMAP |
| ICP / pricing / economics | GTM.md |
