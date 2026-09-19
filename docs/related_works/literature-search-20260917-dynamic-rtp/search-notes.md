# Search Notes

Date: 2026-09-17

## Safe Public Queries

- persistent embodied environment benchmark robot
- continual embodied agent benchmark household
- dynamic open-ended embodied benchmark robot task planning
- lifelong robot task planning benchmark
- robot task generation benchmark large language model
- human robot collaboration benchmark household persistent
- evolving environments embodied benchmark robot
- persistent world robot benchmark
- proactive robot benchmark household task planning
- exact-title checks for Habitat 3.0, PARTNR, BEHAVIOR-1K, CALVIN, LIBERO, GenSim, RoboGen, RoboCasa, and Taskography

## Sources Checked

- arXiv API and stable abstract pages
- OpenAlex and Crossref for discovery, deduplication, DOI, date, and source checks
- CVF Open Access, PMLR, NeurIPS proceedings, IEEE DOI records, RSS DOI records, OpenReview, and project pages where available
- Existing GraphWorld bibliography and related-work notes, followed by independent primary-record verification for included claims

## Screening Boundary

- The search targets robot task planning and embodied benchmarks. Dynamic navigation, persistent mapping, proactive assistance, continual robot learning, and automatic task generation were retained only when they clarify a boundary of the GraphWorld claim.
- Pure perception, generic LLM-agent, web-agent, autonomous-driving, and game-world papers were excluded unless they supplied a uniquely relevant benchmark mechanism.
- Policy-excluded and low-signal sources were excluded from the final set.

## Unknowns

- EvoNav-Bench, LongAct, NIABench, and PBD-AG are recent 2026 preprints; venue status may change.
- PARTNR's public arXiv record is stable, but the final venue record should be rechecked before camera-ready citation.
- No claim of exhaustive absence is made. The supported conclusion is narrower: no inspected high-confidence source combines the four defining properties listed in `papers.md`.

## Handoff Notes

- For writing: use the four-cluster structure in `papers.md`; avoid the unqualified claims "first dynamic benchmark" and "first automatic task generation."
- For experiments: add stationary/evolving, assigned/open-goal, and offline/online-task-arrival ablations.
- For future monitoring: track `lifelong navigation evolving environments`, `persistent household robot benchmark`, `proactive robot assistance benchmark`, and `endogenous task generation embodied agent`.
