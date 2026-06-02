"""WWMD scoring — "would a consultant push this SOW?" (P3.T2).

WWMD = What Would Mika Do. NSOS's policy model predicts, for each candidate SOW,
how hard an experienced consultant would push it to the client. The score is a
blend of two signals:

  1. **Learned policy** — `engine.reasoning.reasoning_engine.predict()` matched
     against consultant patterns (lifted, read-only, from personal NSOS). When
     patterns exist and match, this carries the human-judgment signal: "we have
     seen deals like this; here is how hard we pushed."
  2. **Deterministic deal-quality prior** — magnitude of impact, the candidate's
     own confidence, and breadth (how many independent findings corroborate the
     thrust). This is the offline-safe floor so WWMD still produces a meaningful,
     reproducible score when the patterns file is empty (cold start / offline /
     test) — never a silent 0.

Output per SOW: `wwmd_score` in [0,1], `confidence` in [0,1], and `gaps[]` — the
dimensions a consultant would flag as needing more evidence before pushing. Gaps
are the honest "what we don't know yet" list (Karpathy human-in-loop hook: a SOW
with material gaps routes to FDE review, it does not auto-surface).

No new dollar numbers are minted here — WWMD scores the *push*, not the impact,
so the grounded-numbers gate is untouched by this layer.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field, asdict
from typing import Any, Sequence

# lifted reasoning engine (read-only WWMD policy substrate)
_re = importlib.import_module("engine.reasoning.reasoning_engine")

# ── deterministic deal-quality prior knobs ────────────────────────────────────
# A consultant pushes hardest on large, well-evidenced, broadly-corroborated
# opportunities. These shape the offline floor; the learned policy adjusts it.
IMPACT_SATURATION_USD = 2_000_000.0   # diminishing returns above ~$2M/yr thrust
MIN_CONFIDENCE_TO_PUSH = 0.5          # below this, a consultant hedges
BREADTH_BONUS_PER_FINDING = 0.05      # each corroborating finding firms the push
LEARNED_WEIGHT = 0.45                 # blend weight on the learned-policy signal
PRIOR_WEIGHT = 0.55                   # blend weight on the deterministic prior


@dataclass
class WWMDScore:
    sow_id: str
    wwmd_score: float          # [0,1] how hard a consultant would push
    confidence: float          # [0,1] how sure WWMD is of that push
    learned_signal: float      # raw learned-policy contribution
    prior_signal: float        # raw deterministic-prior contribution
    match_method: str          # which reasoning-engine ladder rung matched
    contributing_patterns: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _situation_text(sow: Any) -> str:
    """Frame a SOW as the consultant-decision situation the policy was trained on."""
    title = _attr(sow, "title", "")
    objective = _attr(sow, "objective", "")
    impact = float(_attr(sow, "impact_usd", 0.0) or 0.0)
    hrs = float(_attr(sow, "impact_hours", 0.0) or 0.0)
    n = len(_attr(sow, "finding_ids", []) or [])
    return (
        f"Consultant engagement: {title}. {objective} "
        f"Quantified opportunity ~${impact:,.0f}/yr and {hrs:.0f} hrs/yr reclaimed, "
        f"corroborated by {n} independent findings. "
        f"How hard should we push this scope of work to the client?"
    )


def _attr(obj: Any, name: str, default=None):
    """Support both SOWCandidate dataclass and plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _deterministic_prior(sow: Any) -> float:
    """Offline-safe deal-quality prior in [0,1]. Monotonic in impact (saturating),
    confidence, and corroboration breadth."""
    impact = float(_attr(sow, "impact_usd", 0.0) or 0.0)
    conf = float(_attr(sow, "confidence", 0.0) or 0.0)
    n_findings = len(_attr(sow, "finding_ids", []) or [])

    # impact, saturating: $0 -> 0, $2M+ -> ~1
    impact_term = min(1.0, impact / IMPACT_SATURATION_USD)
    # confidence term, but only counts once over the push threshold
    conf_term = max(0.0, (conf - MIN_CONFIDENCE_TO_PUSH) / (1.0 - MIN_CONFIDENCE_TO_PUSH)) \
        if conf >= MIN_CONFIDENCE_TO_PUSH else 0.0
    breadth_term = min(0.3, BREADTH_BONUS_PER_FINDING * n_findings)

    prior = 0.5 * impact_term + 0.35 * conf_term + breadth_term
    return round(min(1.0, prior), 4)


