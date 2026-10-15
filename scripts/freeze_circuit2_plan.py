"""Gel du plan CIRCUIT2, avant tout résultat tenu à l'écart.

Ce script ne lance aucune campagne et ne produit aucun résultat. Il écrit
experiment/engine/CIRCUIT2/PLAN.json, scellé par plan_digest, et refuse de
l'écraser. verify_plan(path) refuse tout plan altéré.
"""
from __future__ import annotations

import hashlib
import itertools
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
# Budgets: 16/32 sont insuffisants (engine._metered_attempt renvoie None dès
# que meter.remaining < task_budget: évaluation initiale incomplète, lignée
# inerte). Les valeurs ci-dessous restent à remplacer par des valeurs MESURÉES
# sur LEARN (python scripts/freeze_circuit2_plan.py --measure). Tant qu'elles
# échouent à preflight_learn_only, build_plan refuse de sceller le plan.
# ÉTAT: --measure n'a pas été exécuté, aucune sortie n'est consignée; aucune valeur n'est inventée ici.
PER_GENERATION_LIMIT = 16
TASK_BUDGET = 32
MAX_GENERATIONS = 6
# Graines de contrôle (LEARN seulement), distinctes de SEEDS et des graines aléatoires.
CONTROL_SEEDS = (9001, 9002, 9003)
# Justification chiffrée issue de la mesure; vide tant que rien n'est mesuré.
BUDGET_JUSTIFICATION = ""
# Essais négatifs consignés. 16/32: hypothèse issue de la lecture du code
# (_metered_attempt renvoie None si remaining < task_budget), NON mesurée ici.
NEGATIVE_TRIALS = (
    {"per_generation_limit": 16, "task_budget": 32, "status": "hypothèse non mesurée: évaluation de base impayable"},
)
MEASURE_TASK_BUDGETS = (32, 64, 128, 256)

# Instances tenues à l'écart de CIRCUIT2: familles propres (préfixe c2h_) et
# largeurs 5 à 7, définies ici de façon déterministe. Le préfixe ne prouve rien:
# la disjonction est vérifiée sémantiquement à la construction du plan
# (ValueError sinon), en comparant des tables entières (n_inputs, table):
# contre les tables de LEARN, à l'identique et après toute permutation des
# entrées, et contre les tables tenues à l'écart de CIRCUIT1 (comparaison exacte).


def _popcount(i: int) -> int:
    return bin(i).count("1")


