#!/usr/bin/env python3
"""
NSOS Reasoning Engine — Core Pattern/Prediction/Learning Library
Version: 1.1   (2026-04-25 — opt-029 semantic matching)

Manages the learned pattern library, predictions, outcomes, and gap analysis.
All data stored as JSON/JSONL in NSOS_DIR/reasoning/*.

Key concepts:
- Pattern: Learned rule or heuristic with confidence score
- Prediction: Model assertion about what will happen
- Gap: Known limitation or missing knowledge

v1.1: predict() now uses semantic matching with a graceful fallback ladder:
  1. sentence-transformers cosine similarity (if installed)
  2. character-n-gram TF-IDF cosine (pure stdlib, deterministic)
  3. legacy keyword-overlap (final fallback)
The ladder is chosen at import time; result of step 2/3 is identical
across runs. Threshold for inclusion: 0.30; top-3 by score.

Why: keyword matching scored 0/100 on the gauntlet's
"speculative-improvement" trap because the trap and the rule share zero
words. Semantic matching catches paraphrases.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import uuid


# Paths
NSOS_DIR = Path(__file__).parent
REASONING_DIR = NSOS_DIR / "reasoning"
REASONING_DIR.mkdir(exist_ok=True)

PATTERNS_FILE = REASONING_DIR / "patterns.jsonl"
PREDICTIONS_FILE = REASONING_DIR / "predictions.jsonl"
GAPS_FILE = REASONING_DIR / "gaps.jsonl"
LEARNING_LOG = REASONING_DIR / "learning.jsonl"


# Helper functions
def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON file, return {} if not found."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_json(path: Path, data: Dict[str, Any]) -> None:
    """Save JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file, return [] if not found."""
    if not path.exists():
        return []
    records = []
    try:
        with open(path) as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except IOError:
        pass
    return records


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    """Append record to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def gen_id() -> str:
    """Generate UUID for patterns/predictions/gaps."""
    return str(uuid.uuid4())[:8]


def now_iso() -> str:
    """Current time in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


# Pattern structure
class Pattern:
    """Learned rule or heuristic."""
    def __init__(
        self,
        id: str,
        name: str,
        rule: str,
        confidence: float,
        domain: str,
        category: str,
        source_corrections: List[str],
        times_tested: int = 0,
        times_correct: int = 0,
    ):
        self.id = id
        self.name = name
        self.rule = rule
        self.confidence = min(1.0, max(0.0, confidence))
        self.domain = domain
        self.category = category
        self.source_corrections = source_corrections
        self.times_tested = times_tested
        self.times_correct = times_correct

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "rule": self.rule,
            "confidence": self.confidence,
            "domain": self.domain,
            "category": self.category,
            "source_corrections": self.source_corrections,
            "times_tested": self.times_tested,
            "times_correct": self.times_correct,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Pattern":
        return Pattern(
            id=d["id"],
            name=d["name"],
            rule=d["rule"],
            confidence=d.get("confidence", 0.5),
            domain=d.get("domain", "general"),
            category=d.get("category", "unknown"),
            source_corrections=d.get("source_corrections", []),
            times_tested=d.get("times_tested", 0),
            times_correct=d.get("times_correct", 0),
        )

    def accuracy(self) -> float:
        """Accuracy: correct / tested."""
        if self.times_tested == 0:
            return self.confidence  # Fallback to base confidence
        return self.times_correct / self.times_tested


# ---------------------------------------------------------------------------
# Semantic matching (opt-029) — fallback ladder
# ---------------------------------------------------------------------------

_ST_MODEL = None  # lazy-loaded sentence-transformers model
_ST_TRIED = False
SEMANTIC_THRESHOLD = 0.30  # cosine similarity floor; below = exclude
SEMANTIC_TOP_K = 3


def _get_sentence_transformer():
    """Lazy load sentence-transformers; return None if unavailable."""
    global _ST_MODEL, _ST_TRIED
    if _ST_TRIED:
        return _ST_MODEL
    _ST_TRIED = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _ST_MODEL = None
    return _ST_MODEL


def _ngrams(text: str, n: int = 3) -> Dict[str, int]:
    """Character n-grams (deterministic, stdlib-only)."""
    text = (text or "").lower()
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    text = " ".join(text.split())
    if not text:
        return {}
    padded = " " * (n - 1) + text + " " * (n - 1)
    out: Dict[str, int] = {}
    for i in range(len(padded) - n + 1):
        g = padded[i:i + n]
        out[g] = out.get(g, 0) + 1
    return out


def _cosine_dict(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors (dict)."""
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    import math
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _tfidf_score(situation: str, rule: str) -> float:
    """
    Pure-stdlib TF-IDF on character 3-grams. Deterministic, no deps.
    Returns cosine similarity in [0, 1].
    """
    a = _ngrams(situation)
    b = _ngrams(rule)
    return _cosine_dict({k: float(v) for k, v in a.items()},
                        {k: float(v) for k, v in b.items()})


