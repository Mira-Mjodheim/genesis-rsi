"""Tests hors réseau de l'adjudication de lignée (sans modèle)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import adjudicate_circuit_lineage as adj  # noqa: E402
import freeze_circuit2_plan as fcp  # noqa: E402
import run_circuit2_arms as rca  # noqa: E402
from genesis import circuit_engine as ce  # noqa: E402
from genesis import circuit_tasks as ct  # noqa: E402


def _plan():
    return adj.load_plan(adj.DEFAULT_PLAN)


def _tasks(n=5):
    return list(ct.circuit2_suite(tuple(ct.HELD_OUT)))[:n]


def _hand_record():
    base = ce.Engine().record()
    if not base:
        pytest.skip("Engine() sans composant : pas de base pour la bibliothèque")
    first = base[0]
    comp = ce.Component(
        "main_a", first["arity"], tuple(tuple(s) for s in first["steps"]), 2
    )
    return ce.Engine([comp]).record()


def _yield(engine, tasks):
    budget = _plan()["budgets"]["task_budget"]
    return ce.measure(ce.attempt(engine, tasks, budget))


# Budget local, petit et hors réseau : indépendant du plan préenregistré.
ROUNDTRIP_BUDGET = 20


def _roundtrip_yield(engine, tasks):
    return ce.measure(ce.attempt(engine, tasks, ROUNDTRIP_BUDGET))


def _roundtrip_tasks(n=5):
    # Famille d'apprentissage (ct.LEARN), jamais HELD_OUT.
    return list(ct.circuit2_suite(tuple(ct.LEARN)))[:n]


def _roundtrip_hand_record():
    base = ce.Engine().record()
    assert base, "Engine() sans composant : pas de base pour la bibliothèque"
    first = base[0]
    comp = ce.Component(
        "main_a", first["arity"], tuple(tuple(s) for s in first["steps"]), 2
    )
    return ce.Engine([comp]).record()


def test_engine_from_record_roundtrip():
    tasks = _roundtrip_tasks()
    for rec in (ce.Engine().record(), _roundtrip_hand_record()):
        engine = adj.engine_from_record(rec)
        assert engine.record() == rec
        assert _roundtrip_yield(engine, tasks) == _roundtrip_yield(adj.engine_from_record(rec), tasks)


def _altered(mutate):
    bad = copy.deepcopy(_hand_record())
    mutate(bad[0])
    return bad


def test_altered_record_extra_step_refused():
    def add_step(comp):
        comp["steps"] = list(comp["steps"]) + [comp["steps"][-1]]

    with pytest.raises(ValueError):
        adj.engine_from_record(_altered(add_step))


def test_altered_record_nands_refused():
    def alter(comp):
        comp["nands"] += 1

    with pytest.raises(ValueError):
        adj.engine_from_record(_altered(alter))


def test_altered_record_table_refused():
    def alter(comp):
        comp["table"] = ("altéré", comp["table"])

    with pytest.raises(ValueError):
        adj.engine_from_record(_altered(alter))


def test_weight_alteration_passes_loader_but_fingerprint_detects():
    """Limite documentée : le chargeur n'a aucun invariant sur 'weight'.

    Un poids modifié donne un moteur valide dont record() porte ce poids ;
    l'authenticité exige une empreinte de référence indépendante.
    """
    rec = _hand_record()
    bad = copy.deepcopy(rec)
    bad[0]["weight"] += 1
    engine = adj.engine_from_record(bad)
    assert engine.record() == bad
    assert adj.fingerprint(bad) != adj.fingerprint(rec)


def _guard(monkeypatch):
    original = ct.circuit2_suite

    def guarded(families, *args, **kwargs):
        if tuple(families) == tuple(ct.HELD_OUT):
            raise AssertionError("HELD_OUT lu avant vérification du plan")
        return original(families, *args, **kwargs)

    monkeypatch.setattr(ct, "circuit2_suite", guarded)


def test_missing_plan_raises_before_held_out(monkeypatch, tmp_path):
    _guard(monkeypatch)
    with pytest.raises(adj.PlanError):
        adj.measure_held_out(ce.Engine(), tmp_path / "absent.json")


def test_altered_plan_raises_before_held_out(monkeypatch, tmp_path):
    plan = json.loads(adj.DEFAULT_PLAN.read_text(encoding="utf-8"))
    plan["budgets"]["task_budget"] += 1
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    _guard(monkeypatch)
    with pytest.raises(adj.PlanError):
        adj.measure_held_out(ce.Engine(), path)


def test_final_library_matches_run_arm():
    plan = _plan()
    tasks = fcp.learn_tasks()
    budget = plan["budgets"]["task_budget"]
    recs, engine, _final, _initial = adj.final_library(
        "fixed_procedure", 0, tasks, 2, budget, 1
    )
    # final_library : limit, budget, generations ; run_arm : generations, limit, budget.
    ref = rca.run_arm("fixed_procedure", 0, tasks, 1, 2, budget)
    if isinstance(ref, dict):
        ref = ref["generations"]
    assert len(recs) == 1 == len(ref)
    assert [adj.fingerprint(r) for r in recs] == [adj.fingerprint(r) for r in ref]
    last = recs[-1]
    assert last["transmission"]["library_digest"] == rca.library_digest(engine)
    reloaded = adj.engine_from_record(engine.record())
    assert reloaded.record() == engine.record()
    assert adj.fingerprint(reloaded.record()) == adj.fingerprint(engine.record())
