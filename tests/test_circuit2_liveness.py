"""Vivacité du chemin circuit2 : aucune amélioration de score exigée."""
from dataclasses import replace
import sys
from pathlib import Path

import pytest

try:
    import circuit2_liveness as lv
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import circuit2_liveness as lv

BUDGET = dict(mutations=12, runs=8, randoms=2)


def test_terminaison_et_bilan():
    b = lv.diagnose(seed=1, **BUDGET)
    assert b["mutations_done"] == 12
    assert b["randoms_done"] == 2
    assert b["procedures"] == 1 + 12 + 2
    assert b["runs_done"] == b["procedures"] * b["cases_per_procedure"]
    assert b["cases_per_procedure"] >= 8
    assert b["gates_total"] == sum(n * b["cases_per_procedure"] for n in b["steps_per_procedure"])
    assert b["roundtrips_ok"] == b["procedures"]
    assert len(b["digests"]) == b["procedures"]


def test_contrats():
    assert lv.diagnose(seed=2, **BUDGET)["violations"] == []


def test_mutate_ne_modifie_pas_l_original():
    p = lv.cp.seed_procedure()
    avant = lv._record_json(p)
    rng = lv.random.Random("test|mutate")
    q = lv.cp.mutate(p, rng)
    assert lv._record_json(p) == avant
    assert q is not None
    lv.cp.validate(q)


def test_reproductibilite():
    a = lv.diagnose(seed=3, **BUDGET)
    assert a == lv.diagnose(seed=3, **BUDGET)
    assert a["digests"] != lv.diagnose(seed=4, **BUDGET)["digests"]


def test_taches_apprentissage():
    b = lv.diagnose(seed=0, **BUDGET)
    assert b["learn_task_count"] > 0
    learn = {str(x) for x in lv.tasks.LEARN}
    assert set(b["learn_families"]) <= learn


def test_dependance_interne_manquante_reste_visible(monkeypatch):
    def faux_import(nom, *args, **kwargs):
        raise ModuleNotFoundError("No module named 'numpy_absent'", name="numpy_absent")

    monkeypatch.setattr(lv.importlib, "import_module", faux_import)
    with pytest.raises(ModuleNotFoundError) as info:
        lv._charger("circuit_procedure")
    assert info.value.name == "numpy_absent"


def test_module_essaye_absent_passe_au_prefixe_suivant(monkeypatch):
    sentinelle = object()
    essais = []

    def faux_import(nom, *args, **kwargs):
        essais.append(nom)
        if nom == "genesis.module_x":
            return sentinelle
        raise ModuleNotFoundError(f"No module named '{nom}'", name=nom)

    monkeypatch.setattr(lv.importlib, "import_module", faux_import)
    assert lv._charger("module_x") is sentinelle
    assert essais == ["module_x", "genesis.module_x"]


def test_procedure_de_depart_est_validee_avant_les_mutations(monkeypatch):
    noms = []
    original = lv._valider

    def espion(p, nom, violations):
        noms.append(nom)
        return original(p, nom, violations)

    monkeypatch.setattr(lv, "_valider", espion)
    lv.diagnose(seed=5, mutations=2, runs=1, randoms=1)
    assert noms[0] == "départ"
    assert noms.count("départ") == 1


def test_procedure_de_depart_refusee_donne_une_violation(monkeypatch):
    depart = lv.cp.seed_procedure()
    original = lv.cp.validate

    def validate_refuse_depart(p):
        if p == depart:
            raise lv.cp.ProcedureError("départ refusé")
        return original(p)

    monkeypatch.setattr(lv.cp, "validate", validate_refuse_depart)
    recues = []
    run_original = lv.cp.run

    def run_espion(p, traits):
        recues.append(p)
        return run_original(p, traits)

    monkeypatch.setattr(lv.cp, "run", run_espion)
    b = lv.diagnose(seed=6, mutations=0, runs=1, randoms=0)
    assert any(v.startswith("validate refuse départ") for v in b["violations"])
    assert all(p != depart for p in recues)
    assert b["procedures"] == 0
    assert b["runs_done"] == 0


def test_valider_renvoie_un_booleen_explicite():
    violations = []
    assert lv._valider(lv.cp.seed_procedure(), "ok", violations) is True
    assert violations == []
    p = lv.cp.seed_procedure()
    invalide = replace(p, admit_output=p.n_inputs + len(p.steps))
    assert lv._valider(invalide, "invalide", violations) is False
    assert len(violations) == 1
    assert violations[0].startswith("validate refuse invalide")


def test_suite_vide_donne_une_violation(monkeypatch):
    monkeypatch.setattr(lv.tasks, "circuit2_suite", lambda *a, **k: [])
    b = lv.diagnose(seed=7, mutations=0, runs=1, randoms=0)
    assert "suite circuit2 vide" in b["violations"]


def test_famille_manquante_donne_une_violation(monkeypatch):
    learn = [str(x) for x in lv.tasks.LEARN]
    retiree = learn[-1]
    restantes = [{"family": f} for f in learn[:-1]]
    monkeypatch.setattr(lv.tasks, "circuit2_suite", lambda *a, **k: restantes)
    b = lv.diagnose(seed=8, mutations=0, runs=1, randoms=0)
    assert any("absentes" in v and retiree in v for v in b["violations"])
