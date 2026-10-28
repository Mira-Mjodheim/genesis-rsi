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
import freeze_circuit2_executables as fce  # noqa: E402
import freeze_circuit2_plan as fcp  # noqa: E402
import run_circuit2_arms as rca  # noqa: E402
import run_circuit2_campaign as rcc  # noqa: E402
from genesis import circuit_engine as ce  # noqa: E402
from genesis import circuit_tasks as ct  # noqa: E402


def _plan():
    return adj.load_plan(adj.DEFAULT_PLAN)


_REAL_VERIFY = adj.verify_executables


@pytest.fixture(autouse=True)
def _neutralize_integrity(monkeypatch):
    """Le manifeste officiel n'existe pas encore : vérification neutralisée par défaut."""
    monkeypatch.setattr(adj, "verify_executables", lambda *args, **kwargs: None)


@pytest.fixture
def real_integrity(monkeypatch):
    """Rétablit la vérification réelle pour les tests d'intégrité."""
    monkeypatch.setattr(adj, "verify_executables", _REAL_VERIFY)


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


def _integrity_tree(tmp_path):
    """Faux exécutables et manifeste généré par le script de gel."""
    root = tmp_path / "racine"
    rels = ["scripts/un.py", "genesis/deux.py"]
    for index, rel in enumerate(rels):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"contenu factice {index}\n".encode("utf-8"))
    manifest = tmp_path / "EXECUTABLES.json"
    fce.write_manifest(manifest, root=root, paths=rels)
    return root, manifest, rels


def _bind_root(monkeypatch, root, manifest, rels):
    """Vérification réelle, relative à `root` (faux exécutables) et au canonique `manifest`."""
    monkeypatch.setattr(
        adj,
        "verify_executables",
        lambda manifest_path=None, root_arg=None: _REAL_VERIFY(
            manifest_path, root=root, canonical_path=manifest, required=rels
        ),
    )


