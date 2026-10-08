# Literature Search: RSI and Self-Evolving Agents

Date: 2026-10-05
Search purpose: exploratory direction scouting for recursive self-improvement (RSI), lifelong learning, and self-evolving agents, with GraphWorld as a possible evaluation environment.
Target venue/family: embodied agents, LLM agents, lifelong learning, agent evaluation.
Source-quality policy: applied; primary paper pages and arXiv records used. MDPI and low-signal sources excluded.

## Summary

- Closest-work clusters: experiential/reflective improvement; executable skill-library growth; context and trajectory evolution; code/tool self-modification; embodied lifelong learning.
- Main opportunity: existing work often evaluates improvement on a fixed task family or benchmark. A persistent symbolic world can test whether improvement survives changing tasks, delayed consequences, external agents, and long-horizon responsibility.
- Strongest baselines for GraphWorld: Reflexion, ExpeL, Voyager, LRLL, ACE, SE-Agent, DGM/AlphaEvolve as code-level RSI references.
- Main caution: memory, prompt refinement, skill accumulation, and code mutation are different intervention levels. They should not be reported under one undifferentiated “self-evolution” score.

## Paper Table

| # | Title | Year | Venue/source | Link | Type | Insight | Completeness | Numeric evidence | Overall | Notes |
|---|---|---:|---|---|---|---:|---:|---:|---|---|
| 1 | Reflexion: Language Agents with Verbal Reinforcement Learning | 2023 | arXiv / ICLR-era agent work | https://arxiv.org/abs/2303.11366 | pure method | 4 | 4 | 4 | A | Textual feedback and episodic memory can improve later trials without weight updates. |
| 2 | ExpeL: LLM Agents Are Experiential Learners | 2023 | arXiv | https://arxiv.org/abs/2308.10144 | pure method | 4 | 4 | 4 | A | Extracts reusable natural-language knowledge from agent trajectories. |
| 3 | Voyager: An Open-Ended Embodied Agent with Large Language Models | 2023 | ACM / arXiv | https://arxiv.org/abs/2305.16291 | pure method | 5 | 4 | 4 | A | Automatic curriculum plus executable skill library and iterative code improvement in Minecraft. |
| 4 | Lifelong Robot Library Learning | 2024 | ICRA | https://arxiv.org/abs/2406.18746 | method + benchmark | 4 | 4 | 4 | A | Grows a compositional robot skill library with exploration and skill abstraction. |
| 5 | Embodied Lifelong Learning for Task and Motion Planning | 2023 | arXiv / robotics | https://arxiv.org/abs/2307.06870 | pure method | 4 | 4 | 4 | A | Formalizes lifelong TAMP and learns reusable parameter models online. |
| 6 | RISE: Recursive IntroSpEction | 2024 | NeurIPS workshop-era / arXiv | https://arxiv.org/abs/2407.18219 | pure method | 4 | 3 | 3 | B | Trains models to revise unsuccessful answers recursively; less directly embodied. |
| 7 | From Language Models to Practical Self-Improving Computer Agents | 2024 | arXiv | https://arxiv.org/abs/2404.11964 | system/tool | 4 | 3 | 3 | B | Agent generates augmentations/tools for itself; useful intervention-level reference. |
| 8 | Large Language Models Can Self-Improve At Web Agent Tasks | 2024 | arXiv | https://arxiv.org/abs/2405.20309 | pure method | 3 | 4 | 4 | B | Fine-tuning on self-generated experience improves WebArena performance; highlights data leakage and transfer protocol issues. |
| 9 | Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models | 2025 | arXiv | https://arxiv.org/abs/2510.04618 | pure method | 4 | 3 | 3 | B | Treats prompts/playbooks and memories as evolving artifacts; directly relevant to GraphWorld memory experiments. |
| 10 | SE-Agent: Self-Evolution Trajectory Optimization in Multi-Step Reasoning | 2025 | arXiv | https://arxiv.org/abs/2508.02085 | pure method | 4 | 3 | 3 | B | Optimizes reasoning trajectories and their diversity, rather than only final answers. |
| 11 | Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents | 2025 | arXiv | https://arxiv.org/abs/2505.22954 | pure method | 5 | 3 | 4 | A/Risk | Mutates its own code and validates changes on coding benchmarks; closest conceptual RSI reference. |
| 12 | AlphaEvolve: A Gemini-powered Coding Agent for Designing Advanced Algorithms | 2025 | arXiv white paper | https://arxiv.org/abs/2506.13131 | system/tool | 4 | 3 | 4 | B | Evolutionary code proposals selected by automated evaluators; strong engineering pattern, narrow domain. |
| 13 | ADAM: An Embodied Causal Agent in Open-World Environments | 2024 | arXiv | https://arxiv.org/abs/2410.22194 | method + benchmark | 4 | 3 | 3 | B | Builds an expanding causal graph from interaction in Minecraft; relevant to learned symbolic world models. |

