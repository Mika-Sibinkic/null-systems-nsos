"""WWOD scoring: "would a consultant push this SOW?"

WWOD = "What Would the Operator Do", where the operator is the consultant
deciding which SOW to recommend. Today the score is a deterministic deal-quality
prior: size of impact (saturating), the SOW's own confidence, and how many
independent findings back it. There is no learned signal yet: no past
engagements are on record, and every report says so (COLD_START_GAP).

Output per SOW: `wwod_score` in [0,1], `confidence` in [0,1], and `gaps[]`, the
things a consultant would want firmed up before pushing.

No dollar numbers are minted here. WWOD scores the push, not the impact, so the
grounded-numbers gate is untouched by this layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Sequence

# ── deterministic deal-quality prior knobs ────────────────────────────────────
# A consultant pushes hardest on large, well-evidenced, broadly-corroborated
# opportunities.
IMPACT_SATURATION_USD = 2_000_000.0   # diminishing returns above ~$2M/yr thrust
MIN_CONFIDENCE_TO_PUSH = 0.5          # below this, a consultant hedges
BREADTH_BONUS_PER_FINDING = 0.05      # each corroborating finding firms the push

# True of every SOW until past engagements are on record, so owner-facing text
# states it once instead of per option (presentation/side-by-side/sbs.py).
COLD_START_GAP = (
    "we have no past engagement like this on record, so the conviction score "
    "rests only on size, confidence and how many findings back it"
)


@dataclass
class WWODScore:
    sow_id: str
    wwod_score: float          # [0,1] how hard a consultant would push
    confidence: float          # [0,1] how sure WWOD is of that push
    prior_signal: float        # the deterministic prior (equal to wwod_score today)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


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


def _gaps_for(sow: Any) -> list[str]:
    """The honest 'what a consultant would want firmed up before pushing' list."""
    gaps: list[str] = []
    conf = float(_attr(sow, "confidence", 0.0) or 0.0)
    if conf < MIN_CONFIDENCE_TO_PUSH:
        gaps.append(
            f"low aggregate confidence ({conf:.0%}) — validate the underlying numbers "
            f"with the client before pushing"
        )
    gaps.append(COLD_START_GAP)
    if not _attr(sow, "source", []):
        gaps.append("SOW carries impact with no source trace — grounding gap")
    n = len(_attr(sow, "finding_ids", []) or [])
    if n < 2:
        gaps.append(
            "one finding backs this option; a second, independent finding "
            "would add corroboration"
        )
    return gaps


def score_sow(sow: Any) -> WWODScore:
    """Score one SOW candidate."""
    prior = _deterministic_prior(sow)
    return WWODScore(
        sow_id=_attr(sow, "id", "unknown"),
        wwod_score=prior,
        # 0.25 + 0.3 * prior: the cold-start confidence, low until engagements are on record.
        confidence=round(min(1.0, 0.25 + 0.3 * prior), 4),
        prior_signal=prior,
        gaps=_gaps_for(sow),
    )


def score_sows(sows: Sequence[Any]) -> list[WWODScore]:
    """Score a list of SOW candidates; preserves input order."""
    return [score_sow(s) for s in sows]


def attach_scores(sows: Sequence[Any]) -> list[dict]:
    """Return each SOW as a dict with a `wwod` block attached (for the report layer)."""
    out: list[dict] = []
    for s in sows:
        d = s.to_dict() if hasattr(s, "to_dict") else dict(s)
        d["wwod"] = score_sow(s).to_dict()
        out.append(d)
    return out
