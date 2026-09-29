#!/usr/bin/env python3
"""pillar5_security audit probe — engineering-bar pillars 1/2/4 (security/compliance/throughput).

Graduated checks: a violation that EXISTS fails (exit 1); a control whose feature isn't built yet
is reported as a NOTE (does not fail) so it never false-blocks an early phase. Real secret in the
web surface is always a hard fail.

  python3 scripts/probes/pillar5_security.py            # full repo
  python3 scripts/probes/pillar5_security.py web/        # scope to a path
Exit 0 = clean, 1 = violation.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCOPE = sys.argv[1] if len(sys.argv) > 1 else "."
SKIP = {"node_modules", ".next", ".git", "dist", "build", ".venv", "__pycache__"}

# real-looking secret literals (not env var references)
SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|gh[oprs]_[A-Za-z0-9]{20,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9/+]{16,}['\"])",
    re.IGNORECASE,
)
# allow obvious placeholders / env reads
ALLOW = re.compile(r"(process\.env|os\.environ|getenv|YOUR_|<.*>|xxx|example|placeholder|REDACTED)", re.IGNORECASE)

fails, notes = [], []


def walk(base):
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in SKIP]
        for f in fns:
            if f.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".env", ".yaml", ".yml", ".md")):
                yield os.path.join(dp, f)


# 1. HARD: no secret literals anywhere in scope (esp. web/)
for path in walk(os.path.join(ROOT, SCOPE) if SCOPE != "." else ROOT):
    if os.path.basename(path) in (".env.example",):
        continue
    try:
        with open(path, errors="ignore") as fh:
            for i, line in enumerate(fh, 1):
                if SECRET.search(line) and not ALLOW.search(line):
                    rel = os.path.relpath(path, ROOT)
                    fails.append(f"secret literal: {rel}:{i}")
    except OSError:
        pass

# 2. GRADUATED: if a web surface exists, secrets there are the highest-risk — already covered above.
web = os.path.join(ROOT, "web")
if not os.path.isdir(web):
    notes.append("web/ not built yet — frontend-secret check N/A")

# 3. GRADUATED: per-tenant authz — if onboarding exists, expect tenant_id scoping somewhere in client/.
onb = os.path.join(ROOT, "client", "onboarding")
if os.path.isdir(onb) and os.listdir(onb):
    found = any("tenant_id" in open(p, errors="ignore").read()
                for p in walk(os.path.join(ROOT, "client")) if p.endswith(".py"))
    (notes if False else (fails if not found else notes)).append(
        "per-tenant authz: no 'tenant_id' scoping found in client/" if not found else "per-tenant authz: tenant_id scoping present")
else:
    notes.append("onboarding not built yet — per-tenant authz check N/A")

# 4. GRADUATED: LLM spend cap — note until the diagnostic run path exists (P5 throughput concern).
notes.append("LLM spend-cap: deferred to durable-execution work (P5) — NOTE only")

for n in notes:
    print(f"  note: {n}")
if fails:
    print("pillar5_security: FAIL")
    for f in fails:
        print(f"  ! {f}")
    sys.exit(1)
print("pillar5_security: PASS (no secret literals; graduated controls noted)")
