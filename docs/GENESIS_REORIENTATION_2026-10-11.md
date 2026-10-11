# Genesis reoriented: diagnosis, two architectures, a first CPU prototype — 11 October 2026

General RSI remains the objective, not an achieved result. This document records what the
existing architecture could and could not do, what the published systems actually show, two
candidate architectures, the first measurements of one of them and the cost of the other.
The question is no longer whether Genesis passes another level, but whether it can become
better at improving itself.

## 1. Diagnosis of the existing architecture

What exists: 123 modules (33,560 lines) under `genesis/`, most of them controllers,
policies and transformation languages built for earlier milestones; a validation
infrastructure (isolated Defects4J validator, an external bench of 744 bugs with a reserve
of 173, sealed preregistrations and results, provenance tags, a repository integrity
check); a repair agent and its lineages; a sandbox for model-written programs.

What the measurements say, separated by cause:

| Limitation | Evidence | Kind |
|---|---|---|
| The repair result is decided by the model | Each component of the repair agent changed alone moves nothing (12 → 10–14 of 32); Sonnet 5.5 in place of Haiku 5.5: 11 against 6 (`REPAIR_INTERVENTIONS_2026-10-10.md`) | model |
| Without a model the search space does not contain the fix | 9,239 candidates, none correct; ceiling near 1% (`REPAIR_SEARCH_SPACE_DIAGNOSIS_20261008.md`) | architecture |
| A loop around a strong model adds nothing where one request suffices | Codex, second bench: one request 0.921, seed improver with three 0.920 | architecture |
| Self-written improvers are not better | SELF1: five rewrites, none promoted; on the one family that separates improvers, 13 pairs lost and 2 won (`SELF_IMPROVER_LINEAGES_2026-10-11.md`) | procedure |
| An improver cannot select among its rewrites | Its own check ran each rewrite on four tasks, two instances each, every evaluation paying 24 model requests: selection by noise | procedure |
| The benches were blind | Five families of six gave every improver the same score; a wall-clock limit turned one family into a lottery | procedure (instrument) |
| Model-free recombination stops after one generation | External catalogue, unknown projects: confirmed once, exhausted after | architecture |

Common cause: in every experiment the capability measured sat in the model, and Genesis
changed only what surrounds it. An evaluation of an improvement also cost model requests,
so the judge of improvements was both expensive and noisy.

Kept: the validation infrastructure, the sandbox, the sealed records, the intervention
diagnosis, the ledgers and journals of model requests. Not continued: the lineage of
improvers on the first bench, SELF2 after one generation, and the lineage planned on small
models (below).

## 2. What the published systems show (checked in the papers)

| System | What is modified | What stays fixed | Measured | Limits stated by the authors |
|---|---|---|---|---|
| STOP (Zelikman et al., 2023, arXiv 2310.02304) | The scaffold program that calls the model | The model; the utility | GPT-4, one task (parity with noise), improvers selected over 4 rounds; the improved improver transfers to five other tasks (e.g. 3SAT 21.2% → 75.1%, quadratic assignment 20.6% → 22.1%). With GPT-3.5, 12% of 25 runs gain at least 3% | "not full recursive self-improvement": the model is unchanged; scaffolds not claimed better than hand-made ones |
| Darwin Gödel Machine (Zhang et al., 2025, arXiv 2505.22954) | The code of a coding agent, kept in an archive | Frozen foundation models; archive and parent selection ("not modifiable by the DGM") | 80 iterations, about two weeks for one SWE-bench run; 20.0% → 50.0% on SWE-bench, 14.2% → 30.7% on Polyglot; transfer across models and benchmarks; beats controls without self-improvement or without archive | Cost; capped by the model; the self-improvement machinery is fixed |
| AlphaZero (Silver et al., 2017, arXiv 1712.01815) | The weights of a network, by self-play with search | The algorithm (search and training), the rules of the game | Superhuman chess and shogi from random play within 24 hours | One fixed, exact environment per training; the learning algorithm does not change |
| Self-generated verified puzzles (Haluptzok et al., 2022, arXiv 2207.14502) | The weights of a small model, fine-tuned on its own solutions kept by an interpreter | The procedure | GPT-Neo 2.7B: 7.5% → 20.6% Pass@100 on its own verified data, 38.2% on Codex's; unverified data 21.5% | A second round brings a small further gain; stopped at two for cost |
| Absolute Zero (Zhao et al., 2025, arXiv 2505.03335) | The weights of 3B–14B models; the model proposes its own tasks, an executor verifies | The procedure | Out-of-distribution gain +5.7 (3B), +10.2 (7B), +13.2 (14B) points; Llama-3.1-8B +3.2 | The 3B curve plateaus; gains grow with the size of the model; compute not read in the part consulted |

