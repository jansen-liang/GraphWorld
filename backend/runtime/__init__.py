"""Mutable world execution, simulation sessions, and runtime systems.

Keep package initialization light so core domain modules can be imported by
runtime without eagerly starting the simulation engine.
"""

__all__ = ["advance_time"]


def __getattr__(name: str):
    if name == "advance_time":
        from .time import advance_time

        return advance_time
    raise AttributeError(name)
