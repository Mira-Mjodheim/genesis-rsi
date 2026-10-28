"""Tests de l'orchestrateur CIRCUIT2 (hors réseau, aucun résultat scientifique)."""
import copy
import importlib.util
import inspect
import json
import random
from pathlib import Path

import pytest

from genesis import circuit_engine as ce
from genesis import circuit_procedure as cp
from genesis import circuit_tasks as ct

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_circuit2_arms.py"
_SPEC = importlib.util.spec_from_file_location("run_circuit2_arms", _PATH)
arms = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(arms)

TASK_BUDGET = 500
BIG = 10**6


def _suite(families):
    params = inspect.signature(ct.suite).parameters
    kw = {k: 3 for k in ("inputs", "max_inputs", "n_inputs") if k in params}
    return ct.suite(tuple(families), **kw)


@pytest.fixture
def tasks():
    return _suite(("and", "or", "parity"))


def _run(tasks, limit, generations=3, seeds=(0, 1)):
    return arms.run_all(tasks, seeds, generations, limit, TASK_BUDGET)


def test_arms_are_isolated(tasks):
    res = _run(tasks, BIG)
    assert set(res["arms"]) == set(arms.ARMS)
    snapshot = copy.deepcopy(res)
    runs = [r for lst in res["arms"].values() for r in lst]
    assert len({id(r["generations"]) for r in runs}) == len(runs)
    res["arms"]["fixed_procedure"][0]["generations"].clear()
    res["arms"]["random_procedure"][0]["generations"][0]["digest"] = "x"
    for arm in ("inherited_lineage", "frozen_engine"):
        assert res["arms"][arm] == snapshot["arms"][arm]
    assert _run(tasks, BIG) == snapshot
    initial = arms.library_digest(ce.Engine())
    for arm in arms.ARMS:
        assert snapshot["arms"][arm][0]["generations"][0]["library_digest"] == initial
    for run in snapshot["arms"]["frozen_engine"]:
        gens = run["generations"]
        assert {g["library_digest"] for g in gens} == {initial}
        assert {g["transmission"]["library_digest"] for g in gens} == {initial}


@pytest.mark.parametrize("limit", [0, 40, 400, BIG])
def test_common_cap(tasks, limit):
    for runs in _run(tasks, limit, 2, (0,))["arms"].values():
        for run in runs:
            for g in run["generations"]:
                assert g["spent"] <= limit
                assert sum(g["spend"].values()) == pytest.approx(g["spent"])


def test_transmission(tasks):
    res = _run(tasks, BIG, 3, (0,))["arms"]
    for arm, runs in res.items():
        gens = runs[0]["generations"]
        assert [g["index"] for g in gens] == [0, 1, 2]
        assert gens[0]["parent"] is None
        for prev, nxt in zip(gens, gens[1:]):
            t = prev["transmission"]
            assert nxt["parent"] == t["digest"] == nxt["digest"]
            assert nxt["library_digest"] == t["library_digest"]
            assert nxt["procedure_digest"] == t["procedure_digest"]
        procs = {g["procedure_digest"] for g in gens}
        if arm == "frozen_engine":
            assert procs == {None}
        elif arm == "inherited_lineage":
            assert None not in procs
        else:
            assert len(procs) == 1 and None not in procs
    seed_d = arms.procedure_digest(cp.seed_procedure())
    assert res["fixed_procedure"][0]["generations"][0]["procedure_digest"] == seed_d


def test_exhausted_budget_is_recorded(tasks):
    for runs in _run(tasks, 0, 2, (0,))["arms"].values():
        for run in runs:
            assert len(run["generations"]) == 2
            for g in run["generations"]:
                assert g["exhausted"] is True
                assert g["spent"] == 0
                assert sum(g["spend"].values()) == 0


def test_reproducible_and_json(tasks):
    first = _run(tasks, 200)
    assert first == _run(tasks, 200)
    assert json.loads(json.dumps(first)) == first


def test_refuses_held_out_family():
    held = next(iter(ct.HELD_OUT))
    with pytest.raises(Exception):
        arms.run_arm("fixed_procedure", 0, _suite((held,)), 1, BIG, TASK_BUDGET)


def test_unknown_arm_rejected(tasks):
    with pytest.raises(ValueError):
        arms.run_arm("nope", 0, tasks, 1, BIG, TASK_BUDGET)


