"""Approbation hôte du sceau CIRCUIT2 : hors réseau, fixtures synthétiques (plan factice, coûts 100)."""
from __future__ import annotations

import hashlib
import json
import os
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
ENV = "GENESIS_HOST_APPROVALS"
KEY = "circuit2_launcher_seal_sha256"
DRIVER = """
import sys
import os
from pathlib import Path
root, seal, launcher, out, plan, witness = sys.argv[1:7]
extra = sys.argv[7:]
for entry in (root + "/src", root + "/scripts"):
    sys.path.insert(0, entry)
import run_circuit2_anchored as anchored
import run_circuit2_campaign as campaign
if os.environ.get("TEST_REPO_ROOT"):
    anchored.REPO_ROOT = Path(os.environ["TEST_REPO_ROOT"])
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
argv = ["--plan", plan, "--seeds", "0", "--generations", "1", "--out", out, *extra]
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


def _write_approval(path, digest, mode=0o600):
    """Fixture synthétique : écrit un fichier d'approbation hôte au format JSON attendu."""
    path.write_text(json.dumps({KEY: digest}), encoding="utf-8")
    os.chmod(path, mode)
    return path


@pytest.fixture
def host_approval(tmp_path, launcher_seal, monkeypatch):
    """Fixture synthétique : approbation hôte hors dépôt (tmp_path), mode 0o600, empreinte du sceau courant."""
    path = _write_approval(tmp_path / "host_approvals.json", _approved(launcher_seal))
    assert not path.resolve().is_relative_to(anchored.REPO_ROOT.resolve())
    monkeypatch.setenv(ENV, str(path))
    return path


def test_accepts_the_approved_seal(plan_path, tmp_path, sealed, launcher_seal, host_approval, calls):
    approved = _approved(launcher_seal)
    out = tmp_path / "OUT.json"
    argv = [*_args(plan_path), "--out", str(out)]
    assert anchored.main(argv) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["approved_seal_sha256"] == approved
    assert written["host_approval_file"] == str(host_approval.resolve())
    assert written["command"] == argv
    assert written["launcher_provenance"]["plan_digest"] == sealed["digest"]
    assert calls


def _refused(plan_path, tmp_path, calls, capsys, extra=(), fragment=None):
    """Refus : code 2, aucune sortie standard, aucun fichier --out, aucune génération."""
    out = tmp_path / "OUT.json"
    assert anchored.main([*_args(plan_path), "--out", str(out), *extra]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    if fragment is not None:
        assert fragment in captured.err
    assert not out.exists()
    assert calls == []


def test_refusal_without_the_environment_variable(host_approval, plan_path, tmp_path, calls, capsys, monkeypatch):
    monkeypatch.delenv(ENV)
    _refused(plan_path, tmp_path, calls, capsys, fragment=ENV)


def test_refusal_with_a_missing_approval_file(plan_path, tmp_path, calls, capsys, monkeypatch):
    monkeypatch.setenv(ENV, str(tmp_path / "absent.json"))
    _refused(plan_path, tmp_path, calls, capsys, fragment="illisible")


@pytest.mark.parametrize(
    "content",
    ["", "{", "[]", "{}", json.dumps({KEY: 5}), json.dumps({KEY: ""}), json.dumps({KEY: "abc"}), json.dumps({KEY: "F" * 64}), json.dumps({KEY: "g" * 64}), json.dumps({KEY: "0" * 63}), json.dumps({KEY: "f" * 64})],
)
def test_refusal_with_an_invalid_or_different_approval(content, host_approval, plan_path, tmp_path, calls, capsys):
    host_approval.write_text(content, encoding="utf-8")
    _refused(plan_path, tmp_path, calls, capsys)


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o660, 0o606, 0o666])
def test_refusal_when_the_approval_is_writable_by_group_or_others(mode, host_approval, plan_path, tmp_path, calls, capsys):
    os.chmod(host_approval, mode)
    _refused(plan_path, tmp_path, calls, capsys, fragment="inscriptible")


def test_refusal_when_the_approval_is_inside_the_repository(host_approval, plan_path, tmp_path, calls, capsys, monkeypatch):
    monkeypatch.setattr(anchored, "REPO_ROOT", tmp_path)
    _refused(plan_path, tmp_path, calls, capsys, fragment="dépôt")


def test_refusal_for_a_file_of_the_real_repository(plan_path, tmp_path, calls, capsys, monkeypatch):
    monkeypatch.setenv(ENV, str(Path(__file__).resolve()))
    _refused(plan_path, tmp_path, calls, capsys, fragment="dépôt")


@pytest.mark.parametrize("form", ["separate", "equals"])
def test_command_line_anchor_is_refused_even_with_a_valid_host_approval(form, host_approval, launcher_seal, plan_path, tmp_path, calls, capsys):
    approved = _approved(launcher_seal)
    extra = [ANCHOR, approved] if form == "separate" else [f"{ANCHOR}={approved}"]
    _refused(plan_path, tmp_path, calls, capsys, extra=extra, fragment=ANCHOR)


