"""
ingest-instagram — run one pass of the Instagram 'Work' saved-posts pipeline.

    nsos ingest-instagram          # process all pending audio → insights
    nsos ingest-instagram status   # show pipeline state

Thin wrapper around instagram-pipeline.py (which lives at module root
with a hyphenated filename, so we import via importlib). Every new
insight produced this pass is scored by quality_judge before the
per-insight summary is returned to the user.

On the daemon cycle, a separate step invokes this at :00 of every 30min.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Not SKIP_JUDGE — we explicitly want the summary scored.

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))

_PIPELINE_PATH = NSOS_DIR / "instagram-pipeline.py"


def _load_pipeline():
    spec = importlib.util.spec_from_file_location("ig_pipeline", _PIPELINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _summarize(ig, top_n: int = 3) -> str:
    """Build a user-facing summary after an ingest pass."""
    stats = ig.get_pipeline_stats()
    lines = [
        f"instagram pipeline:",
        f"  audio files:      {stats.get('total_audio', 0)}",
        f"  processed:        {stats.get('processed', 0)}",
        f"  pending:          {stats.get('pending', 0)}",
        f"  llm available:    {stats.get('llm_available')}",
        f"  last run:         {stats.get('last_run')}",
    ]
    index = ig.load_jsonl(ig.IG_INDEX)
    if index:
        top = sorted(index, key=lambda r: r.get("priority_score", 0), reverse=True)[:top_n]
        lines.append("")
        lines.append(f"top {len(top)} by priority:")
        for r in top:
            uploader = r.get("uploader", "?")
            summary = (r.get("summary") or r.get("title") or "").replace("\n", " ")[:120]
            score = r.get("priority_score", 0)
            lines.append(f"  [{uploader}] {summary} (priority {score})")
    return "\n".join(lines)


def handle(envelope: Dict[str, Any]) -> str:
    try:
        ig = _load_pipeline()
    except Exception as e:
        return f"(instagram pipeline import failed: {type(e).__name__}: {e})"

    parts = (envelope.get("text") or "").split(None, 1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    if arg == "status":
        return _summarize(ig)

    # Run one ingestion pass. Capture the before/after processed counts so we
    # can report what this invocation actually did, not just overall state.
    before_stats = ig.get_pipeline_stats()
    try:
        ig.ingest()
    except Exception as e:
        return f"(ingest failed: {type(e).__name__}: {e})"
    after_stats = ig.get_pipeline_stats()
    delta = after_stats.get("processed", 0) - before_stats.get("processed", 0)

    header = f"instagram ingest pass: +{delta} processed this run (total {after_stats.get('processed', 0)})"
    return header + "\n\n" + _summarize(ig)
