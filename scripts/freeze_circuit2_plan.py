"""Gel du plan CIRCUIT2, avant tout résultat tenu à l'écart.

Ce script ne lance aucune campagne et ne produit aucun résultat. Il écrit
experiment/engine/CIRCUIT2/PLAN.json, scellé par plan_digest, et refuse de
l'écraser. verify_plan(path) refuse tout plan altéré.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / "experiment" / "engine" / "CIRCUIT2" / "PLAN.json"
MACHINERY_FILES = (
    "genesis/circuit_engine.py",
    "genesis/circuit_procedure.py",
    "genesis/circuit_meta_lineage.py",
    "genesis/circuit_tasks.py",
    "scripts/freeze_circuit2_plan.py",
)
SEEDS = list(range(20))
RANDOM_PROCEDURE_SEED_OFFSET = 10000
# Budgets volontairement petits, fixés avant toute mesure.
PER_GENERATION_LIMIT = 16
TASK_BUDGET = 32
MAX_GENERATIONS = 6

# Instances tenues à l'écart de CIRCUIT2: familles propres (préfixe c2h_) et
# largeurs 5 à 7, définies ici de façon déterministe. Elles sont distinctes de
# LEARN par construction et leur disjonction avec les tables tenues à l'écart
# de CIRCUIT1 est vérifiée à la construction du plan (ValueError sinon).


def _popcount(i: int) -> int:
    return bin(i).count("1")


_GENERATORS = {
    "c2h_parity": (lambda i, n: _popcount(i) % 2, (5, 6, 7)),
    "c2h_majority": (lambda i, n: int(2 * _popcount(i) > n), (5, 7)),
    "c2h_threshold2": (lambda i, n: int(_popcount(i) >= 2), (5, 6)),
    "c2h_popcount_mod3": (lambda i, n: int(_popcount(i) % 3 == 0), (5, 6)),
    "c2h_halves_equal": (
        lambda i, n: int((i >> (n // 2)) == (i & ((1 << (n // 2)) - 1))),
        (6,),
    ),
}


def instances() -> list:
    out = []
    for family in sorted(_GENERATORS):
        fn, widths = _GENERATORS[family]
        for n in widths:
            rows = [int(fn(i, n)) for i in range(1 << n)]
            out.append({"id": f"{family}_w{n}", "family": family, "n_inputs": n, "rows": rows})
    return out


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_of(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def seal(plan: dict) -> dict:
    body = {k: v for k, v in plan.items() if k != "plan_digest"}
    return {**body, "plan_digest": digest_of(body)}


def machinery(root: Path = ROOT) -> dict:
    return {
        rel: hashlib.sha256((Path(root) / rel).read_bytes()).hexdigest()
        for rel in MACHINERY_FILES
    }


def head_commit(root: Path = ROOT) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _tasks():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from genesis import circuit_tasks
    return circuit_tasks


def learn_families() -> list:
    out = []
    for item in _tasks().LEARN:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append(str(item.get("family", item.get("name"))))
        else:
            out.append(str(getattr(item, "family", None) or getattr(item, "name", item)))
    return sorted(set(out))


def circuit1_heldout_tables() -> set:
    mod = _tasks()
    tasks = tuple(mod.suite(mod.HELD_OUT))
    if not tasks:
        raise ValueError("tâches tenues à l'écart de CIRCUIT1 introuvables")
    tables = {
        tuple((t.target >> r) & 1 for r in range(1 << t.inputs)) for t in tasks
    }
    return tables


def build_plan(root: Path = ROOT) -> dict:
    inst = instances()
    learn = learn_families()
    held_families = sorted({i["family"] for i in inst})
    if set(held_families) & set(learn):
        raise ValueError("famille tenue à l'écart présente dans LEARN")
    tables = [tuple(i["rows"]) for i in inst]
    if len(set(tables)) != len(tables):
        raise ValueError("instances tenues à l'écart dupliquées")
    circuit1 = circuit1_heldout_tables()
    if set(tables) & circuit1:
        raise ValueError("instance commune avec les tâches tenues à l'écart de CIRCUIT1")
    total = PER_GENERATION_LIMIT * MAX_GENERATIONS
    return seal(
        {
            "plan": "CIRCUIT2",
            "commit": head_commit(root),
            "machinery": machinery(root),
            "seeds": list(SEEDS),
            "budget": {
                "per_generation_limit": PER_GENERATION_LIMIT,
                "task_budget": TASK_BUDGET,
                "max_generations": MAX_GENERATIONS,
                "total_budget": total,
                "note": "identique pour tous les bras; valeurs petites fixées avant toute mesure",
            },
            "stop_rules": [
                "arrêt à max_generations générations",
                "arrêt dès que total_budget est consommé",
                "aucune extension de budget ni de graines après gel",
                "aucune lecture des familles tenues à l'écart pendant la sélection",
            ],
            "metric": {
                "name": "rendement",
                "definition": "tâches tenues à l'écart résolues / total des tâches tenues à l'écart",
            },
            "arms": {
                "meta_lineage": "procédure héritée et recherchée récursivement (circuit_meta_lineage)",
                "frozen_engine": "moteur gelé, sans changement de procédure",
                "fixed_procedure": "seed_procedure de CIRCUIT1",
                "random_procedure": "random_procedure, graines déclarées dans random_procedure_seeds",
            },
            "random_procedure_seeds": {str(s): RANDOM_PROCEDURE_SEED_OFFSET + s for s in SEEDS},
            "learn_families": learn,
            "heldout_families": held_families,
            "heldout_instances": inst,
            "heldout_tables_digest": digest_of([list(t) for t in tables]),
            "circuit1_heldout_tables_digest": digest_of(sorted(list(t) for t in circuit1)),
            "instances_justification": "familles propres à CIRCUIT2 (préfixe c2h_), largeurs 5 à 7; disjonction avec CIRCUIT1 vérifiée par comparaison des tables et non par les noms",
            "criterion": {
                "unit": "points de rendement (rendement x 100)",
                "min_gain_final_vs_fixed_points": 10.0,
                "min_gain_final_vs_random_points": 10.0,
                "min_gain_per_transition_points": 5.0,
                "n_successive_transitions": 2,
                "transitions_require_identical_initial_library": True,
                "n_seeds": 20,
                "min_seeds_won_per_comparison": 16,
                "ablation": {
                    "operation": "replace_procedure restaurant la procédure initiale",
                    "residual_gain_must_be_below_points": 5.0,
                    "note": "seuil opérationnel de 'le gain disparaît', à confirmer; non mesuré",
                },
                "otherwise": "échec publié",
            },
            "claim_boundary": "un seul domaine (circuits); aucune RSI générale établie",
        }
    )


def verify_plan(path, root: Path = ROOT) -> dict:
    try:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"plan illisible: {exc}") from exc
    if not isinstance(plan, dict) or "plan_digest" not in plan:
        raise ValueError("plan_digest absent")
    body = {k: v for k, v in plan.items() if k != "plan_digest"}
    if digest_of(body) != plan["plan_digest"]:
        raise ValueError("plan_digest invalide: plan altéré")
    if plan.get("machinery") != machinery(root):
        raise ValueError("empreintes de la machinerie différentes: plan altéré ou moteur modifié")
    expected = build_plan(root)
    skip = ("commit", "plan_digest")
    if {k: v for k, v in body.items() if k not in skip} != {
        k: v for k, v in expected.items() if k not in skip
    }:
        raise ValueError("contenu du plan différent du plan reconstruit")
    return plan


def freeze(path=PLAN_PATH, root: Path = ROOT) -> dict:
    path = Path(path)
    if path.exists():
        raise SystemExit(f"refus: {path} existe déjà, le plan est gelé")
    plan = build_plan(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    verify_plan(path, root)
    return plan


def main() -> int:
    plan = freeze()
    print(f"plan gelé: {PLAN_PATH} plan_digest={plan['plan_digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
