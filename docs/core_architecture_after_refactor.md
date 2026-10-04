# Core Architecture After Refactor

## Runtime data flow

```text
UI input -> InteractionRequest -> resolve_interaction
          -> MutationPipeline -> WorldGraph (Node + Edge)
          -> WorldDelta + source_json -> React state -> Three.js projection
```

The browser sends an input or canonical Action request. It does not execute
world rules locally. A long-lived `World` resolves the input, applies one
atomic mutation, and returns the resulting `WorldDelta` and authoritative
scene snapshot.

## Backend files

| File | Responsibility |
| --- | --- |
| `backend/core/node.py`, `edge.py`, `articulation.py` | Canonical graph entities and structure-tree view. |
| `backend/core/action.py`, `requirement.py`, `effect.py` | Action contracts and declarative preconditions/effects. |
| `backend/runtime/world/graph.py` | Mutable graph store and disposable relationship indices. |
| `backend/runtime/action_executor.py` | Atomic action transaction and `WorldDelta` generation. |
| `backend/runtime/input_adapter.py` | Converts keyboard/mouse intent into a canonical Action without mutating state. |
| `backend/runtime/time.py`, `process_rules.py` | Clock-driven rules and process transitions. |
| `backend/app/services/simulation_service.py` | Long-lived simulation session API facade. |
| `backend/app/api/routes/scenes.py` | HTTP endpoints for session start, dispatch, and stop. |
| `backend/tests/`, `backend/app/tests/` | Contracts for interaction, placement, processes, and session protocol. |
| `backend/app/tests/test_simulation_service.py` | API Delta and Action round-trip contracts. |

## Frontend files

| File | Responsibility |
| --- | --- |
| `frontend/web/src/api/scenes.ts` | Starts and dispatches the long-lived simulation session, receiving snapshots and deltas. |
| `frontend/web/src/features/scene-builder/SceneBuilderPage.tsx` | Owns draft snapshot and applies returned session deltas; editor changes write edges. |
| `frontend/web/src/features/scene-builder/Scene3DCanvas.tsx` | Projects nodes/edges into Three.js and emits input; it contains no world-rule implementation. |
| `frontend/web/src/rendering/partTree.ts` | Visual joints and mechanical part projection only. |
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