def test_state_digests_of_initial_state_match_fresh_engine_and_seed_procedure():
    state = arms.lineage.initial_state()
    lib_d, proc_d = arms.state_digests(state)
    assert lib_d == arms.library_digest(ce.Engine())
    assert proc_d == arms.procedure_digest(cp.seed_procedure())


def test_state_digests_refuse_a_state_without_engine():
    with pytest.raises(RuntimeError):
        arms.state_digests({"procedure": cp.to_record(cp.seed_procedure())})


def test_procedure_digest_refuses_a_record():
    record = cp.to_record(cp.seed_procedure())
    with pytest.raises(cp.ProcedureError):
        arms.procedure_digest(record)


def test_score_recorded_per_generation(tasks):
    for runs in _run(tasks, BIG, 2, (0,))["arms"].values():
        for g in runs[0]["generations"]:
            if g["score"] is None:
                assert g["exhausted"] is True
                assert sum(g["spend"].values()) == g["spent"]
            else:
                assert isinstance(g["score"], list) and len(g["score"]) == 2
                assert all(isinstance(x, int) for x in g["score"])


def test_inherited_score_is_the_transmitted_librarys_score(tasks, monkeypatch):
    def fake_step(state, tasks, task_budget, meter, rng):
        body = {key: copy.deepcopy(value)
                for key, value in state.items() if key != "digest"}
        body["index"] += 1
        body["parent_score"] = [1, -5]
        body["score"] = [2, -3]
        body["spent"] = {post: 0 for post in arms.POSTS}
        body["exhausted"] = False
        return arms.lineage._seal(body, state.engine)

    monkeypatch.setattr(arms.lineage, "step", fake_step)
    result = _run(tasks, BIG, 2, (0,))["arms"]
    for g in result["inherited_lineage"][0]["generations"]:
        assert g["score"] == [1, -5]
        assert g["selection_score"] == [2, -3]
    for arm in arms.ARMS:
        if arm != "inherited_lineage":
            for g in result[arm][0]["generations"]:
                assert g["selection_score"] is None

@pytest.mark.parametrize("arm", arms.ARMS)
def test_interrupted_baseline_keeps_its_paid_spend(tasks, monkeypatch, arm):
    def fake_attempt(engine, tasks, task_budget, meter, spent):
        meter.charge(7)
        spent["evaluations"] += 7
        return None

    monkeypatch.setattr(ce, "_metered_attempt", fake_attempt)
    result = arms.run_arm(arm, 0, tasks, 2, 100, TASK_BUDGET)
    assert len(result["generations"]) == 2
    for g in result["generations"]:
        assert g["score"] is None
        assert g["exhausted"] is True
        assert g["spent"] == 7
        assert g["spend"]["evaluations"] == 7
        assert sum(g["spend"].values()) == g["spent"]

def _projection(run):
    return [
        (g["library_digest"], g["spend"], g["score"],
         g["transmission"]["library_digest"])
        for g in run["generations"]
    ]


def test_fixed_procedure_versus_another_procedure(tasks):
    seed_proc = cp.seed_procedure()
    seed_d = arms.procedure_digest(seed_proc)
    other = None
    for k in range(64):
        cand = cp.mutate(copy.deepcopy(seed_proc),
                         random.Random(f"test-mutate|{k}"))
        if arms.procedure_digest(cand) != seed_d:
            other = cand
            break
    if other is None:
        pytest.skip("aucune mutation à digest distinct trouvée sur 64 graines")
    other_d = arms.procedure_digest(other)
    seeds = (0, 1, 2)
    base = [arms.run_arm("fixed_procedure", s, tasks, 3, BIG, TASK_BUDGET)
            for s in seeds]
    alt = [arms.run_arm("fixed_procedure", s, tasks, 3, BIG, TASK_BUDGET,
                        procedure=other)
           for s in seeds]
    for b, a in zip(base, alt):
        assert b["generations"][0]["procedure_digest"] == seed_d
        assert a["generations"][0]["procedure_digest"] == other_d
        assert b["generations"] != a["generations"]
    if not any(_projection(b) != _projection(a) for b, a in zip(base, alt)):
        pytest.skip("aucun effet observé sur ces graines : seuls les digests de procédure diffèrent")
