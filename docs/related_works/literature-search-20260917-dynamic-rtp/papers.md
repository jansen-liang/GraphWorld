# Literature Search: Dynamic and Open-Ended Robot Task Planning Benchmarks

Date: 2026-09-17

Search purpose: identify the closest work to GraphWorld's persistent, dynamically generated robot task-planning evaluation.

Source-quality policy: primary proceedings, OpenReview/project pages, arXiv records, and stable publisher pages were prioritized. Policy-excluded sources were not used.

## Bottom Line

No inspected work combines all four of the following in one robot task-planning benchmark:

1. a persistent world that is not reset after one assigned task;
2. exogenous human/environment processes that continuously create new needs;
3. no single externally assigned task, so the robot must discover, prioritize, switch, and resume maintenance goals;
4. time-integrated world-health and human-process evaluation rather than per-task success alone.

The novelty is therefore not simply "dynamic scenes" or "automatic task generation." It is **endogenous task arrival from executable world dynamics, followed by open-ended robot task selection and long-term evaluation**. This claim is supportable only if the benchmark protocol keeps these properties explicit.

## Closest Papers

| # | Work | Source status | Type | What overlaps | What remains different | I/C/E | Label |
|---|---|---|---|---|---|---|---|
| 1 | [EvoNav-Bench](https://arxiv.org/abs/2609.08292) | arXiv, 2026-09-08 | pure benchmark | Lifelong sequence in one evolving ProcTHOR environment; human activity motivates environment changes; persistent representations can become stale | Navigation subtasks remain externally sequenced; changes occur between tasks; no maintenance-task discovery or long-term world-health objective | 4/4/N/A | Risk |
| 2 | [LongAct: When Robots Do the Chores](https://arxiv.org/abs/2605.14504) | arXiv, 2026-05-14 | method + benchmark | Free-form, long-horizon household instructions; dependency management, memory, replanning; persistent world model in the agent | One instruction still defines the episode; no continuing human disturbance or autonomous responsibility allocation | 4/4/4 | Risk |
| 3 | [NIABench](https://arxiv.org/abs/2605.01368) | arXiv, 2026-05-02 | method + benchmark | Robot acts proactively without direct commands while a human performs an ongoing multi-step activity; jointly reasons about when and what to do | Assistance is subordinate to a known human plan; not an indefinitely running multi-role world or general maintenance stream | 4/4/4 | Risk |
| 4 | [PBD-AG](https://arxiv.org/abs/2608.10449) | arXiv, 2026-08-11 | pure method | Persistent baseline-delta graph for stable fixtures and revisable dynamic object events; uncertainty-aware inspection | Focuses on perception/world-model maintenance, not task generation, scheduling, or benchmark reward | 4/4/4 | A |
| 5 | [PARTNR](https://arxiv.org/abs/2411.00081) | arXiv/project release, 2024; benchmark used in 2025 literature | pure benchmark | 100k grounded household tasks; temporal/spatial constraints, human-robot coordination, task tracking and recovery; LLM-assisted task generation with simulator verification | Tasks are generated offline and assigned per episode; scene dynamics serve the task rather than generate an ongoing responsibility stream | 5/5/N/A | Risk |
| 6 | [Habitat 3.0](https://arxiv.org/abs/2310.13724) | CVPR 2024 / arXiv 2023 | method + benchmark | Human-avatar-robot co-habitat, human-in-the-loop, unseen human behaviors, collaborative rearrangement | Two predefined collaborative task families and episode completion remain central | 5/5/5 | A |
| 7 | [Daily Composite Tasks](https://arxiv.org/abs/2509.17425) | arXiv, 2025-09-22 | pure benchmark | Dynamic simulated homes and composite tasks spanning objects, space, and social activity | Evaluates a fixed suite of composite tasks for MLLMs, not continual robot action planning under endogenous task arrival | 3/3/N/A | B |
| 8 | [BEHAVIOR-1K](https://arxiv.org/abs/2403.09227) | CoRL preliminary version / arXiv benchmark release | pure benchmark | 1,000 everyday activities, rich object states, realistic household simulation, goal conditions | Large and compositional but still task-instance/episode oriented; no open-ended responsibility selection | 5/5/N/A | A |
| 9 | [CALVIN](https://doi.org/10.1109/LRA.2022.3180108) | IEEE RA-L 2022 | pure benchmark | Language-conditioned long-horizon composition, unconstrained language, novel environments/objects | Evaluates commanded manipulation sequences; world and goal do not continuously regenerate through human schedules | 5/5/N/A | A |
| 10 | [LIBERO](https://proceedings.neurips.cc/paper_files/paper/2023/hash/8c3c666820ea055a77726d66fc7d447f-Abstract-Datasets_and_Benchmarks.html) | NeurIPS 2023 Datasets and Benchmarks | pure benchmark | Lifelong transfer across sequential robot tasks and multiple knowledge types | "Lifelong" means continual learning across a task curriculum, not uninterrupted operation in one evolving world | 5/5/N/A | A |
| 11 | [GenSim](https://arxiv.org/abs/2310.01361) | ICRA 2024 / arXiv | method + benchmark | LLM generates and verifies simulation tasks; exploratory generation expands task-level diversity | Generation is an offline data/curriculum pipeline; generated tasks do not arise from runtime world changes | 5/4/4 | Risk |
| 12 | [RoboGen](https://arxiv.org/abs/2311.01455) | ICML 2024 | method + benchmark | Generative simulation automates task proposals, environments, rewards, and skill learning | Optimizes scalable training-data generation, not persistent evaluation with task competition and delayed consequences | 5/5/5 | Risk |
| 13 | [RoboCasa](https://doi.org/10.15607/RSS.2024.XX.050) | RSS 2024 | method + benchmark | Large-scale everyday simulation, 100 tasks, LLM-guided composite-task design, automated trajectories | Predefined evaluation tasks and demonstrations; no endogenous arrival or continuing human use of the environment | 5/5/5 | A |
| 14 | [Taskography](https://arxiv.org/abs/2207.05006) | CoRL-era paper / arXiv 2022 | pure benchmark | Robot task planning over large 3D scene graphs; directly relevant to scene-graph RTP | Static goal-directed planning; lacks persistent temporal processes and autonomous task selection | 5/4/N/A | A |

`I/C/E` denotes insight, completeness, and experimental numeric evidence on a 1-5 scale. Pure benchmarks use `N/A` for numeric-evidence scoring and are judged by scope, realism, metric validity, baselines, and reproducibility instead.

## Closest-Work Clusters

### 1. Evolving or persistent worlds

Representative work: EvoNav-Bench, PBD-AG, Habitat 3.0.

- Already covered: environments can change, persistent memories can become stale, and humans can coexist or collaborate with robots.
- Under-tested: whether a planner can detect that world changes have created new obligations, arbitrate among them, and recover the world's operating condition over an indefinite horizon.
- Positioning: GraphWorld should claim **persistent task-generating dynamics**, not merely a dynamic scene graph.

### 2. Long-horizon and lifelong robot tasks

Representative work: LongAct, CALVIN, LIBERO, BEHAVIOR-1K, Taskography.

- Already covered: long action chains, language grounding, sequential skill composition, transfer across task sequences, and graph-based task planning.
- Under-tested: absence of a single supplied goal, competition among simultaneously valid goals, interruption/resumption, and delayed impact on later human activities.
- Positioning: distinguish `long task` from `long-running service`: the former lengthens one goal; the latter continually decides which goal should exist and matter now.

### 3. Human-robot activity and proactive assistance

Representative work: NIABench, PARTNR, Habitat 3.0.

- Already covered: collaboration, proactive assistance, timing, cross-step dependency, task tracking, and recovery.
- Under-tested: multiple independent human roles whose ordinary schedules continuously consume resources and displace or dirty objects, without making the robot a participant in one shared task.
- Positioning: humans are **exogenous workload generators and beneficiaries**, not merely teammates in a fixed cooperative episode.

### 4. Automatic task generation

Representative work: GenSim, RoboGen, RoboCasa, PARTNR.

- Already covered: LLM-assisted proposal of novel tasks, code/reward generation, curriculum expansion, and simulator-in-the-loop verification.
- Under-tested: online task generation as a deterministic consequence of world-state transitions rather than a model writing a new task description.
- Positioning: call the mechanism **state-grounded endogenous task generation**. LLM generation can be an optional authoring tool, but should not be the core novelty claim.

## Opportunity Map

| Dimension | Status | Defensible GraphWorld contribution | Evidence needed |
|---|---|---|---|
| Evolving environment | crowded but open | executable temporal graph with human, device, resource, and decay processes | controlled stationary-vs-evolving ablation |
| Long-horizon RTP | crowded | continual goal discovery, scheduling, switching, resumption, and closure | compare single-task, reactive, scheduler, and oracle variants |
| Task generation | crowded offline; benchmark gap online | goals are grounded from current state debt and human-process preconditions at runtime | publish task-arrival traces and deterministic trigger semantics |
| Human cohabitation | crowded but open | routine human activity is the workload source; robot is evaluated on preserving future activity feasibility | human-blocking and recovery metrics with causal examples |
| Evaluation | benchmark gap | time-integrated state, spatial order, human-flow, backlog/latency, and recovery | add debt/backlog, response latency, interruption and starvation metrics |

## Novelty Risks

1. Saying only "dynamic benchmark" is too broad and is directly challenged by EvoNav-Bench, Habitat 3.0, and dynamic-home evaluations.
2. Saying only "open tasks" is ambiguous. LongAct already uses free-form tasks; MineDojo-style work uses open-ended in another sense. Define open-ended here as no fixed terminal task list and online goal arrival from state transitions.
3. Saying "automatic task generation" invites direct comparison with GenSim/RoboGen/PARTNR. GraphWorld's stronger distinction is that tasks are *not authored online as text*: they become valid because executable predicates are violated.
4. Current GraphWorld still has a finite hand-authored ontology, five base scenes, finite schedules, and 12 procedural skills. It is an open-ended **protocol over a bounded world model**, not proof of unbounded semantic task generation.
5. The current metrics partly reward generic cleaning/closing. A stronger RTP benchmark needs task-level backlog, response time, preemption, resumption, deadline, and starvation diagnostics in addition to world-health averages.

## Recommended One-Sentence Positioning

> GraphWorld evaluates robot task planning as continual responsibility management: executable human and environment processes generate grounded maintenance goals online, and the robot must discover, prioritize, interrupt, resume, and close those goals while preserving long-term world health and human activity feasibility.