def _gaps_for(sow: Any, learned_conf: float, match_method: str) -> list[str]:
    """The honest 'what a consultant would want firmed up before pushing' list."""
    gaps: list[str] = []
    conf = float(_attr(sow, "confidence", 0.0) or 0.0)
    if conf < MIN_CONFIDENCE_TO_PUSH:
        gaps.append(
            f"low aggregate confidence ({conf:.0%}) — validate the underlying numbers "
            f"with the client before pushing"
        )
    if match_method in ("none", "keyword-fallback") or learned_conf == 0.0:
        gaps.append(
            "no comparable prior engagement in the WWMD policy — first-of-kind push, "
            "score leans on the deterministic prior"
        )
    if not _attr(sow, "source", []):
        gaps.append("SOW carries impact with no source trace — grounding gap")
    n = len(_attr(sow, "finding_ids", []) or [])
    if n < 2:
        gaps.append(
            "single-finding thrust — thin corroboration; one more independent "
            "signal would firm the recommendation"
        )
    return gaps


def score_sow(sow: Any, *, domain: str | None = "consulting") -> WWMDScore:
    """Score one SOW candidate. Degrades gracefully when no patterns exist."""
    situation = _situation_text(sow)
    try:
        pred = _re.predict(situation, domain=domain)
    except Exception:
        pred = {"confidence": 0.0, "contributing_patterns": [], "match_method": "none"}

    learned_conf = float(pred.get("confidence", 0.0) or 0.0)
    match_method = pred.get("match_method", "none")
    contributing = list(pred.get("contributing_patterns", []) or [])

    prior = _deterministic_prior(sow)

    # blend: when the learned signal is absent (cold start), fall back entirely
    # to the prior rather than dragging the score toward 0.
    if learned_conf <= 0.0:
        wwmd = prior
    else:
        wwmd = round(LEARNED_WEIGHT * learned_conf + PRIOR_WEIGHT * prior, 4)

    # WWMD's own confidence: high when both signals agree and a real pattern
    # matched; low at cold start.
    agreement = 1.0 - abs(learned_conf - prior) if learned_conf > 0 else 0.5
    method_bonus = 0.0 if match_method in ("none", "keyword-fallback") else 0.2
    confidence = round(min(1.0, 0.5 * agreement + 0.3 * (learned_conf or prior) + method_bonus), 4)

    gaps = _gaps_for(sow, learned_conf, match_method)

    return WWMDScore(
        sow_id=_attr(sow, "id", "unknown"),
        wwmd_score=round(min(1.0, wwmd), 4),
        confidence=confidence,
        learned_signal=round(learned_conf, 4),
        prior_signal=prior,
        match_method=match_method,
        contributing_patterns=contributing,
        gaps=gaps,
    )


def score_sows(sows: Sequence[Any], *, domain: str | None = "consulting") -> list[WWMDScore]:
    """Score a list of SOW candidates; preserves input order."""
    return [score_sow(s, domain=domain) for s in sows]


def attach_scores(sows: Sequence[Any], *, domain: str | None = "consulting") -> list[dict]:
    """Return each SOW as a dict with a `wwmd` block attached (for the report layer)."""
    out: list[dict] = []
    for s in sows:
        d = s.to_dict() if hasattr(s, "to_dict") else dict(s)
        d["wwmd"] = score_sow(s, domain=domain).to_dict()
        out.append(d)
    return out
