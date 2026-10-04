"""Static process and placement rule declarations."""

from dataclasses import dataclass
from backend.generation.assets.object_library import PROCESS_DURATIONS

APPLIANCE_CYCLE_STEPS: dict[str, int] = PROCESS_DURATIONS
PROCESS_WATER_COST = 25.0
DRYING_RACK_STEPS = 6
TRASHABLE_SEMANTICS = frozenset({"food", "milk", "juice", "vegetable", "fruit", "raw_food", "cooked_food"})
PLACE_TARGET_TYPES = frozenset({"room", "object"})
SURFACE_SEMANTICS = frozenset({"drying_rack", "rack", "table", "counter", "shelf"})


@dataclass(frozen=True)
class DumpRule:
    container_semantic: str
    target_semantics: tuple[str, ...]
    requires_non_empty: bool
    effect: str


DUMP_RULES = {
    "trash_bin": DumpRule("trash_bin", ("garbage_station",), True, "empty_trash_bin"),
    "cup": DumpRule("cup", ("sink",), True, "empty_fill_level"),
    "wateringcan": DumpRule("wateringcan", ("plant", "flower", "vase"), True, "water_plant"),
}

__all__ = ["APPLIANCE_CYCLE_STEPS", "PROCESS_WATER_COST", "DRYING_RACK_STEPS", "DUMP_RULES", "DumpRule", "PLACE_TARGET_TYPES", "SURFACE_SEMANTICS", "TRASHABLE_SEMANTICS"]