def _semantic_score(situation: str, rule: str) -> Tuple[float, str]:
    """
    Score similarity, return (score, method). Tries:
      1. sentence-transformers (best)
      2. tfidf char-ngram (always works)
    """
    model = _get_sentence_transformer()
    if model is not None:
        try:
            import numpy as np  # type: ignore
            embs = model.encode([situation or "", rule or ""], normalize_embeddings=True)
            sim = float(np.dot(embs[0], embs[1]))
            return sim, "sentence-transformers"
        except Exception:
            pass
    return _tfidf_score(situation, rule), "tfidf-ngram"


def _keyword_overlap(situation: str, rule: str) -> float:
    """Legacy: fraction of rule words present in situation."""
    s = (situation or "").lower()
    rule_words = (rule or "").lower().split()
    if not rule_words:
        return 0.0
    matches = sum(1 for w in rule_words if w in s)
    return matches / len(rule_words)


# Core functions
def predict(situation: str, domain: Optional[str] = None) -> Dict[str, Any]:
    """
    Find applicable patterns and generate prediction.

    Args:
        situation: Description of current situation
        domain: Optional domain filter

    Returns:
        {id, prediction_text, confidence, contributing_patterns,
         match_method, scores}

    v1.1: semantic matching with fallback ladder. Threshold = SEMANTIC_THRESHOLD.
    """
    patterns = load_jsonl(PATTERNS_FILE)

    # Filter by domain if specified
    if domain:
        patterns = [p for p in patterns if p.get("domain") == domain]

    if not patterns:
        return {
            "id": gen_id(),
            "prediction_text": "No applicable patterns found",
            "confidence": 0.0,
            "contributing_patterns": [],
            "match_method": "none",
            "scores": [],
        }

    # Score every pattern with the semantic ladder.
    method_seen = set()
    scored = []
    for pattern in patterns:
        rule = pattern.get("rule", "")
        if not rule:
            continue
        sem, method = _semantic_score(situation, rule)
        method_seen.add(method)
        # Combine with confidence — high-confidence patterns matter more
        # at equal similarity.
        conf = float(pattern.get("confidence", 0.5))
        composite = sem * (0.7 + 0.3 * conf)
        if sem >= SEMANTIC_THRESHOLD:
            scored.append((composite, sem, pattern))

    # If semantic ladder produced nothing, do one final pass on keyword
    # overlap so we never silently return zero matches when at least one
    # rule literally shares a word with the situation.
    if not scored:
        for pattern in patterns:
            rule = pattern.get("rule", "")
            if not rule:
                continue
            kw = _keyword_overlap(situation, rule)
            if kw > 0:
                conf = float(pattern.get("confidence", 0.5))
                scored.append((kw * conf, kw, pattern))
                method_seen.add("keyword-fallback")

    if not scored:
        return {
            "id": gen_id(),
            "prediction_text": "No matching patterns for this situation",
            "confidence": 0.0,
            "contributing_patterns": [],
            "match_method": next(iter(method_seen), "none"),
            "scores": [],
        }

    # Sort by composite score descending, take top-K.
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:SEMANTIC_TOP_K]
    top_patterns = [p for _, _, p in top]
    score_trace = [
        {"pattern_id": p.get("id"), "name": p.get("name"),
         "similarity": round(sim, 4), "composite": round(comp, 4)}
        for comp, sim, p in top
    ]

    # Confidence: weighted average of contributing pattern confidences,
    # weighted by similarity. This lets a single very-similar high-conf
    # pattern dominate a noisy long tail.
    sims = [sim for _, sim, _ in top]
    weight_sum = sum(sims) or 1.0
    weighted_conf = sum(
        p.get("confidence", 0.5) * sim for sim, p in zip(sims, top_patterns)
    ) / weight_sum

    prediction_text = "Based on: " + ", ".join(
        p.get("name", "unknown") for p in top_patterns
    )

    method = "sentence-transformers" if "sentence-transformers" in method_seen else \
             "tfidf-ngram" if "tfidf-ngram" in method_seen else \
             "keyword-fallback"

    return {
        "id": gen_id(),
        "prediction_text": prediction_text,
        "confidence": weighted_conf,
        "contributing_patterns": [p.get("id") for p in top_patterns],
        "match_method": method,
        "scores": score_trace,
    }


