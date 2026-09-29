#!/usr/bin/env python3
"""grounded_numbers audit probe — the LeCun grounding gate.

Every finding that asserts a dollar/hours impact MUST trace to a source and carry a confidence.
Scans findings JSONL (default: runs/**/findings.jsonl, plus any path args). An impact number with
no non-empty evidence/source AND no confidence is a hard fail. If no findings exist yet, passes
(nothing to ground) — so it never false-blocks a phase before findings are produced.

  python3 scripts/probes/grounded_numbers.py
  python3 scripts/probes/grounded_numbers.py runs/synthetic-client-a/gauntlet/financial/findings.jsonl
Exit 0 = all grounded (or none yet), 1 = an ungrounded number exists.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMPACT_KEYS = ("impact_usd", "impact_hours")
SOURCE_KEYS = ("evidence", "source", "sources", "citations")

paths = sys.argv[1:] or glob.glob(os.path.join(ROOT, "runs", "**", "findings.jsonl"), recursive=True)
paths += glob.glob(os.path.join(ROOT, "examples", "**", "findings.jsonl"), recursive=True)
paths = sorted(set(paths))

if not paths:
    print("grounded_numbers: PASS (no findings files yet — nothing to ground)")
    sys.exit(0)

fails, checked = [], 0
for p in paths:
    try:
        with open(p, errors="ignore") as fh:
            for ln, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    fails.append(f"{os.path.relpath(p, ROOT)}:{ln} not valid JSON")
                    continue
                has_impact = any(rec.get(k) not in (None, "", 0) for k in IMPACT_KEYS)
                if not has_impact:
                    continue
                checked += 1
                src = next((rec.get(k) for k in SOURCE_KEYS if rec.get(k)), None)
                conf = rec.get("confidence")
                rel = f"{os.path.relpath(p, ROOT)}:{ln}"
                if not src:
                    fails.append(f"{rel} asserts impact with no evidence/source[]")
                if conf in (None, ""):
                    fails.append(f"{rel} asserts impact with no confidence band")
    except OSError as e:
        fails.append(f"{p}: {e}")

if fails:
    print(f"grounded_numbers: FAIL ({checked} impact findings checked)")
    for f in fails:
        print(f"  ! {f}")
    sys.exit(1)
print(f"grounded_numbers: PASS ({checked} impact findings all source-traced + confidence-banded)")
