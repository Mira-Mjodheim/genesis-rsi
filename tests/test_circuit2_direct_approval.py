"""Approbation du wrapper non scellé, hors réseau, sans génération réelle.

Seul le point d'entrée hôte (wrapper non scellé + fichier d'approbation hors dépôt,
variable GENESIS_HOST_APPROVALS) est protégé. L'appel direct du lanceur historique
gelé n'est PAS protégé par le wrapper, et cette limite subsiste : le refuser
exigerait un nouveau lanceur re-scellé, décision à prendre séparément.
Le dépôt ne prouve pas l'indépendance de l'approbation : elle dépend de la
configuration de l'hôte (fichier hors dépôt, non inscriptible par le candidat).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import run_circuit2_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_circuit2_anchored.py"
LAUNCHER = ROOT / "scripts" / "run_circuit2_campaign.py"
OPTION = "--approved-seal-sha256"
ENV = "GENESIS_HOST_APPROVALS"
KEY = "circuit2_launcher_seal_sha256"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchored(tmp_path, extra, approvals=None):
    out = tmp_path / "OUT.json"
    env = {k: v for k, v in os.environ.items() if k != ENV}
    if approvals is not None:
        env[ENV] = str(approvals)
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
        env=env,
    )


def test_anchored_subprocess_requires_approval(tmp_path):
    done = _anchored(tmp_path, [])
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.startswith("refus")
    assert list(tmp_path.iterdir()) == []


def _host_file(tmp_path_factory, content):
    """Fichier d'approbation hôte hors dépôt et hors du répertoire de travail, mode 0o600."""
    path = tmp_path_factory.mktemp("host") / "approvals.json"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    assert not path.resolve().is_relative_to(ROOT.resolve())
    return path


@pytest.mark.parametrize("value", ["", "abc", "F" * 64, "0" * 63, "0" * 64])
def test_anchored_subprocess_refuses_a_command_line_anchor(tmp_path, tmp_path_factory, value):
    """Empreinte hôte volontairement différente du sceau : aucune génération possible, même en cas de régression."""
    approvals = _host_file(tmp_path_factory, json.dumps({KEY: "0" * 64}))
    done = _anchored(tmp_path, [OPTION, value], approvals)
    assert done.returncode == 2
    assert done.stdout == ""
    assert OPTION in done.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content", ["", "{", "[]", "{}", json.dumps({KEY: "F" * 64}), json.dumps({KEY: "0" * 64})])
def test_anchored_subprocess_refuses_an_invalid_or_different_host_approval(tmp_path, tmp_path_factory, content):
    approvals = _host_file(tmp_path_factory, content)
    done = _anchored(tmp_path, [], approvals)
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.startswith("refus")
    assert list(tmp_path.iterdir()) == []


def test_historical_launcher_matches_the_versioned_seal():
    seal = json.loads(Path(campaign.SEAL_PATH).read_bytes())
    assert _sha(LAUNCHER) == seal["launcher_sha256"]

def test_direct_historical_entry_point_bypasses_the_wrapper():
    """Limite connue, qui subsiste : l'appel direct du lanceur gelé n'est PAS protégé par le wrapper.

    Seul le point d'entrée hôte (wrapper + fichier d'approbation hors dépôt) est protégé.
    Fermer l'appel direct exigerait un nouveau lanceur re-scellé, décision à prendre
    séparément. L'indépendance de l'approbation n'est pas prouvée par le dépôt : elle
    dépend de la configuration de l'hôte (fichier hors dépôt, non inscriptible par le candidat).
    """
    source = LAUNCHER.read_text(encoding="utf-8")
    module = ast.parse(source)
    expected = ast.parse(
        'if __name__ == "__main__":\n'
        '    raise SystemExit(main())\n'
    ).body[0]
    assert ast.dump(module.body[-1]) == ast.dump(expected)
    assert OPTION not in source
    assert "run_circuit2_anchored" not in source
