"""Runtime world package.

The static scene model lives in :mod:`backend.core`; this package owns the
mutable graph used by an editor preview or simulation run.
"""

from .graph import World, move_position

__all__ = ["World", "move_position"]
