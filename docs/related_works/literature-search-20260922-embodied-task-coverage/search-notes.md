# Search Notes

Date: 2026-09-22

This follow-up reuses the verified source set and screening notes in
`../literature-search-20260917-dynamic-rtp/`. No OpenAlex discovery result was
used as final evidence. The purpose here is implementation triage, not a new
systematic review.

## Queries and screening

The earlier report covered persistent embodied environments, continual
household planning, dynamic task generation, human-robot activity, and scene
graph planning. The follow-up screened those papers against five runtime
contracts: observability, recovery, workload, affordance grounding, and replay.
Papers were retained when the contract was explicit in the benchmark or method;
otherwise the entry is marked partial or low rather than inferred from broad
claims.

## Evidence interpretation

- `persistent world` means state survives a task boundary; it does not imply
  online goal generation.
- `interruption/recovery` means the method exposes recovery or replanning
  behavior, not merely a long action sequence.
- `replay contract` means transitions or traces can be replayed and diagnosed,
  not simply that a simulator logs frames.
- `affordance/graph` includes containment, support, control, and action
  preconditions grounded in scene structure.

## Implementation handoff

The first code slice should add lifecycle checkpoints with:

```text
goal_id, phase, status, priority, started_step, last_progress_step,
preempted_at, preempt_reason, resume_count, deadline_step
```

The checkpoint must be serializable, survive a runtime tick, and preserve the
existing phase-specific goal fields. A preempted goal should remain resumable;
it must not be silently regenerated as a new goal. Tests should cover a goal
being interrupted by a higher-priority goal, resumed after the higher-priority
goal closes, and aging so a low-priority goal cannot starve indefinitely.

The second slice should distinguish `unknown` from `not_present` in observations
and candidate generation. This remains important as the first-person camera
contract grows into renderer raycasts: a missed ray or occluded object must not
be treated as evidence that the object does not exist.
