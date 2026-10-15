"""Mesure hors réseau, sans modèle, sur LEARN seul, pour calibrer le budget CIRCUIT2.

Le test n'écrit aucun fichier: la sortie passe par print uniquement. Il ne
vérifie que la forme des résultats, jamais les valeurs mesurées.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PER_GENERATION_LIMITS = (16, 32, 64, 128, 256, 512, 1024, 2048)


def _load():
    path = ROOT / "scripts" / "freeze_circuit2_plan.py"
    spec = importlib.util.spec_from_file_location("freeze_circuit2_plan", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fp = _load()


@pytest.mark.parametrize("task_budget", fp.MEASURE_TASK_BUDGETS)
def test_initial_evaluation_spend_shape(task_budget):
    result = fp.initial_evaluation_spend(task_budget)
    print(f"INITIAL task_budget={task_budget} result={result}")
    assert isinstance(result, dict)
    assert {"task_budget", "evaluations", "solved", "tasks"} <= set(result)


@pytest.mark.parametrize("task_budget", fp.MEASURE_TASK_BUDGETS)
@pytest.mark.parametrize("per_generation_limit", PER_GENERATION_LIMITS)
def test_preflight_learn_only_grid_shape(per_generation_limit, task_budget):
    try:
        reports = fp.preflight_learn_only(per_generation_limit, task_budget)
    except ValueError as exc:
        print(f"GRID per_generation_limit={per_generation_limit} task_budget={task_budget} ECHEC ValueError: {exc}")
        return
    assert isinstance(reports, list)
    assert len(reports) == len(fp.CONTROL_SEEDS)
    for report in reports:
        print(f"GRID per_generation_limit={per_generation_limit} task_budget={task_budget} OK report={report}")
        assert isinstance(report, dict)
