# The first two lineages of improvers: no promotion, and a bench that could not tell

Negative result. General RSI remains the objective, not an achieved result.

Protocol: [SELF_IMPROVER_PROTOCOL_2026-10-11.md](SELF_IMPROVER_PROTOCOL_2026-10-11.md).
Records: `experiment/improver/SELF1/`, `experiment/improver/SELF2/`.

## What ran

| Lineage | Model | Generations planned | Sealed | Promotions |
|---|---|---|---|---|
| SELF1 | Haiku 5.5 (OpenRouter) | 5 | 5 | 0 |
| SELF2 | gpt-6.1-sol, low effort (Codex client) | 5 | 1 | 0 |

In every generation the current improver, still the 39-line seed, was handed its own source
as the program to improve. In SELF1 it returned a rewritten improver five times (66 to 118
lines: several candidates per request, evaluation details fed back, the last rejected
candidate shown). None passed the judge. In SELF2 the first self-application returned the
seed unchanged: none of its rewrites scored above it on the improver's own check.

SELF1, candidate against parent on 30 fresh tasks per generation:

| Generation | Parent mean | Candidate mean | Tasks won | Tasks lost | Sign test |
|---|---|---|---|---|---|
| 1 | 0.594 | 0.589 | 5 | 6 | 0.73 |
| 2 | 0.597 | 0.674 | 4 | 7 | 0.89 |
| 3 | 0.623 | 0.651 | 3 | 3 | 0.66 |
| 4 | 0.619 | 0.658 | 7 | 5 | 0.39 |
| 5 | 0.654 | 0.617 | 2 | 6 | 0.96 |

USD 4.71 spent of the 5.50 ceiling. Chain criterion (three promotions): not met.

## What the bench could measure

The same 150 task pairs, by family (post hoc; a pair is won or lost beyond 0.005):

| Family | Pairs | Won by the candidate | Lost | Scores of exactly zero (of 50) |
|---|---|---|---|---|
| bin packing | 25 | 2 | 1 | 0 |
| colouring | 25 | 1 | 1 | 0 |
| tardiness | 25 | 0 | 0 | 0 |
| quadratic assignment | 25 | 7 | 3 | 0 |
| travelling salesman | 25 | 9 | 9 | 16 |
| regression | 25 | 2 | 13 | 0 |

- Three families give every improver the same score: the first program the model writes is
  as good as anything six requests reach. They carry no information about the improver.
- Travelling salesman is decided by the time limit. Programs that search until the two
  seconds are nearly spent pass or fail with the load of the machine: 16 of 50 scores are
  exactly zero, on both sides. The differences between generation means (0.34 against 0.84
  in generation 2) are this and nothing else.
- Regression is the one family where improvers differ, and there the candidates are worse:
  13 pairs lost, 2 won.

So the mean scores of the table above say nothing, and the only family with a signal says
the rewritten improvers are worse than the seed. Both weaknesses of the bench were listed
in the protocol before the lineages ran; their size was not known.

## Why the candidates are not better (reading, not a test)

The improver selects among its rewrites with what the task "improver" lets it measure: six
evaluations, each running a rewrite on four tasks and scoring two instances per task. On a
bench where five families out of six do not separate improvers, that measure is noise, and
the rewrite that comes out is the one that was lucky. Nothing here shows that the model
cannot write a better improver; nothing shows that it can.

## SELF2 is stopped after one generation

SELF2 shares the bench of SELF1. Its four remaining generations would cost about 1,700
requests of a shared subscription to repeat a measurement now known to be blind. It is
stopped; this is a deviation from its plan, decided after seeing SELF1, and SELF2 counts as
an unfinished lineage, not as a reproduction.

## What changes for the next lineage

A new bench, frozen by a new plan; SELF1 and SELF2 stay as they are, reproducible at
`provenance/self-improver-plan-20261011` and `provenance/self-improver-plan2-20261011`.

- **Families where the program is a learner.** Each instance hides a rule and gives
  examples; the program must find the rule and answer queries. Development: regression,
  classification, regular languages, list transformations, forecasting, cellular automata.
  Held out: sequence prediction, matrix completion, next-symbol prediction, modular
  relations. The five optimisation families no lineage used stay apart as a far test. The
  five families of the first bench that carried SELF1 are retired.
- **Processor time, not wall-clock time**, for the two-second limit.
- **Twenty hidden instances per task** instead of five, six instead of two for an
  improver's own check, and one task of every development family in that check.
- **Three requests per task** instead of six, so that a generation fits in about 300
  requests with 30 paired tasks.
- **Wilcoxon signed-rank test** over the paired tasks, exact and one-sided, in place of the
  sign test with a margin: scores are now graded on every family.

## The second bench, checked before any lineage (pilots, not evidence)

Thirty development tasks (twelve on Codex), the same for every improver; scores are host
scores on the twenty hidden instances.

| Model | One request | Seed improver (three requests) | Tasks won / lost | Signed-rank |
|---|---|---|---|---|
| gpt-6.1-sol, low effort (Codex) | 0.921 | 0.920 | — | — |
| gpt-oss-120b | 0.729 | 0.753 | 12 / 5 | 0.07 |
| gpt-oss-20b | 0.600 | 0.707 | 15 / 3 | 0.009 |

The bench separates improvers only where the model is weak. On the strong model one
request already reaches what three reach: no improver can be told from another, and no
lineage is worth running. On the weakest model a loop helps, which is known, and a lineage
there would measure how well a scaffold compensates a small model. No third lineage is
planned: see [GENESIS_REORIENTATION_2026-10-11.md](GENESIS_REORIENTATION_2026-10-11.md).
Cost of the pilots: 48 Codex requests and about USD 0.15.
