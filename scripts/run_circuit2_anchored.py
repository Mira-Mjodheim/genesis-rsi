"""Lanceur CIRCUIT2 ancré : vérifie l'empreinte SHA-256 du sceau approuvé avant toute génération.

Ce script n'est pas scellé. Le lanceur scellé (run_circuit2_campaign.py) est appelé
inchangé, sans l'ancre : l'ancre n'est vérifiée que par ce script non scellé, qui la
retire des arguments avant de déléguer. Refus (code 2) avant toute génération et sans
sortie standard si l'ancre est absente, mal formée ou différente de l'empreinte du
fichier de sceau, ou si le fichier de sortie existe déjà.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_circuit2_campaign as campaign  # noqa: E402

_HEX64 = re.compile(r"[0-9a-f]{64}")


class AnchorError(Exception):
    """Ancre absente, mal formée ou différente de l'empreinte du sceau."""


def seal_sha256() -> str:
    """Empreinte SHA-256 des octets du fichier de sceau courant."""
    try:
        return hashlib.sha256(Path(campaign.SEAL_PATH).read_bytes()).hexdigest()
    except OSError as exc:
        raise AnchorError(f"sceau illisible : {exc}") from exc


def check_approved(approved: str | None) -> str:
    """Valide l'ancre contre l'empreinte du sceau ; lève AnchorError sinon."""
    if approved is None:
        raise AnchorError("--approved-seal-sha256 est requis")
    if not _HEX64.fullmatch(approved):
        raise AnchorError("--approved-seal-sha256 doit être 64 caractères hexadécimaux minuscules")
    actual = seal_sha256()
    if actual != approved:
        raise AnchorError("l'empreinte du sceau ne correspond pas à l'ancre approuvée")
    return approved


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--approved-seal-sha256", default=None)
    parser.add_argument("--out", default=None)
    known, rest = parser.parse_known_args(args)
    try:
        approved = check_approved(known.approved_seal_sha256)
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