def _weighted_threshold(i: int, n: int) -> int:
    total = sum(k + 1 for k in range(n) if (i >> k) & 1)
    return int(2 * total > n * (n + 1) // 2)


def _alternating_chain(i: int, n: int) -> int:
    value = i & 1
    for k in range(1, n):
        bit = (i >> k) & 1
        value = (value & bit) if k % 2 else (value ^ bit)
    return value


def _pair_inner_product(i: int, n: int) -> int:
    return sum(((i >> (2 * j)) & (i >> (2 * j + 1))) & 1 for j in range(n // 2)) % 2


def _transitions(i: int, n: int) -> int:
    return int(_popcount((i ^ (i >> 1)) & ((1 << (n - 1)) - 1)) >= 3)


_GENERATORS = {
    "c2h_weighted_threshold": (_weighted_threshold, (5, 6, 7)),
    "c2h_alternating_chain": (_alternating_chain, (5, 6, 7)),
    "c2h_pair_inner_product": (_pair_inner_product, (5, 6, 7)),
    "c2h_transitions": (_transitions, (5, 6, 7)),
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


def learn_tables() -> set:
    """Couples (n_inputs, table) de toutes les tâches de circuit_tasks.LEARN."""
    mod = _tasks()
    return {
        (t.inputs, tuple((t.target >> r) & 1 for r in range(1 << t.inputs)))
        for t in mod.suite(mod.LEARN)
    }


def _permuted_hit(n_inputs: int, rows: tuple, known: set) -> bool:
    """True si rows, après une permutation des entrées, est une table de known de même largeur."""
    size = 1 << n_inputs
    ones = sum(rows)
    pool = {t for (n, t) in known if n == n_inputs and sum(t) == ones}
    if not pool:
        return False
    for perm in itertools.permutations(range(n_inputs)):
        image = tuple(
            rows[sum(((j >> perm[k]) & 1) << k for k in range(n_inputs))]
            for j in range(size)
        )
        if image in pool:
            return True
    return False


def _learn_tasks() -> list:
    mod = _tasks()
    return list(mod.suite(mod.LEARN))


def _level1_ok(states: list) -> bool:
    first = states[1]
    return (
        first["score"] is not None
        and first["exhausted"] is False
        and len(first["evaluated"]) >= 1
    )


def initial_evaluation_spend(task_budget: int) -> dict:
    """Dépense réelle de l'évaluation initiale de la bibliothèque vide, LEARN seulement."""
    _tasks()
    from genesis import circuit_engine as engine

    solutions = engine.attempt(engine.Engine(), _learn_tasks(), task_budget)
    return {
        "task_budget": task_budget,
        "evaluations": sum(s.evaluations for s in solutions),
        "solved": sum(1 for s in solutions if s.solved),
        "tasks": len(solutions),
    }


def _lineage_passes(limit: int, task_budget: int, seeds, generations: int = 2) -> bool:
    _tasks()
    from genesis import circuit_meta_lineage as lineage

    learn = _learn_tasks()
    return all(
        _level1_ok(lineage.run_lineage(generations, learn, task_budget, limit, seed))
        for seed in seeds
    )


def minimal_generation_limit(task_budget: int, seeds=CONTROL_SEEDS, ceiling: int = 10**6):
    """Plus petit plafond par génération qui passe le contrôle de non-inertie (None si aucun).

    Recherche par doublement puis dichotomie; suppose la monotonie en limit,
    à confirmer en rejouant la valeur trouvée et la valeur juste en dessous.
    """
    high = 1
    while not _lineage_passes(high, task_budget, seeds):
        high *= 2
        if high > ceiling:
            return None
    low = high // 2
    while high - low > 1:
        mid = (low + high) // 2
        if _lineage_passes(mid, task_budget, seeds):
            high = mid
        else:
            low = mid
    return high


def measure(task_budgets=MEASURE_TASK_BUDGETS, seeds=CONTROL_SEEDS) -> list:
    """Mesure hors réseau, sans modèle, sur LEARN uniquement."""
    return [
        {
            "initial_evaluation": initial_evaluation_spend(tb),
            "minimal_per_generation_limit": minimal_generation_limit(tb, seeds),
            "control_seeds": list(seeds),
        }
        for tb in task_budgets
    ]


def preflight_learn_only(per_generation_limit, task_budget, seeds=None) -> list:
    """Précontrôle sur LEARN seul (jamais les familles tenues à l'écart).

    Rapporte par graine de contrôle: coût de l'évaluation de base, budget restant
    après elle, appel effectif d'improved_by avec au moins un candidat admis et
    essayé, consommation totale. ValueError si la recherche ne démarre pas.
    Ne démontre aucune amélioration: seul CIRCUIT2 adjugé la mesurera.
    """
    controls = tuple(CONTROL_SEEDS if seeds is None else seeds)
    reserved = set(SEEDS) | {RANDOM_PROCEDURE_SEED_OFFSET + s for s in SEEDS}
    if not controls or set(controls) & reserved:
        raise ValueError("preflight LEARN: graines de contrôle absentes ou communes avec le plan")
    _tasks()
    from genesis import circuit_engine as engine
    from genesis import circuit_meta_lineage as lineage

    learn = _learn_tasks()
    base_cost = sum(s.evaluations for s in engine.attempt(engine.Engine(), learn, task_budget))
    reports = []
    for seed in controls:
        calls = []
        real = engine.improved_by

        def spy(*args, **kwargs):
            result = real(*args, **kwargs)
            calls.append(result[2])
            return result

        engine.improved_by = spy
        try:
            states = lineage.run_lineage(1, learn, task_budget, per_generation_limit, seed)
        finally:
            engine.improved_by = real
        state = states[1]
        tried = sum(len(info.get("trials", [])) for info in calls)
        admitted = sum(info.get("admitted", 0) for info in calls)
        report = {
            "seed": seed,
            "base_cost": base_cost,
            "remaining_after_base": per_generation_limit - base_cost,
            "improved_by_called": bool(calls),
            "admitted": admitted,
            "tried": tried,
            "total_spent": sum(state["spent"].values()),
            "exhausted": state["exhausted"],
        }
        reports.append(report)
        if state["score"] is None:
            raise ValueError(
                f"preflight LEARN: évaluation de base incomplète, limit={per_generation_limit} task_budget={task_budget} {report}"
            )
        if not calls or state["exhausted"] is not False:
            raise ValueError(
                f"preflight LEARN: recherche non démarrée (improved_by non appelé ou budget épuisé), {report}"
            )
        if admitted < 1 or tried < 1:
            raise ValueError(
                f"preflight LEARN: aucun candidat admis et essayé, {report}"
            )
    return reports


def build_plan(root: Path = ROOT) -> dict:
    inst = instances()
    learn = learn_families()
    held_families = sorted({i["family"] for i in inst})
    if set(held_families) & set(learn):
        raise ValueError("famille tenue à l'écart présente dans LEARN")
    tables = [tuple(i["rows"]) for i in inst]
    if len(set(tables)) != len(tables):
        raise ValueError("instances tenues à l'écart dupliquées")
    learn_known = learn_tables()
    for item in inst:
        key = (item["n_inputs"], tuple(item["rows"]))
        if key in learn_known:
            raise ValueError(f"instance {item['id']} identique à une tâche de LEARN")
        if _permuted_hit(key[0], key[1], learn_known):
            raise ValueError(f"instance {item['id']} identique à une tâche de LEARN après permutation des entrées")
    circuit1 = circuit1_heldout_tables()
    if set(tables) & circuit1:
        raise ValueError("instance commune avec les tâches tenues à l'écart de CIRCUIT1")
    preflight_learn_only(PER_GENERATION_LIMIT, TASK_BUDGET)
    if not BUDGET_JUSTIFICATION:
        raise ValueError("preflight LEARN: justification chiffrée du budget absente")
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
                "control_seeds": list(CONTROL_SEEDS),
                "justification": BUDGET_JUSTIFICATION,
                "note": "identique pour tous les bras; valeurs mesurées sur LEARN uniquement (voir justification)",
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
            "instances_justification": "familles propres à CIRCUIT2 (préfixe c2h_), largeurs 5 à 7; le préfixe ne prouve rien: disjonction vérifiée sémantiquement par comparaison de tables entières (n_inputs, table) avec LEARN, à l'identique et après permutation des entrées, et avec les tables tenues à l'écart de CIRCUIT1 (comparaison exacte)",
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


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--measure"]:
        print(json.dumps(measure(), indent=2, sort_keys=True))
        return 0
    plan = freeze()
    print(f"plan gelé: {PLAN_PATH} plan_digest={plan['plan_digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
