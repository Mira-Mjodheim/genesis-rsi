"""Lanceur CIRCUIT2 ancré : vérifie l'empreinte SHA-256 du sceau approuvé avant toute génération.

Ce script n'est pas scellé. Le lanceur scellé (run_circuit2_campaign.py) est appelé
inchangé. L'empreinte approuvée n'est jamais lue sur la ligne de commande : elle vient
d'un fichier d'approbation hôte, dont le chemin est donné par la variable d'environnement
GENESIS_HOST_APPROVALS (JSON {"circuit2_launcher_seal_sha256": "<64 hex minuscules>"}).
Tout ce qui vit dans le dépôt pouvant être modifié conjointement par un candidat, ce
fichier doit se trouver hors de la racine du dépôt et n'être inscriptible ni par le groupe
ni par les autres. Cette séparation dépend de la configuration de l'hôte ; le dépôt ne la
prouve pas. Refus (code 2) avant toute génération, sans sortie standard et sans fichier
--out, si la variable est absente, si le fichier est illisible, mal formé, situé dans le
dépôt ou modifiable par le groupe ou les autres, si l'empreinte est mal formée ou différente
de celle du sceau courant, si --approved-seal-sha256 est passé en ligne de commande ou si
--out existe déjà.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_circuit2_campaign as campaign  # noqa: E402

_HEX64 = re.compile(r"[0-9a-f]{64}")
ENV_VAR = "GENESIS_HOST_APPROVALS"
APPROVAL_KEY = "circuit2_launcher_seal_sha256"
REPO_ROOT = Path(__file__).resolve().parents[1]


class AnchorError(Exception):
    """Approbation hôte absente, non fiable, mal formée ou différente de l'empreinte du sceau."""


def seal_sha256() -> str:
    """Empreinte SHA-256 des octets du fichier de sceau courant."""
    try:
        return hashlib.sha256(Path(campaign.SEAL_PATH).read_bytes()).hexdigest()
    except OSError as exc:
        raise AnchorError(f"sceau illisible : {exc}") from exc


def load_host_approval() -> tuple[str, Path]:
    """Lit l'empreinte approuvée dans le fichier d'approbation hôte ; lève AnchorError s'il n'est pas fiable."""
    raw = os.environ.get(ENV_VAR)
    if not raw:
        raise AnchorError(f"{ENV_VAR} est requis")
    try:
        path = Path(raw).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AnchorError(f"fichier d'approbation hôte illisible : {exc}") from exc
    if path.is_relative_to(REPO_ROOT.resolve()):
        raise AnchorError("le fichier d'approbation hôte ne doit pas se trouver dans le dépôt")
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise AnchorError(f"fichier d'approbation hôte illisible : {exc}") from exc
    if mode & 0o022:
        raise AnchorError("le fichier d'approbation hôte est inscriptible par le groupe ou les autres")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise AnchorError(f"fichier d'approbation hôte illisible ou mal formé : {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get(APPROVAL_KEY), str):
        raise AnchorError("fichier d'approbation hôte mal formé")
    approved = data[APPROVAL_KEY]
    if not _HEX64.fullmatch(approved):
        raise AnchorError("l'empreinte approuvée doit être 64 caractères hexadécimaux minuscules")
    return approved, path


def check_approved(approved: str) -> str:
    """Compare l'empreinte approuvée à celle du fichier de sceau courant ; lève AnchorError sinon."""
    if seal_sha256() != approved:
        raise AnchorError("l'empreinte du sceau ne correspond pas à l'approbation hôte")
    return approved


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--approved-seal-sha256", default=None)
    parser.add_argument("--out", default=None)
    known, rest = parser.parse_known_args(args)
    if known.approved_seal_sha256 is not None:
        print("refus : --approved-seal-sha256 n'est pas accepté en ligne de commande ; l'approbation vient du fichier désigné par GENESIS_HOST_APPROVALS", file=sys.stderr)
        return 2
    try:
        approved, approval_file = load_host_approval()
        check_approved(approved)
    except AnchorError as exc:
        print(f"refus : {exc}", file=sys.stderr)
        return 2
    if known.out is None:
        print("refus : --out est requis", file=sys.stderr)
        return 2
    out = Path(known.out)
    if out.exists():
        print(f"refus : {out} existe déjà", file=sys.stderr)
        return 2
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = campaign.main(rest)
    if code:
        return code
    try:
        result = json.loads(buffer.getvalue())
    except ValueError:
        result = None
    if not isinstance(result, dict):
        print("refus : la sortie du lanceur n'est pas un objet JSON", file=sys.stderr)
        return 2
    result["approved_seal_sha256"] = approved
    result["host_approval_file"] = str(approval_file)
    result["command"] = args
    try:
        with open(out, "x", encoding="utf-8") as handle:
            handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        print(f"refus : {out} existe déjà", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
