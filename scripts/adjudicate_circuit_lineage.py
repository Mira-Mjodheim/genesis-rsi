"""Adjudication de la lignée de circuits : rendements held-out par bras et par graine.

Ce script ne calcule aucun gain, seuil ni succès : il mesure et consigne.
Les budgets proviennent du plan gelé et ne sont jamais redéfinis ici.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import freeze_circuit2_plan as fcp  # noqa: E402
import run_circuit2_arms as rca  # noqa: E402
import run_circuit2_campaign as rcc  # noqa: E402
from run_circuit2_campaign import ArmRun, PlanError, load_plan, new_run  # noqa: E402,F401
from genesis import circuit_engine as ce  # noqa: E402
from genesis import circuit_procedure as cp  # noqa: E402
from genesis import circuit_tasks as ct  # noqa: E402

DEFAULT_PLAN = fcp.PLAN_PATH


def fingerprint(obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def engine_from_record(rec):
    """Reconstruit un Engine ; ValueError si Engine.record() diffère de rec."""
    engine = ce.Engine(
        [
            ce.Component(r["name"], r["arity"], tuple(tuple(s) for s in r["steps"]), r["weight"])
            for r in rec
        ]
    )
    if engine.record() != rec:
        raise ValueError("enregistrement non reproduit exactement par Engine.record()")
    return engine


def _procedure_record(run, arm):
    if arm == "inherited_lineage":
        return run.state["procedure"]
    return cp.to_record(run.procedure)


def final_library(arm, seed, tasks, limit, budget, generations):
    """Pilote un ArmRun persistant, sans rejeu de préfixe.

    Renvoie (enregistrements de génération, Engine final, procédure finale,
    procédure initiale).
    """
    run = new_run(arm, seed, tasks, limit, budget)
    initial = _procedure_record(run, arm)
    records = []
    for _ in range(generations):
        record = run.step()
        records.append(record)
        if rcc._stops(record):
            break
    engine = run.state.engine if arm == "inherited_lineage" else run.engine
    return records, engine, _procedure_record(run, arm), initial


def _n_inputs(task):
    value = task.inputs
    return value if isinstance(value, int) else len(value)


def measure_held_out(engine, plan_path=None):
    """Rendement held-out de `engine` après vérification du plan gelé.

    Le plan est lu et vérifié (freeze_circuit2_plan.verify_plan) avant toute
    construction de la suite HELD_OUT ; absent, illisible ou invalide => PlanError.
    Le filtre inputs <= plan['selection']['max_inputs'] est un choix de
    l'adjudicateur : le plan ne le précise pas pour les familles tenues à l'écart.
    """
    path = Path(plan_path) if plan_path is not None else DEFAULT_PLAN
    try:
        plan = load_plan(path)
        fcp.verify_plan(plan)
        max_inputs = plan["selection"]["max_inputs"]
        task_budget = plan["budgets"]["task_budget"]
    except PlanError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PlanError(f"plan illisible ou invalide : {exc}") from exc
    suite = ct.circuit2_suite(tuple(ct.HELD_OUT))
    tasks = [t for t in suite if _n_inputs(t) <= max_inputs]
    return ce.measure(ce.attempt(engine, tasks, task_budget))[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--arms", nargs="+", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if (ROOT / "results").resolve() not in out.parents:
        raise SystemExit("--out doit se trouver sous results/")
    plan_path = Path(args.plan) if args.plan else DEFAULT_PLAN
    plan = load_plan(plan_path)
    fcp.verify_plan(plan)
    tasks = fcp.learn_tasks()
    budget = plan["budgets"]["task_budget"]
    limit = args.limit if args.limit is not None else plan["budgets"]["per_generation_limit"]
    arms = args.arms or list(getattr(rca, "ARMS", ("fixed_procedure", "inherited_lineage")))
    rows = []
    for arm in arms:
        for seed in args.seeds:
            records, engine, _final, _initial = final_library(
                arm, seed, tasks, limit, budget, args.generations
            )
            rows.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "generations": len(records),
                    "held_out_yield": measure_held_out(engine, plan_path),
                    "library_fingerprint": fingerprint(engine.record()),
                }
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        json.dump({"rows": rows}, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
