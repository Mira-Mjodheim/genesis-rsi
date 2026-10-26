# Second-order improvement of a repair learner — REPAIR2 and REPAIR3 results (20 October 2026)

**Results only.** The repair engine these experiments run on belongs to Anthony Mets's private
Mira project; its implementation is not published here. Protocols, frozen plans, raw results and
code are kept in that private repository and can be shown on request. The frozen plan digests
below let a reviewer with access check that nothing was changed after the freeze.

## Why this experiment

CIRCUIT2 asked whether an inherited improvement procedure improves itself. Its development
diagnosis ([CIRCUIT2 diagnostic](../../experiment/engine/CIRCUIT2/DEV_DIAGNOSTIC_2026-10-20.md))
found that the circuit bench has no leverage: the first level stops learning after one or two
generations and procedures change held-out results by 0 to 3 tasks out of 37, so its criterion
was unreachable by construction. The second-order question was moved to a learner that does
keep improving: a no-model program-repair learner.

## Setting

- **First level (learner).** At each generation the learner receives a new batch of validated
  fixes of real student programs (Refactory, four exercises) and turns them into a bounded memory
  of expression-rewrite rules. It repairs with no model call: a candidate is proposed only if it
  passes the provided tests.
- **Second level (learning procedure).** How fixes become rules: how much a rule is generalised,
  where it may apply, which rules are kept, how they are ranked, and whether the memory is tried
  before or after a generic edit grammar (768 procedures, written by hand).
- **Selection.** At each generation, variants of the current procedure are scored on the *next*
  batch of training fixes (not yet learnt from); the best is adopted only if strictly better.
- **Judge.** Held-out programs, never read for any choice, judged by their provided tests plus
  inputs allowed by the exercise statement, labelled by consensus of five correct submissions.
- **Liveness test before any freeze** (development seeds only): the first level must keep
  improving and procedures must change outcomes. Both held here (15.2 to 26.0 solved over six
  generations; 13 to 37 across procedures), unlike CIRCUIT2.
- All lineages are replayed exactly from a precomputed rule × case matrix built in an offline
  sandbox. Zero model calls during the experiments; the training fixes were obtained earlier.

## REPAIR2 (frozen plan sha256 `c96fa315cde7e433faa98b676e49ab4356a647e2d1788a166386bf1f383ba6d6`)

160 held-out programs, 20 seeds (order in which fixes arrive), six generations. Mean held-out
programs repaired correctly:

| Generation | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| fixed procedure | 18.3 | 20.6 | 22.1 | 23.6 | 24.7 | 25.4 |
| **selected procedure** | 19.4 | 24.1 | 27.6 | 30.6 | 32.2 | **33.4** |
| drift (variants adopted at random) | 19.2 | 20.9 | 21.1 | 24.3 | 24.9 | 26.8 |
| random procedure | 16.4 | 18.0 | 18.9 | 21.5 | 21.9 | 22.3 |

All four frozen criteria passed: selected beats fixed in 19/20 seeds (one-sided sign test
p = 2e-5, +4.9 points), drift in 18/20, random in 19/20; 47 of 59 adoptions (80 %) improve
held-out results with identical fixes. The gap widens at every generation, and drift does not
beat fixed: the gain comes from selection, not from change. Without ever reading the held-out
set, selection converged on trying the learnt memory before the generic grammar (18/20 seeds)
and on concrete rather than generalised rules (15/20).

## REPAIR3 (frozen plan sha256 `33b02f2f6a376d2d456a57724e58c4a5a630ad7c7ef7f7f7d84913f10a5e6cc5`)

257 fresh held-out programs, never used before, judged the same way.

| Question | Result | Verdict |
|---|---|---|
| Replication of REPAIR2 | selected 51.0 vs fixed 42.2; 19 wins, 0 losses, 1 tie (p = 2e-6) | **passed** |
| Recursion: does the *selector* improve when it is itself selected (third level, judged on a held-aside training split)? | 53.4 vs 51.0; 10 wins, 2 losses, 8 ties (p = 0.02) | failed (15/20 required) |
| Third-level selector vs randomly changed selector | 12 wins, 4 losses, 4 ties | failed |
| Third-level adoptions that improve held-out results | 19 of 52 (37 %) | failed (60 % required) |
| Transfer: learn on three exercises, judge on the fourth | 8 wins, 8 losses, 64 ties | failed |

## What is and is not established

- **Established, in this bounded setting:** a learning procedure selected on training data,
  generation after generation, makes a no-model repair learner learn better than a fixed
  procedure, a drifting one or a random one, on held-out programs; the result replicates on a
  fresh held-out set.
- **Not established:** improvement of the selector itself (signal weak, below the frozen
  threshold); transfer across exercises (rules stay exercise-specific); invention of new
  learning mechanisms (the procedure space is hand-written); general RSI.
- A follow-up (learning which generic edits to trust) was **not run**: on the fresh set a better
  choice could fix at most 6 programs and abstention avoid 7 false fixes out of 257, because the
  generic grammar applies to only 15 % of defects.

## Lesson for Genesis

Higher levels have traction only when the first level has headroom. Across CIRCUIT2, REPAIR3
and the follow-up, the limit is the **representation** of what is learnt (exercise-specific
rules, a grammar covering few defects), the expressivity limit Genesis already recorded in the
A6 campaigns. The next step is a first level with a more general representation.
