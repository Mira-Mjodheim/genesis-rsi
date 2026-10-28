"""Tests hors réseau de l'adjudication de lignée (sans modèle)."""
import copy
import json
import sys
import uuid
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


def _stub_final_library(arm, seed, tasks, limit, budget, generations):
    """Stub (non réel) : petits enregistrements, Engine() vide."""
    records = [{"stub": True, "arm": arm, "seed": seed}]
    return records, ce.Engine(), None, None


def _stub_measure_held_out(engine, plan_path=None):
    """Stub (non réel) : rendement fixe, sans évaluation."""
    return 0.0


def _use_stubs(monkeypatch):
    monkeypatch.setattr(adj, "final_library", _stub_final_library)
    monkeypatch.setattr(adj, "measure_held_out", _stub_measure_held_out)


def _results_tmp():
    return adj.ROOT / "results" / f"tmp_adjudication_{uuid.uuid4().hex}.json"


@pytest.mark.parametrize("arm", list(rca.ARMS))
def test_procedure_record_every_arm(arm):
    plan = _plan()
    run = adj.new_run(
        arm,
        plan["seeds"][0],
        fcp.learn_tasks(),
        plan["budgets"]["per_generation_limit"],
        plan["budgets"]["task_budget"],
    )
    record = adj._procedure_record(run, arm)
    if arm == "frozen_engine":
        assert record is None


def _read(out):
    return json.loads(out.read_text(encoding="utf-8"))


def test_main_four_arms_writes_file(monkeypatch):
    _use_stubs(monkeypatch)
    plan = _plan()
    out = _results_tmp()
    try:
        argv = ["--seeds", str(plan["seeds"][0]), "--generations", "1", "--out", str(out)]
        assert adj.main(argv) == 0
        assert out.exists()
        assert len(_read(out)["rows"]) == 4
    finally:
        out.unlink(missing_ok=True)


def test_main_metadata_reduced_scale(monkeypatch):
    _use_stubs(monkeypatch)
    plan = _plan()
    if len(plan["seeds"]) == 1 and plan["budgets"]["generations"] == 1:
        pytest.skip("le plan ne permet pas d'exécution réduite")
    seed = plan["seeds"][0]
    out = _results_tmp()
    try:
        argv = ["--seeds", str(seed), "--generations", "1", "--out", str(out)]
        assert adj.main(argv) == 0
        data = _read(out)
    finally:
        out.unlink(missing_ok=True)
    assert data["plan_digest"] == adj.fingerprint(plan)
    assert "machinery_commit" in data
    assert data["task_budget"] == plan["budgets"]["task_budget"]
    assert data["per_generation_limit"] == plan["budgets"]["per_generation_limit"]
    assert data["generations"] == 1
    assert data["seeds"] == [seed]
    assert data["arms"] == list(rca.ARMS)
    assert data["scale"] == "reduced"


_REFUSALS = {
    "seed_hors_plan": lambda p, s: ["--seeds", str(max(p["seeds"]) + 1000)],
    "seed_dupliquee": lambda p, s: ["--seeds", s, s],
    "generations_zero": lambda p, s: ["--seeds", s, "--generations=0"],
    "generations_negatif": lambda p, s: ["--seeds", s, "--generations=-1"],
    "generations_superieur_plan": lambda p, s: [
        "--seeds", s, f"--generations={p['budgets']['generations'] + 1}"
    ],
    "bras_inconnu": lambda p, s: ["--seeds", s, "--arms", "bras_inconnu"],
    "bras_duplique": lambda p, s: ["--seeds", s, "--arms", list(rca.ARMS)[0], list(rca.ARMS)[0]],
}


def _assert_refused(capsys, out, argv):
    rc = adj.main(argv)
    assert rc == 2
    assert capsys.readouterr().err.startswith("erreur : ")
    assert not out.exists()


@pytest.mark.parametrize("case", sorted(_REFUSALS))
def test_main_refuses_invalid_request(monkeypatch, capsys, case):
    def forbidden(*args, **kwargs):
        raise AssertionError("aucun calcul attendu en cas de refus")
    monkeypatch.setattr(adj, "final_library", forbidden)
    monkeypatch.setattr(adj, "measure_held_out", forbidden)
    plan = _plan()
    out = _results_tmp()
    try:
        extra = _REFUSALS[case](plan, str(plan["seeds"][0]))
        _assert_refused(capsys, out, extra + ["--out", str(out)])
    finally:
        out.unlink(missing_ok=True)


def test_main_refuses_out_outside_results(monkeypatch, capsys, tmp_path):
    _use_stubs(monkeypatch)
    out = tmp_path / "sortie.json"
    seed = str(_plan()["seeds"][0])
    _assert_refused(capsys, out, ["--seeds", seed, "--out", str(out)])


def test_validate_request_refuses_bool_generations():
    plan = _plan()
    arms = list(rca.ARMS)
    seeds = [plan["seeds"][0]]
    assert adj._validate_request(plan, seeds, True, arms) is not None
    assert adj._validate_request(plan, seeds, 1, arms) is None


def test_main_rejects_limit_option(capsys, tmp_path):
    seed = str(_plan()["seeds"][0])
    argv = ["--seeds", seed, "--out", str(tmp_path / "x.json"), "--limit", "3"]
    with pytest.raises(SystemExit):
        adj.main(argv)


def _n_inputs(task):
    value = task.inputs
    return value if isinstance(value, int) else len(value)


def test_measure_held_out_evaluates_full_suite(monkeypatch):
    plan = _plan()
    suites = []
    captured = []
    original = ct.circuit2_suite

    def recording(families, *args, **kwargs):
        suite = list(original(families, *args, **kwargs))
        if tuple(families) == tuple(ct.HELD_OUT):
            suites.append(suite)
        return suite

    def stub_attempt(engine, tasks, budget):
        captured.append((list(tasks), budget))
        return None

    def stub_measure(result):
        return (0.0,)

    monkeypatch.setattr(ct, "circuit2_suite", recording)
    monkeypatch.setattr(adj.ce, "attempt", stub_attempt)
    monkeypatch.setattr(adj.ce, "measure", stub_measure)
    assert adj.measure_held_out(ce.Engine()) == 0.0
    assert len(captured) == 1
    tasks, budget = captured[0]
    expected = suites[-1]
    assert budget == plan["budgets"]["task_budget"]
    assert len(tasks) == len(expected)
    assert all(a is b for a, b in zip(tasks, expected))
    # Les tâches à 4 entrées ou plus (famille multiply) ne sont plus écartées.
    assert max(_n_inputs(t) for t in tasks) >= 4
