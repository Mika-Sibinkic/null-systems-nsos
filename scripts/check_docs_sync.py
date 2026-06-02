#!/usr/bin/env python3
"""docs_sync gate (UPDATE-PROTOCOL).

Fails the build when source under engine/ client/ web/ learning/ presentation/ changed
but none of the doc-of-record files (docs/STATE.md, docs/ROADMAP.md, docs/site/index.html)
changed in the same diff — forcing STATE/ROADMAP/mind-map to stay recursive to code.

Override: include `[skip-docs-sync]` in the commit message (logged here, not silent).

Diff scope (first that applies):
  - explicit range via argv (e.g. `HEAD~1 HEAD` or `origin/main...HEAD`)
  - in CI with a base ref, compares against it
  - otherwise: staged changes (git diff --cached), then working tree, then last commit

Exit 0 = in sync (or nothing relevant changed, or override), 1 = drift.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PREFIXES = ("engine/", "client/", "web/", "learning/", "presentation/")
DOC_FILES = {"docs/STATE.md", "docs/ROADMAP.md", "docs/site/index.html"}
SKIP_TAG = "[skip-docs-sync]"
# Source paths that are docs-adjacent or non-shipping — changing them alone doesn't require a doc bump.
IGNORE_SUFFIXES = (".md",)  # e.g. engine/SANITIZED.md


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), *args],
                                       stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        return ""


def _changed_files() -> list[str]:
    # Explicit range from argv.
    if len(sys.argv) > 1:
        rng = sys.argv[1:]
        out = _git("diff", "--name-only", *rng)
        if out.strip():
            return out.split()
    # Staged.
    out = _git("diff", "--cached", "--name-only")
    if out.strip():
        return out.split()
    # Working tree.
    out = _git("diff", "--name-only")
    if out.strip():
        return out.split()
    # Fallback: last commit.
    out = _git("diff", "--name-only", "HEAD~1", "HEAD")
    return out.split()


def _last_commit_msg() -> str:
    return _git("log", "-1", "--pretty=%B")


def main() -> int:
    changed = _changed_files()
    if not changed:
        print("docs_sync: PASS (no changes detected)")
        return 0

    src_changed = [
        f for f in changed
        if f.startswith(SOURCE_PREFIXES) and not f.endswith(IGNORE_SUFFIXES)
    ]
    docs_changed = [f for f in changed if f in DOC_FILES]

    if not src_changed:
        print("docs_sync: PASS (no shipping source changed)")
        return 0

    if docs_changed:
        print(f"docs_sync: PASS ({len(src_changed)} source files; docs updated: {docs_changed})")
        return 0

    if SKIP_TAG in _last_commit_msg():
        print(f"docs_sync: PASS (override {SKIP_TAG} present — logged, not silent)")
        return 0

    print("docs_sync: FAIL — source changed but STATE/ROADMAP/site did not")
    for f in src_changed[:20]:
        print(f"  source changed: {f}")
    print(f"  -> update one of: {sorted(DOC_FILES)}  (or add {SKIP_TAG} to the commit message)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
