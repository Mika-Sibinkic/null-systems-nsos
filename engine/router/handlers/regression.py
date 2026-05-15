"""
regression — run NSOS regression suite and return a compact summary.

    regression          full: imports + gauntlet sampler (3 scenarios)
    regression imports  import sweep only (fast, no NIM calls)
    regression latest   summarize most recent regression record
"""

import sys
from pathlib import Path

SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))


def _fmt_latest(r):
    imp = r.get("import_sweep", {})
    g = r.get("gauntlet")
    lines = [
        f"last run: {r.get('timestamp','?')[:19]}",
        f"imports: {imp.get('passed','?')}/{imp.get('total','?')} ok",
    ]
    if imp.get("failures"):
        for f in imp["failures"][:5]:
            lines.append(f"  ✗ {f.get('module')}: {f.get('error','?')[:80]}")
    if g:
        lines.append(
            f"gauntlet: score={g.get('avg_score','?')}/100 acc={g.get('accuracy','?')} "
            f"scenarios={g.get('scenarios_evaluated','?')} ({g.get('elapsed_s','?')}s)"
        )
    lines.append(f"overall_ok: {r.get('overall_ok', False)}")
    return "\n".join(lines)


def handle(envelope):
    import regression_runner

    text = (envelope.get("text") or "").strip()
    parts = text.split(None, 2)
    sub = parts[1].lower() if len(parts) > 1 else "full"

    try:
        if sub == "imports":
            r = regression_runner.import_sweep()
            return (
                f"imports: {r['passed']}/{r['total']} ok\n"
                + "\n".join(
                    f"  ✗ {f['module']}: {f.get('error','?')[:100]}"
                    for f in r["failures"][:10]
                )
            )
        if sub == "latest":
            r = regression_runner.latest()
            if not r:
                return "no regression records yet — run `regression` to create one"
            return _fmt_latest(r)
        # default: full
        r = regression_runner.full_check()
        return _fmt_latest(r)
    except Exception as e:
        return f"[regression] error: {type(e).__name__}: {e}"
