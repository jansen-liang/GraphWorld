from __future__ import annotations

from dataclasses import dataclass


APPLIANCE_CYCLE_STEPS: dict[str, int] = {
    "washer": 3,
    "washing_machine": 3,
    "dishwasher": 3,
    "microwave": 2,
    "coffee_machine": 2,
    "coffee_maker": 2,
    "coffeemachine": 2,
    "clothesdryer": 4,
    "dryer": 4,
    "printer": 2,
    "toaster": 2,
    "workbench": 3,
    "assembly_line": 4,
    "stove": 3,
    "elevator": 2,
}

DRYING_RACK_STEPS = 6

CLOTH_SEMANTICS = frozenset({"clothes", "towel", "blanket"})
TRASHABLE_SEMANTICS = frozenset({"food", "milk", "juice", "vegetable", "fruit", "raw_food", "cooked_food"})

PLACE_TARGET_TYPES = frozenset({"room", "fixed_object"})
BLOCKED_PLACE_TARGET_SEMANTICS = frozenset({"button", "switch", "door", "light", "display", "tv", "faucet", "knob"})
SURFACE_SEMANTICS = frozenset({"drying_rack", "rack", "table", "counter", "shelf"})
CONTAINMENT_CONTAINER_SEMANTICS = frozenset(
    {
        "fridge",
        "refrigerator",
        "microwave",
        "washer",
        "washing_machine",
        "dishwasher",
        "cabinet",
        "drawer",
    }
)


@dataclass(frozen=True)
class DumpRule:
    container_semantic: str
    target_semantics: tuple[str, ...]
    requires_non_empty: bool
    effect: str


DUMP_RULES: dict[str, DumpRule] = {
    "trash_bin": DumpRule(
        container_semantic="trash_bin",
        target_semantics=("garbage_station",),
        requires_non_empty=True,
        effect="empty_trash_bin",
    ),
    "cup": DumpRule(
        container_semantic="cup",
        target_semantics=("sink",),
        requires_non_empty=True,
        effect="empty_fill_level",
    ),
    "wateringcan": DumpRule(
        container_semantic="wateringcan",
        target_semantics=("plant", "flower", "vase"),
        requires_non_empty=True,
        effect="water_plant",
    ),
}


__all__ = [
    "APPLIANCE_CYCLE_STEPS",
    "BLOCKED_PLACE_TARGET_SEMANTICS",
    "CLOTH_SEMANTICS",
    "CONTAINMENT_CONTAINER_SEMANTICS",
    "DRYING_RACK_STEPS",
    "DUMP_RULES",
    "DumpRule",
    "PLACE_TARGET_TYPES",
    "SURFACE_SEMANTICS",
    "TRASHABLE_SEMANTICS",
]