def test_integrity_valid_manifest_accepted(real_integrity, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert sorted(data["files"]) == sorted(rels)
    result = adj.verify_executables(
        manifest, root=root, canonical_path=manifest, required=rels
    )
    assert result is None


def test_integrity_altered_file_refused(real_integrity, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    (root / rels[0]).write_bytes(b"altere\n")
    with pytest.raises(adj.PlanError):
        adj.verify_executables(
            manifest, root=root, canonical_path=manifest, required=rels
        )


def test_integrity_missing_file_refused(real_integrity, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    (root / rels[1]).unlink()
    with pytest.raises(adj.PlanError):
        adj.verify_executables(
            manifest, root=root, canonical_path=manifest, required=rels
        )


def test_integrity_absent_manifest_refused(real_integrity, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    with pytest.raises(adj.PlanError):
        adj.verify_executables(
            tmp_path / "absent.json", root=root, canonical_path=manifest, required=rels
        )


def test_integrity_unreadable_manifest_refused(real_integrity, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    manifest.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(adj.PlanError):
        adj.verify_executables(
            manifest, root=root, canonical_path=manifest, required=rels
        )


def test_freeze_executables_refuses_overwrite_and_missing(tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    with pytest.raises(FileExistsError):
        fce.write_manifest(manifest, root=root, paths=rels)
    autre = tmp_path / "autre.json"
    with pytest.raises(FileNotFoundError):
        fce.write_manifest(autre, root=root, paths=rels + ["absent.py"])
    assert not autre.exists()


def test_main_refuses_altered_executable_without_computing(monkeypatch, capsys, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    (root / rels[0]).write_bytes(b"altere\n")
    _bind_root(monkeypatch, root, manifest, rels)

    def forbidden(*args, **kwargs):
        raise AssertionError("aucun calcul attendu en cas de refus")

    monkeypatch.setattr(adj, "final_library", forbidden)
    monkeypatch.setattr(adj, "measure_held_out", forbidden)
    out = _results_tmp()
    seed = str(_plan()["seeds"][0])
    argv = ["--seeds", seed, "--out", str(out), "--integrity", str(manifest)]
    try:
        _assert_refused(capsys, out, argv)
    finally:
        out.unlink(missing_ok=True)


def test_main_accepts_valid_executables(monkeypatch, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    _bind_root(monkeypatch, root, manifest, rels)
    _use_stubs(monkeypatch)
    out = _results_tmp()
    seed = str(_plan()["seeds"][0])
    argv = ["--seeds", seed, "--out", str(out), "--integrity", str(manifest)]
    try:
        assert adj.main(argv) == 0
    finally:
        out.unlink(missing_ok=True)


def test_measure_held_out_refuses_altered_executables_before_held_out(monkeypatch, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    (root / rels[0]).write_bytes(b"altere\n")
    _bind_root(monkeypatch, root, manifest, rels)
    _guard(monkeypatch)
    with pytest.raises(adj.PlanError):
        adj.measure_held_out(ce.Engine(), None, manifest)
    with pytest.raises(adj.PlanError):
        adj.measure_held_out(ce.Engine(), None, tmp_path / "absent.json")


def test_integrity_incomplete_manifest_refused(real_integrity, tmp_path):
    root, _manifest, rels = _integrity_tree(tmp_path)
    sans_rapport = "scripts/sans_rapport.py"
    (root / sans_rapport).write_bytes(b"sans rapport\n")
    incomplet = tmp_path / "incomplet.json"
    fce.write_manifest(incomplet, root=root, paths=[sans_rapport])
    with pytest.raises(adj.PlanError):
        adj.verify_executables(
            incomplet, root=root, canonical_path=incomplet, required=rels
        )
    surplus = tmp_path / "surplus.json"
    fce.write_manifest(surplus, root=root, paths=rels + [sans_rapport])
    with pytest.raises(adj.PlanError):
        adj.verify_executables(
            surplus, root=root, canonical_path=surplus, required=rels
        )


def test_integrity_recomputed_manifest_after_alteration_refused(real_integrity, monkeypatch, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    _forbid_compute(monkeypatch)
    (root / rels[0]).write_bytes(b"altere\n")
    recalcule = tmp_path / "recalcule.json"
    fce.write_manifest(recalcule, root=root, paths=rels)
    with pytest.raises(adj.PlanError, match="différent du manifeste canonique"):
        adj.verify_executables(
            recalcule, root=root, canonical_path=manifest, required=rels
        )


def test_integrity_conforming_copy_accepted(real_integrity, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    copie = tmp_path / "copie.json"
    copie.write_bytes(manifest.read_bytes())
    result = adj.verify_executables(
        copie, root=root, canonical_path=manifest, required=rels
    )
    assert result is None


def _real_canonical(tmp_path):
    """Manifeste canonique des vrais exécutables, écrit hors du dépôt."""
    canon = tmp_path / "canon.json"
    fce.write_manifest(canon, root=ROOT, paths=fce.EXECUTABLES)
    return canon


def test_integrity_real_files_conforming_copy_accepted(real_integrity, tmp_path):
    canon = _real_canonical(tmp_path)
    copie = tmp_path / "copie.json"
    copie.write_bytes(canon.read_bytes())
    assert adj.verify_executables(copie, canonical_path=canon) is None


def test_integrity_real_files_modified_copy_refused(real_integrity, monkeypatch, tmp_path):
    canon = _real_canonical(tmp_path)
    _forbid_compute(monkeypatch)
    data = json.loads(canon.read_text(encoding="utf-8"))
    rel = sorted(data["files"])[0]
    data["files"][rel] = "0" * 64
    data["digest"] = fce.global_digest(data["files"])
    modifie = tmp_path / "modifie.json"
    modifie.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(adj.PlanError, match="différent du manifeste canonique"):
        adj.verify_executables(modifie, canonical_path=canon)


def _forbid_compute(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("aucun calcul attendu en cas de refus")

    monkeypatch.setattr(adj, "final_library", forbidden)
    monkeypatch.setattr(adj, "measure_held_out", forbidden)


def test_main_with_canonical_manifest_returns_zero(real_integrity, monkeypatch, tmp_path):
    canon = _real_canonical(tmp_path)
    monkeypatch.setattr(fce, "MANIFEST_PATH", canon)
    _use_stubs(monkeypatch)
    out = _results_tmp()
    seed = str(_plan()["seeds"][0])
    try:
        assert adj.main(["--seeds", seed, "--out", str(out)]) == 0
    finally:
        out.unlink(missing_ok=True)


def test_main_refuses_without_canonical_manifest(real_integrity, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(fce, "MANIFEST_PATH", tmp_path / "absent.json")
    _forbid_compute(monkeypatch)
    out = _results_tmp()
    seed = str(_plan()["seeds"][0])
    try:
        _assert_refused(capsys, out, ["--seeds", seed, "--out", str(out)])
    finally:
        out.unlink(missing_ok=True)


def test_main_refuses_recomputed_manifest_without_computing(monkeypatch, capsys, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    (root / rels[0]).write_bytes(b"altere\n")
    recalcule = tmp_path / "recalcule.json"
    fce.write_manifest(recalcule, root=root, paths=rels)
    _bind_root(monkeypatch, root, manifest, rels)
    _forbid_compute(monkeypatch)
    out = _results_tmp()
    seed = str(_plan()["seeds"][0])
    argv = ["--seeds", seed, "--out", str(out), "--integrity", str(recalcule)]
    try:
        _assert_refused(capsys, out, argv)
    finally:
        out.unlink(missing_ok=True)


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


def _fake_record(same, exhausted=True):
    """Enregistrement de génération minimal, sans calcul."""
    return {
        "exhausted": exhausted,
        "digest": "d0",
        "transmission": {"digest": "d0" if same else "d1", "library_digest": "d0"},
    }


def _stub_final_library(arm, seed, tasks, limit, budget, generations):
    """Stub (non réel) : petits enregistrements, Engine() vide."""
    records = [dict(_fake_record(False, False), stub=True, arm=arm, seed=seed)]
    return records, ce.Engine(), None, None


def _stub_measure_held_out(engine, plan_path=None, integrity=None):
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


def test_main_writes_four_rows_with_doubled_arms(monkeypatch):
    """Écriture du fichier avec bras doublés : aucun ArmRun n'est exécuté."""
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


def _reference_arm(arm, seed, plan):
    """Référence indépendante de adj.final_library, aux budgets gelés."""
    limit = plan["budgets"]["per_generation_limit"]
    budget = plan["budgets"]["task_budget"]
    tasks = fcp.learn_tasks()
    # run_arm : generations, limit, budget.
    ref = rca.run_arm(arm, seed, tasks, 1, limit, budget)
    if isinstance(ref, dict):
        ref = ref["generations"]
    # run_arm ne renvoie pas l'Engine : relecture via un ArmRun piloté une fois.
    run = rcc.new_run(arm, seed, tasks, limit, budget)
    run.step()
    engine = run.state.engine if arm == "inherited_lineage" else run.engine
    return ref, engine


def test_main_four_arms_real_arm_runs(monkeypatch):
    """Quatre bras réels aux budgets gelés ; seule la mesure held-out est doublée."""
    plan = _plan()
    if len(plan["seeds"]) == 1 and plan["budgets"]["generations"] == 1:
        pytest.skip("le plan ne permet pas d'exécution réduite")
    monkeypatch.setattr(adj, "measure_held_out", _stub_measure_held_out)
    seed = plan["seeds"][0]
    limit = plan["budgets"]["per_generation_limit"]
    budget = plan["budgets"]["task_budget"]
    out = _results_tmp()
    try:
        argv = ["--seeds", str(seed), "--generations", "1", "--out", str(out)]
        assert adj.main(argv) == 0
        assert out.exists()
        data = _read(out)
    finally:
        out.unlink(missing_ok=True)
    assert data["plan_digest"] == plan["digest"]
    assert "machinery_commit" in data
    assert data["task_budget"] == budget
    assert data["per_generation_limit"] == limit
    assert data["generations"] == 1
    assert data["seeds"] == [seed]
    assert data["arms"] == list(rca.ARMS)
    assert data["scale"] == "reduced"
    rows = data["rows"]
    assert len(rows) == 4
    assert [row["arm"] for row in rows] == list(rca.ARMS)
    for row in rows:
        arm = row["arm"]
        ref, ref_engine = _reference_arm(arm, seed, plan)
        recs, engine, _final, _initial = adj.final_library(
            arm, seed, fcp.learn_tasks(), limit, budget, 1
        )
        assert row["generations"] == 1
        assert row["library_fingerprint"] == adj.fingerprint(ref_engine.record())
        assert rca.library_digest(ref_engine) == ref[-1]["transmission"]["library_digest"]
        expected = rcc.STOP_REASON if rcc._stops(ref[-1]) else rcc.LIMIT_REASON
        assert row["stop_reason"] == expected
        assert [adj.fingerprint(r) for r in recs] == [adj.fingerprint(r) for r in ref]
        assert recs[-1]["transmission"]["library_digest"] == rca.library_digest(engine)


class _FakeRun:
    """ArmRun doublé : compte les appels de step()."""

    def __init__(self, same):
        self.same = same
        self.calls = 0
        self.procedure = None
        self.engine = ce.Engine()

    def step(self):
        self.calls += 1
        return _fake_record(self.same)


def _inject_fake_run(monkeypatch, same):
    run = _FakeRun(same)
    monkeypatch.setattr(adj, "new_run", lambda *args, **kwargs: run)
    return run


def test_stop_reason_exhausted_without_adoption(monkeypatch):
    run = _inject_fake_run(monkeypatch, True)
    records, _engine, _final, _initial = adj.final_library(
        "fixed_procedure", 0, [], 2, 1, 3
    )
    assert run.calls == 1
    assert len(records) == 1
    assert adj.stop_reason(records) == "exhausted_without_adoption"


def test_stop_reason_generation_limit(monkeypatch):
    run = _inject_fake_run(monkeypatch, False)
    records, _engine, _final, _initial = adj.final_library(
        "fixed_procedure", 0, [], 2, 1, 3
    )
    assert run.calls == 3
    assert len(records) == 3
    assert adj.stop_reason(records) == "generation_limit"


def _scale_of(monkeypatch, extra):
    _use_stubs(monkeypatch)
    plan = _plan()
    out = _results_tmp()
    argv = (
        ["--seeds"] + [str(s) for s in plan["seeds"]]
        + ["--generations", str(plan["budgets"]["generations"]), "--out", str(out)]
        + extra
    )
    try:
        assert adj.main(argv) == 0
        return _read(out)["scale"]
    finally:
        out.unlink(missing_ok=True)


def test_scale_reduced_with_single_arm(monkeypatch):
    scale = _scale_of(monkeypatch, ["--arms", "inherited_lineage"])
    assert scale == "reduced"


def test_scale_full_with_complete_campaign(monkeypatch):
    assert _scale_of(monkeypatch, []) == "full"


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
    assert data["plan_digest"] == plan["digest"]
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


def _same_json_other_bytes(raw):
    """Variantes au contenu JSON égal mais aux octets différents."""
    import re

    data = json.loads(raw)
    reformatted = [
        json.dumps(data, indent=4),
        json.dumps(data, indent=4) + "\n",
        json.dumps(data, separators=(",", ":")),
    ]
    rel = sorted(data["files"])[0]
    pattern = (
        re.escape(json.dumps(rel))
        + r"\s*:\s*"
        + re.escape(json.dumps(data["files"][rel]))
    )
    match = re.search(pattern, raw)
    assert match, "clé de fichier introuvable dans le manifeste"
    duplicated = raw[: match.end()] + "," + match.group(0) + raw[match.end():]
    reformatted = [v for v in reformatted if v != raw]
    assert reformatted, "aucune variante reformatée distincte du canonique"
    return reformatted, duplicated


def _same_json_sources(tmp_path, source):
    """(racine, canonique, requis) : arbre factice ou vrais exécutables."""
    if source == "vrais_executables":
        return ROOT, _real_canonical(tmp_path), fce.EXECUTABLES
    root, manifest, rels = _integrity_tree(tmp_path)
    return root, manifest, rels


@pytest.mark.parametrize("source", ["arbre_factice", "vrais_executables"])
@pytest.mark.parametrize("kind", ["reformate", "cle_dupliquee"])
def test_integrity_same_json_other_bytes_refused(real_integrity, monkeypatch, tmp_path, source, kind):
    _forbid_compute(monkeypatch)
    root, canon, required = _same_json_sources(tmp_path, source)
    raw = canon.read_text(encoding="utf-8")
    reformatted, duplicated = _same_json_other_bytes(raw)
    variants = reformatted if kind == "reformate" else [duplicated]
    for index, text in enumerate(variants):
        variant = tmp_path / f"variante_{index}.json"
        variant.write_text(text, encoding="utf-8")
        # Sans contenu JSON égal, le test ne prouverait rien.
        assert json.loads(text) == json.loads(raw)
        assert variant.read_bytes() != canon.read_bytes()
        with pytest.raises(adj.PlanError, match="différent du manifeste canonique"):
            adj.verify_executables(
                variant, root=root, canonical_path=canon, required=required
            )


def test_main_refuses_same_json_other_bytes_without_computing(monkeypatch, capsys, tmp_path):
    root, manifest, rels = _integrity_tree(tmp_path)
    reformatted, duplicated = _same_json_other_bytes(manifest.read_text(encoding="utf-8"))
    _bind_root(monkeypatch, root, manifest, rels)
    _forbid_compute(monkeypatch)
    seed = str(_plan()["seeds"][0])
    for index, text in enumerate(reformatted + [duplicated]):
        variant = tmp_path / f"variante_{index}.json"
        variant.write_text(text, encoding="utf-8")
        out = _results_tmp()
        argv = ["--seeds", seed, "--out", str(out), "--integrity", str(variant)]
        try:
            _assert_refused(capsys, out, argv)
        finally:
            out.unlink(missing_ok=True)


@pytest.mark.parametrize("arm", ["frozen_engine", "inherited_lineage"])
def test_main_end_to_end_real_computation(real_integrity, monkeypatch, tmp_path, arm):
    """Parcours réduit réel : aucune doublure sur final_library, la mesure ni new_run."""
    plan = _plan()
    budget = plan["budgets"]["task_budget"]
    limit = plan["budgets"]["per_generation_limit"]
    seed = plan["seeds"][0]
    canon = tmp_path / "canon.json"
    fce.write_manifest(canon, root=ROOT, paths=fce.EXECUTABLES)
    monkeypatch.setattr(fce, "MANIFEST_PATH", canon)
    out = _results_tmp()
    argv = ["--seeds", str(seed), "--generations", "1", "--arms", arm, "--out", str(out)]
    try:
        assert adj.main(argv) == 0
        data = _read(out)
    finally:
        out.unlink(missing_ok=True)
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["arm"] == arm
    assert row["seed"] == seed
    assert row["generations"] == 1
    assert isinstance(row["held_out_yield"], (int, float))
    assert not isinstance(row["held_out_yield"], bool)
    _records, engine, _final, _initial = adj.final_library(
        arm, seed, fcp.learn_tasks(), limit, budget, 1
    )
    assert row["library_fingerprint"] == adj.fingerprint(engine.record())
    held_out = list(ct.circuit2_suite(tuple(ct.HELD_OUT)))
    reference = ce.measure(
        ce.attempt(adj.engine_from_record(engine.record()), held_out, budget)
    )[0]
    assert row["held_out_yield"] == reference
    assert data["plan_digest"] == plan["digest"]
    assert data["arms"] == [arm]
    assert data["scale"] == "reduced"
