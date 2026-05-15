"""Council protocol — debate + recursive-weight scoring.

See docs/COUNCIL-PROTOCOL.md for the authoritative spec.
"""
from .recursive_weights import rank_findings, score_finding, ScoreBreakdown
from .council import run_council

__all__ = ["rank_findings", "score_finding", "ScoreBreakdown", "run_council"]