What carries over to Genesis and what does not:

- STOP is the lineage of improvers already run here. Its positive result needs GPT-4-level
  rewriting, a task where one request is far from the ceiling, and a meta-utility cheap
  enough to select on. Genesis had the second with small models only and never the third.
- The Darwin Gödel Machine needs weeks of a frontier model on a benchmark with a wide gap
  between a bare agent and a good one. Its selection machinery is fixed: it is cumulative
  improvement of an agent, not of the improver.
- AlphaZero and the two fine-tuning systems improve the component that holds the
  capability. In all three the improvement procedure is fixed and gains flatten.
- None of them shows a system becoming better at improving itself over generations. That
  criterion is ours and is open.

## 3. Two architectures

**A — a self-evolving algorithmic engine.** The capability judged is executable code and
data owned by Genesis: solver, representations, search heuristics, and the procedure that
proposes and selects changes. A model may propose designs; it does not run inside the
solver, so judging a change costs processor time only and is exact.

**B — an open model whose weights change.** A small open model writes exercises and
solutions, a deterministic judge keeps the correct ones, the model is retrained on them
(LoRA or QLoRA), and the next generation is kept only if it is better on unseen tasks.

| | A | B |
|---|---|---|
| Where the capability is | Code and learned data structures | Weights |
| Judge of a change | Deterministic, processor time only | Deterministic for answers; training is stochastic |
| Cost of one generation | Seconds to minutes of CPU | About one to three GPU-hours for a 1.5B–3B model |
| What can compound | Components reused to find larger components; a procedure selecting better procedures | Better solutions give better training data; harder self-proposed tasks |
| Known ceiling | Enumeration explodes; expressing the improver in the solver's own domain | Plateau after one to a few rounds in the literature; gains shrink with small models |
| Improver modifiable by the system | Yes in principle (it is code); a hand-written search over procedures in the prototype | No in the published systems (fixed training recipe) |
| Risk of a fabricated success | Planting the structure to be found in the tasks | Evaluating on the distribution trained on |
| Needs | This VPS | A rented GPU; Anthony's agreement |

Hybrid (not started; the first experiments stay independent): the engine of A as the
verifier and curriculum of B, or a small trained model as the proposal heuristic of A, as
in AlphaZero. It becomes worth building once each track has a measured ceiling.

Common protocol for both: budget fixed per task in the unit that the architecture spends
(component applications for A, generated tokens and GPU-seconds for B); a frozen control
with no improvement and a control with the improvement applied at once; held-out families
never read by any improvement step; several seeds; every run, generation and
transformation stored in a database; a lineage stops at the first generation that brings
nothing. The criterion that matters is second order: is the gain of a step larger after
earlier steps than before them, and is an improvement procedure selected on some families
better on others.

## 4. First prototype of A: a circuit engine that learns its own components

`genesis/circuit_engine.py`, `genesis/circuit_tasks.py`, `scripts/run_circuit_lineage.py`.

- **Solver.** A target truth table, one initial component (NAND), bottom-up search in
  increasing total weight of the components used, one signal kept per truth table, a
  budget counted in component applications. No model, no clock: same engine, same task,
  same budget, same result.
- **Engine.** What a generation hands on: a library of components (each a NAND circuit of
  at most three inputs found in earlier solutions), their weights and their order.
- **Improvement step.** Read the circuits found, extract sub-circuits of one or two layers
  that recur across tasks, add each of the six best-ranked alone, refit weights to use,
  keep the best if more learning tasks are solved or as many with fewer evaluations.
  Components found at a later step can be made of earlier ones.
- **Improvement procedure.** Ranking, largest arity, heaviest weight and dropping of unused
  components are parameters: 24 variants, the seed among them.
- **Tasks.** 50 learning tasks in seven families (and/nor, or, parity, equality,
  multiplexers, adder bits, thresholds), 41 held-out tasks in five families (comparison,
  subtraction, population count, exactly-k, multiplier bits) that no step reads, and random
  functions as a family with nothing to reuse.

