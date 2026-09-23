# Embodied Scene Capability Progress

This document records implementation gates for the embodied-scene expansion.

## Stage 1: Composition Contract

Status: complete

Implemented in `backend/core/composition.py` and `backend/core/assets/object_library.py`:

- `ComponentSpec`: semantic role, host-facing mount face, normalized local anchor, capabilities.
- `StorageTopology`: open/shelved/drawer/mixed topology, levels, columns, depth, drawer count.
- Default declarations for washing machines, toilets, refrigerators, cabinets, wardrobes, and drawers.
- Object catalog responses now expose `composition`.
- Layout validation checks component mount faces and host references.

Gate evidence:

- `backend/core/test_composition.py`
- `backend/app/tests/test_scene_layout.py`

## Stage 2: Runtime And Editor Materialization

Status: complete

Implemented in `backend/runtime/engine/runtime.py` and `frontend/src/features/scene-builder/Scene3DCanvas.tsx`:

- Runtime composition expansion is idempotent.
- Component nodes receive `component_of`, `component_role`, `mount_face`, and `mount_anchor`.
- Controls receive `controls` edges.
- Cabinet storage creates level/column slots and drawer nodes.
- Microwave and dishwasher declarations now materialize independent doors and start buttons.
- The 3D editor renders doors, buttons, storage dividers, shelves, and drawer fronts while selecting the host object.

Gate evidence:

- Runtime composition tests pass.
- `npm run build` passes.

## Stage 3: Resource Instances And Manipulation Semantics

Status: partial, core loop complete

Implemented in `backend/core/resources.py` and `backend/core/action_schemas.py`:

- A `resource_pool` keeps finite source inventory separate from item instances.
- `dispense` decrements inventory and creates an independent held node.
- Resource dispensing emits a structured `resource_dispensed` event linking the
  source pool, actor, generated instance, and remaining count.
- Dispensing the final unit also emits `resource_depleted`, making source
  exhaustion observable to task selection, replay, and explanations.
- Loaded detergent instances are consumed when a washer or dishwasher cycle
  starts and emit `resource_consumed`; appliances without detergent remain
  backward-compatible with existing scenes.
- Home-scene preparation seeds an idempotent refrigerated food pool with six
  initial units inside the kitchen refrigerator. Once the refrigerator is
  accessible, it exposes a legal `dispense` candidate and generates an
  independent food node per use.
- Scene resource pools are declared through the reusable
  `SCENE_RESOURCE_POOL_SPECS` catalog rather than a one-off home-scene branch.
  The default home catalog also seeds finite laundry-detergent and hand-soap
  sources when their washer/sink/dishwasher/printer/assembly-line parents exist; optional layouts are filtered
  without creating dangling pools.
- Re-running scene preparation preserves the pool's runtime
  `available_count` and `dispensed_count` instead of restoring defaults, so
  initialization remains safe for persistent worlds.
- `release` drops a held object into the current room.
- `release` records `release_mode`, room, anchor, and drop height provenance separately from `place`.
- `place` records a normalized surface anchor, optional physical hit point, target surface size, and grid snapping.
- `place` rejects an anchor when the item footprint would cross the declared surface boundary.
- Common movable objects now receive default footprints (cup, plate, bowl, glass, milk, fruit, box, and similar items).
- `place` rejects overlapping footprints and optional `max_load_kg` overloads on a support surface.
- Container interiors now expose `interior_size_cm` and accept normalized 3D volume anchors.
- Volume placement validates width/depth/height bounds and rejects 3D AABB overlap in the same slot.
- Volume placement also honors `max_load_kg`/`interior_load_kg`, summing existing interior children and rejecting overweight storage placements.
- Access checks walk the full containment chain, so a closed cabinet blocks placement into its
  generated storage slots and drawers.
- Fragile glass/ceramic objects can become `is_broken` when released above the configured safe height.
- Released objects now carry a discrete `physics_state`: elevated drops advance from `falling` to `settled` on timed ticks, with an `object_settled` event and configurable `gravity_step_cm`.
- `visual_cues` derives renderer-facing cues from runtime states.

Gate evidence:

- `backend/core/test_resources.py`
- `backend/core/test_animation.py`
- `backend/core/test_placement.py` (surface and 3D interior placement cases)

