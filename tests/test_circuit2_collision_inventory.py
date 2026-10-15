"""Tests hors réseau de l'inventaire des collisions CIRCUIT2 (aucun PLAN.json écrit)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    path = ROOT / "scripts" / "diagnose_circuit2_collisions.py"
    spec = importlib.util.spec_from_file_location("diagnose_circuit2_collisions", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


diag = _load()
fp = diag.FP


def _task(name):
    ct = diag._tasks()
    return next(t for t in ct.suite(ct.LEARN) if t.name == name)


def test_inventory_is_deterministic():
    one, two = diag.inventory(), diag.inventory()
    assert one == two
    assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True)


def test_exact_learn_duplicate_is_detected(monkeypatch):
    monkeypatch.setattr(fp, "_GENERATORS", {"c2h_dup": (lambda i, n: bin(i).count("1") % 2, (5,))})
    found = [c for c in diag.inventory() if c["instance"] == "c2h_dup_w5"]
    assert any(c["type"] == "exact" and c["group"] == "LEARN" and c["task"] == "parity5" for c in found)


def test_permuted_learn_duplicate_is_detected_with_valid_witness(monkeypatch):
    task = _task("mux4")
    table = diag.table_of(task)

    def rotated(i, width):
        return table[((i << 1) | (i >> (width - 1))) & ((1 << width) - 1)]

    monkeypatch.setattr(fp, "_GENERATORS", {"c2h_rot": (rotated, (6,))})
    found = [c for c in diag.inventory() if c["instance"] == "c2h_rot_w6" and c["task"] == "mux4"]
    assert len(found) == 1 and found[0]["type"] == "permuté" and found[0]["group"] == "LEARN"
    rows = next(i["rows"] for i in fp.instances() if i["id"] == "c2h_rot_w6")
    assert diag.apply_perm(tuple(rows), tuple(found[0]["permutation"])) == table


def test_real_inventory_witnesses_reproduce_tables():
    ct = diag._tasks()
    rows_by_id = {i["id"]: tuple(i["rows"]) for i in fp.instances()}
    attr_of = {"LEARN": "LEARN", "HELD_OUT CIRCUIT1": "HELD_OUT"}
    tables = {
        (attr, t.name): diag.table_of(t)
        for attr in ("LEARN", "HELD_OUT")
        for t in ct.suite(getattr(ct, attr))
    }
    for c in diag.inventory():
        table = tables[(attr_of[c["group"]], c["task"])]
        assert diag.apply_perm(rows_by_id[c["instance"]], tuple(c["permutation"])) == table


def test_real_inventory_has_no_collision():
    # Inventaire vide: absence de collision de tables (égalité exacte ou permutation des entrées) seulement, pas indépendance des familles.
    assert diag.inventory() == []


def test_plan_json_is_not_created(capsys):
    before = fp.PLAN_PATH.exists()
    assert diag.main() == 0
    json.loads(capsys.readouterr().out)
    assert fp.PLAN_PATH.exists() == before
