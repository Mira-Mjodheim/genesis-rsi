# An engine that learns its own components — 11 October 2026

Anthony directs that Genesis be reoriented toward a system whose capability lies in its own
executable code and which improves its own mechanisms cumulatively, a language model being
at most a design tool. Under the standing PUBLIC_AGPL_COMMERCIAL_OPTION decision, publish a
bounded prototype: a circuit-synthesis engine that starts from NAND alone, searches
bottom-up under a budget counted in component applications, and after each pass extracts
components shared by the circuits it found, keeps one only if it then solves more of the
tasks it learns from, and refits the weights that order its search. The improvement
procedure is itself a set of parameters whose variants are compared by the gain of the
lineages they produce.

Review precedes the first run on held-out families. AI development assistance is as
recorded in `docs/AI_ASSISTED_DEVELOPMENT_PROVENANCE.md`; no model takes part in a run.
Prior art is acknowledged and no novelty is asserted over it: library learning from solved
tasks (Ellis et al., "DreamCoder", 2021), bottom-up enumeration with observational
equivalence, cut enumeration in logic synthesis, weighted enumeration by learned usage. No
third-party code or data is used: the tasks are truth tables of textbook functions.
Software AGPL-3.0-only; prose follows LICENSE_POLICY.md. No patent-first, trade-secret,
confidential-third-party or embargo reason identified.

Safety boundary: the engine executes no generated code, only NAND steps over integers; it
reads no file and reaches no network. No frozen experiment changes. No held-out Defects4J
case and no reserve case of the external catalogue is involved. No general RSI claim
follows: one domain, one engine, and a procedure search written by hand.