The human run candidate panel now exposes legal `dispense`, `place`, and
`release` actions from the same server-side candidate set. Dispense candidates
are generated only for accessible pools with remaining inventory, and the panel
labels generated instances and elevator destinations explicitly.
Runtime human control now submits the geometric hints supported by the action
contract: `place` uses the normalized surface center by default and `release`
uses a normalized floor anchor. The server still resolves action identity and
target/object arguments from the legal candidate set.
Place candidates now also declare `placement_hint=surface|volume` from the
target's geometry metadata. The human run UI sends a 2D surface anchor for
tables/counters and a 3D volume anchor for cabinet slots, drawers, and other
container interiors.

Remaining limitations before closing this stage:

- Floor releases now perform a discrete footprint-overlap check at the normalized room anchor, with an explicit `allow_floor_stacking` escape hatch. A richer collision/weight model and continuous physics are still needed for non-surface spatial volumes; release-to-floor gravity remains discrete.
- A first-person runtime surface picker is still pending; the current human-run
  panel exposes validated geometry controls for dispense, place, and release.

The human-run action endpoint now accepts only geometric interaction hints
(`surface_anchor`, `surface_point_cm`, `volume_anchor`, `volume_point_cm`, and
`release_anchor`) from the client; action identity and object/target arguments
remain server-selected from legal candidates.

Gate evidence: `backend/app/tests/test_action_payload.py` and
`backend/runtime/agent/test_planning.py`.

## Stage 4: Tasks, Time, And Effects

Status: foundation expanded, crafting loop implemented, continued work pending

Existing support includes timed appliance cycles, wet/dry transitions, temperature, dirt, rot, wilt, finite resources, and task skill templates. Drying also reads optional per-room humidity: low humidity accelerates drying and high humidity delays it, while the default 50% preserves the weather-only behavior. Runtime observations now expose `room_humidity` from step zero, even when the mapping is empty. Remaining work is to generalize task grounding/replay and extend environmental systems beyond the current discrete contracts.

The focused follow-up coverage review is recorded in
`docs/related_works/literature-search-20260922-embodied-task-coverage/`.
It identifies durable goal interruption/resumption, partial observability, and
versioned transition replay as higher-value next steps than adding another
device-specific recipe. First-person camera hit testing and the LLM-facing
action protocol remain deliberately deferred until their server-side contracts
are specified.

Active maintenance goals now carry a durable lifecycle checkpoint: stable
`goal_id`, `status`, `priority`, `preempted_at`, `preempt_reason`,
`resume_count`, and `deadline_step`. Experiment checkpoints persist paused goals
and restore them before proposing a new goal; paused goals age by wait time so
repeated interruption cannot starve them. Covered by
`backend/runtime/agent/test_planning.py`.

Fog-of-war observations now distinguish node and room knowledge states:
`visible`, `occluded`, `stale`, and `unknown`, with per-node last-seen steps.
Closed appliance/cabinet interiors are reported as occluded instead of silently
disappearing, while never-visited rooms remain unknown and previously observed
nodes become stale after leaving visibility. The legacy room confidence map and
memory-node fields remain compatible. Covered by
`backend/runtime/test_scene_preparation.py` and the web API smoke tests.

Runtime scene snapshots now expose a versioned `world_state.transition_log`
alongside the unchanged legacy `event_log`. Each envelope has a deterministic
`transition_id`, source classification (`action`, `process`,
`timed_transition`, `human_event`, or `rule`), before/after steps, and an
effects summary. This gives replay and evaluation a common transition IR
without invalidating existing event consumers. Covered by
`backend/core/test_transitions.py` and the full backend suite.

Fans are now a canonical switchable home-device template. Pressing a fan
toggles `is_on`, updates room ventilation state, and emits the `airflow` visual
cue; the 3D editor animates an active fan using the same runtime feedback path
as other running devices. Fan behavior is covered by the animation and task
effect tests.

Time-driven state changes now emit structured lifecycle events (`drying_completed`,
`water_depleted`, `flower_wilted`, `food_spoiled`, `dirt_accumulated`, and
`temperature_relaxed`) in addition to changing node state, making decay and
environmental transitions observable to replay and task explanation layers.

Implemented in this stage:

