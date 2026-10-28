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


@pytest.fixture(autouse=True)
def canonical(tmp_path, sealed, monkeypatch):
    path = tmp_path / "CANONICAL.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    monkeypatch.setattr(campaign, "CANONICAL_PLAN_PATH", path)
    return path


def _record(exhausted=False, adopted=False, label="d", spent=10):
    return {"exhausted": exhausted, "digest": label, "spent": spent, "transmission": {"digest": (label + "+") if adopted else label}}


def _fake_run_arm(calls, script=None):
    """Faux run_arm instrumenté : enregistre chaque appel, enregistrements contrôlés (fixtures unitaires)."""

    def run_arm(arm, seed, learn, generations, limit, budget):
        calls.append({"arm": arm, "seed": seed, "generations": generations, "learn": learn, "limit": limit, "budget": budget})
        make = script or (lambda a, s, g: _record())
        return {"arm": arm, "seed": seed, "generations": [make(arm, seed, g) for g in range(1, generations + 1)]}

    return run_arm


def _no_run_all(*args, **kwargs):
    raise AssertionError("run_all ne doit plus être appelé par le lanceur")


def _patch(monkeypatch, calls, script=None):
    monkeypatch.setattr(campaign.arms, "run_all", _no_run_all)
    monkeypatch.setattr(campaign.arms, "run_arm", _fake_run_arm(calls, script))


def _gens_for(calls, arm, seed):
    return [c["generations"] for c in calls if c["arm"] == arm and c["seed"] == seed]


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


