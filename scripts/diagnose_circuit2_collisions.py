"""Diagnostic en lecture seule des collisions de tables CIRCUIT2 (aucun fichier écrit, ni réseau, ni modèle).

Compare chaque instance c2h_ de freeze_circuit2_plan.instances() aux tâches de LEARN et aux tâches
tenues à l'écart de CIRCUIT1 (même largeur): égalité exacte, puis égalité après permutation des
entrées (convention de _permuted_hit). Une absence de collision de tables ne prouve pas
l'indépendance des familles.
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = (("LEARN", "LEARN"), ("HELD_OUT", "HELD_OUT CIRCUIT1"))


def _load_freeze():
    mod = sys.modules.get("freeze_circuit2_plan")
    if mod is not None:
        return mod
    path = ROOT / "scripts" / "freeze_circuit2_plan.py"
    spec = importlib.util.spec_from_file_location("freeze_circuit2_plan", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tasks():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from genesis import circuit_tasks
    return circuit_tasks


FP = _load_freeze()


def apply_perm(rows, perm):
    """Même convention que _permuted_hit."""
    n = len(perm)
    return tuple(rows[sum(((j >> perm[k]) & 1) << k for k in range(n))] for j in range(1 << n))


def table_of(task):
    return tuple((task.target >> r) & 1 for r in range(1 << task.inputs))


def _witness(rows, table, n):
    if table == rows:
        return tuple(range(n))
    if sum(table) != sum(rows):
        return None
    for perm in itertools.permutations(range(n)):
        if apply_perm(rows, perm) == table:
            return perm
    return None


def inventory():
    ctasks = _tasks()
    groups = [(label, list(ctasks.suite(getattr(ctasks, attr)))) for attr, label in GROUPS]
    found = []
    for inst in FP.instances():
        if not inst["family"].startswith("c2h_"):
            continue
        n = inst["n_inputs"]
        rows = tuple(inst["rows"])
        for label, tasks in groups:
            for task in tasks:
                if task.inputs != n:
                    continue
                table = table_of(task)
                witness = _witness(rows, table, n)
                if witness is None:
                    continue
                found.append(
                    {
                        "instance": inst["id"],
                        "task": task.name,
                        "type": "exact" if table == rows else "permuté",
                        "group": label,
                        "permutation": list(witness),
                    }
                )
    found.sort(key=lambda c: (c["instance"], c["group"], c["task"], c["type"]))
    return found


def main() -> int:
    found = inventory()
    report = {
        "collisions": found,
        "count": len(found),
        "plan_path": str(FP.PLAN_PATH.relative_to(ROOT)),
        "plan_exists": FP.PLAN_PATH.exists(),
        "note": "l'absence de collision de tables ne prouve pas l'indépendance des familles",
    }
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