def compare(prediction_id: str, actual_outcome: str) -> Dict[str, Any]:
    """
    Compare prediction vs actual. Update pattern confidence based on outcome.

    Args:
        prediction_id: ID from original prediction
        actual_outcome: What actually happened

    Returns:
        {correct, delta, patterns_updated}
    """
    predictions = load_jsonl(PREDICTIONS_FILE)
    pred = next((p for p in predictions if p.get("id") == prediction_id), None)

    if not pred:
        return {"error": "Prediction not found"}

    # Load patterns
    patterns = load_jsonl(PATTERNS_FILE)
    pattern_dict = {p.get("id"): p for p in patterns}

    # Check if prediction was correct (very simple heuristic)
    correct = "correct" in actual_outcome.lower() or "success" in actual_outcome.lower()

    # Update patterns that contributed
    delta = 0.0
    updated_count = 0
    for pattern_id in pred.get("contributing_patterns", []):
        if pattern_id in pattern_dict:
            pattern = pattern_dict[pattern_id]
            pattern["times_tested"] = pattern.get("times_tested", 0) + 1
            if correct:
                pattern["times_correct"] = pattern.get("times_correct", 0) + 1
                delta += 0.02
            else:
                delta -= 0.05

            # Clamp confidence
            pattern["confidence"] = min(1.0, max(0.0, pattern["confidence"] + delta))
            pattern_dict[pattern_id] = pattern
            updated_count += 1

    # Save updated patterns
    with open(PATTERNS_FILE, "w") as f:
        for p in pattern_dict.values():
            f.write(json.dumps(p) + "\n")

    return {
        "correct": correct,
        "delta": delta,
        "patterns_updated": updated_count,
    }


def extract_pattern(correction_data: Dict[str, Any]) -> Pattern:
    """
    Extract pattern from operator correction.

    Args:
        correction_data: {pattern_name, context, what_model_did, what_operator_wanted, ...}

    Returns:
        Pattern object
    """
    pattern_id = gen_id()
    name = correction_data.get("pattern_name", f"pattern-{pattern_id}")
    rule = correction_data.get("what_operator_wanted", "")
    domain = correction_data.get("domain", "general")
    category = correction_data.get("category", "decision-making")

    # Start with baseline confidence (corrections are high-signal)
    confidence = 0.8 if correction_data.get("severity") == "high" else 0.6

    source_correction = correction_data.get("correction_id", pattern_id)

    pattern = Pattern(
        id=pattern_id,
        name=name,
        rule=rule,
        confidence=confidence,
        domain=domain,
        category=category,
        source_corrections=[source_correction],
    )

    return pattern


