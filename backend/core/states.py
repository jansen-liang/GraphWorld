from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class DiscreteState(str, Enum):
    CYCLE_REMAINING = "cycle_remaining"
    FILL_LEVEL = "fill_level"
    FOLDED = "folded"
    IS_BLOCKED = "is_blocked"
    IS_BROKEN = "is_broken"
    IS_BOILING = "is_boiling"
    IS_BURNT = "is_burnt"
    IS_COOKED = "is_cooked"
    IS_DIRTY = "is_dirty"
    IS_FROZEN = "is_frozen"
    IS_FULL = "is_full"
    HAS_WATER = "has_water"
    WATER_LEVEL = "water_level"
    IS_RUNNING = "is_running"
    USES_LEFT = "uses_left"
    COUNT = "count"
    AMOUNT = "amount"
    CAPACITY = "capacity"
    IS_ON = "is_on"
    IS_OPEN = "is_open"
    IS_PRESSED = "is_pressed"
    IS_ROTTEN = "is_rotten"
    IS_SPOILED = "is_spoiled"
    FRESHNESS = "freshness"
    IS_WET = "is_wet"
    IS_WILTED = "is_wilted"
    TEMPERATURE = "temperature"
    VITALITY = "vitality"


class StateCategory(str, Enum):
    CONTROL = "control"
    CONDITION = "condition"
    QUANTITY = "quantity"
    THERMAL = "thermal"
    MATERIAL = "material"
    LIFE = "life"


class StateValueType(str, Enum):
    BOOLEAN = "boolean"
    NUMBER = "number"
    ENUM = "enum"
    NUMBER_OR_ENUM = "number_or_enum"


DISCRETE_STATE_SPACE: tuple[str, ...] = tuple(state.value for state in DiscreteState)
TEMPERATURE_VALUES = frozenset({"cold", "room", "warm", "hot"})
THERMAL_PHASES = frozenset({"frozen", "cold", "room", "warm", "hot", "boiling", "burning"})
TEMPERATURE_NUMERIC_RANGE = (-50.0, 300.0)
NUMERIC_STATES = frozenset({"cycle_remaining", "fill_level", "vitality", "freshness", "uses_left", "count", "amount", "capacity", "water_level"})


@dataclass(frozen=True)
class StateDefinition:
    name: str
    category: StateCategory
    value_type: StateValueType
    domain: tuple[object, ...] = ()
    applies_to: tuple[str, ...] = ()
    requires_capabilities: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()
    description: str = ""

    def accepts(self, *, semantic_type: str = "", capabilities: set[str] | None = None) -> bool:
        capabilities = capabilities or set()
        if semantic_type in self.applies_to:
            return True
        # Capability-only extension is reserved for generic condition states
        # such as dirt/wetness. Domain/material states remain type-gated: a
        # cookable pan may have temperature, but it does not become "cooked"
        # food merely because it can hold heat.
        if self.category in {StateCategory.CONDITION, StateCategory.QUANTITY} and self.requires_capabilities:
            return bool(set(self.requires_capabilities) & capabilities)
        return not self.applies_to and (not self.requires_capabilities or bool(set(self.requires_capabilities) & capabilities))

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "category": self.category.value,
            "value_type": self.value_type.value,
            "domain": list(self.domain),
            "applies_to": list(self.applies_to),
            "requires_capabilities": list(self.requires_capabilities),
            "derived_from": list(self.derived_from),
            "description": self.description,
        }


@dataclass(frozen=True)
class StateSpec:
    name: str
    value_type: str
    applies_to: tuple[str, ...]
    positive_value: object
    worsened_by: tuple[str, ...]
    improved_by: tuple[str, ...]
    downstream_effects: tuple[str, ...]
    score_weight: float = 1.0
    category: StateCategory = StateCategory.CONDITION
    value_kind: StateValueType = StateValueType.BOOLEAN
    requires_capabilities: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()


def is_discrete_state(name: str) -> bool:
    return str(name or "") in DISCRETE_STATE_SPACE


def normalize_discrete_value(name: str, value: object) -> int | float | str | None:
    if name == DiscreteState.TEMPERATURE.value:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(float(value), 4)
        return str(value).strip().lower()
    if name in NUMERIC_STATES:
        try:
            number = round(float(value), 4) if value is not None else None
            if number is None:
                return None
            if name == DiscreteState.WATER_LEVEL.value:
                return max(0.0, min(100.0, number))
            return number
        except (TypeError, ValueError):
            return None
    if value is None:
        return None
    return bool(value)