## Clusters

### 1. Experience, reflection, and memory

- Representative papers: Reflexion, ExpeL, RISE.
- What is covered: feedback can be converted into text memories or revised responses, often without changing base-model weights.
- Remaining gap: most protocols use short task trials and do not test stale memory, delayed consequences, conflicting goals, or long-term world maintenance.
- Possible differentiation: GraphWorld can measure whether a memory improves world-state and human-event outcomes across episodes, and whether it causes harmful persistence after a rule change.

### 2. Skill-library and embodied lifelong learning

- Representative papers: Voyager, Lifelong Robot Library Learning, Embodied Lifelong Learning for TAMP.
- What is covered: agents accumulate executable skills or reusable motion/planning components and use exploration to expand competence.
- Remaining gap: skill growth is usually evaluated on a single game, manipulation suite, or planner family; responsibility for a shared changing world is under-tested.
- Possible differentiation: define skill usefulness by transfer, compositionality, recovery benefit, and side effects in multiple GraphWorld domains.

### 3. Context and trajectory evolution

- Representative papers: ACE, SE-Agent, self-improving WebArena work.
- What is covered: prompts, playbooks, trajectories, and self-generated data can be curated or optimized to improve later decisions.
- Remaining gap: benchmark scores can conflate memorization, evaluator gaming, and true causal improvement; cross-world holdout protocols are often limited.
- Possible differentiation: freeze hidden GraphWorld rules and evaluate improvement on unseen topology, event schedules, and perturbations.

### 4. Code-level and recursive self-improvement

- Representative papers: DGM and AlphaEvolve.
- What is covered: candidate code/tool changes are proposed, executed, and selected by an evaluator; DGM explicitly allows the system to improve its own improvement process.
- Remaining gap: coding benchmarks provide crisp evaluators but weakly represent persistent embodied consequences, social tradeoffs, and delayed failures.
- Possible differentiation: permit bounded changes to agent memory, planner, or skill code while GraphWorld supplies a multi-objective, adversarially audited evaluator.

## Opportunity Map

| Cluster | Status | Open gap | Possible direction | Evidence needed | Risk |
|---|---|---|---|---|---|
| Memory/reflection | crowded but open | durable, correctable memory under changing rules | lifelong memory benchmark | learning curves, stale-memory tests, holdout worlds | memory may be prompt caching only |
| Skill accumulation | crowded but open | compositional skills under cross-domain transfer | GraphWorld skill-library track | transfer, composition, recovery, cost | skill API can encode task answers |
| Context/trajectory evolution | mechanism gap | causal improvement vs evaluator overfitting | evolving playbook/trajectory track | fixed hidden test worlds, ablations | leakage and benchmark gaming |
| Code/tool RSI | deployment/system gap | safe, useful self-modification in embodied worlds | bounded harness evolution | versioned changes, rollback, regression tests | large engineering scope |
| Learned symbolic model | benchmark gap | learning rules and causes from interaction | symbolic world-model induction track | prediction error, intervention tests, rule-change adaptation | current GraphWorld rules are hand-authored |

## Benchmark And Dataset Candidates

| Name | Link | Task | Metrics | Fit | Risks |
|---|---|---|---|---|---|
| GraphWorld lifelong maintenance | repo-local | persistent multi-domain service | world/state/spatial/human score, recovery, backlog | strongest fit | limited scene count today |
| WebArena | https://webarena.dev/ | web task execution | task success, step cost | useful self-improvement comparison | less embodied and less persistent |
| Minecraft Voyager setting | https://arxiv.org/abs/2305.16291 | open-ended exploration and skills | milestone/skill discovery | skill growth precedent | game-specific affordances |
| TAMP lifelong learning | https://arxiv.org/abs/2307.06870 | reusable planning parameters | planning success and efficiency | formal lifelong planning precedent | continuous control assumptions |

## Citation And Positioning Cautions

- Do not equate recursive reflection, memory updates, skill growth, prompt evolution, and code mutation. State the intervention level explicitly.
- DGM is the closest RSI concept, but its empirical evaluator is coding performance; it does not establish embodied self-improvement.
- Voyager is a strong lifelong embodied precedent, but its world and objective are open-ended Minecraft exploration rather than human-centered maintenance.
- A GraphWorld claim should be framed as a new evaluation setting/protocol unless a new learning algorithm is actually implemented.
- “Improves over episodes” is insufficient evidence for RSI. Require unseen worlds, rule perturbations, regression checks, and a frozen evaluator.