def test_run_arm_receives_exactly_the_plan_budgets_learn_tasks_and_seeds(sealed, monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    campaign.run_campaign(sealed)
    count = sealed["budgets"]["generations"]
    assert list(dict.fromkeys(c["arm"] for c in calls)) == list(campaign.arms.ARMS)
    assert {c["seed"] for c in calls} == set(sealed["seeds"])
    for call in calls:
        assert call["limit"] == sealed["budgets"]["per_generation_limit"]
        assert call["budget"] == sealed["budgets"]["task_budget"]
        assert list(call["learn"]) == freeze.learn_tasks()
    for arm in campaign.arms.ARMS:
        for seed in sealed["seeds"]:
            assert _gens_for(calls, arm, seed) == list(range(1, count + 1))
    given = calls[0]["learn"]
    assert given and {t.family for t in given} <= set(tasks.LEARN)


def test_seeds_outside_the_plan_or_too_many_generations_are_refused(sealed, monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    too_many = sealed["budgets"]["generations"] + 1
    for kwargs in ({"seeds": [999]}, {"seeds": [0, 999]}, {"seeds": []}, {"generations": too_many}, {"generations": 0}):
        with pytest.raises(ValueError):
            campaign.run_campaign(sealed, **kwargs)
    assert calls == []


def test_scale_is_reduced_for_a_sub_campaign_and_full_otherwise(sealed, monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    small = campaign.run_campaign(sealed, seeds=[1, 0], generations=1)
    assert small["scale"] == "reduced" and small["seeds"] == [1, 0] and small["generations"] == 1
    fewer = campaign.run_campaign(sealed, generations=1)
    assert fewer["scale"] == "reduced"
    full = campaign.run_campaign(sealed, seeds=list(sealed["seeds"]), generations=sealed["budgets"]["generations"])
    assert full["scale"] == "full" and full["seeds"] == sealed["seeds"]
    assert full["plan_digest"] == sealed["digest"] and full["machinery_commit"] == COMMIT
    assert set(full["arms"]) == set(ARMS)


def test_a_second_write_to_the_same_output_is_refused(plan_path, tmp_path, monkeypatch):
    _patch(monkeypatch, [])
    out = tmp_path / "OUT.json"
    argv = ["--plan", str(plan_path), "--seeds", "0", "--generations", "1", "--out", str(out)]
    assert campaign.main(argv) == 0
    written = out.read_text(encoding="utf-8")
    assert campaign.main(argv) != 0
    assert out.read_text(encoding="utf-8") == written
    assert json.loads(written)["scale"] == "reduced"


def test_the_output_has_no_gain_or_success_key(sealed, monkeypatch):
    _patch(monkeypatch, [])
    result = campaign.run_campaign(sealed, seeds=[0], generations=1)
    keys = [k.lower() for k in _keys(result)]
    assert keys and not [k for k in keys if any(word in k for word in FORBIDDEN)]


def _bump_costs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if "cost" in str(key) and isinstance(value, dict) and value and all(
                isinstance(v, int) and not isinstance(v, bool) for v in value.values()
            ):
                for name in value:
                    value[name] += 1
                return True
            if _bump_costs(value):
                return True
    elif isinstance(node, list):
        return any(_bump_costs(item) for item in node)
    return False


def _resealed_other_costs(sealed):
    other = copy.deepcopy(sealed)
    assert _bump_costs(other), "coûts de référence introuvables dans le plan"
    return freeze.seal({k: v for k, v in other.items() if k != "digest"})


def _total(value):
    if isinstance(value, dict):
        return sum(_total(v) for v in value.values())
    if isinstance(value, list):
        return sum(_total(v) for v in value)
    return value


def test_a_plan_with_modified_reference_costs_resealed_is_refused(tmp_path, sealed):
    path = tmp_path / "COSTS.json"
    path.write_text(json.dumps(_resealed_other_costs(sealed)), encoding="utf-8")
    with pytest.raises(freeze.PlanError):
        campaign.load_plan(path)


def test_an_altered_dict_passed_to_run_campaign_is_refused_without_running(sealed, monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    altered = copy.deepcopy(sealed)
    altered["criterion"]["text"] = altered["criterion"]["text"].replace("10 points", "5 points")
    assert altered["criterion"]["text"] != sealed["criterion"]["text"]
    for candidate in (altered, _resealed_other_costs(sealed)):
        with pytest.raises(freeze.PlanError):
            campaign.run_campaign(candidate, seeds=[0], generations=1)
    assert calls == []


def test_a_valid_plan_with_another_digest_is_refused(tmp_path, sealed, monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    other = freeze.build_plan(measure=lambda: {str(s): 101 for s in freeze.SEEDS}, machinery_commit=COMMIT)
    freeze.verify_plan(other)
    assert other["digest"] != sealed["digest"]
    with pytest.raises(freeze.PlanError):
        campaign.check_plan(other)
    with pytest.raises(freeze.PlanError):
        campaign.run_campaign(other)
    path = tmp_path / "OTHER_VALID.json"
    path.write_text(json.dumps(other), encoding="utf-8")
    assert campaign.main(["--plan", str(path), "--seeds", "0", "--generations", "1"]) == 2
    assert calls == []


def test_a_missing_or_invalid_canonical_plan_is_refused_without_fallback(tmp_path, sealed, monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    monkeypatch.setattr(campaign, "CANONICAL_PLAN_PATH", tmp_path / "absent.json")
    with pytest.raises(freeze.PlanError):
        campaign.canonical_digest()
    with pytest.raises(freeze.PlanError):
        campaign.run_campaign(sealed)
    broken = tmp_path / "BROKEN.json"
    broken.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(campaign, "CANONICAL_PLAN_PATH", broken)
    with pytest.raises(freeze.PlanError):
        campaign.canonical_digest()
    assert calls == []


def test_canonical_digest_is_read_from_the_published_file(canonical, sealed):
    assert campaign.canonical_digest() == sealed["digest"]
    assert campaign.canonical_digest(canonical) == sealed["digest"]


def _script(stops=None, adopted=(), bare=False):
    """Fixture unitaire : épuisement à la génération stops[(bras, graine)], avec adoption si la clé est dans adopted."""
    stops = stops or {}

    def make(arm, seed, g):
        if bare:
            return {"exhausted": True}
        key = (arm, seed)
        hit = stops.get(key) == g
        return _record(exhausted=hit, adopted=hit and key in adopted, label=f"{arm}-{seed}-{g}")

    return make


def test_stop_at_the_second_generation_is_effective_and_the_third_is_never_called(sealed, monkeypatch):
    """Fixture unitaire : enregistrements contrôlés par le faux run_arm, aucune mesure."""
    calls, arm, seed = [], ARMS[0], sealed["seeds"][0]
    count = sealed["budgets"]["generations"]
    assert count >= 3
    _patch(monkeypatch, calls, _script({(arm, seed): 2}))
    result = campaign.run_campaign(sealed, seeds=[seed], generations=count)
    assert _gens_for(calls, arm, seed) == [1, 2]
    assert not [c for c in calls if c["arm"] == arm and c["generations"] >= 3]
    run = result["arms"][arm][0]
    assert run["generations_run"] == len(run["generations"]) == 2
    assert run["stopped_early"] is True and run["stop_reason"] == "exhausted_without_adoption"
    assert sum(record["spent"] for record in run["generations"]) == 2 * 10


def test_exhaustion_with_adoption_continues_until_the_generation_limit(sealed, monkeypatch):
    """Fixture unitaire : épuisée mais digests différents (adoption) => poursuite jusqu'à count."""
    calls, arm, seed = [], ARMS[0], sealed["seeds"][0]
    count = sealed["budgets"]["generations"]
    _patch(monkeypatch, calls, _script({(arm, seed): 2}, adopted={(arm, seed)}))
    run = campaign.run_campaign(sealed, seeds=[seed], generations=count)["arms"][arm][0]
    assert _gens_for(calls, arm, seed) == list(range(1, count + 1))
    assert run["generations_run"] == len(run["generations"]) == count
    assert run["stopped_early"] is False and run["stop_reason"] == "generation_limit"


def test_missing_digests_never_truncate(sealed, monkeypatch):
    """Fixture unitaire : sans les deux digests, l'adoption n'est pas déductible ; rien n'est tronqué."""
    calls, seed = [], sealed["seeds"][0]
    count = sealed["budgets"]["generations"]
    _patch(monkeypatch, calls, _script(bare=True))
    result = campaign.run_campaign(sealed, seeds=[seed], generations=count)
    for name in ARMS:
        run = result["arms"][name][0]
        assert _gens_for(calls, name, seed) == list(range(1, count + 1))
        assert run["generations_run"] == len(run["generations"]) == count
        assert run["stopped_early"] is False and run["stop_reason"] == "generation_limit"


def test_a_stop_does_not_influence_other_arms_or_seeds(sealed, monkeypatch):
    """Fixture unitaire : arrêt à la 2e pour (bras A, graine 0) ; (bras B, graine 1) va à count."""
    calls, first, second = [], sealed["seeds"][0], sealed["seeds"][1]
    count = sealed["budgets"]["generations"]
    _patch(monkeypatch, calls, _script({(ARMS[0], first): 2}))
    result = campaign.run_campaign(sealed, seeds=[first, second], generations=count)
    assert _gens_for(calls, ARMS[0], first) == [1, 2]
    for arm, seed in ((ARMS[1], second), (ARMS[0], second), (ARMS[1], first)):
        assert _gens_for(calls, arm, seed) == list(range(1, count + 1))
    stopped, other = result["arms"][ARMS[0]][0], result["arms"][ARMS[1]][1]
    assert stopped["generations_run"] == 2 and stopped["stopped_early"] is True
    assert other["seed"] == second and other["generations_run"] == count
    assert other["stopped_early"] is False and other["stop_reason"] == "generation_limit"


def test_reduced_real_run_of_the_four_arms_applies_the_stop_rule(sealed):
    """Exécution réelle réduite : 1 graine, 1 génération, coûts factices 100 (plafond 800)."""
    seed = sealed["seeds"][0]
    result = campaign.run_campaign(sealed, seeds=[seed], generations=1)
    assert result["scale"] == "reduced" and result["seeds"] == [seed]
    assert set(result["arms"]) == set(ARMS)
    for name in ARMS:
        runs = result["arms"][name]
        assert len(runs) == 1
        run = runs[0]
        assert run["generations_run"] == len(run["generations"]) == 1
        for record in run["generations"]:
            assert record["spent"] <= record["limit"]
            assert _total(record["spend"]) == record["spent"]
        fired = any(campaign._stops(r) for r in run["generations"])
        assert run["stopped_early"] is fired
        assert run["stop_reason"] == ("exhausted_without_adoption" if fired else "generation_limit")


def test_real_run_arm_for_one_generation_is_a_prefix_of_two_generations(sealed):
    """Justifie le rejeu déterministe (bras frozen_engine, hors lignée). Temps CPU non mesuré."""
    seed = sealed["seeds"][0]
    learn = freeze.learn_tasks()
    limit, budget = sealed["budgets"]["per_generation_limit"], sealed["budgets"]["task_budget"]
    one = campaign.arms.run_arm("frozen_engine", seed, learn, 1, limit, budget)
    two = campaign.arms.run_arm("frozen_engine", seed, learn, 2, limit, budget)
    assert len(one["generations"]) == 1 and len(two["generations"]) == 2
    assert one["generations"] == two["generations"][:1]
