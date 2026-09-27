# Core Architecture After Refactor

## Runtime data flow

```text
UI input -> InteractionRequest -> resolve_interaction
          -> MutationPipeline -> WorldGraph (Node + Edge)
          -> WorldDelta + source_json -> React state -> Three.js projection
```

The browser sends an input or canonical Action request. It does not execute
world rules locally. The API rebuilds a `WorldGraph`, resolves the input,
applies one mutation through `MutationPipeline`, and returns the resulting
`WorldDelta` and authoritative scene snapshot.

## Backend files

| File | Responsibility |
| --- | --- |
| `backend/core/model.py` | Flat `Node` and `Edge` value models. No relationship cache is stored on a node. |
| `backend/core/world_graph.py` | Mutable graph store and old-scene import adapter. Rebuilds disposable `parent_of`, `room_of`, and control indices from edges. |
| `backend/core/edges.py` | Relation names and relation metadata. |
| `backend/core/relationship_ops.py` | Canonical relationship mutation helpers. |
| `backend/core/composition.py` | Materializes declared appliance parts and storage slots. It fills missing static composition data for old snapshots. |
| `backend/core/interaction.py` | Converts keyboard/mouse intent into a canonical Action without mutating state. |
| `backend/core/action_schemas.py` | Action preconditions and direct effects. |
| `backend/core/mutation.py` | Single Action/Rule/System mutation entry point and `WorldDelta` generation. |
| `backend/core/effects.py` | Pure domain effects invoked by action schemas. |
| `backend/core/timed_transitions.py` | Clock-driven rules invoked through `MutationPipeline.run_system`. |
| `backend/core/processes.py` | Process start/complete bookkeeping for timed devices. |
| `backend/app/services/simulation_service.py` | Stateless editor-preview API facade. |
| `backend/app/api/routes/scenes.py` | HTTP endpoints for interactions and ticks. |
| `backend/core/test_home_behavior_contract.py` | Contracts for laundry, lights, faucet, two hands, placement, and device progress/stop. |
| `backend/app/tests/test_simulation_service.py` | API Delta and Action round-trip contracts. |

## Frontend files

| File | Responsibility |
| --- | --- |
| `frontend/src/api/scenes.ts` | Sends interaction/move requests and receives `SceneInteractionResponse`. |
| `frontend/src/features/scene-builder/SceneBuilderPage.tsx` | Owns draft snapshot and applies returned `source_json`; editor changes write edges. |
| `frontend/src/features/scene-builder/Scene3DCanvas.tsx` | Projects nodes/edges into Three.js and emits input; it contains no world-rule implementation. |
| `frontend/src/features/scene-builder/compositeRuntime.ts` | Visual joints and mechanical part projection only. |
| `frontend/e2e/home-behavior.cjs` | Reproducible v28 API behavior suite plus browser/WebGL smoke test. |

## Compatibility boundary

`WorldGraph` and `materialize_compositions` are the only places that read
legacy `parent`, `runtime_relation`, `child`, and partial composition data.
They immediately convert those records into canonical edges. Runtime writes
must use `move_node`, `move_relationship`, or the mutation pipeline.

## Removed or forbidden patterns

- No `scenegraph.py` hierarchy or semantic Node/Edge subclasses.
- No `resolve_and_apply_interaction` shortcut around the mutation pipeline.
- No browser-side `runtime*` truth for device, faucet, light, or progress.
- No relationship writes to `node.parent`, `node.child`, or `node.inventory`.
