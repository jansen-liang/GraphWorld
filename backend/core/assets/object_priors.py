"""Data-driven placement priors layered on top of core ObjectTemplate.

The core library defines runtime semantics. This module only exposes observed
room/parent/capability priors and must not be used as an action validator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.generation.ontology import load_ontology


# object_priors.py lives in backend/core/assets; the repository root is three
# levels above it and generated statistics live below backend/data.
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATS_DIR = ROOT / "backend" / "data" / "external_stats"


@dataclass(frozen=True)
class ObjectPrior:
    object_type: str
    room_frequency: dict[str, float] = field(default_factory=dict)
    parent_frequency: dict[str, float] = field(default_factory=dict)
    observed_capabilities: dict[str, float] = field(default_factory=dict)
    evidence_count: int = 0
    source: tuple[str, ...] = ()

    @property
    def allowed_rooms(self) -> tuple[str, ...]:
        return tuple(sorted(self.room_frequency))

    @property
    def allowed_parents(self) -> tuple[str, ...]:
        return tuple(sorted(self.parent_frequency))

    @property
    def functional_class(self) -> tuple[str, ...]:
        return tuple(sorted(self.observed_capabilities))

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "room_frequency": dict(self.room_frequency),
            "parent_frequency": dict(self.parent_frequency),
            "observed_capabilities": dict(self.observed_capabilities),
            "allowed_rooms": list(self.allowed_rooms),
            "allowed_parents": list(self.allowed_parents),
            "functional_class": list(self.functional_class),
            "evidence_count": self.evidence_count,
            "source": list(self.source),
        }


def load_object_priors(stats_dir: str | Path = DEFAULT_STATS_DIR) -> dict[str, ObjectPrior]:
    stats_dir = Path(stats_dir)
    ontology = load_ontology()
    room_paths = [
        stats_dir / "ai2thor_room_object_counts.json",
        stats_dir / "procthor_room_object_counts.json",
    ]
    parent_paths = [
        stats_dir / "ai2thor_object_parent_counts.json",
        stats_dir / "procthor_object_parent_counts.json",
    ]
    capability_paths = [
        stats_dir / "ai2thor_object_capability_stats.json",
        stats_dir / "procthor_object_capability_stats.json",
    ]
    if not any(path.exists() for path in room_paths + parent_paths + capability_paths):
        return {}
    rooms: dict[str, dict[str, int]] = {}
    evidence: dict[str, int] = {}
    sources: dict[str, set[str]] = {}
    for path in room_paths:
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            object_type = ontology.normalize("objects", row.get("object_type")) or str(row.get("object_type") or "")
            room = ontology.normalize("rooms", row.get("room_type")) or str(row.get("room_type") or "")
            if object_type and room:
                rooms.setdefault(object_type, {})[room] = rooms.setdefault(object_type, {}).get(room, 0) + int(row.get("count", 0) or 0)
                evidence[object_type] = evidence.get(object_type, 0) + int(row.get("count", 0) or 0)
                sources.setdefault(object_type, set()).add(path.stem.split("_", 1)[0])
    parents: dict[str, dict[str, int]] = {}
    for path in parent_paths:
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            object_type = ontology.normalize("objects", row.get("object_type")) or str(row.get("object_type") or "")
            parent_type = ontology.normalize("objects", row.get("parent_type")) or str(row.get("parent_type") or "")
            if object_type and parent_type:
                count = int(row.get("count", 0) or 0)
                parents.setdefault(object_type, {})[parent_type] = parents.setdefault(object_type, {}).get(parent_type, 0) + count
                sources.setdefault(object_type, set()).add(path.stem.split("_", 1)[0])
    functions: dict[str, dict[str, float]] = {}
    for path in capability_paths:
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            object_type = ontology.normalize("objects", row.get("object_type")) or str(row.get("object_type") or "")
            if not object_type:
                continue
            fields = functions.setdefault(object_type, {})
            for field in ("pickupable", "receptacle", "openable", "toggleable", "moveable"):
                value = row.get(field)
                if value is True or (isinstance(value, dict) and value.get("true", 0) > value.get("false", 0)):
                    if isinstance(value, dict):
                        total = int(value.get("true", 0) or 0) + int(value.get("false", 0) or 0)
                        fields[field] = (int(value.get("true", 0) or 0) / total) if total else 0.0
                    elif value is True:
                        fields[field] = 1.0
                sources.setdefault(object_type, set()).add(path.stem.split("_", 1)[0])
    result = {}
    for object_type in sorted(set(rooms) | set(parents) | set(functions)):
        room_counts = rooms.get(object_type, {})
        parent_counts = parents.get(object_type, {})
        room_total = sum(room_counts.values()) or 1
        parent_total = sum(parent_counts.values()) or 1
        result[object_type] = ObjectPrior(
            object_type=object_type,
            room_frequency={key: value / room_total for key, value in sorted(room_counts.items())},
            parent_frequency={key: value / parent_total for key, value in sorted(parent_counts.items())},
            observed_capabilities=dict(sorted(functions.get(object_type, {}).items())),
            evidence_count=evidence.get(object_type, 0),
            source=tuple(sorted(sources.get(object_type, set()))),
        )
    return result


def get_object_prior(object_type: str, stats_dir: str | Path = DEFAULT_STATS_DIR) -> ObjectPrior | None:
    return load_object_priors(stats_dir).get(str(object_type or "").strip())


__all__ = ["ObjectPrior", "get_object_prior", "load_object_priors"]
