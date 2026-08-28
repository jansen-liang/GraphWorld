from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.core.actions import ActionType
from backend.core.assets.npc_library import NPC_EVENT_LIBRARY
from backend.core.assets.object_library import OBJECT_LIBRARY
from backend.core.assets.room_library import ROOM_LIBRARY
from backend.core.assets.task_library import SKILLS_BY_NAME
from backend.core.edges import SpatialRelation
from backend.core.states import DISCRETE_STATE_SPACE


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MAPPING_PATH = Path(__file__).with_name("mappings.json")
NON_OBJECT_TYPES = frozenset({"floor", "human", "robot", "room"})
DOMAIN_ROOM_TYPES = frozenset(
    {
        "outside_home", "lobby", "registration", "waiting_area", "corridor_main",
        "outpatient_clinic", "treatment_room", "pharmacy", "staff_room",
        "produce_area", "shelf_area", "checkout_area", "cold_storage",
        "open_office", "meeting_room", "pantry", "manager_office", "restroom",
        "workshop", "assembly_line", "warehouse", "control_room", "break_room",
    }
)
DOMAIN_OBJECT_TYPES = frozenset(
    {
        "bed_sheet", "cart_return", "finished_product", "food", "garbage_station",
        "linen_bin", "medical_waste", "medical_waste_bin", "prescription_return",
        "quality_record", "receiving_dock", "report", "safety_gear", "supply_cabinet",
        "supply_zone", "toolkit",
    }
)


def _key(value: object) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[\s/-]+", "_", value)
    return re.sub(r"_+", "_", value)


@dataclass(frozen=True)
class OntologyAudit:
    category: str
    raw_value: str
    normalized_value: str | None
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str | None]:
        return {
            "category": self.category,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "status": self.status,
            "detail": self.detail,
        }


class Ontology:
    """Canonical registry backed by the existing ``backend.core`` contracts.

    This layer deliberately does not mutate core registries. It normalizes
    external labels and reports unsupported values for later decisions.
    """

    def __init__(self, mapping_path: str | Path = DEFAULT_MAPPING_PATH) -> None:
        payload = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        self.version = str(payload.get("version") or "0")
        self.aliases: dict[str, dict[str, str | None]] = {
            category: {
                _key(raw): (None if value is None else _key(value))
                for raw, value in (payload.get(category) or {}).items()
            }
            for category in ("rooms", "objects", "relations", "actions", "activities", "skills")
        }
        self.canonical: dict[str, set[str]] = {
            "rooms": set(ROOM_LIBRARY) | set(DOMAIN_ROOM_TYPES),
            "objects": set(OBJECT_LIBRARY) | set(DOMAIN_OBJECT_TYPES),
            "relations": {item.value for item in SpatialRelation},
            "actions": {item.value for item in ActionType},
            "activities": set(NPC_EVENT_LIBRARY),
            "skills": set(SKILLS_BY_NAME),
            "states": set(DISCRETE_STATE_SPACE),
        }

    def normalize(self, category: str, value: object) -> str | None:
        category = _key(category)
        raw = _key(value)
        if not raw:
            return None
        if raw in self.aliases.get(category, {}):
            return self.aliases[category][raw]
        if raw in self.canonical.get(category, set()):
            return raw
        return None

    def audit_values(self, category: str, values: Iterable[object]) -> list[OntologyAudit]:
        result = []
        for value in sorted({_key(item) for item in values if _key(item)}):
            normalized = self.normalize(category, value)
            if normalized is None:
                result.append(OntologyAudit(category, value, None, "unmapped"))
            elif normalized not in self.canonical.get(category, set()):
                result.append(OntologyAudit(category, value, normalized, "missing_template"))
            elif category in {"rooms", "objects"} and normalized not in self.core_templates(category):
                result.append(OntologyAudit(category, value, normalized, "missing_template", "canonical domain label lacks core template"))
            else:
                result.append(OntologyAudit(category, value, normalized, "mapped"))
        return result

    def core_templates(self, category: str) -> set[str]:
        if category == "rooms":
            return set(ROOM_LIBRARY)
        if category == "objects":
            return set(OBJECT_LIBRARY)
        return set(self.canonical.get(category, set()))

    def audit_action_values(self, values: Iterable[object]) -> list[OntologyAudit]:
        result = []
        for value in sorted({_key(item) for item in values if _key(item)}):
            normalized = self.normalize("actions", value)
            if normalized is None and _key(value) in self.aliases["actions"]:
                result.append(OntologyAudit("actions", value, None, "unsupported", "explicitly excluded"))
            elif normalized is None:
                result.append(OntologyAudit("actions", value, None, "unmapped"))
            else:
                result.append(OntologyAudit("actions", value, normalized, "mapped"))
        return result


def load_ontology(mapping_path: str | Path = DEFAULT_MAPPING_PATH) -> Ontology:
    return Ontology(mapping_path)


__all__ = ["Ontology", "OntologyAudit", "load_ontology"]
