"""Gèle les empreintes sha256 des exécutables de la campagne circuit2.

Écrit experiment/engine/CIRCUIT2/EXECUTABLES.json en création exclusive
(refus si le fichier existe). Ne modifie pas le plan gelé.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "experiment" / "engine" / "CIRCUIT2" / "EXECUTABLES.json"
EXECUTABLES = (
    "scripts/adjudicate_circuit_lineage.py",
    "scripts/run_circuit2_campaign.py",
    "scripts/run_circuit2_arms.py",
    "scripts/freeze_circuit2_plan.py",
    "genesis/circuit_engine.py",
    "genesis/circuit_procedure.py",
    "genesis/circuit_meta_lineage.py",
    "genesis/circuit_tasks.py",
)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def global_digest(files):
    """Digest global des empreintes (clés triées)."""
    data = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_manifest(root=ROOT, paths=EXECUTABLES):
    """Calcule le manifeste ; FileNotFoundError si un chemin est absent."""
    root = Path(root)
    missing = [rel for rel in paths if not (root / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"exécutables absents : {missing}")
    files = {rel: file_sha256(root / rel) for rel in sorted(paths)}
    return {"digest": global_digest(files), "files": files}


def write_manifest(manifest_path=MANIFEST_PATH, root=ROOT, paths=EXECUTABLES):
    """Écrit le manifeste en création exclusive ; FileExistsError s'il existe."""
    manifest = compute_manifest(root, paths)
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(MANIFEST_PATH))
    args = ap.parse_args(argv)
    try:
        manifest = write_manifest(Path(args.out))
    except OSError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 2
    print(f"manifeste écrit : {args.out} (digest {manifest['digest']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