def _spec(name: str, category: StateCategory, value_kind: StateValueType, applies: tuple[str, ...], positive: object, worse: tuple[str, ...], better: tuple[str, ...], effects: tuple[str, ...], caps: tuple[str, ...] = ()) -> StateSpec:
    return StateSpec(name, value_kind.value, applies, positive, worse, better, effects, category=category, value_kind=value_kind, requires_capabilities=caps)


STATE_SPECS: dict[str, StateSpec] = {
    "is_open": _spec("is_open", StateCategory.CONTROL, StateValueType.BOOLEAN, ("door", "cabinet", "fridge", "drawer", "washer", "microwave"), False, ("left_open",), ("close",), ("controls access",), ("openable",)),
    "is_on": _spec("is_on", StateCategory.CONTROL, StateValueType.BOOLEAN, ("stove", "faucet", "washer", "dishwasher", "light", "tv", "microwave"), False, ("left_running",), ("press",), ("starts cycles",), ("switchable",)),
    "is_pressed": _spec("is_pressed", StateCategory.CONTROL, StateValueType.BOOLEAN, ("button", "switch", "knob"), False, ("press",), ("cycle_completion",), ("propagates control",), ("switchable",)),
    "cycle_remaining": _spec("cycle_remaining", StateCategory.QUANTITY, StateValueType.NUMBER, ("washer", "dishwasher", "microwave"), 0, ("press_start",), ("timed_transition",), ("tracks cycle completion",)),
    "is_dirty": _spec("is_dirty", StateCategory.CONDITION, StateValueType.BOOLEAN, ("plate", "cup", "table", "clothes", "floor", "toilet", "sink"), False, ("use", "spill"), ("brush",), ("surface needs cleaning",), ("cleanable",)),
    "is_rotten": _spec("is_rotten", StateCategory.MATERIAL, StateValueType.BOOLEAN, ("food", "milk", "juice", "vegetable", "fruit", "organic_item"), False, ("time_decay",), (), ("dispose or remove",), ("perishable",)),
    "is_spoiled": _spec("is_spoiled", StateCategory.MATERIAL, StateValueType.BOOLEAN, ("food", "milk", "juice", "vegetable", "fruit", "organic_item"), False, ("time_decay",), ("cooling",), ("intermediate food quality",), ("perishable",)),
    "freshness": _spec("freshness", StateCategory.LIFE, StateValueType.NUMBER, ("food", "milk", "juice", "vegetable", "fruit", "organic_item"), 100.0, ("time_decay",), ("cooling",), ("continuous food quality",), ("perishable",)),
    "is_full": _spec("is_full", StateCategory.QUANTITY, StateValueType.BOOLEAN, ("trash_bin", "basket", "cup", "container"), False, ("place",), (), ("blocks filling",), ("fillable",)),
    "fill_level": _spec("fill_level", StateCategory.QUANTITY, StateValueType.NUMBER, ("trash_bin", "cup", "container"), 0, ("place",), (), ("drives is_full",), ("fillable",)),
    "has_water": _spec("has_water", StateCategory.QUANTITY, StateValueType.BOOLEAN, ("sink", "vase", "cup", "mug", "bowl", "wateringcan", "spraybottle"), False, ("empty", "consume", "evaporate"), ("open_faucet", "fill", "refill"), ("controls watering and wetting effects",), ("water_container",)),
    "water_level": _spec("water_level", StateCategory.QUANTITY, StateValueType.NUMBER, ("sink", "vase", "cup", "mug", "bowl", "wateringcan", "spraybottle"), 0, ("empty", "consume", "evaporate"), ("open_faucet", "fill", "refill"), ("continuous water quantity; has_water is its compatibility projection",), ("water_container",)),
    "is_running": _spec("is_running", StateCategory.CONTROL, StateValueType.BOOLEAN, ("washer", "washing_machine", "dryer", "clothesdryer", "microwave", "printer", "coffeemachine", "coffee_machine"), False, ("start",), ("finish",), ("tracks active process",), ("timed_device",)),
    "uses_left": _spec("uses_left", StateCategory.QUANTITY, StateValueType.NUMBER, (), 0, ("consume",), ("refill",), ("finite resource availability",), ("finite_resource",)),
    "count": _spec("count", StateCategory.QUANTITY, StateValueType.NUMBER, (), 0, ("consume",), ("refill",), ("resource inventory",), ("finite_resource",)),
    "amount": _spec("amount", StateCategory.QUANTITY, StateValueType.NUMBER, (), 0, ("consume",), ("refill",), ("material quantity",), ("finite_resource",)),
    "capacity": _spec("capacity", StateCategory.QUANTITY, StateValueType.NUMBER, (), 0, ("place",), (), ("limits contained item count",), ("capacity_holder",)),
    "is_wet": _spec("is_wet", StateCategory.CONDITION, StateValueType.BOOLEAN, ("clothes", "towel", "floor", "cup", "sink_area"), False, ("water",), ("drying",), ("blocks folding",)),
    "temperature": _spec("temperature", StateCategory.THERMAL, StateValueType.NUMBER_OR_ENUM, ("food", "drink", "milk", "juice", "vegetable", "fruit", "egg", "bread", "water"), "room", ("cooling",), ("heating",), ("drives thermal phases and cooking",), ("temperature_sensitive", "cookable")),
    "is_cooked": _spec("is_cooked", StateCategory.MATERIAL, StateValueType.BOOLEAN, ("food", "egg", "bread"), False, ("raw_food",), ("cooking",), ("enables eating",), ("cookable",)),
    "is_burnt": _spec("is_burnt", StateCategory.MATERIAL, StateValueType.BOOLEAN, ("food", "egg", "bread"), False, ("overcook",), (), ("food disposal",), ("cookable",)),
    "is_frozen": _spec("is_frozen", StateCategory.MATERIAL, StateValueType.BOOLEAN, ("food", "drink", "milk", "juice", "vegetable", "fruit"), False, ("freeze",), ("thaw",), ("blocks immediate use",), ("temperature_sensitive",)),
    "is_broken": _spec("is_broken", StateCategory.CONDITION, StateValueType.BOOLEAN, ("cup", "plate", "computer", "device"), False, ("break",), (), ("blocks normal use",)),
    "is_blocked": _spec("is_blocked", StateCategory.CONDITION, StateValueType.BOOLEAN, ("door", "path", "container"), False, ("obstruct",), (), ("blocks navigation or access",)),
    "folded": _spec("folded", StateCategory.CONDITION, StateValueType.BOOLEAN, ("clothes", "towel", "blanket"), True, ("unfold",), ("fold",), ("improves storage",), ("foldable",)),
    "is_wilted": _spec("is_wilted", StateCategory.LIFE, StateValueType.BOOLEAN, ("plant",), False, ("time_without_water",), (), ("lowers vitality",), ("plant_life",)),
    "vitality": _spec("vitality", StateCategory.LIFE, StateValueType.NUMBER, ("plant",), 1, ("time_without_water",), ("water",), ("drives wilted",), ("plant_life",)),
}


