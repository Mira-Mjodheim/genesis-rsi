# CIRCUIT2 — diagnostic de développement avant gel (20 octobre 2026)

Statut : **aucun plan gelé, aucune campagne.** Mesures faites uniquement sur des graines de
développement (100 à 102), jamais sur les graines 0 à 19 réservées au plan.

Question de CIRCUIT2 : *l'améliorateur s'améliore-t-il ?* (la procédure héritée, qui choisit les
composants ajoutés à la bibliothèque, choisit aussi la procédure suivante).

## 1. Défauts corrigés (dans cette branche)

| Défaut | Effet | Correction |
|---|---|---|
| Le générateur de tâches ignorait la graine | les 20 graines évaluaient les mêmes 37 tâches | graine incluse dans le tirage ; 20 empreintes distinctes sur 20 |
| Support d'une procédure candidate = nombre de tirages identiques | presque toujours 1 ; la procédure initiale (support ≥ 2) n'admettait **aucun** candidat (0/13) | support = décisions justes sur les composants réellement essayés à l'étape (a) (garder un utile, écarter un inutile) |
| Budget d'une génération épuisé par l'étape (a) | l'étape (b) ne s'exécutait jamais | la moitié du reste est réservée à l'étape (b) |

Après correction, des procédures candidates sont bien évaluées (2 à 6 par génération).
**Aucune n'est adoptée**, ce qui conduit au constat suivant.

## 2. Constat bloquant : le premier niveau n'a pas de marge

`scripts/run_circuit2_leverage_probe.py` fait tourner six générations avec la procédure initiale puis
avec dix procédures mutées, et compte les tâches réservées résolues (sur 37).

| Tâches d'apprentissage | Budget par tâche | Essais par génération | Bibliothèque finale | Procédure initiale | Procédures mutées |
|---|---:|---:|---:|---:|---|
| ≤ 4 entrées (20) | 16 384 | 2 | 1 composant | 5 / 7 / 7 | 5–6 / 7 / 7 |
| ≤ 4 entrées (20) | 16 384 | 3 | 1–2 | 6 / 7 / 8 | 5–6 / 7 / 7–8 |
| ≤ 4 entrées (20) | 65 536 | 2 | 1 | 7 / 9 / 8 | 7–8 / 9–12 / 8 |

- Le moteur cesse d'apprendre après **une ou deux** générations : 5 à 9 composants proposés,
  1 ou 2 retenus, puis plus rien.
- Changer de procédure ne déplace le résultat que **de 0 à 3 tâches sur 37**, et presque
  toujours de zéro.
- Le critère prévu (+10 points contre la procédure fixe et contre l'aléatoire dans 16 graines
  sur 20, deux transitions successives de +5 points) est donc **inatteignable par
  construction**, même si la récursion fonctionnait parfaitement.

Un échec de CIRCUIT2 sur ce banc ne dirait rien sur la récursion : il mesurerait la saturation
du premier niveau. Le plan n'est pas gelé.

## 3. Condition pour un test valide du second ordre

Avant tout gel, un banc doit passer un **test de vivacité**, mesuré sur des graines de
développement :
1. le premier niveau continue de s'améliorer pendant au moins six générations ;
2. le nombre de candidats dépasse nettement le nombre d'essais, pour que le classement compte ;
3. des procédures différentes donnent des résultats nettement différents en évaluation (levier).

Ces trois conditions ne disent rien de quel bras gagnera ; elles garantissent seulement que la
question peut recevoir une réponse.

Le banc CIRCUIT (circuits NAND, composants d'arité ≤ 3) ne les remplit pas.