- `flush_toilet`: pressing a toilet control cleans the controlled toilet.
- `heat_milk`: microwave completion changes milk/juice/food/drink/water children to `temperature=hot`.
  The active goal now follows `load -> run -> waiting -> unload`; it requires
  the hot item to be picked from the microwave and placed on a compatible
  same-room surface before completion.
- Added task templates for `brew_coffee`, `restock_cabinet`, and `access_control_delivery` to keep multi-step planning explicit.
- Access-controlled doors can now declare `required_credential`; their control button rejects actors without a matching held credential and opens normally once the credential is held.
- Added a declarative `workbench` recipe (`bread` + `tomato` -> `sandwich`) with a timed process, input consumption, independent output node, and `craft_sandwich` task template.
- Added a declarative `assembly_line` recipe (`component_a` + `component_b` -> `finished_product`) with the same staged process/event contract, providing a production-line primitive for multi-station delivery tasks.
- Added the `assemble_product` task skill. It is emitted when an idle assembly line has both required component types available anywhere in the scene, including warehouse or upstream stations, and describes collect/transit/load/run/inspect phases. The process precondition remains stricter: both parts must be physically placed in the line before pressing it.
- Timed recipes emit `process_started`, `process_consumed`, and `process_completed`
  events with input/output node identifiers for replay and planner explanations.
- Candidate catalog capabilities now contribute their declared actions to `interactive_actions`, so generated appliances and workbenches satisfy action preconditions consistently.

Gate evidence: `backend/core/test_task_effects.py`, `backend/core/test_resources.py`, and the full core/app test suite.

Elevator routing is now represented as a first transport stage: an `elevator`
node declares `served_rooms`, has an open/closed state and a door component, and
room movement may cross non-adjacent rooms only when an elevator serving both
rooms is open. Closed-elevator rejection and successful cross-room movement are
covered by `backend/core/test_task_effects.py`.

Planner and runtime adapter candidate handling preserves one `press` action per
served elevator destination. The destination is included in the stable action
ID, so selecting a floor cannot collapse into another floor or become
unresolvable. This is covered by `backend/runtime/agent/test_planning.py`.

## Stage 5: Visual Runtime Feedback

Status: contract and basic editor feedback complete, richer runtime effects pending

`visual_cues` currently emits `running_pulse`, `emissive`, `open_pose`, `water_droplets`, `broken`, and `falling`. Three.js runtime animation consumes these cues for device vibration, light emission, door/drawer motion, drying indicators, falling objects, and breakage.

The 3D scene editor now consumes the corresponding node states directly: running objects receive a subtle vibration animation, active light objects use an emissive material, doors/drawers animate from component state, and wet/broken effect meshes are hidden or shown as state changes during the render loop. The run-monitor graph also consumes `visual_cues`, using distinct status borders and tooltip status text for running, wet, and broken nodes.

Door and drawer poses now ease toward their open/closed target over successive
render frames. Drawers visibly translate along their depth while doors rotate
from their closed pose, so triggering an interaction produces a real transition
instead of a one-frame teleport. Component offsets and drawer pull direction
are transformed by the host's quaternion, so rotating a cabinet or appliance
does not make its drawer slide along a stale world axis. The frontend
production build verifies the animation code compiles. Static mounted parts
such as buttons and hinges now use the same local-space binding and are
updated every render frame, so moving or rotating a host keeps all controls
and hardware attached rather than leaving them behind.

Generated mechanical parts now also expose explicit graph relations:
`hinge_of` links a hinge to its door, while `slides_in` links each drawer to
its host storage body. This separates mechanical semantics from the generic
`component_of` containment edge and is covered by
`backend/core/test_composition.py`.
The scene-layout validator now checks that these mechanical edges connect
matching component roles on the same host, and the canonical edge factory can
round-trip both relations through `SceneGraph`.
The BEHAVIOR-compatible transient `touching` relation is also now part of the
canonical edge vocabulary. Existing `on`/`ontop`, `in`/`inside`, and
`contains` relations remain available for containment and support semantics.

Editor physical coordinates are now preserved when the backend re-enriches a
scene layout. Previously `_add_physical_geometry` reset every object's `z_cm`
to zero, causing a light moved downward with the 3D transform gizmo to jump
back upward after release or refresh. The 2D editor also writes updated
centimeter X/Y coordinates when moving an object, keeping grid and physical
representations consistent. Covered by
`backend/app/tests/test_scene_layout.py` and the frontend production build.

