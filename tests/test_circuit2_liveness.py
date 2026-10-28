"""Vivacité du chemin circuit2 : aucune amélioration de score exigée."""
import sys
from pathlib import Path

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
