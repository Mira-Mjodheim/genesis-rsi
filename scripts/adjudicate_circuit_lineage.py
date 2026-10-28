"""Adjudication de la lignée de circuits : rendements held-out par bras et par graine.

Ce script ne calcule aucun gain, seuil ni succès : il mesure et consigne.
Les budgets proviennent du plan gelé et ne sont jamais redéfinis ici.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import freeze_circuit2_executables as fce  # noqa: E402
import freeze_circuit2_plan as fcp  # noqa: E402
import run_circuit2_arms as rca  # noqa: E402
import run_circuit2_campaign as rcc  # noqa: E402
from run_circuit2_campaign import ArmRun, PlanError, load_plan, new_run  # noqa: E402,F401
from genesis import circuit_engine as ce  # noqa: E402
from genesis import circuit_procedure as cp  # noqa: E402
from genesis import circuit_tasks as ct  # noqa: E402

DEFAULT_PLAN = fcp.PLAN_PATH


def fingerprint(obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def engine_from_record(rec):
    """Reconstruit un Engine ; ValueError si Engine.record() diffère de rec."""
    engine = ce.Engine(
        [
            ce.Component(r["name"], r["arity"], tuple(tuple(s) for s in r["steps"]), r["weight"])
            for r in rec
        ]
    )
    if engine.record() != rec:
        raise ValueError("enregistrement non reproduit exactement par Engine.record()")
    return engine


def _procedure_record(run, arm):
    if arm == "inherited_lineage":
        return run.state["procedure"]
    if run.procedure is None:
        return None
    return cp.to_record(run.procedure)


def final_library(arm, seed, tasks, limit, budget, generations):
    """Pilote un ArmRun persistant, sans rejeu de préfixe.

    Renvoie (enregistrements de génération, Engine final, procédure finale,
    procédure initiale).
    """
    run = new_run(arm, seed, tasks, limit, budget)
    initial = _procedure_record(run, arm)
    records = []
    for _ in range(generations):
        record = run.step()
        records.append(record)
        if rcc._stops(record):
            break
    engine = run.state.engine if arm == "inherited_lineage" else run.engine
    return records, engine, _procedure_record(run, arm), initial


def stop_reason(records):
    """Raison d'arrêt d'une exécution, dérivée des enregistrements de génération."""
    if records and rcc._stops(records[-1]):
        return rcc.STOP_REASON
    return rcc.LIMIT_REASON


def _read_manifest(path, label):
    """Contenu JSON d'un manifeste ; PlanError si absent ou illisible."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanError(f"manifeste d'exécutables {label} absent : {path}") from exc
    except (OSError, ValueError) as exc:
        raise PlanError(f"manifeste d'exécutables {label} illisible : {exc}") from exc


