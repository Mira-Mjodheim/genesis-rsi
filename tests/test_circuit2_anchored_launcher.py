"""Ancre du sceau CIRCUIT2 : hors réseau, fixtures synthétiques (plan factice, coûts 100)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import freeze_circuit2_plan as freeze
import run_circuit2_anchored as anchored
import run_circuit2_campaign as campaign
import seal_circuit2_launcher as sealing

COMMIT = "a" * 40
REAL_SEAL = Path(campaign.SEAL_PATH)
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ANCHOR = "--approved-seal-sha256"
DRIVER = """
import sys
from pathlib import Path
root, seal, launcher, approved, out, plan, witness = sys.argv[1:8]
for entry in (root + "/src", root + "/scripts"):
    sys.path.insert(0, entry)
import run_circuit2_anchored as anchored
import run_circuit2_campaign as campaign
campaign.SEAL_PATH = Path(seal)
campaign.LAUNCHER_FILE = Path(launcher)
campaign.CANONICAL_PLAN_PATH = Path(plan)
class _FakeRun:
    def step(self):
        return {"exhausted": False, "digest": "d", "spent": 0, "transmission": {"digest": "d"}}
def new_run(arm, seed, learn, limit, budget):
    Path(witness).write_text("appel", encoding="utf-8")
    return _FakeRun()
