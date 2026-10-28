"""Diagnostic de vivacité du chemin circuit2 : aucune tâche n'est résolue.

Le diagnostic ne lit que les tâches d'apprentissage de CIRCUIT1 (familles de
tasks.LEARN, obtenues famille par famille via tasks.tasks). Il n'appelle jamais
_circuit2_assignment, ne construit aucune famille HELD_OUT ni CONTROL, et
n'établit rien sur la génération CIRCUIT2 elle-même.
"""
import importlib
import json
import random
import sys
from pathlib import Path

_RACINE = Path(__file__).resolve().parent.parent
for _chemin in (_RACINE, _RACINE / "scripts"):
    if str(_chemin) not in sys.path:
        sys.path.insert(0, str(_chemin))


def _parents(chemin):
    parties = chemin.split(".")
    return {".".join(parties[:i]) for i in range(1, len(parties) + 1)}


def _charger(nom):
    for prefixe in ("", "genesis.", "scripts.", "src.genesis.", "src."):
        essai = prefixe + nom
        try:
            return importlib.import_module(essai)
        except ModuleNotFoundError as exc:
            if exc.name in _parents(essai):
                continue
            raise
    raise ModuleNotFoundError(nom, name=nom)


cp = _charger("circuit_procedure")
tasks = _charger("circuit_tasks")

CAS_TRAITS = ((0, 0, 0, False), (1, 1, 1, False), (2, 2, 3, True), (4, 3, 5, True))


def _record_json(p):
    return json.dumps(cp.to_record(p), sort_keys=True, default=str)


def _famille(t):
    if isinstance(t, dict):
        return t.get("family")
    return getattr(t, "family", None)


def _valider(p, nom, violations):
    try:
        cp.validate(p)
    except cp.ProcedureError as exc:
        violations.append(f"validate refuse {nom} : {exc}")
        return False
    return True


def _verifier_run(p, traits, nom, violations):
    prio, admis, portes = cp.run(p, traits)
    sorties = getattr(p, "priority_outputs", None)
    if not isinstance(prio, int) or isinstance(prio, bool):
        violations.append(f"priorité non entière sur {nom}")
    elif sorties is not None and not 0 <= prio < 2 ** len(sorties):
        violations.append(f"priorité hors bornes sur {nom}")
    if not isinstance(admis, bool):
        violations.append(f"admis non booléen sur {nom}")
    if portes != len(p.steps):
        violations.append(f"portes != len(steps) sur {nom}")
    return portes


def diagnose(seed=0, mutations=20, runs=20, randoms=3):
    rng = random.Random(f"liveness|{seed}")
    violations = []
    courant = cp.seed_procedure()
    procs = []
    mutations_done = 0
    if _valider(courant, "départ", violations):
        procs.append(("départ", courant))
        for i in range(mutations):
            avant = _record_json(courant)
            nouveau = cp.mutate(courant, rng)
            if _record_json(courant) != avant:
                violations.append(f"mutate modifie son entrée (étape {i})")
            if nouveau is None:
                continue
            if not _valider(nouveau, f"mutée {i}", violations):
                continue
            mutations_done += 1
            procs.append((f"mutée {i}", nouveau))
            courant = nouveau
    randoms_done = 0
    for j in range(randoms):
        n = rng.randint(0, cp.MAX_STEPS)
        q = cp.random_procedure(rng, n)
        if not _valider(q, f"aléatoire {j}", violations):
            continue
        randoms_done += 1
        procs.append((f"aléatoire {j}", q))
    nb_traits = len(cp.TRAITS)
    cas_fixes = [cp.traits_of(*c) for c in CAS_TRAITS]
    runs_done = 0
    gates_total = 0
    roundtrips_ok = 0
    digests = []
    steps_par_proc = []
    for nom, p in procs:
        cas = [tuple(rng.randint(0, 1) for _ in range(nb_traits)) for _ in range(runs)]
        cas += cas_fixes
        for traits in cas:
            gates_total += _verifier_run(p, traits, nom, violations)
            runs_done += 1
        steps_par_proc.append(len(p.steps))
        d1 = cp.replay_digest(p, cas)
        if cp.replay_digest(p, cas) != d1:
            violations.append(f"replay_digest instable sur {nom}")
        digests.append(str(d1))
        copie = cp.from_record(cp.to_record(p))
        if _record_json(copie) == _record_json(p) and cp.replay_digest(copie, cas) == d1:
            roundtrips_ok += 1
        else:
            violations.append(f"aller-retour en échec sur {nom}")
    taches = []
    for famille in tasks.LEARN:
        suite = tasks.tasks(famille, seed)
        taches.extend(suite.values() if isinstance(suite, dict) else suite)
    familles = sorted({str(f) for f in map(_famille, taches) if f is not None})
    hors = [f for f in familles if f not in {str(x) for x in tasks.LEARN}]
    if hors:
        violations.append(f"familles hors LEARN : {hors}")
    if not taches:
        violations.append("suite circuit2 vide")
    manquantes = sorted({str(x) for x in tasks.LEARN} - set(familles))
    if manquantes:
        violations.append(f"familles LEARN absentes : {manquantes}")
    return {
        "seed": seed,
        "mutations_done": mutations_done,
        "randoms_done": randoms_done,
        "procedures": len(procs),
        "cases_per_procedure": runs + len(cas_fixes),
        "runs_done": runs_done,
        "gates_total": gates_total,
        "steps_per_procedure": steps_par_proc,
        "roundtrips_ok": roundtrips_ok,
        "learn_task_count": len(taches),
        "learn_families": familles,
        "digests": digests,
        "violations": violations,
    }


def main():
    print(json.dumps(diagnose(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