def test_existing_output_is_refused(plan_path, tmp_path, launcher_seal, host_approval, calls, capsys):
    out = tmp_path / "OUT.json"
    out.write_text("existant", encoding="utf-8")
    argv = [*_args(plan_path), "--out", str(out)]
    assert anchored.main(argv) == 2
    assert out.read_text(encoding="utf-8") == "existant"
    assert capsys.readouterr().out == ""
    assert calls == []


def test_coordinated_alteration_is_refused_and_the_positive_control_generates(tmp_path):
    plan = freeze.build_plan(measure=lambda: {str(s): 100 for s in freeze.SEEDS}, machinery_commit=COMMIT)
    plan_file = tmp_path / "PLAN_SUBPROCESS.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    real_launcher = Path(campaign.LAUNCHER_FILE)
    host_dir = tmp_path / "host"
    host_dir.mkdir()

    def run(seal, launcher, approval, out, witness, extra=(), repo_root=None):
        env = {k: v for k, v in os.environ.items() if k not in (ENV, "TEST_REPO_ROOT")}
        if approval is not None:
            env[ENV] = str(approval)
        if repo_root is not None:
            env["TEST_REPO_ROOT"] = str(repo_root)
        command = [sys.executable, "-I", str(driver), str(SCRIPTS.parent), str(seal), str(launcher), str(out), str(plan_file), str(witness), *extra]
        return subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)

    good_seal = tmp_path / "seal_ok.json"
    good_seal.write_text(json.dumps(sealing.build_seal(plan["digest"])), encoding="utf-8")
    old = _approved(good_seal)
    host_ok = _write_approval(host_dir / "host_ok.json", old)
    out_ok = tmp_path / "OUT_OK.json"
    witness_ok = tmp_path / "WITNESS_OK.txt"
    positive = run(good_seal, real_launcher, host_ok, out_ok, witness_ok)
    assert positive.returncode == 0, positive.stderr
    assert out_ok.exists()
    assert witness_ok.exists()
    assert json.loads(out_ok.read_text(encoding="utf-8"))["host_approval_file"] == str(host_ok.resolve())

    launcher = tmp_path / "launcher_altered.py"
    launcher.write_bytes(real_launcher.read_bytes() + b"\n# altere\n")
    body = {k: v for k, v in json.loads(good_seal.read_text(encoding="utf-8")).items() if k != "digest"}
    body["launcher_sha256"] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    seal = tmp_path / "seal_altered.json"
    seal.write_text(json.dumps({**body, "digest": sealing.digest_of(body)}), encoding="utf-8")
    new = _approved(seal)
    assert new != old
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    in_repo = _write_approval(fake_repo / "approvals.json", new)
    group_writable = _write_approval(host_dir / "host_group.json", new, 0o660)

    def attempt(label, approval, fragment, extra=(), repo_root=None):
        out = tmp_path / f"OUT_{label}.json"
        witness = tmp_path / f"WITNESS_{label}.txt"
        result = run(seal, launcher, approval, out, witness, extra, repo_root)
        assert result.returncode == 2, result.stderr
        assert result.stdout == ""
        assert fragment in result.stderr
        assert not out.exists()
        assert not witness.exists()

    attempt("argument", host_ok, ANCHOR, extra=[ANCHOR, new])
    attempt("in_repo", in_repo, "dépôt", repo_root=fake_repo)
    attempt("group_writable", group_writable, "inscriptible")
    attempt("unchanged_host", host_ok, "ne correspond pas")


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


def test_campaign_receives_no_anchor_and_seal_is_untouched(received, plan_path, tmp_path, launcher_seal, host_approval):
    approved = _approved(launcher_seal)
    before = _approved(campaign.SEAL_PATH)
    out = tmp_path / "OUT.json"
    assert anchored.main([*_args(plan_path), "--out", str(out)]) == 0
    assert received == [_args(plan_path)]
    assert ANCHOR not in received[0] and approved not in received[0]
    for flag in ("--plan", "--seeds", "--generations"):
        assert flag in received[0]
    assert _approved(campaign.SEAL_PATH) == before == approved
    assert json.loads(out.read_text(encoding="utf-8"))["approved_seal_sha256"] == approved


def test_received_argv_does_not_depend_on_the_option_order(received, plan_path, tmp_path, host_approval):
    base = _args(plan_path)
    assert anchored.main([*base, "--out", str(tmp_path / "A.json")]) == 0
    assert anchored.main(["--out", str(tmp_path / "B.json"), *base]) == 0
    assert campaign.main(base) == 0
    assert received[0] == received[1] == received[2] == base
