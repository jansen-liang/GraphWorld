# Literature Search: Embodied Task Coverage And Runtime Gaps

Date: 2026-09-22

Purpose: decide which runtime capability should be implemented next after the
composition, resource, process, placement, and maintenance-task work already
landed in GraphWorld. The first-person camera is now represented by a staged
runtime contract (pose, hit metadata, and server-side validation); continuous
renderer raycast/occlusion and the LLM-facing action protocol remain later
stages.

## Scope and evidence boundary

This is a focused follow-up to
`literature-search-20260917-dynamic-rtp`. It reuses the primary-source set in
that report and maps the papers to implementation contracts rather than making
a new claim of exhaustive literature coverage. The comparison asks whether a
work provides evidence for one or more of:

1. persistent or evolving world state;
2. partial observability and visibility changes;
3. long-horizon execution with interruption or recovery;
4. multi-agent or human workload;
5. executable scene-graph affordances and containment;
6. replayable action/transition semantics.

## Coverage matrix

| Work | Persistent world | Visibility / uncertainty | Interruption / recovery | Human or multi-agent | Affordance / graph grounding | Replay contract | GraphWorld implication |
|---|---|---|---|---|---|---|---|
| EvoNav-Bench | strong | strong | partial | human activity as change source | navigation-centric | partial | add observability and stale-belief evaluation |
| LongAct | episode persistence | partial | strong | limited | household action grounding | partial | model resumable goals and durable checkpoints |
| NIABench | ongoing human activity | strong | strong | strong | activity-centric | partial | add workload and interruption metrics |
| PBD-AG | persistent graph delta | strong | partial | none | graph/world-model-centric | strong | preserve event provenance and belief updates |
| PARTNR | episode state | partial | strong | strong | grounded household graph | partial | add coordination and conflict cases |
| Habitat 3.0 | cohabiting world | strong | strong | strong | simulator affordances | partial | evaluate human-flow feasibility |
| BEHAVIOR-1K | task episode | partial | partial | limited | rich object states | partial | keep expanding generic predicates, not task names |
| CALVIN | sequence persistence | low | partial | none | manipulation-centric | strong | use transition traces for replay and diagnosis |
| LIBERO | curriculum persistence | low | low | none | manipulation-centric | strong | distinguish lifelong learning from one-world service |
| GenSim / RoboGen | generated scenes/tasks | low | low | none | simulator code generation | partial | generation should remain optional authoring, not runtime truth |
| RoboCasa / Daily Composite Tasks | dynamic household episode | partial | partial | limited | household composition | partial | add cross-task backlog and deadline metrics |
| Taskography | static scene graph | low | low | none | strong graph planning | strong | preserve containment and support relations as first-class facts |

## Current GraphWorld coverage

Implemented contracts already cover:

- component containment and mounted controls, doors, hinges, storage slots,
  drawers, and cabinet topology;
- surface and volume placement, footprint/capacity checks, floor release,
  discrete settling, fragile-object breakage, and placement provenance;
- finite resource pools, independent dispensed instances, consumption, and
  process output provenance;
- timed appliance processes, environmental decay, water depletion, temperature,
  dirt, wetness, spoilage, wilt, and structured lifecycle events;
- maintenance goals for laundry, dishwashing, heating, cooking, crafting,
  assembly, coffee, printing, disposal, and restoration;
- a server-side legal action catalog used by both runtime planning and human
  control.

The remaining high-value gaps are cross-cutting rather than another isolated
device template:

1. **Goal interruption and resumption.** Active goals have phases, but the
   runtime does not yet expose a durable checkpoint, explicit preemption reason,
   priority/aging policy, or starvation metric.
2. **Partial observability contract.** Visibility is represented in observations,
   but there is no first-class stale-belief record or distinction between
   unknown, known-empty, and temporarily occluded.
3. **Generic transition/replay IR.** Events are increasingly structured, yet
   action effects, process effects, and timed transitions do not share one
   versioned transition envelope for deterministic replay.
4. **Human/multi-agent workload.** The scene can contain connected rooms and
   tasks, but there is no explicit workload source, ownership, conflict, or
   service-level metric.
5. **Continuous physical interaction.** Placement is geometrically validated,
   and first-person hit metadata now has a server-checked contract, but floor
   release, collision, and renderer-side occlusion remain discrete/partial.

## Recommended implementation order

1. Add a durable goal checkpoint and interruption/resumption fields to the
   active-goal lifecycle. This improves the existing planner immediately and
   enables fair comparison with LongAct/NIABench-style recovery without
   committing to a camera or LLM protocol.
2. Add a small observation-status schema (`visible`, `occluded`, `unknown`,
   `stale_since`) and make candidate generation treat unknown targets as
   unresolved rather than absent.
3. Unify action/process/timed events under a versioned transition envelope and
   add deterministic replay tests.
4. Add workload/conflict metrics after the lifecycle and observation contracts
   are stable.

## Claims to avoid

- Do not call GraphWorld the first dynamic or open-ended benchmark.
- Do not equate a long task with a long-running service.
- Do not claim continuous physics until the runtime has a continuous collision
  and settling model.
- Do not expose first-person hit points as an agent API until camera frame,
  raycast semantics, occlusion, and server-side validation are specified.

## Decision

The next implementation slice should be **durable goal interruption and
resumption**, followed by a minimal partial-observability contract. These are
small enough to test against the current runtime and unlock the most important
evaluation dimensions identified by the literature without expanding the
object catalog.