Contained component/storage children now inherit the host's current X/Y
physical position during layout enrichment while retaining their own local
vertical offset; their relative grid anchor is synchronized as well. Moving a
refrigerator, cabinet, or appliance therefore keeps its buttons, doors,
drawers, and storage slots attached in both 2D and 3D views. This is covered
by the contained-child layout regression in `test_scene_layout.py`.

Layout validation now also checks scene-graph edge endpoints, rejects multiple
component hosts, and detects cycles in `component_of` containment chains before
geometry checks run. This turns malformed parent/child graphs into explicit
validation issues instead of later "must remain inside room" surprises.

Added a complete plant-care loop: a filled `wateringcan` can be dumped into a
plant or vase, consuming its water and restoring plant vitality/clearing
`is_wilted`. The `water_plant` task is emitted when vitality decays below full
or a plant wilts, connecting the time-transition system to an executable
recovery task. Covered by `backend/core/test_task_effects.py`.

An empty vase containing a flower or plant now emits a separate `refill_vase`
task, so vase water depletion is independently actionable rather than relying
on the plant's vitality threshold.

Door-bearing appliances, refrigerators, elevators, cabinets, and wardrobes
now declare an explicit `hinge` child component in addition to the door. The
3D editor renders the hinge as a small mounted cylinder while the door keeps
its existing open animation and interaction contract.
Dryers (`dryer` and `clothesdryer`) now use the same door/hinge/start-button
composition, covering the remaining door-bearing appliance template.
Medicine refrigerators and lockers now use the same explicit door/hinge
composition with multi-level interior storage slots. Dressers now materialize
three independent drawer nodes and matching storage volumes instead of being
represented as one opaque furniture block. Covered by
`backend/core/test_composition.py`.

Tool use now has an executable contract for brushable targets that declare
`required_tool`: the actor must hold a matching semantic/tool type, exhausted
tools are rejected, successful use decrements `uses_left`, and a structured
`tool_used` event is emitted. Targets without this declaration retain the
legacy direct-brush behavior.

The human run panel now exposes geometry controls for placement actions:
surface placement edits U/V, volume placement edits U/V/W, and release edits
floor X/Z. The run API continues to accept only these geometric hints while
the server selects and validates the action identity, object, target, and
capacity constraints.

Release hints are normalized server-side to a clamped room-floor X/Z anchor;
the released node records both `release_anchor` and `floor_contact` before its
discrete falling/settled transition. This makes a release location explicit
without claiming continuous rigid-body simulation.

High drops of fragile glass/ceramic objects now also emit `object_broken` with
the object, material, height, and cause, so replay does not need to infer the
break from state diffs alone.

Placement and release now also emit structured `object_placed` and
`object_released` events, including the target relation and surface/volume or
floor anchor. Replay and task explanations can therefore follow item flow
without reconstructing every parent-map diff.

Held food and drink instances now support an explicit `consume` action. The
action rejects rotten, burnt, or non-consumable objects, removes the held
instance, and emits `object_consumed` with `resource_instance_of` provenance
when applicable; candidate generation exposes it only for the currently held
item. Resource pools also retain a `consumed_count` counter and emit a
compatibility `resource_consumed` event, so inventory accounting distinguishes
dispensed-but-held units from units actually consumed by an actor.

Discrete gravity completion emits `object_settled` with both the canonical
`object_id` and legacy `item_id` aliases, keeping replay consumers consistent
with placement/release events without breaking older logs.

Stackable support surfaces now record a deterministic `stack_index` and the
immediate `support_object_id` when overlapping placement is explicitly allowed;
ordinary surfaces continue to reject footprint overlap.

Water containers now support an optional numeric `water_level` (0-100) in
addition to the legacy boolean `has_water`. Faucet/sink filling, vase filling,
and watering-can use consume or set the numeric quantity while maintaining the
boolean compatibility projection. This supports partially filled containers
without invalidating older scene snapshots. Numeric vases now lose water in
discrete increments over multiple time cycles; `water_depleted` and flower
wilt effects occur only after the level reaches zero.

