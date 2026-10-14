"""Tests hors réseau du gel du plan CIRCUIT2 (aucune campagne lancée)."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    path = ROOT / "scripts" / "freeze_circuit2_plan.py"
    spec = importlib.util.spec_from_file_location("freeze_circuit2_plan", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fp = _load()


@pytest.fixture()
def frozen(tmp_path):
    path = tmp_path / "CIRCUIT2" / "PLAN.json"
    plan = fp.freeze(path)
    return path, plan


def test_plan_reproducible_and_verified(frozen):
    path, plan = frozen
    assert fp.build_plan() == plan
    assert fp.verify_plan(path) == plan
    assert json.loads(path.read_text(encoding="utf-8")) == plan


def _seeds(p):
    p["seeds"][-1] = 99


def _budget(p):
    p["budget"]["task_budget"] += 1


def _threshold(p):
    p["criterion"]["min_gain_final_vs_fixed_points"] = 1.0


def _machinery(p):
    first = sorted(p["machinery"])[0]
    p["machinery"][first] = "0" * 64


@pytest.mark.parametrize("mutate", [_seeds, _budget, _threshold, _machinery])
@pytest.mark.parametrize("resealed", [False, True])
def test_altered_plan_refused(frozen, tmp_path, mutate, resealed):
    _, plan = frozen
    altered = copy.deepcopy(plan)
    mutate(altered)
    if resealed:
        altered = fp.seal(altered)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises((ValueError, SystemExit)):
        fp.verify_plan(bad)


def test_twenty_distinct_paired_seeds(frozen):
    _, plan = frozen
    assert len(plan["seeds"]) == 20
    assert len(set(plan["seeds"])) == 20


def test_heldout_families_not_in_learn(frozen):
    _, plan = frozen
    assert plan["heldout_families"]
    assert not set(plan["heldout_families"]) & set(fp.learn_families())


def test_new_instances_disjoint_from_circuit1(frozen):
    _, plan = frozen
    mine = {tuple(i["rows"]) for i in plan["heldout_instances"]}
    assert len(mine) == len(plan["heldout_instances"])
    assert not mine & fp.circuit1_heldout_tables()


def test_second_freeze_refused(frozen):
    path, _ = frozen
    before = path.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        fp.freeze(path)
    assert path.read_text(encoding="utf-8") == before


def _circuit_tasks():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from genesis import circuit_tasks
    return circuit_tasks


def _expected_tables(ct):
    tasks = list(ct.suite(ct.HELD_OUT))
    tables = [
        tuple((t.target >> r) & 1 for r in range(1 << t.inputs)) for t in tasks
    ]
    return tasks, tables


def test_held_out_is_nonempty_tuple_of_family_names():
    ct = _circuit_tasks()
    assert isinstance(ct.HELD_OUT, tuple)
    assert len(ct.HELD_OUT) > 0
    assert all(isinstance(f, str) for f in ct.HELD_OUT)


def test_circuit1_heldout_tables_equal_suite_tables():
    ct = _circuit_tasks()
    tasks, tables = _expected_tables(ct)
    assert tasks
    got = fp.circuit1_heldout_tables()
    assert got == set(tables)
    assert len(got) == len(set(tables))
    assert len(got) <= len(tasks)
    for t, rows in zip(tasks, tables):
        assert len(rows) == 1 << t.inputs
        assert all(type(b) is int and b in (0, 1) for b in rows)
        assert rows in got


def test_circuit1_and_circuit2_tables_share_representation(frozen):
    _, plan = frozen
    mine = {tuple(i["rows"]) for i in plan["heldout_instances"]}
    for rows in fp.circuit1_heldout_tables() | mine:
        assert isinstance(rows, tuple)
        assert all(type(b) is int and b in (0, 1) for b in rows)


def test_circuit2_disjoint_from_suite_held_out(frozen):
    _, plan = frozen
    ct = _circuit_tasks()
    _, tables = _expected_tables(ct)
    mine = {tuple(i["rows"]) for i in plan["heldout_instances"]}
    assert mine
    assert not mine & set(tables)


def test_empty_heldout_suite_raises(monkeypatch):
    class _Empty:
        HELD_OUT = ("less",)

        @staticmethod
        def suite(names):
            return []

    monkeypatch.setattr(fp, "_tasks", lambda: _Empty)
    with pytest.raises(ValueError):
        fp.circuit1_heldout_tables()


def test_witness_arms_declared(frozen):
    _, plan = frozen
    for arm in ("meta_lineage", "frozen_engine", "fixed_procedure", "random_procedure"):
        assert arm in plan["arms"]
    assert plan["random_procedure_seeds"] == {
        str(s): fp.RANDOM_PROCEDURE_SEED_OFFSET + s for s in plan["seeds"]
    }


def test_budgets_frozen(frozen):
    _, plan = frozen
    b = plan["budget"]
    assert b["per_generation_limit"] == 16
    assert b["task_budget"] == 32
    assert b["max_generations"] == 6
    assert b["total_budget"] == 16 * 6


def test_preregistered_criterion(frozen):
    _, plan = frozen
    c = plan["criterion"]
    assert c["min_gain_final_vs_fixed_points"] == 10.0
    assert c["min_gain_final_vs_random_points"] == 10.0
    assert c["min_gain_per_transition_points"] == 5.0
    assert c["n_successive_transitions"] == 2
    assert c["n_seeds"] == 20
    assert c["min_seeds_won_per_comparison"] == 16
    assert c["ablation"]["operation"].startswith("replace_procedure")
    assert c["ablation"]["residual_gain_must_be_below_points"] == 5.0
    assert c["otherwise"] == "échec publié"
