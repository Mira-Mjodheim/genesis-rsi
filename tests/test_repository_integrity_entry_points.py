"""Entry-point exemptions of the orphan check are explicit, not prefix-wide."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import types

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_repository_integrity.py"


def _load() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_repository_integrity_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def integrity(tmp_path, monkeypatch):
    module = _load()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def _write_scripts(root: Path, *names: str) -> None:
    for name in names:
        (root / "scripts" / f"{name}.py").write_text("pass\n", encoding="utf-8")


def _orphan_message(name: str) -> str:
    return f"{Path('scripts') / (name + '.py')} is not imported by any entry point"


def test_generic_prefixes_are_not_entry_points(integrity):
    assert "diagnose_" not in integrity.ENTRY_POINT_PREFIXES
    assert "freeze_" not in integrity.ENTRY_POINT_PREFIXES


def test_declared_names_are_exactly_the_two_known_scripts(integrity):
    assert "diagnose_circuit2_collisions" in integrity.ENTRY_POINT_NAMES
    assert "freeze_circuit2_plan" in integrity.ENTRY_POINT_NAMES
    assert set(integrity.ENTRY_POINT_NAMES) == {
        "diagnose_circuit2_collisions",
        "freeze_circuit2_plan",
    }


def test_declared_scripts_are_not_reported(integrity):
    _write_scripts(integrity.ROOT, "freeze_circuit2_plan", "diagnose_circuit2_collisions")
    assert integrity.check_orphans() == []


def test_arbitrary_diagnose_and_freeze_scripts_are_reported(integrity):
    _write_scripts(integrity.ROOT, "diagnose_arbitraire", "freeze_arbitraire")
    assert integrity.check_orphans() == [
        _orphan_message("diagnose_arbitraire"),
        _orphan_message("freeze_arbitraire"),
    ]


def test_run_prefix_remains_an_entry_point(integrity):
    _write_scripts(integrity.ROOT, "run_x")
    assert integrity.check_orphans() == []