Added a cooking process for the existing stove template: an `egg` placed on
the stove is consumed after a timed cycle and replaced by an independent
`cooked_egg` output, with the usual process lifecycle events. The new
`cook_egg` skill is emitted only when an idle stove has the required input. Its
active goal tracks `prepare -> cook -> waiting -> serve`, binds the generated
output through recipe provenance, and requires the cooked egg to be picked
from the stove and placed on a compatible surface.
The `craft_sandwich` skill now has the corresponding active-goal loop for two
inputs: it collects bread and tomato, loads both into the workbench, waits for
the recipe output, and serves the newly generated sandwich on a compatible
surface. The goal remains tied to the two input IDs and the output provenance,
so an older sandwich cannot satisfy a new task.
The factory `assemble_product` skill now follows the same contract across
stations: it collects `component_a` and `component_b` from their upstream
locations, loads the assembly line, waits for the generated
`finished_product`, and places it on an inspection surface.
The `brew_coffee` active goal covers water/bean/cup preparation and preserves
the recipe's containment semantics: the generated `coffee` remains a child of
the cup while the robot serves the cup to its final surface.
An analogous `print_document` skill is emitted only when an idle printer has
both paper and ink, covering supply validation, timed printing, and receipt
collection on top of the declarative printer recipe. Its active-goal phases
are `print`, `collect`, and `place`: a newly generated receipt is identified
by its ID (rather than accidentally reusing an older receipt), picked from
the printer, and placed on a same-room compatible surface before completion.
The `dishwash_dishes` skill is emitted for idle dishwashers containing dirty
dishes, connecting loading, the timed wash cycle, and unloading to the same
task discovery layer. Its active-goal phases are `load`, `run`,
`washing_wait`, and `unload`; completion now requires the clean dish to be
picked from the dishwasher and placed on its baseline compatible surface (or
a same-room fallback surface), rather than stopping while it remains inside
the appliance.
Cooking outputs also carry explicit state changes (`is_cooked=true` and, for
egg/coffee outputs, `temperature=hot`) so production is represented as both a
new node and a semantic state transition.
These output states now live in each `RECIPE_SPECS` entry rather than in an
output-type conditional, making new recipes data-extensible.
Recipe outputs now also retain `produced_by_device`, `produced_by_recipe`,
`produced_at_step`, and `output_relation` metadata; matching process events
carry the recipe and production step so replay and downstream task grounding
can distinguish a newly produced instance from an older object of the same
semantic type.
Printer paper and ink consumption is also declared in
`RECIPE_SPECS.resource_costs`; the former printer-only process branch now uses
the same registry path as coffee, crafting, assembly, and cooking.
Office paper-pack and ink-cartridge resource instances can now be placed into
the printer: loading removes the instance, increments the printer's internal
`count`/`amount`, updates the source pool's `consumed_count`, and emits a
`resource_loaded` event before a print cycle starts.
Water-consuming recipes now read numeric `water_level` when available, require
at least the configured process cost, decrement it on start, and update the
legacy `has_water` projection.

The watering-can semantic is now a canonical object template with an initial
numeric water quantity, so plant-care tasks can be instantiated from the
catalog instead of relying on ad-hoc scene nodes.

Agents now have an explicit `wait` action. It is a validated temporal no-op
that emits `robot_action_wait` for replay/audit while the normal runtime tick
advances timed appliance processes, drying, gravity, and natural decay. The
candidate adapter exposes one wait candidate with a stable explanation, so a
planner or LLM does not need to invent an unsupported empty action while
waiting for a process to finish. Covered by `backend/core/test_wait_action.py`.

Resource loading into appliance supply slots is now kept distinct from placing
an object into an appliance interior. A detergent instance can enter a
washer/dishwasher's front-accessible supply slot while the user door is closed;
duplicate supply instances are still rejected, and the final event is the
authoritative `resource_loaded` record rather than a misleading generic
`object_placed` event. This preserves the finite-resource and replay
contracts for legacy washer scenes and is covered by the task-effect tests.

The first-person runtime contract now has a server-visible camera frame. Each
agent observation includes a versioned camera spec with eye height, FOV,
near/far planes, explicit forward/up vectors, and a center-screen interaction
ray in `agent_local` space. Renderer clients can use this frame for mesh
raycasting while the server remains the authority for validating the resulting
surface/volume anchor. This is the contract layer only: continuous raycast,
occlusion, and hit-point reconciliation remain a subsequent implementation
stage. Covered by `backend/runtime/test_camera.py`.