campaign.new_run = new_run
argv = ["--plan", plan, "--seeds", "0", "--generations", "1", "--approved-seal-sha256", approved, "--out", out]
sys.exit(anchored.main(argv))
"""


@pytest.fixture(scope="module")
def sealed():
    """Fixture synthétique : plan factice aux coûts de référence 100."""
    return freeze.build_plan(measure=lambda: {str(s): 100 for s in freeze.SEEDS}, machinery_commit=COMMIT)


@pytest.fixture(autouse=True)
def canonical(tmp_path, sealed, monkeypatch):
    path = tmp_path / "CANONICAL.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    monkeypatch.setattr(campaign, "CANONICAL_PLAN_PATH", path)
    return path


@pytest.fixture(autouse=True)
def launcher_seal(tmp_path, sealed, monkeypatch):
    """Fixture synthétique : sceau valide écrit dans tmp_path pour le vrai lanceur et le plan factice."""
    path = tmp_path / "LAUNCHER_SEAL.json"
    path.write_text(json.dumps(sealing.build_seal(sealed["digest"])), encoding="utf-8")
    monkeypatch.setattr(campaign, "SEAL_PATH", path)
    return path


@pytest.fixture
def calls(monkeypatch):
    """Fixture synthétique : new_run factice, aucune génération réelle ; enregistre les appels."""
    recorded = []

    class _FakeRun:
        def step(self):
            return {"exhausted": False, "digest": "d", "spent": 0, "transmission": {"digest": "d"}}

    def new_run(arm, seed, learn, limit, budget):
        recorded.append((arm, seed))
        return _FakeRun()

    monkeypatch.setattr(campaign, "new_run", new_run)
    return recorded


@pytest.fixture
def plan_path(tmp_path, sealed):
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    return path


def _approved(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _args(plan):
    return ["--plan", str(plan), "--seeds", "0", "--generations", "1"]


def test_accepts_the_approved_seal(plan_path, tmp_path, sealed, launcher_seal, calls):
    approved = _approved(launcher_seal)
    out = tmp_path / "OUT.json"
    argv = [*_args(plan_path), ANCHOR, approved, "--out", str(out)]
    assert anchored.main(argv) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["approved_seal_sha256"] == approved
    assert written["command"] == argv
    assert written["launcher_provenance"]["plan_digest"] == sealed["digest"]
    assert calls


@pytest.mark.parametrize("anchor", [None, "", "abc", "f" * 64, "F" * 64, "g" * 64, "0" * 63])
def test_refusal_before_any_generation(anchor, plan_path, tmp_path, calls, capsys):
    out = tmp_path / "OUT.json"
    argv = [*_args(plan_path), "--out", str(out)]
    if anchor is not None:
        argv += [ANCHOR, anchor]
    assert anchored.main(argv) == 2
    assert capsys.readouterr().out == ""
    assert not out.exists()
    assert calls == []


def test_existing_output_is_refused(plan_path, tmp_path, launcher_seal, calls, capsys):
    out = tmp_path / "OUT.json"
    out.write_text("existant", encoding="utf-8")
    argv = [*_args(plan_path), ANCHOR, _approved(launcher_seal), "--out", str(out)]
    assert anchored.main(argv) == 2
    assert out.read_text(encoding="utf-8") == "existant"
    assert capsys.readouterr().out == ""
    assert calls == []


def test_joint_alteration_of_launcher_and_seal_is_refused(tmp_path):
    plan = freeze.build_plan(measure=lambda: {str(s): 100 for s in freeze.SEEDS}, machinery_commit=COMMIT)
    plan_file = tmp_path / "PLAN_SUBPROCESS.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    real_launcher = Path(campaign.LAUNCHER_FILE)

    def run(seal, launcher, approved, out, witness):
        return subprocess.run([sys.executable, "-I", str(driver), str(SCRIPTS.parent), str(seal), str(launcher), approved, str(out), str(plan_file), str(witness)], capture_output=True, text=True, timeout=120)

    good_seal = tmp_path / "seal_ok.json"
    good_seal.write_text(json.dumps(sealing.build_seal(plan["digest"])), encoding="utf-8")
    approved = _approved(good_seal)
    out_ok = tmp_path / "OUT_OK.json"
    witness_ok = tmp_path / "WITNESS_OK.txt"
    positive = run(good_seal, real_launcher, approved, out_ok, witness_ok)
    assert positive.returncode == 0, positive.stderr
    assert out_ok.exists()
    assert witness_ok.exists()

    launcher = tmp_path / "launcher_altered.py"
    launcher.write_bytes(real_launcher.read_bytes() + b"\n# altere\n")
    body = {k: v for k, v in json.loads(good_seal.read_text(encoding="utf-8")).items() if k != "digest"}
    body["launcher_sha256"] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    seal = tmp_path / "seal_altered.json"
    seal.write_text(json.dumps({**body, "digest": sealing.digest_of(body)}), encoding="utf-8")
    out = tmp_path / "OUT_ALTERED.json"
    witness = tmp_path / "WITNESS_ALTERED.txt"
    result = run(seal, launcher, approved, out, witness)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "ne correspond pas à l'ancre approuvée" in result.stderr
    assert not out.exists()
    assert not witness.exists()


def test_canonical_launcher_matches_the_versioned_seal():
    seal = json.loads(REAL_SEAL.read_text(encoding="utf-8"))
    body = {k: v for k, v in seal.items() if k != "digest"}
    assert seal["digest"] == sealing.digest_of(body)
    assert seal["launcher_sha256"] == sealing.file_sha256(campaign.LAUNCHER_FILE)
    assert seal["verifier_sha256"] == sealing.file_sha256(Path(sealing.__file__))


@pytest.fixture
def received(monkeypatch):
    """Fixture synthétique : campaign.main factice, enregistre son argv et imprime un JSON valide."""
    argvs = []

    def fake_main(argv=None):
        argvs.append(list(argv))
        print(json.dumps({"launcher_provenance": {}}))
        return 0

    monkeypatch.setattr(campaign, "main", fake_main)
    return argvs


def test_campaign_receives_no_anchor_and_seal_is_untouched(received, plan_path, tmp_path, launcher_seal):
    approved = _approved(launcher_seal)
    before = _approved(campaign.SEAL_PATH)
    out = tmp_path / "OUT.json"
    assert anchored.main([*_args(plan_path), ANCHOR, approved, "--out", str(out)]) == 0
    assert received == [_args(plan_path)]
    assert ANCHOR not in received[0] and approved not in received[0]
    for flag in ("--plan", "--seeds", "--generations"):
        assert flag in received[0]
    assert _approved(campaign.SEAL_PATH) == before == approved
    assert json.loads(out.read_text(encoding="utf-8"))["approved_seal_sha256"] == approved


def test_received_argv_is_identical_with_and_without_anchor(received, plan_path, tmp_path, launcher_seal):
    approved = _approved(launcher_seal)
    base = _args(plan_path)
    assert anchored.main([*base, ANCHOR, approved, "--out", str(tmp_path / "A.json")]) == 0
    assert anchored.main([ANCHOR, approved, "--out", str(tmp_path / "B.json"), *base]) == 0
    assert campaign.main(base) == 0
    assert received[0] == received[1] == received[2] == base