### CIRCUIT1: plan frozen before any held-out result (`provenance/circuit-engine-plan-20261011`)

Five seeds (a seed draws the four fifths of the learning tasks an engine learns from), a
budget of 30,000 component applications per task and a second one of 5,000, at most 30
generations, 280 runs, 80 minutes of processor time in all, no model request.
Records: `experiment/engine/CIRCUIT1/`; every run, generation, engine and task result is in
a SQLite file rebuilt by `scripts/run_circuit_lineage.py run`.

Held-out tasks solved, of 41, by seed:

| Arm | Budget 30,000 | Mean | Budget 5,000 | Mean |
|---|---|---|---|---|
| Frozen engine (never improved) | 11, 11, 11, 11, 11 | 11.0 | 8, 8, 8, 8, 8 | 8.0 |
| Lineage (seed procedure) | 11, 17, 14, 11, 11 | 12.8 | 8, 11, 8, 8, 16 | 10.2 |
| Together (as many components, one step) | 11, 12, 12, 11, 11 | 11.4 | 8, 9, 9, 9, 7 | 8.4 |
| Lineage with random choice of components | 11, 11, 14, 14, 11 | 12.2 | 9, 16, 8, 8, 16 | 11.4 |
| Frozen engine, 10 times the budget | 18 | | 14 | |
| Frozen engine, 100 times the budget | 18 | | 18 | |

Answers to the five questions of the plan:

1. **Accumulation: real, small, and worth less than more search.** The lineage never loses
   to the frozen engine and gains in two seeds of five at each budget (+1.8 and +2.2 tasks
   on average). The frozen engine given ten times the budget solves 18 and 14: more than
   any lineage on average, while a lineage spends far more than ten times the budget on
   its learning passes. On random functions, where nothing can be reused, the lineage
   changes nothing (8.6 against 8.4): the gain is reuse, not a side effect.
2. **Cumulative, not one-shot: yes, modestly.** The same number of components added in one
   step gives 11.4 and 8.4. What the lineage gains comes from steps taken in order.
3. **Ranking: no contribution.** Drawing the components to try at random does as well
   (12.2) or better (11.4 against 10.2 at the small budget). With six candidates tried and
   rarely more found, the ranking decides almost nothing.
4. **Yield of successive steps.** Learning tasks gained at each step, by seed, at 30,000:
   `0` · `1, 4, 1, 0, 1, 0` · `1, 0, 0, 3, 3, 0` · `1, 0` · `0`. A later step does sometimes
   gain more than an earlier one (4 after 1; 3 and 3 after two steps that only saved
   evaluations): components made of earlier components open tasks that were closed. But
   every lineage ends within seven steps, two of five never start, and the ending is always
   the same: no candidate component solves one more learning task.
5. **Improving the improver: not shown.** Over the 24 procedure variants, the one that
   gains most on family set A (weights not learned) gains 5.0 tasks against 4.2 for the
   seed procedure; on family set B both gain 3.0. Rank correlation of the variants between
   A and B: 0.10. A procedure selected for the gains of its lineages on some families is
   not better on others. Ranking variants give identical lineages throughout.

What this prototype shows and what blocks it:

- A model-free engine can accumulate improvements of its own machinery that carry over to
  families it never read, and a later improvement can depend on an earlier one. That much
  of the criterion is met, at a small scale and not in every seed.
- It does not become better at improving itself: yields do not grow, lineages stop after a
  few steps, and selecting the improvement procedure brings nothing that transfers.
- The wall is the solver, not the library: search is blind enumeration, the target is used
  only to recognise success, so depth is bought at exponential cost and a component helps
  only when it happens to shorten a circuit to within reach. The improvement step can only
  propose what solved tasks contain and only keep what solves one more task at once.
- The procedure variants explored are parameters of one hand-written step. A search over
  them is not an improver expressed in the terms the engine works in; nothing here is
  recursive, as the plan stated in advance.


## 5. Cost of B (no GPU reserved, nothing spent)

Candidate models: the Qwen2.5-Coder family (1.5B, 3B, 7B), the one Absolute Zero used at
3B to 14B; Qwen3 8B and Llama 3.1 8B as general alternatives. Published gains shrink with
size (3B: +5.7 points and an early plateau; 7B: +10.2), so a pilot below 3B would most
likely show nothing, and 7B is the smallest size with a documented clear effect.