def _manifest_files(manifest):
    """Empreintes d'un manifeste valide ; PlanError sinon."""
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or not files:
        raise PlanError("manifeste d'exécutables sans fichiers listés")
    if manifest.get("digest") != fce.global_digest(files):
        raise PlanError("digest global du manifeste d'exécutables invalide")
    for rel in sorted(files):
        if not isinstance(files[rel], str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise PlanError(f"entrée invalide dans le manifeste : {rel}")
    return files


def verify_executables(manifest_path=None, root=ROOT, canonical_path=None, required=None):
    """Vérifie les exécutables gelés contre le manifeste canonique d'empreintes.

    Les défauts sont résolus à l'appel : canonical_path = fce.MANIFEST_PATH et
    required = fce.EXECUTABLES. Ordre des contrôles :
    a. le manifeste canonique est chargé et validé (absent, illisible ou
       invalide => PlanError) ;
    b. ses fichiers listés doivent être exactement ceux de `required` ;
    c. un manifeste `manifest_path` distinct du canonique n'est admis que s'il
       en est une copie conforme (contenu JSON égal), jamais comme source
       d'empreintes ;
    d. chaque fichier de `root` est comparé aux empreintes canoniques.
    Aucun calcul ni lecture de HELD_OUT.

    Le manifeste canonique officiel (experiment/engine/CIRCUIT2/EXECUTABLES.json)
    n'existe pas encore : il sera créé après fusion par
    scripts/freeze_circuit2_executables.py (action run), depuis main, dans un
    changement séparé. Tant qu'il est absent, le lancement réel est refusé, ce
    qui est voulu.
    """
    if canonical_path is None:
        canonical_path = fce.MANIFEST_PATH
    if required is None:
        required = fce.EXECUTABLES
    canonical_path = Path(canonical_path)
    root = Path(root)
    canonical = _read_manifest(canonical_path, "canonique")
    files = _manifest_files(canonical)
    if set(files) != set(required):
        missing = sorted(set(required) - set(files))
        extra = sorted(set(files) - set(required))
        raise PlanError(
            "manifeste canonique non conforme à la liste attendue : "
            f"manque {missing}, surplus {extra}"
        )
    if manifest_path is not None and Path(manifest_path) != canonical_path:
        provided = _read_manifest(manifest_path, "fourni")
        if provided != canonical:
            raise PlanError("manifeste fourni différent du manifeste canonique")
    for rel in sorted(files):
        try:
            actual = fce.file_sha256(root / rel)
        except OSError as exc:
            raise PlanError(f"exécutable absent ou illisible : {rel}") from exc
        if actual != files[rel]:
            raise PlanError(f"exécutable altéré : {rel}")


def measure_held_out(engine, plan_path=None, integrity=None):
    """Rendement held-out de `engine` après vérification du plan gelé.

    Le plan est lu et vérifié (freeze_circuit2_plan.verify_plan) avant toute
    construction de la suite HELD_OUT ; absent, illisible ou invalide => PlanError.
    Toute la suite circuit2_suite(HELD_OUT) est évaluée avec le task_budget du
    plan, sans filtre sur le nombre d'entrées.
    Les exécutables sont vérifiés (verify_executables) juste après le plan.
    """
    path = Path(plan_path) if plan_path is not None else DEFAULT_PLAN
    try:
        plan = load_plan(path)
        fcp.verify_plan(plan)
        verify_executables(integrity)
        task_budget = plan["budgets"]["task_budget"]
    except PlanError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PlanError(f"plan illisible ou invalide : {exc}") from exc
    tasks = list(ct.circuit2_suite(tuple(ct.HELD_OUT)))
    return ce.measure(ce.attempt(engine, tasks, task_budget))[0]


def _git_commit():
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = res.stdout.strip()
    return commit if res.returncode == 0 and commit else None


def _validate_request(plan, seeds, generations, arms):
    """Message de refus, ou None si la demande est conforme au plan gelé."""
    if not seeds:
        return "seeds vide"
    if len(set(seeds)) != len(seeds):
        return "seeds dupliquées"
    unknown = sorted(set(seeds) - set(plan["seeds"]))
    if unknown:
        return f"seeds hors plan : {unknown}"
    max_gen = plan["budgets"]["generations"]
    if isinstance(generations, bool) or not isinstance(generations, int):
        return "generations doit être un entier"
    if not 1 <= generations <= max_gen:
        return f"generations doit être dans [1, {max_gen}]"
    if len(set(arms)) != len(arms):
        return "arms dupliqués"
    bad = [a for a in arms if a not in rca.ARMS]
    if bad:
        return f"arms inconnus : {bad}"
    return None


def _refuse(message):
    print(f"erreur : {message}", file=sys.stderr)
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--arms", nargs="+", default=None)
    ap.add_argument("--integrity", default=None)
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if (ROOT / "results").resolve() not in out.parents:
        return _refuse("--out doit se trouver sous results/")
    plan_path = Path(args.plan) if args.plan else DEFAULT_PLAN
    try:
        plan = load_plan(plan_path)
        fcp.verify_plan(plan)
        verify_executables(args.integrity)
        arms = list(args.arms) if args.arms is not None else list(rca.ARMS)
        message = _validate_request(plan, args.seeds, args.generations, arms)
    except PlanError as exc:
        return _refuse(str(exc))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _refuse(f"plan illisible ou invalide : {exc}")
    if message:
        return _refuse(message)
    if out.exists():
        return _refuse("le fichier de sortie existe déjà")
    tasks = fcp.learn_tasks()
    budget = plan["budgets"]["task_budget"]
    limit = plan["budgets"]["per_generation_limit"]
    rows = []
    for arm in arms:
        for seed in args.seeds:
            records, engine, _final, _initial = final_library(
                arm, seed, tasks, limit, budget, args.generations
            )
            row = {
                "arm": arm,
                "seed": seed,
                "generations": len(records),
                "held_out_yield": measure_held_out(engine, plan_path, args.integrity),
                "library_fingerprint": fingerprint(engine.record()),
            }
            row["stop_reason"] = stop_reason(records)
            rows.append(row)
    full = (
        set(args.seeds) == set(plan["seeds"])
        and args.generations == plan["budgets"]["generations"]
        and set(arms) == set(rca.ARMS)
    )
    payload = {
        "rows": rows,
        "plan_digest": plan["digest"],
        "machinery_commit": _git_commit(),
        "task_budget": budget,
        "per_generation_limit": limit,
        "generations": args.generations,
        "seeds": list(args.seeds),
        "arms": arms,
        "scale": "full" if full else "reduced",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
