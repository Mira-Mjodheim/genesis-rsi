"""Approbation du wrapper non scellé, hors réseau, sans génération réelle.

Point ouvert pour la PR : l'appel direct au lanceur historique est protégé par
la vérification du sceau, mais pas par l'ancre extérieure du wrapper. Le refuser
exigerait de modifier le lanceur gelé, en conflit avec son sceau.
Tests et git diff --check non exécutés lors de la proposition de ce diff.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import run_circuit2_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_circuit2_anchored.py"
LAUNCHER = ROOT / "scripts" / "run_circuit2_campaign.py"
OPTION = "--approved-seal-sha256"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchored(tmp_path, extra):
    out = tmp_path / "OUT.json"
    return subprocess.run(
        [
            sys.executable, "-B", str(SCRIPT),
            "--seeds", "0", "--generations", "1",
            "--out", str(out), *extra,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_anchored_subprocess_requires_approval(tmp_path):
    done = _anchored(tmp_path, [])
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.startswith("refus")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("approved", ["", "abc", "F" * 64, "g" * 64, "0" * 63, "different"])
def test_anchored_subprocess_refuses_invalid_approval(tmp_path, approved):
    if approved == "different":
        actual = _sha(Path(campaign.SEAL_PATH))
        approved = "0" * 64 if actual != "0" * 64 else "1" * 64
        assert approved != actual
    done = _anchored(tmp_path, [OPTION, approved])
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.startswith("refus")
    assert list(tmp_path.iterdir()) == []


def test_historical_launcher_matches_the_versioned_seal():
    seal = json.loads(Path(campaign.SEAL_PATH).read_bytes())
    assert _sha(LAUNCHER) == seal["launcher_sha256"]

def test_direct_historical_entry_point_bypasses_the_wrapper():
    """Limite connue : refuser cet appel modifierait le lanceur gelé et son hash."""
    source = LAUNCHER.read_text(encoding="utf-8")
    module = ast.parse(source)
    expected = ast.parse(
        'if __name__ == "__main__":\n'
        '    raise SystemExit(main())\n'
    ).body[0]
    assert ast.dump(module.body[-1]) == ast.dump(expected)
    assert OPTION not in source
    assert "run_circuit2_anchored" not in source