Method: QLoRA (4-bit base, low-rank adapters) fits a 7B–8B model on one 24 GB card
according to current guides (12 to 24 GB depending on sequence length); Absolute Zero
appears to update all weights, which needs 40–80 GB at 7B. Pilot choice: QLoRA on 3B and
7B, full fine-tuning left aside.

Rental prices found on 11 October 2026 (comparison sites dated July–August 2026, to be
checked on the provider's page before any reservation; marketplaces move daily):

| GPU | RunPod community / secure | Vast.ai typical | Lambda |
|---|---|---|---|
| RTX 4090 24 GB | about $0.34 / $0.69 per hour | $0.29–0.50 | — |
| L40S 48 GB | $0.35–0.70 | $0.10–0.30 | $1.00–1.50 |
| A100 80 GB | $1.19–1.49 | $0.60–1.10 | $1.29–2.79 |
| H100 80 GB | about $1.99 / $2.89 | $1.49–2.21 | about $3.99 |

Sources of the prices: <https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/>,
<https://tech-insider.org/runpod-vs-lambda-vs-vast-ai-2026/>,
<https://www.promptquorum.com/local-llms/cloud-gpu-rental-comparison-2026>,
<https://www.synpixcloud.com/blog/cloud-gpu-pricing-comparison-2026>. They disagree with one
another by up to a factor of two.

Pilot protocol (durations are estimates, not measurements):

- Tasks: families with a deterministic judge already in the repository (the learner
  families of `improver_runtime.py`, the truth tables of the circuit engine, programming
  puzzles in the format of Haluptzok et al.), split once into training and held-out
  families.
- One generation: the model writes and solves exercises (about 20,000 attempts), the judge
  keeps the correct ones, QLoRA on those, evaluation on held-out families. About two
  GPU-hours for a 3B model on a 24 GB card, about four for 7B.
- Arms: lineage of three generations; frozen model; one round on three times the data (no
  accumulation); training on unverified data. Three seeds for the lineage, one for each
  control.
- Stopping: a generation not better than its parent on held-out tasks ends the lineage.
- Budget: 3B, about 30 GPU-hours on an RTX 4090, $10–20; 7B, about 60 GPU-hours on an
  L40S or A100, $40–80. Ceiling proposed: $60 for the 3B pilot and the first 7B lineage,
  $100 absolute, with the instance destroyed at the end of each session.

What a positive pilot would and would not show: that verified self-generated data improves
a small model on unseen families (already published); whether a second and third round
still gain (open; the literature says little or no); not that the model becomes better at
improving itself, since the training recipe stays fixed.


## 6. Roadmap from what was observed

1. **Record the negative results** (done here): lineages of improvers SELF1 and SELF2,
   the blind first bench, the saturated second bench on a strong model. The pilot on small
   models shows the second bench does separate improvers there (gpt-oss-20b: one request
   0.600, seed improver 0.707, 15 tasks won and 3 lost, signed-rank 0.009; gpt-oss-120b:
   0.729 against 0.753, 0.07). A lineage on a weak model would probably succeed and would
   show only that a loop compensates a weak model: it is not run.
2. **Track A, next experiment (CPU, a few dollars at most):** make the solver's search
   algorithm the object, since that is where CIRCUIT1 is blocked. A model proposes changes
   to the code of the solver and of the improvement step; each proposal is judged by the
   lineages it produces, deterministically and without any model request, on learning
   families, then on held-out ones. Controls: the same number of proposals judged without
   accumulation, and the model asked once for its best solver. Test of the criterion:
   proposals made from generation n's code must gain more than proposals made from
   generation 0's, at equal numbers of requests. Expected weakness, stated now: a model
   that knows textbook synthesis algorithms may deliver them in one request, and the
   lineage would then add nothing to the model, as on repair.
3. **Track B, pilot (GPU, on Anthony's decision):** the protocol of section 5. It is the
   only track in which the component that limited every experiment so far is the one that
   changes.
4. **Hybrid, later:** a small trained model as the guidance of the engine's search (the
   missing piece of CIRCUIT1 is exactly a learned heuristic telling which signals are worth
   building for a target). Worth building once tracks A and B each have a measured
   ceiling.
5. **Stopping rules for the programme:** a track whose second experiment shows no growth of
   yield across generations and no transfer of a selected improver is closed and written
   up, not re-benchmarked.