def update_patterns(learning_results: Dict[str, Any]) -> int:
    """
    Bulk update patterns from learning synthesis.

    Args:
        learning_results: {patterns_to_promote, patterns_to_demote, ...}

    Returns:
        Number of patterns updated
    """
    patterns = load_jsonl(PATTERNS_FILE)
    pattern_dict = {p.get("id"): p for p in patterns}

    updated = 0

    # Promote patterns
    for pat_id in learning_results.get("patterns_to_promote", []):
        if pat_id in pattern_dict:
            pattern_dict[pat_id]["confidence"] = min(
                1.0, pattern_dict[pat_id].get("confidence", 0.5) + 0.1
            )
            updated += 1

    # Demote patterns
    for pat_id in learning_results.get("patterns_to_demote", []):
        if pat_id in pattern_dict:
            pattern_dict[pat_id]["confidence"] = max(
                0.0, pattern_dict[pat_id].get("confidence", 0.5) - 0.15
            )
            updated += 1

    # Save updated patterns
    with open(PATTERNS_FILE, "w") as f:
        for p in pattern_dict.values():
            f.write(json.dumps(p) + "\n")

    return updated


def get_gaps() -> List[Dict[str, Any]]:
    """
    Get current knowledge gaps (what model doesn't know yet).

    Returns:
        List of gap records
    """
    return load_jsonl(GAPS_FILE)


def add_gap(gap_description: str, domain: str, severity: str = "medium") -> str:
    """
    Record a new knowledge gap.

    Args:
        gap_description: What the model is missing
        domain: What domain this applies to
        severity: low|medium|high

    Returns:
        Gap ID
    """
    gap_id = gen_id()
    gap = {
        "id": gap_id,
        "description": gap_description,
        "domain": domain,
        "severity": severity,
        "created": now_iso(),
        "resolved": False,
    }
    append_jsonl(GAPS_FILE, gap)
    return gap_id


def resolve_gap(gap_id: str) -> bool:
    """Mark a gap as resolved."""
    gaps = load_jsonl(GAPS_FILE)
    updated = False

    for gap in gaps:
        if gap.get("id") == gap_id:
            gap["resolved"] = True
            gap["resolved_at"] = now_iso()
            updated = True
            break

    if updated:
        with open(GAPS_FILE, "w") as f:
            for gap in gaps:
                f.write(json.dumps(gap) + "\n")

    return updated


def get_stats() -> Dict[str, Any]:
    """Get reasoning engine statistics."""
    patterns = load_jsonl(PATTERNS_FILE)
    predictions = load_jsonl(PREDICTIONS_FILE)
    gaps = load_jsonl(GAPS_FILE)

    avg_confidence = (
        sum(p.get("confidence", 0.5) for p in patterns) / len(patterns)
        if patterns
        else 0.0
    )

    avg_accuracy = (
        sum(
            p.get("times_correct", 0) / p.get("times_tested", 1)
            for p in patterns
            if p.get("times_tested", 0) > 0
        )
        / max(1, len([p for p in patterns if p.get("times_tested", 0) > 0]))
        if patterns
        else 0.0
    )

    unresolved_gaps = sum(1 for g in gaps if not g.get("resolved", False))

    return {
        "total_patterns": len(patterns),
        "avg_confidence": avg_confidence,
        "avg_accuracy": avg_accuracy,
        "total_predictions": len(predictions),
        "total_gaps": len(gaps),
        "unresolved_gaps": unresolved_gaps,
    }


if __name__ == "__main__":
    # Test
    print("Reasoning Engine Stats:")
    print(json.dumps(get_stats(), indent=2))
