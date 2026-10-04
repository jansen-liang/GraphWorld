# Web Client

The browser application lives here. It uses the shared backend API; scene
editing and runtime presentation remain client concerns, while world state
and action effects are authoritative in the backend runtime.

The other clients follow the same API contract in `frontend/isaac` and
`frontend/unity`; this package must not introduce client-specific world rules.