STATE_DEFINITIONS: dict[str, StateDefinition] = {
    name: StateDefinition(name, spec.category, spec.value_kind, applies_to=spec.applies_to, requires_capabilities=spec.requires_capabilities, derived_from=spec.derived_from, description=spec.downstream_effects[0] if spec.downstream_effects else "")
    for name, spec in STATE_SPECS.items()
}
STATE_DEFINITIONS["is_boiling"] = StateDefinition("is_boiling", StateCategory.THERMAL, StateValueType.BOOLEAN, applies_to=("water", "drink", "liquid"), requires_capabilities=("liquid", "cookable"), derived_from=("temperature",), description="Derived when liquid temperature reaches its boiling point.")


def state_definition(name: str) -> StateDefinition:
    return STATE_DEFINITIONS[str(name)]


def state_table_for_object(semantic_type: str, capabilities: Iterable[str] = ()) -> dict[str, StateDefinition]:
    capability_set = set(capabilities)
    return {name: definition for name, definition in STATE_DEFINITIONS.items() if definition.accepts(semantic_type=semantic_type, capabilities=capability_set)}


__all__ = ["DISCRETE_STATE_SPACE", "DiscreteState", "NUMERIC_STATES", "STATE_SPECS", "STATE_DEFINITIONS", "StateCategory", "StateDefinition", "StateSpec", "StateValueType", "TEMPERATURE_VALUES", "THERMAL_PHASES", "TEMPERATURE_NUMERIC_RANGE", "is_discrete_state", "normalize_discrete_value", "state_definition", "state_table_for_object"]
