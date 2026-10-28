"""Orchestrateur des quatre bras CIRCUIT2 (orchestration seule, hors réseau).

Aucun gain annoncé, aucun gel, aucune famille tenue à l'écart : seules les
familles de circuit_tasks.LEARN sont acceptées (contrôle délégué à
genesis.circuit_meta_lineage._learn_tasks).

Les quatre bras partagent les mêmes tâches, la même bibliothèque initiale
Engine(), les mêmes graines et un Meter(per_generation_limit) neuf par
génération ; chaque bras possède son propre état (aucun objet partagé).

Point à trancher avant gel : le plan dit « initial procedure kept, no procedure
selection » pour frozen_engine, ce qui ressemble à fixed_procedure. Par
interprétation provisoire (NON figée), frozen_engine est ici une bibliothèque
jamais améliorée, évaluée seulement (baseline).

Les interfaces des modules genesis.circuit_* sont appelées directement, sans
introspection : empreintes par genesis.trust_root.digest_of, dépense et
drapeau « exhausted » lus dans l'état ou l'information renvoyés par les
modules. « exhausted » reste enregistré même si la baseline n'est pas payée.
Le champ « score » est celui de la bibliothèque transmise ; « selection_score »
est celui de la procédure candidate pour inherited_lineage, sinon None.
Aucune exception n'est levée pour un budget épuisé ; seule une comptabilité
incohérente est refusée. Validation technique seulement : aucune preuve de
progrès RSI.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from genesis import circuit_engine as ce  # noqa: E402
from genesis import circuit_meta_lineage as lineage  # noqa: E402
from genesis import circuit_procedure as cp  # noqa: E402
from genesis import circuit_tasks as ct  # noqa: E402
from genesis.trust_root import digest_of  # noqa: E402

ARMS = ("inherited_lineage", "frozen_engine", "fixed_procedure", "random_procedure")
POSTS = ("procedure", "synthesis", "evaluations")


def library_digest(engine):
    """Empreinte de la bibliothèque (Engine)."""
    return digest_of(engine.record())


def procedure_digest(procedure):
    """Empreinte d'une procédure ; None si absente."""
    return None if procedure is None else digest_of(cp.to_record(procedure))


def _engine_of(state):
    """Moteur vivant d'un état de lignée (attribut .engine, pas une clé)."""
    engine = getattr(state, "engine", None)
    if engine is None:
        raise RuntimeError("état de lignée sans moteur vivant (.engine absent ou None)")
    return engine


def state_digests(state):
    """Empreintes (bibliothèque, procédure) portées par l'état de lignée."""
    return library_digest(_engine_of(state)), digest_of(state["procedure"])


def _node(lib_d, proc_d):
    blob = json.dumps([lib_d, proc_d])
    return hashlib.sha256(blob.encode()).hexdigest()


def _draw_random(seed):
    rng = random.Random(f"circuit2-random|{seed}")
    n = rng.randint(0, cp.MAX_STEPS)
    return cp.random_procedure(rng, n)


def _learn(tasks):
    checked = lineage._learn_tasks(tasks)
    return copy.deepcopy(tasks if checked is None else checked)


def _score(solutions):
    """Score [résolues, -évaluations] ; None si la baseline n'est pas payée."""
    if solutions is None:
        return None
    solved, evaluations = ce.measure(solutions)
    return [solved, -evaluations]


def _view(engine, procedure, state):
    if state is not None:
        return state_digests(state)
    return library_digest(engine), procedure_digest(procedure)


def _generation(arm, engine, procedure, tasks, task_budget, meter, index):
    """Une génération hors lignée ; renvoie (engine, spent, exhausted, solutions)."""
    spent = {post: 0 for post in POSTS}
    baseline = ce._metered_attempt(engine, tasks, task_budget, meter, spent)
    if baseline is None:
        return engine, spent, True, None
    if arm == "frozen_engine":
        return engine, spent, False, baseline
    library, after, info = ce.improved_by(
        engine, tasks, task_budget, baseline, procedure, meter, generation=index
    )
    for post, value in info["spent"].items():
        spent[post] = spent.get(post, 0) + value
    return library, spent, bool(info["exhausted"]), after


def _check(spend, meter, limit):
    total = sum(spend.values())
    if meter.spent > limit or not math.isclose(total, meter.spent):
        raise RuntimeError(
            f"comptabilité incohérente : somme={total}, meter={meter.spent}, limite={limit}"
        )


def run_arm(arm, seed, tasks, generations, per_generation_limit, task_budget,
            procedure=None):
    """Exécute un bras sur une graine ; renvoie un dict JSON-sérialisable."""
    if arm not in ARMS:
        raise ValueError(f"bras inconnu : {arm!r}")
    if procedure is not None and arm != "fixed_procedure":
        raise ValueError("procédure imposée réservée à fixed_procedure")
    tasks = _learn(tasks)
    engine, state = ce.Engine(), None
    if arm == "inherited_lineage":
        state = lineage.initial_state()
    elif arm == "fixed_procedure":
        procedure = cp.seed_procedure() if procedure is None else procedure
    elif arm == "random_procedure":
        procedure = _draw_random(seed)
    records, parent = [], None
    for index in range(generations):
        meter = ce.Meter(per_generation_limit)
        lib_d, proc_d = _view(engine, procedure, state)
        if arm == "inherited_lineage":
            state = lineage.step(state, tasks, task_budget, meter,
                                 random.Random(f"meta|{seed}|{index}"))
            spend, exhausted = state["spent"], state["exhausted"]
            score = None if state["parent_score"] is None else list(state["parent_score"])
            selection_score = None if state["score"] is None else list(state["score"])
        else:
            engine, spend, exhausted, solutions = _generation(
                arm, engine, procedure, tasks, task_budget, meter, index)
            score = _score(solutions)
            selection_score = None
        spend = {post: spend[post] for post in sorted(spend)}
        _check(spend, meter, per_generation_limit)
        out_lib, out_proc = _view(engine, procedure, state)
        records.append({
            "index": index,
            "library_digest": lib_d,
            "procedure_digest": proc_d,
            "digest": _node(lib_d, proc_d),
            "parent": parent,
            "spend": spend,
            "spent": meter.spent,
            "limit": per_generation_limit,
            "exhausted": bool(exhausted),
            "score": score,
            "selection_score": selection_score,
            "transmission": {
                "library_digest": out_lib,
                "procedure_digest": out_proc,
                "digest": _node(out_lib, out_proc),
            },
        })
        parent = records[-1]["transmission"]["digest"]
    return {"arm": arm, "seed": seed, "task_budget": task_budget,
            "per_generation_limit": per_generation_limit,
            "generations": records}


def run_all(tasks, seeds, generations, per_generation_limit, task_budget):
    """Lance les quatre bras avec mêmes tâches, graines et plafond."""
    seeds = list(seeds)
    return {
        "seeds": seeds,
        "arms": {
            arm: [
                run_arm(arm, seed, tasks, generations,
                        per_generation_limit, task_budget)
                for seed in seeds
            ]
            for arm in ARMS
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", nargs="+", default=["and", "or", "parity"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0])
    ap.add_argument("--generations", type=int, default=2)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--task-budget", type=int, default=500)
    a = ap.parse_args(argv)
    tasks = ct.suite(tuple(a.families))
    out = run_all(tasks, a.seeds, a.generations, a.limit, a.task_budget)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