The interaction payload now accepts a validated `interaction_hit` object for
human control. Its node id must equal the server-selected target and be visible
in the current observation; normalized surface UVs, optional physical point,
normal, ray, and distance fields are type/range checked. A valid surface UV is
used as the placement anchor and retained as provenance. This is the first
server-side raycast handoff layer; it still does not claim continuous physics
or independently reconstruct a hit from an untrusted client ray.

Placement candidates now also carry the target's declared `surface_size_cm` or
`interior_size_cm` alongside `placement_hint`. A first-person client can
therefore convert a validated mesh hit into normalized surface/volume
coordinates without duplicating the catalog geometry locally.
The same hit handoff now supports normalized `volume_uv` coordinates for
drawers, storage slots, and appliance interiors; volume placement preserves the
validated hit provenance just like surface placement.
The frontend API types now expose the same `FirstPersonCamera` and
`InteractionHit` contracts, so a runtime viewport can consume and submit these
fields without falling back to untyped payloads.

The Three.js scene raycaster now materializes that contract directly from a
pointer hit (node id, mesh UV when available, world point in centimetres,
transformed normal, ray origin/direction, and distance) through the optional
`Scene3DCanvas.onInteractionHit` callback. The editor keeps its existing
selection behavior; runtime views can reuse this callback for server-validated
placement instead of duplicating intersection conversion.
The scene builder surfaces the latest hit node and UV in its 3D toolbar as a
small diagnostic readout, making the client-to-server hit contract observable
during authoring and debugging.

Visual state cues now distinguish active drying and hot items: wet objects
with a drying cycle emit `drying_bubbles`, while hot food/drink emits `steam`.
Existing `water_droplets`, running, open, broken, and falling cues remain
backward compatible, allowing renderers to add bubbles/steam without guessing
from raw state fields.
The 3D editor now renders those cues as animated drying bubbles and steam puffs
attached to the host mesh, and hides them automatically when the state clears.
The scene graph view also gives drying and hot nodes distinct status borders,
so non-3D monitoring retains the same process feedback.

Multi-agent contention is now measured before fallback resolution. Each
experiment step records conflict groups, conflicting agents, and whether the
contention was over a shared target or shared object. The existing resolver
still chooses a legal fallback, while these metrics preserve the workload
signal for evaluation instead of hiding it. Covered by
`backend/runtime/test_action_conflicts.py` and integrated into experiment step
metrics.

Every server-generated candidate now also carries an `action_contract` with its
category, required parameters, human-readable description, edge/state mutation
flags, and effect summary derived from `ACTION_SPECS`. This is the first stable
LLM-facing tool description: models can select among legal candidates using
explicit semantics, while identity, arguments, and final validation remain
server-controlled.
The Web API exposes the same contract as a first-class `CandidateAction` field
while retaining the legacy payload copy for older clients.
The human-control panel now uses the contract description for action tooltips
and shows the action category beside each candidate, making the same interface
legible to both people and language-model controllers.
Canonical vases now also initialize `water_level=0`, keeping new object
instances aligned with the numeric water contract while retaining
`has_water=false` compatibility.
State normalization clamps externally supplied `water_level` values to the
declared `0–100` range.

Placing an empty watering can into a running, water-filled sink now fills it
to `water_level=100` and restores `has_water=true`, completing the refill phase
described by the plant-care task.

## Research Anchors

- VirtualHome: https://arxiv.org/abs/1806.07011
- ALFRED: https://arxiv.org/abs/1912.01734
- BEHAVIOR in Habitat 2.0: https://arxiv.org/abs/2206.06489
- Mini-BEHAVIOR: https://arxiv.org/abs/2310.01824
- ProcTHOR: https://arxiv.org/abs/2206.06994
- RFUniverse: https://arxiv.org/abs/2202.00199
- LUMINOUS: https://arxiv.org/abs/2111.05527
- KARMA: https://arxiv.org/abs/2409.14908

These sources motivate separating static composition, dynamic state, finite resources, long-horizon task programs, and physics-sensitive effects instead of encoding them as one flat object label.

Latest verification: the project `.venv` passes 101 tests across
`backend/core`, `backend/runtime`, and `backend/app/tests`. Backend
`compileall`, `git diff --check`, the wait-action smoke check, and the frontend
production build also pass (with the existing chunk-size warning).
