"""Tests for scripts/check_docs_sync.py — the docs-sync drift gate."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_docs_sync", ROOT / "scripts" / "check_docs_sync.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_fails_when_source_changed_without_docs():
    m = _load()
    m._changed_files = lambda: ["engine/teaser/teaser.py", "client/adapters/quickbooks.py"]
    m._last_commit_msg = lambda: "feat: stuff"
    assert m.main() == 1


def test_passes_when_source_and_docs_changed():
    m = _load()
    m._changed_files = lambda: ["engine/teaser/teaser.py", "docs/STATE.md"]
    assert m.main() == 0


def test_passes_when_only_md_source_changed():
    m = _load()
    m._changed_files = lambda: ["engine/SANITIZED.md"]
    assert m.main() == 0


def test_skip_override_passes_and_is_logged(capsys):
    m = _load()
    m._changed_files = lambda: ["engine/teaser/teaser.py"]
    m._last_commit_msg = lambda: "wip [skip-docs-sync]"
    assert m.main() == 0
    assert "skip-docs-sync" in capsys.readouterr().out


def test_passes_when_no_changes():
    m = _load()
    m._changed_files = lambda: []
    assert m.main() == 0
