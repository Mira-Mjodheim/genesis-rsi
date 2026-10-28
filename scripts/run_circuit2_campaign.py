"""Lanceur hors réseau de la campagne CIRCUIT2, conforme au plan gelé.

Exécute les quatre bras sur les seules tâches LEARN du plan vérifié. Ne calcule ni
gain, ni rendement, ni succès : l'adjudication exige l'évaluation tenue à l'écart.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _path in (HERE, HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import freeze_circuit2_plan as freeze  # noqa: E402
import run_circuit2_arms as arms  # noqa: E402

PlanError = freeze.PlanError


def load_plan(path=freeze.PLAN_PATH):
    """Lit le plan scellé et le vérifie (digest, empreintes) ; aucune erreur n'est tolérée."""
    try:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"plan illisible ({path}) : {exc}") from exc
    if not isinstance(plan, dict):
        raise PlanError("le plan n'est pas un objet JSON")
    try:
        freeze.verify_plan(plan)
    except PlanError:
        raise
    except Exception as exc:
        raise PlanError(f"vérification du plan impossible : {exc}") from exc
    return plan


def run_campaign(plan, seeds=None, generations=None):
    """Exécute les bras sur LEARN seul ; ne calcule aucun gain ni succès."""
    budgets = plan["budgets"]
    plan_seeds = list(plan["seeds"])
    chosen = plan_seeds if seeds is None else list(seeds)
    if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= set(plan_seeds):
        raise ValueError(f"graines hors du plan ou invalides : {chosen}")
    max_generations = budgets["generations"]
    count = max_generations if generations is None else generations
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= max_generations:
        raise ValueError(f"générations invalides : {count} (maximum du plan : {max_generations})")
    learn = freeze.learn_tasks()
    results = arms.run_all(learn, chosen, count, budgets["per_generation_limit"], budgets["task_budget"])
    full = set(chosen) == set(plan_seeds) and count == max_generations
    return {
        "plan_digest": plan["digest"],
        "machinery_commit": plan["machinery_commit"],
        "seeds": chosen,
        "generations": count,
        "scale": "full" if full else "reduced",
        "arms": results,
    }


def _parse_seeds(text):
    try:
        return [int(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"graines invalides : {text!r}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=str(freeze.PLAN_PATH))
    parser.add_argument("--seeds", type=_parse_seeds, default=None, help="sous-ensemble des graines du plan, séparées par des virgules")
    parser.add_argument("--generations", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    try:
        if args.out is not None and Path(args.out).exists():
            raise FileExistsError(f"sortie déjà existante : {args.out}")
        plan = load_plan(args.plan)
        result = run_campaign(plan, args.seeds, args.generations)
        text = json.dumps(result, indent=2) + "\n"
        if args.out is None:
            sys.stdout.write(text)
        else:
            with open(args.out, "x", encoding="utf-8") as handle:
                handle.write(text)
    except (PlanError, ValueError, OSError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
