"""Lanceur de campagne CIRCUIT2 : hors réseau, sans modèle, plan scellé dans tmp_path."""
from __future__ import annotations

import copy
import json

import pytest

import freeze_circuit2_plan as freeze
import run_circuit2_campaign as campaign
from genesis import circuit_tasks as tasks

COMMIT = "a" * 40
ARMS = ("inherited_lineage", "frozen_engine", "fixed_procedure", "random_procedure")
FORBIDDEN = ("gain", "yield", "rendement", "succ")


@pytest.fixture(scope="module")
def sealed():
    return freeze.build_plan(measure=lambda: {str(s): 100 for s in freeze.SEEDS}, machinery_commit=COMMIT)


@pytest.fixture
def plan_path(tmp_path, sealed):
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    return path


def _fake(calls):
    def run_all(*args):
        calls.append(args)
        return {name: {"seeds": list(args[1]), "generations": args[2]} for name in ARMS}
    return run_all


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_a_valid_plan_loads(plan_path, sealed):
    assert campaign.load_plan(plan_path)["digest"] == sealed["digest"]


def test_a_missing_plan_is_refused(tmp_path):
    with pytest.raises(freeze.PlanError):
        campaign.load_plan(tmp_path / "absent.json")


def test_an_altered_plan_is_refused(tmp_path, sealed):
    altered = copy.deepcopy(sealed)
    altered["criterion"]["text"] = altered["criterion"]["text"].replace("10 points", "5 points")
    path = tmp_path / "ALTERED.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(freeze.PlanError):
        campaign.load_plan(path)


def test_a_plan_with_other_machinery_fingerprints_is_refused(tmp_path, sealed):
    other = copy.deepcopy(sealed)
    other["machinery_digests"]["genesis/circuit_engine.py"] = "0" * 64
    resealed = freeze.seal({k: v for k, v in other.items() if k != "digest"})
    path = tmp_path / "OTHER.json"
    path.write_text(json.dumps(resealed), encoding="utf-8")
    with pytest.raises(freeze.PlanError):
        campaign.load_plan(path)


def test_run_all_receives_exactly_the_plan_budgets_learn_tasks_and_seeds(sealed, monkeypatch):
    calls = []
    monkeypatch.setattr(campaign.arms, "run_all", _fake(calls))
    campaign.run_campaign(sealed)
    assert len(calls) == 1
    given, seeds, generations, limit, budget = calls[0]
    assert limit == sealed["budgets"]["per_generation_limit"]
    assert budget == sealed["budgets"]["task_budget"]
    assert seeds == sealed["seeds"] and generations == sealed["budgets"]["generations"]
    assert list(given) == freeze.learn_tasks()
    assert given and {t.family for t in given} <= set(tasks.LEARN)


def test_seeds_outside_the_plan_or_too_many_generations_are_refused(sealed, monkeypatch):
    calls = []
    monkeypatch.setattr(campaign.arms, "run_all", _fake(calls))
    too_many = sealed["budgets"]["generations"] + 1
    for kwargs in ({"seeds": [999]}, {"seeds": [0, 999]}, {"seeds": []}, {"generations": too_many}, {"generations": 0}):
        with pytest.raises(ValueError):
            campaign.run_campaign(sealed, **kwargs)
    assert calls == []


def test_scale_is_reduced_for_a_sub_campaign_and_full_otherwise(sealed, monkeypatch):
    calls = []
    monkeypatch.setattr(campaign.arms, "run_all", _fake(calls))
    small = campaign.run_campaign(sealed, seeds=[1, 0], generations=1)
    assert small["scale"] == "reduced" and small["seeds"] == [1, 0] and small["generations"] == 1
    fewer = campaign.run_campaign(sealed, generations=1)
    assert fewer["scale"] == "reduced"
    full = campaign.run_campaign(sealed, seeds=list(sealed["seeds"]), generations=sealed["budgets"]["generations"])
    assert full["scale"] == "full" and full["seeds"] == sealed["seeds"]
    assert full["plan_digest"] == sealed["digest"] and full["machinery_commit"] == COMMIT
    assert set(full["arms"]) == set(ARMS)


def test_a_second_write_to_the_same_output_is_refused(plan_path, tmp_path, monkeypatch):
    monkeypatch.setattr(campaign.arms, "run_all", _fake([]))
    out = tmp_path / "OUT.json"
    argv = ["--plan", str(plan_path), "--seeds", "0", "--generations", "1", "--out", str(out)]
    assert campaign.main(argv) == 0
    written = out.read_text(encoding="utf-8")
    assert campaign.main(argv) != 0
    assert out.read_text(encoding="utf-8") == written
    assert json.loads(written)["scale"] == "reduced"


def test_the_output_has_no_gain_or_success_key(sealed, monkeypatch):
    monkeypatch.setattr(campaign.arms, "run_all", _fake([]))
    result = campaign.run_campaign(sealed, seeds=[0], generations=1)
    keys = [k.lower() for k in _keys(result)]
    assert keys and not [k for k in keys if any(word in k for word in FORBIDDEN)]
