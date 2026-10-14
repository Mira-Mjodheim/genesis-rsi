import copy
import json
import random

import pytest

from genesis import circuit_engine as engine
from genesis import circuit_meta_lineage as lineage
from genesis import circuit_procedure as cp
from genesis import circuit_tasks as tasks
from genesis.circuit_engine import Meter

BUDGET = 500
BIG = 10**6
LEARN = [task for task in tasks.suite(("and", "or", "parity")) if task.inputs <= 3]


def _procedure(admit, outs=(11, 11), steps=((0, 0), (0, 10))):
    """With the default steps signal 11 is constant 1: admit=11 admits every candidate."""
    procedure = cp.Procedure(len(cp.TRAITS), steps, outs, admit)
    cp.validate(procedure)
    return procedure


def _nothing():
    return _procedure(admit=12, steps=((0, 0), (0, 10), (11, 11)))


def _run(generations=3, limit=BIG, seed=1):
    return lineage.run_lineage(generations, LEARN, BUDGET, limit, seed)


def _rng(seed, index=0):
    return random.Random(f"meta|{seed}|{index}")


def test_two_identical_runs_give_the_same_fingerprints():
    one, two = _run(4), _run(4)
    assert [state["digest"] for state in one] == [state["digest"] for state in two]
    assert one == two and len(one) == 5
    assert json.loads(json.dumps(one)) == one
    assert lineage.verify_lineage(json.loads(json.dumps(one))) is True


def _spend_more(chain):
    chain[2]["spent"]["synthesis"] += 1


def _bend_parent(chain):
    chain[3]["parent"] = "0" * 64


def _bend_procedure(chain):
    chain[2]["procedure"]["admit_output"] = 0


def _bend_library(chain):
    chain[1]["library"] = {"altered": True}


def _reseal_forgery(chain):
    body = dict(chain[1])
    body["spent"] = {**body["spent"], "synthesis": body["spent"]["synthesis"] + 1}
    chain[1] = lineage.seal(body)


def _swap(chain):
    chain[1], chain[2] = chain[2], chain[1]


def _skip(chain):
    del chain[2]


def test_every_generation_points_to_its_parent_and_a_tampered_chain_is_refused():
    states = _run(4)
    assert states[0]["parent"] is None
    for before, after in zip(states, states[1:]):
        assert after["parent"] == before["digest"] and after["index"] == before["index"] + 1
    assert lineage.verify_lineage(states) is True
    assert lineage.verify_lineage([]) is True
    for alter in (_spend_more, _bend_parent, _bend_procedure, _bend_library, _reseal_forgery, _swap, _skip):
        chain = copy.deepcopy([dict(state) for state in states])
        alter(chain)
        with pytest.raises(lineage.LineageError):
            lineage.verify_lineage(chain)


@pytest.mark.parametrize("limit", [0, 1, 7, 60, 400, 3000, 20000, BIG])
def test_the_ceiling_is_exact_and_the_posts_add_up(limit):
    start = lineage.initial_state()
    meter = Meter(limit)
    state = lineage.step(start, LEARN, BUDGET, meter, _rng(1))
    assert meter.spent <= limit
    assert sum(state["spent"].values()) == meter.spent
    assert state["parent"] == start["digest"] and lineage.verify_lineage([start, state]) is True
    if limit == 0:
        assert state["exhausted"] is True and meter.spent == 0
        assert state["library"] == start["library"] and state["procedure"] == start["procedure"]
    if limit == BIG:
        assert state["exhausted"] is False
    for generated in _run(3, limit)[1:]:
        assert sum(generated["spent"].values()) <= limit


def test_the_inherited_procedure_changes_what_is_evaluated():
    base = lineage.initial_state()
    everything = lineage.replace_procedure(base, _procedure(admit=11))
    nothing = lineage.replace_procedure(base, _nothing())
    assert everything["library"] == nothing["library"]
    witnesses = []
    for seed in range(6):
        one = lineage.step(everything, LEARN, BUDGET, Meter(BIG), _rng(seed))
        two = lineage.step(nothing, LEARN, BUDGET, Meter(BIG), _rng(seed))
        if one["evaluated"] and one["evaluated"] != two["evaluated"]:
            witnesses.append(seed)
    assert witnesses


def test_held_out_and_control_tasks_are_refused():
    held = [task for family in tasks.HELD_OUT for task in tasks.tasks(family)[:1]]
    control = [engine.Task("control", family, 2, 0b0110) for family in getattr(tasks, "CONTROL", ())]
    unknown = [engine.Task("unknown", "no-such-family", 2, 0b0110)]
    assert held
    for bad in [[task] for task in (*held, *control)] + [unknown]:
        with pytest.raises(lineage.LineageError):
            lineage.run_lineage(1, bad, BUDGET, BIG, 1)
        with pytest.raises(lineage.LineageError):
            lineage.run_lineage(1, LEARN + bad, BUDGET, BIG, 1)


def test_selection_uses_learning_tasks_only_and_never_asks_for_held_out(monkeypatch):
    original = tasks.tasks

    def guarded(family, *args, **kwargs):
        if family in tasks.HELD_OUT:
            raise AssertionError(f"held-out family requested: {family}")
        return original(family, *args, **kwargs)

    real = engine.improved_by
    seen = []

    def spy(first, given, *args, **kwargs):
        seen.append([task.name for task in given])
        return real(first, given, *args, **kwargs)

    monkeypatch.setattr(tasks, "tasks", guarded)
    monkeypatch.setattr(engine, "improved_by", spy)
    states = _run(3)
    assert len(states) == 4 and seen
    assert all(names == [task.name for task in LEARN] for names in seen)


def test_a_parent_is_kept_when_no_candidate_is_strictly_better():
    single = [engine.Task("x", "and", 2, 0b1010)]
    base = lineage.replace_procedure(lineage.initial_state(), _procedure(admit=11))
    tried = []
    for seed in range(4):
        out = lineage.step(base, single, 100, Meter(BIG), _rng(seed))
        assert out["adopted"] is False and out["procedure"] == base["procedure"]
        assert out["library"] == base["library"] and out["score"] == out["parent_score"]
        tried.append(out["evaluated"])
    assert any(tried)


def test_a_candidate_is_adopted_only_when_strictly_better():
    states = _run(4)
    for before, after in zip(states, states[1:]):
        if after["adopted"]:
            assert tuple(after["score"]) > tuple(after["parent_score"])
            assert after["procedure"] != before["procedure"]
        else:
            assert after["score"] == after["parent_score"]
            assert after["procedure"] == before["procedure"]


def test_replace_procedure_restores_the_ancestor_without_touching_the_library():
    states = _run(3)
    ancestral = lineage.replace_procedure(states[3], cp.seed_procedure())
    assert ancestral["library"] == states[3]["library"]
    assert ancestral["procedure"] == cp.to_record(cp.seed_procedure())
    assert ancestral["index"] == states[3]["index"] and ancestral["parent"] == states[3]["parent"]
    assert lineage.verify_lineage(states[:3] + [ancestral]) is True


def test_bad_arguments_are_refused():
    for bad in (-1, True, 1.5):
        with pytest.raises(lineage.LineageError):
            lineage.run_lineage(bad, LEARN, BUDGET, BIG, 1)
        with pytest.raises(lineage.LineageError):
            lineage.run_lineage(1, LEARN, BUDGET, bad, 1)
