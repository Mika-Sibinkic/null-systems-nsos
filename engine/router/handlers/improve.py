"""
improve — manual trigger for the NSOS self-improvement loop.

    improve          one full pass (fix if broken, else predict on next gap)
    improve fix      attempt autofix on latest regression
    improve predict  log one prediction on the top-impact open gap
    improve status   show last 10 autofix attempts + predictions
"""

import json
import sys
from pathlib import Path

SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))


def handle(envelope):
    from self_improver import attempt_autofix, predict_on_next_gap, run_once, show_status
    import regression_runner

    text = (envelope.get("text") or "").strip()
    parts = text.split(None, 2)
    sub = parts[1].lower() if len(parts) > 1 else "run"

    try:
        if sub == "status":
            return show_status(limit=10)
        if sub == "fix":
            latest = regression_runner.latest()
            if latest is None:
                latest = regression_runner.full_check(skip_gauntlet=True)
            rec = attempt_autofix(latest)
            return f"autofix: {rec.get('outcome')} — module={rec.get('module','?')}"
        if sub == "predict":
            rec = predict_on_next_gap()
            out = rec.get("outcome", "?")
            if out == "predicted":
                return f"predicted on gap {rec.get('gap_id')}:\n{rec.get('prediction','')[:500]}"
            return f"predict: {out} — {rec.get('reason') or rec.get('error','')}"
        # default: run
        summary = run_once()
        return f"improve: mode={summary.get('mode')} result={json.dumps(summary.get('result',{}), default=str)[:400]}"
    except Exception as e:
        return f"[improve] error: {type(e).__name__}: {e}"
