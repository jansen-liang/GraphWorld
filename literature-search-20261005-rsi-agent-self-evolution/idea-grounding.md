# Idea-Grounding Packet

## Scope And Evidence Boundary

- Topic / seed: RSI and self-evolving agents evaluated in GraphWorld.
- Search date: 2026-10-05.
- Source-supported facts: listed papers report reflection, memory, skill accumulation, context/trajectory optimization, or code/tool evolution in their stated settings.
- Searcher inferences: GraphWorld may fill a protocol gap for persistent, multi-domain, human-centered consequences.
- Unknowns: complete overlap with the newest 2025-2026 preprints and whether any existing work already uses a comparable persistent symbolic world.

## Evidence Cards

| Source | Supported observation | Reported limitation / transfer condition | Mechanism primitive | Protocol anchor | Confidence |
|---|---|---|---|---|---|
| Reflexion | linguistic feedback and episodic memory can improve later trials | no weight update; task-trial setting | verbal reflection + memory | compare with/without memory | direct |
| ExpeL | trajectories can be converted into reusable textual knowledge | knowledge quality and retrieval matter | experience extraction | cross-episode replay | direct |
| Voyager | executable skills and self-verification support open-ended embodied progress | Minecraft-specific evaluator | skill library + automatic curriculum | skill discovery and transfer | direct |
| LRLL | robot skill libraries can grow through exploration and abstraction | manipulation/planning setting | skill abstraction + soft memory | compositional skill transfer | direct |
| ACE | evolving structured contexts avoid naive summary collapse | context-level intervention, not full RSI | generate/reflect/curate playbook | memory version curves | direct |
| SE-Agent | trajectory diversity and optimization can improve multi-step reasoning | reasoning benchmark scope | trajectory-level search | fixed evaluator and ablation | direct |
| DGM | code mutation with empirical validation is a concrete RSI loop | coding benchmark and evaluator | self-modifying code + selection | regression and improvement archive | direct |
| ADAM | an agent can construct causal graph knowledge from interaction | open-world game setting | causal graph induction | intervention/prediction tests | direct |

## Cross-Source Relations

| Source pair / cluster | Relation | Open gap or conflict | Why it matters | Evidence needed next |
|---|---|---|---|---|
| Reflexion / ExpeL / ACE | supports | all improve non-parametric artifacts, but artifact quality is hard to audit | natural first GraphWorld track | memory provenance and stale-memory tests |
| Voyager / LRLL / TAMP | supports | skill accumulation is stronger than text memory but can encode task answers | tests whether skills transfer | unseen topology and compositional tasks |
| DGM / AlphaEvolve vs embodied work | leaves-open | code-level RSI has crisp evaluators but weak persistent social consequences | GraphWorld can add long-horizon consequences | bounded harness mutation and rollback |
| ADAM vs GraphWorld | depends-on | learned causal graphs need an external state-transition oracle | GraphWorld already exposes symbolic truth | prediction and intervention benchmark |

## Idea Constraints

- Already covered central claims: memory-based improvement, skill-library growth, trajectory refinement, and code-level evolutionary search each have precedents.
- Transferable mechanism primitives: experience extraction, executable skill storage, structured playbooks, trajectory selection, evaluator-driven candidate generation.
- Protocols suitable for direct comparison: first-vs-later episode curves, unseen-world transfer, rule-change adaptation, retention/regression, recovery latency, multi-objective world/human score.
- Stale or overcrowded routes: claiming “LLM reflects and improves” without a new environment or falsifiable protocol.
- Minimum viable research question: does an agent artifact updated from GraphWorld interaction improve performance on unseen persistent worlds while preserving old-world competence and avoiding harmful side effects?
