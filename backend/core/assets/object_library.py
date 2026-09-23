from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ..nodes import ControlObject, FixedObject, MovableObject, NodeType
from ..states import DISCRETE_STATE_SPACE, DiscreteState, state_table_for_object
from ..composition import composition_for
from ..placement import footprint_for, interior_spec_for, surface_spec_for
from .object_model import ObjectFamily, ObjectFamilySpec, PlacementSpec, SystemDependency, infer_family


ALLOWED_STATE_NAMES = frozenset(DISCRETE_STATE_SPACE)


@dataclass(frozen=True)
class Capability:
    name: str
    states: Dict[str, Any] = field(default_factory=dict)
    actions: tuple[str, ...] = ()
    properties: Dict[str, Any] = field(default_factory=dict)


def _merge_actions(*groups: Iterable[str]) -> List[str]:
    actions: List[str] = []
    seen: set[str] = set()
    for group in groups:
        for action in group:
            if action in seen:
                continue
            seen.add(action)
            actions.append(action)
    return actions


MOVEABLE = Capability("moveable", actions=("move",))
REACHABLE = Capability("reachable", actions=("move",))
PICKABLE = Capability("pickable", actions=("pick", "place"))
PLACE_TARGET = Capability("place_target", actions=("place",))
CARRYING = Capability(
    "capacity_holder",
    states={DiscreteState.CAPACITY.value: 1},
    actions=("place",),
    properties={"max_capacity": 1, "accepted_families": ("food",)},
)
NON_FOOD_CARRYING = Capability(
    "capacity_holder",
    states={DiscreteState.CAPACITY.value: 5},
    actions=("place",),
    properties={"max_capacity": 5, "accepted_families": ("non_food",)},
)
CLEANABLE = Capability("cleanable", states={DiscreteState.IS_DIRTY.value: False}, actions=("brush",))
SWITCHABLE = Capability("switchable", states={DiscreteState.IS_ON.value: False}, actions=("press",))
OPENABLE = Capability("openable", states={DiscreteState.IS_OPEN.value: False}, actions=("open", "close"))
FOLDABLE = Capability("foldable", states={DiscreteState.FOLDED.value: True}, actions=("fold",))
FILLABLE = Capability(
    "fillable",
    states={
        DiscreteState.FILL_LEVEL.value: 0.0,
        DiscreteState.IS_FULL.value: False,
    },
)
WATER_SOURCE_CONTROL = Capability("water_source_control", actions=("open", "close"))
FINITE_RESOURCE = Capability("finite_resource", actions=("press", "refill"), properties={"resource_based": True})
TIMED_DEVICE = Capability(
    "timed_device",
    states={"is_running": False, "cycle_remaining": 0},
    actions=("press",),
    properties={"timed_device": True},
)
WORKBENCH = Capability(
    "workbench",
    actions=("press", "place"),
    properties={"workbench": True},
)
PERISHABLE = Capability("perishable", states={DiscreteState.IS_ROTTEN.value: False})
PLANT_LIFE = Capability(
    "plant_life",
    states={
        DiscreteState.IS_WILTED.value: False,
        DiscreteState.IS_WET.value: True,
        DiscreteState.VITALITY.value: 1.0,
    },
)
STRUCTURAL_DOOR = Capability(
    "structural_door",
    states={DiscreteState.IS_OPEN.value: False},
    actions=("open", "close"),
    properties={
        "door_kind": "structural",
        "blocks_visibility": True,
        "blocks_navigation": True,
    },
)
CONTAINMENT_BLOCKER = Capability(
    "containment_blocker",
    properties={"blocks_containment": True},
)
START_REQUIRES_CLOSED = Capability(
    "start_requires_closed",
    properties={"requires_closed_to_start": True},
)
DUMPABLE = Capability("dumpable", actions=("dump",))


ACTION_CAPABILITIES = {
    "move": REACHABLE,
    "pick": PICKABLE,
    "place": PLACE_TARGET,
    "brush": CLEANABLE,
    "press": SWITCHABLE,
    "open": OPENABLE,
    "close": OPENABLE,
    "dump": DUMPABLE,
}


@dataclass(frozen=True, init=False)
class ObjectTemplate:
    """Runtime object definition; placement evidence lives in ObjectPrior.

    The old positional declaration form is accepted only while the catalog is
    being migrated.  It is immediately normalized into the v2 fields below.
    """

    semantic_type: str
    name: str
    name_cn: str
    node_type: NodeType
    family: ObjectFamily
    capabilities: tuple[Capability, ...]
    default_states: Dict[str, Any]
    placement_spec: PlacementSpec
    family_spec: ObjectFamilySpec
    required_systems: tuple[SystemDependency, ...]
    variant_of: str | None
    parent_device_type: Optional[str]
    resource_capacity: Dict[str, float | int]

    def __init__(
        self,
        semantic_type: str,
        name: str,
        name_cn: str,
        node_type: NodeType,
        default_states: Dict[str, Any] | None = None,
        interactive_actions: Iterable[str] | None = None,
        placement: str | PlacementSpec = "room",
        capabilities: tuple[Capability, ...] = (),
        *,
        family: ObjectFamily | str | None = None,
        placement_spec: PlacementSpec | None = None,
        required_systems: Iterable[SystemDependency | str] = (),
        variant_of: str | None = None,
        parent_device_type: Optional[str] = None,
        resource_capacity: Optional[Dict[str, float | int]] = None,
    ) -> None:
        explicit_actions = tuple(interactive_actions or ())
        effective_capabilities = list(capabilities)
        capability_names = {item.name for item in effective_capabilities}
        for action in explicit_actions:
            capability = ACTION_CAPABILITIES.get(str(action))
            if capability is not None and capability.name not in capability_names:
                effective_capabilities.append(capability)
                capability_names.add(capability.name)
        states: Dict[str, Any] = {}
        actions: List[str] = []
        properties: Dict[str, Any] = {}
        for capability in effective_capabilities:
            states.update(deepcopy(capability.states))
            actions = _merge_actions(actions, capability.actions)
            properties.update(deepcopy(capability.properties))
        states.update(deepcopy(default_states or {}))
        actions = _merge_actions(actions, explicit_actions)
        invalid_states = sorted(set(states) - ALLOWED_STATE_NAMES)
        if invalid_states:
            raise ValueError(f"{self.semantic_type} uses states outside DiscreteState: {invalid_states}")

        normalized_family = ObjectFamily(family) if family is not None else infer_family(semantic_type, node_type, {item.name for item in effective_capabilities})
        mode_spec = placement_spec or (placement if isinstance(placement, PlacementSpec) else PlacementSpec(mode=str(placement)))
        normalized_systems = tuple(SystemDependency(item) for item in required_systems)
        if parent_device_type is None:
            parent_device_type = properties.get("parent_device_type")
        object.__setattr__(self, "semantic_type", semantic_type)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_cn", name_cn)
        object.__setattr__(self, "node_type", node_type)
        object.__setattr__(self, "family", normalized_family)
        object.__setattr__(self, "capabilities", tuple(effective_capabilities))
        object.__setattr__(self, "default_states", states)
        object.__setattr__(self, "placement_spec", mode_spec)
        object.__setattr__(self, "family_spec", ObjectFamilySpec(normalized_family, normalized_systems))
        object.__setattr__(self, "required_systems", normalized_systems)
        object.__setattr__(self, "variant_of", variant_of)
        object.__setattr__(self, "parent_device_type", parent_device_type)
        object.__setattr__(self, "resource_capacity", dict(resource_capacity or {}))

    @property
    def interactive_actions(self) -> list[str]:
        return _merge_actions(*(capability.actions for capability in self.capabilities))

    @property
    def placement(self) -> str:
        return self.placement_spec.mode

    @property
    def allowed_rooms(self) -> tuple[str, ...]:
        return self.placement_spec.allowed_rooms

    @property
    def allowed_parents(self) -> tuple[str, ...]:
        return self.placement_spec.allowed_parents

    @property
    def functional_class(self) -> tuple[str, ...]:
        return (self.family.value,)

    @property
    def state_schema(self) -> dict[str, dict[str, Any]]:
        """States this object may own; unrelated global states are excluded."""
        return {
            name: definition.to_dict()
            for name, definition in state_table_for_object(
                self.semantic_type,
                {capability.name for capability in self.capabilities},
            ).items()
        }

    def _property(self, name: str, default: Any = None) -> Any:
        for capability in self.capabilities:
            if name in capability.properties:
                return capability.properties[name]
        return default

    @property
    def door_kind(self) -> Optional[str]:
        return self._property("door_kind")

    @property
    def blocks_visibility(self) -> bool:
        return bool(self._property("blocks_visibility", False))

    @property
    def blocks_navigation(self) -> bool:
        return bool(self._property("blocks_navigation", False))

    @property
    def blocks_containment(self) -> bool:
        return bool(self._property("blocks_containment", False))

    @property
    def requires_closed_to_start(self) -> bool:
        return bool(self._property("requires_closed_to_start", False))

    @property
    def max_capacity(self) -> int | None:
        value = self._property("max_capacity")
        return int(value) if value is not None else None

    @property
    def accepted_families(self) -> tuple[str, ...]:
        return tuple(self._property("accepted_families", ()))

    def to_spec(self) -> Dict[str, Any]:
        return {
            "semantic_type": self.semantic_type,
            "name": self.name,
            "name_cn": self.name_cn,
            "node_type": self.node_type.value,
            "family": self.family.value,
            "default_states": deepcopy(self.default_states),
            "state_schema": deepcopy(self.state_schema),
            "interactive_actions": list(self.interactive_actions),
            "placement": self.placement,
            "capabilities": [capability.name for capability in self.capabilities],
            "family_spec": self.family_spec.to_dict(),
            "placement_spec": self.placement_spec.to_dict(),
            "required_systems": [item.value for item in self.required_systems],
            "variant_of": self.variant_of,
            "door_kind": self.door_kind,
            "blocks_visibility": self.blocks_visibility,
            "blocks_navigation": self.blocks_navigation,
            "blocks_containment": self.blocks_containment,
            "requires_closed_to_start": self.requires_closed_to_start,
            "parent_device_type": self.parent_device_type,
            "resource_capacity": deepcopy(self.resource_capacity),
            "max_capacity": self.max_capacity,
            "accepted_families": list(self.accepted_families),
            "composition": composition_for(self.semantic_type).to_dict(),
            **(surface_spec_for(self.semantic_type) or {}),
            **(footprint_for(self.semantic_type) or {}),
            **(interior_spec_for(self.semantic_type) or {}),
        }

    def instantiate(self, node_id: str, *, parent: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cls = {
            NodeType.FIXED_OBJECT: FixedObject,
            NodeType.MOVABLE_OBJECT: MovableObject,
            NodeType.CONTROL_OBJECT: ControlObject,
        }.get(self.node_type, FixedObject)
        kwargs: Dict[str, Any] = {
            "states": deepcopy(self.default_states),
            "interactive_actions": _merge_actions(
                self.interactive_actions,
                *(capability.actions for capability in self.capabilities),
            ),
            "parent": parent,
        }
        if cls is ControlObject:
            kwargs.update(
                {
                    "door_kind": self.door_kind,
                    "blocks_visibility": self.blocks_visibility,
                    "blocks_navigation": self.blocks_navigation,
                    "blocks_containment": self.blocks_containment,
                    "requires_closed_to_start": self.requires_closed_to_start,
                    "parent_device_type": self.parent_device_type,
                }
            )
        node = cls(str(node_id), self.semantic_type, self.name, self.name_cn, **kwargs).to_dict()
        for key in (
            "door_kind",
            "blocks_visibility",
            "blocks_navigation",
            "blocks_containment",
            "requires_closed_to_start",
            "parent_device_type",
        ):
            value = getattr(self, key)
            if value not in (None, False):
                node[key] = value
        if self.capabilities:
            node["capabilities"] = [capability.name for capability in self.capabilities]
        if self.max_capacity is not None:
            node["max_capacity"] = self.max_capacity
            node["accepted_families"] = list(self.accepted_families)
        if any(capability.name == "finite_resource" for capability in self.capabilities):
            capacities = self.resource_capacity or {key: value for key, value in self.default_states.items() if key in {"uses_left", "count", "amount"}}
            if capacities:
                node["resource_capacity"] = capacities
        node["state_schema"] = deepcopy(self.state_schema)
        surface_spec = surface_spec_for(self.semantic_type)
        if surface_spec:
            node.update(surface_spec)
        footprint = footprint_for(self.semantic_type)
        if footprint:
            node.update(footprint)
        interior = interior_spec_for(self.semantic_type)
        if interior:
            node.update(interior)
        composition = composition_for(self.semantic_type).to_dict()
        if composition["components"] or composition.get("storage"):
            node["composition"] = composition
        if overrides:
            for key, value in overrides.items():
                if key == "states" and isinstance(value, dict):
                    node["states"].update(value)
                else:
                    node[key] = value
        return node


OBJECT_LIBRARY: Dict[str, ObjectTemplate] = {
    "door": ObjectTemplate(
        "door",
        "door",
        "门",
        NodeType.CONTROL_OBJECT,
        {"is_dirty": False},
        ["move"],
        "wall",
        capabilities=(STRUCTURAL_DOOR,),
    ),
    "button": ObjectTemplate(
        "button",
        "button",
        "按钮",
        NodeType.CONTROL_OBJECT,
        {"is_pressed": False},
        ["move"],
        "wall",
        capabilities=(SWITCHABLE,),
    ),
    "room_light": ObjectTemplate(
        "room_light",
        "light",
        "灯",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "ceiling",
        capabilities=(SWITCHABLE,),
    ),
    "air_conditioner": ObjectTemplate(
        "air_conditioner",
        "air conditioner",
        "空调",
        NodeType.FIXED_OBJECT,
        {"is_on": False},
        ["move"],
        "wall",
        capabilities=(SWITCHABLE, CLEANABLE),
    ),
    "fan": ObjectTemplate(
        "fan",
        "fan",
        "风扇",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_running": False},
        ["move"],
        "room",
        capabilities=(SWITCHABLE, CLEANABLE),
    ),
    "rack": ObjectTemplate(
        "rack",
        "rack",
        "架子",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False},
        ["move"],
        "wall",
    ),
    "shoe_rack": ObjectTemplate(
        "shoe_rack",
        "shoe rack",
        "鞋架",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "seat": ObjectTemplate(
        "seat",
        "seat",
        "座椅",
        NodeType.FIXED_OBJECT,
        {},
        ["move", "place"],
        "room",
        capabilities=(CLEANABLE,),
    ),
    "chair": ObjectTemplate(
        "chair",
        "chair",
        "椅子",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "table": ObjectTemplate(
        "table",
        "table",
        "桌子",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "coffee_table": ObjectTemplate(
        "coffee_table",
        "coffee table",
        "茶几",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "counter": ObjectTemplate(
        "counter",
        "counter",
        "操作台",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "desk": ObjectTemplate(
        "desk",
        "desk",
        "书桌",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "drawer": ObjectTemplate(
        "drawer",
        "drawer",
        "抽屉",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "container",
        capabilities=(OPENABLE, CLEANABLE, PLACE_TARGET),
    ),
    "sofa": ObjectTemplate(
        "sofa",
        "sofa",
        "沙发",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "bed": ObjectTemplate(
        "bed",
        "bed",
        "床",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "room",
        capabilities=(CLEANABLE,),
    ),
    "wardrobe": ObjectTemplate(
        "wardrobe",
        "wardrobe",
        "衣柜",
        NodeType.FIXED_OBJECT,
        {"is_open": False, "is_dirty": False},
        ["move", "open", "close", "press"],
        "wall",
    ),
    "cabinet": ObjectTemplate(
        "cabinet",
        "cabinet",
        "柜子",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(OPENABLE, CLEANABLE, PLACE_TARGET),
    ),
    "sink": ObjectTemplate(
        "sink",
        "sink",
        "水槽",
        NodeType.FIXED_OBJECT,
        {"has_water": False},
        ["move", "dump"],
        PlacementSpec(mode="wall", capacity=1),
        capabilities=(CLEANABLE, PLACE_TARGET),
    ),
    "faucet": ObjectTemplate(
        "faucet",
        "faucet",
        "水龙头",
        NodeType.FIXED_OBJECT,
        {"is_on": False},
        [],
        "wall",
        capabilities=(SWITCHABLE, WATER_SOURCE_CONTROL),
    ),
    "toilet": ObjectTemplate(
        "toilet",
        "toilet",
        "马桶",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False},
        ["move", "brush"],
        "wall",
    ),
    "shower": ObjectTemplate(
        "shower",
        "shower",
        "淋浴",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_dirty": False},
        ["move", "press", "brush"],
        "wall",
    ),
    "refrigerator": ObjectTemplate(
        "refrigerator",
        "refrigerator",
        "冰箱",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(OPENABLE, CLEANABLE, CONTAINMENT_BLOCKER),
    ),
    "microwave": ObjectTemplate(
        "microwave",
        "microwave",
        "微波炉",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "counter",
        capabilities=(SWITCHABLE, TIMED_DEVICE, OPENABLE, CLEANABLE, CONTAINMENT_BLOCKER, START_REQUIRES_CLOSED),
    ),
    "stove": ObjectTemplate(
        "stove",
        "stove",
        "炉灶",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_dirty": False},
        ["move", "press", "brush"],
        "counter",
    ),
    "assembly_line": ObjectTemplate(
        "assembly_line",
        "assembly line",
        "装配线",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_running": False, "cycle_remaining": 0},
        ["move"],
        "room",
        capabilities=(SWITCHABLE, TIMED_DEVICE, WORKBENCH, PLACE_TARGET),
    ),
    "washing_machine": ObjectTemplate(
        "washing_machine",
        "washing machine",
        "洗衣机",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(SWITCHABLE, TIMED_DEVICE, OPENABLE, CLEANABLE, CONTAINMENT_BLOCKER, START_REQUIRES_CLOSED),
    ),
    "washer": ObjectTemplate(
        "washer",
        "washer",
        "洗衣机",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(SWITCHABLE, TIMED_DEVICE, OPENABLE, CLEANABLE, CONTAINMENT_BLOCKER, START_REQUIRES_CLOSED),
    ),
    "drying_rack": ObjectTemplate(
        "drying_rack",
        "drying rack",
        "晾衣架",
        NodeType.FIXED_OBJECT,
        {},
        ["move", "place"],
        "wall",
    ),
    "television": ObjectTemplate(
        "television",
        "television",
        "电视",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_dirty": False},
        ["move", "press", "brush"],
        "wall",
    ),
    "display": ObjectTemplate(
        "display",
        "display",
        "显示屏",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(SWITCHABLE, CLEANABLE),
    ),
    "plant": ObjectTemplate(
        "plant",
        "plant",
        "植物",
        NodeType.MOVABLE_OBJECT,
        {},
        ["move", "dump"],
        "room",
        capabilities=(PICKABLE, PLANT_LIFE),
    ),
    "mug": ObjectTemplate(
        "mug",
        "mug",
        "杯子",
        NodeType.MOVABLE_OBJECT,
        {},
        [],
        "surface",
        capabilities=(PICKABLE, CLEANABLE, FILLABLE),
    ),
    "cup": ObjectTemplate(
        "cup",
        "cup",
        "杯子",
        NodeType.MOVABLE_OBJECT,
        {DiscreteState.IS_WET.value: False},
        [],
        "surface",
        capabilities=(PICKABLE, CLEANABLE, FILLABLE),
    ),
    "plate": ObjectTemplate(
        "plate",
        "plate",
        "盘子",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place", "brush"],
        "surface",
        capabilities=(CARRYING,),
    ),
    "bowl": ObjectTemplate(
        "bowl",
        "bowl",
        "碗",
        NodeType.MOVABLE_OBJECT,
        {DiscreteState.IS_WET.value: False},
        [],
        "surface",
        capabilities=(PICKABLE, CLEANABLE, CARRYING),
    ),
    "book": ObjectTemplate(
        "book",
        "book",
        "书",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "surface",
    ),
    "remote": ObjectTemplate(
        "remote",
        "remote",
        "遥控器",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "is_pressed": False},
        ["pick", "place", "press"],
        "surface",
    ),
    "clothes": ObjectTemplate(
        "clothes",
        "clothes",
        "衣物",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "is_wet": False},
        ["pick", "place"],
        "container",
        capabilities=(FOLDABLE,),
    ),
    "shoes": ObjectTemplate(
        "shoes",
        "shoes",
        "鞋",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "is_wet": False},
        ["pick", "place", "brush"],
        "rack",
    ),
    "box": ObjectTemplate(
        "box",
        "box",
        "箱子",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "surface",
        capabilities=(NON_FOOD_CARRYING,),
    ),
    "cart": ObjectTemplate(
        "cart",
        "cart",
        "推车",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["move", "pick", "place"],
        "room",
        capabilities=(NON_FOOD_CARRYING,),
    ),
    "computer": ObjectTemplate(
        "computer",
        "computer",
        "电脑",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_dirty": False},
        ["move", "press", "brush"],
        "table",
    ),
    "dishwasher": ObjectTemplate(
        "dishwasher",
        "dishwasher",
        "洗碗机",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(SWITCHABLE, OPENABLE, CLEANABLE, CONTAINMENT_BLOCKER, START_REQUIRES_CLOSED),
    ),
    "elevator": ObjectTemplate(
        "elevator",
        "elevator",
        "电梯",
        NodeType.FIXED_OBJECT,
        {"is_open": False},
        ["move", "open", "close", "press"],
        "room",
        capabilities=(OPENABLE,),
    ),
    "dispenser": ObjectTemplate(
        "dispenser",
        "dispenser",
        "分配器",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False, "fill_level": 1.0},
        ["move", "press"],
        "wall",
        capabilities=(FILLABLE,),
    ),
    "doctor_coat": ObjectTemplate(
        "doctor_coat",
        "doctor coat",
        "医生白大褂",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "container",
    ),
    "drink": ObjectTemplate(
        "drink",
        "drink",
        "饮料",
        NodeType.MOVABLE_OBJECT,
        {},
        [],
        "shelf",
        capabilities=(PICKABLE, OPENABLE, PERISHABLE),
    ),
    "fruit": ObjectTemplate(
        "fruit",
        "fruit",
        "水果",
        NodeType.MOVABLE_OBJECT,
        {},
        [],
        "shelf",
        capabilities=(PICKABLE, PERISHABLE),
    ),
    "hand_sanitizer_dispenser": ObjectTemplate(
        "hand_sanitizer_dispenser",
        "hand sanitizer dispenser",
        "免洗洗手液机",
        NodeType.FIXED_OBJECT,
        {"fill_level": 1.0, "is_dirty": False},
        ["move", "press"],
        "wall",
        capabilities=(FILLABLE,),
    ),
    "juice": ObjectTemplate(
        "juice",
        "juice",
        "果汁",
        NodeType.MOVABLE_OBJECT,
        {},
        [],
        "container",
        capabilities=(PICKABLE, OPENABLE, PERISHABLE),
    ),
    "knob": ObjectTemplate(
        "knob",
        "knob",
        "旋钮",
        NodeType.FIXED_OBJECT,
        {"is_on": False},
        ["move", "press"],
        "appliance",
    ),
    "locker": ObjectTemplate(
        "locker",
        "locker",
        "储物柜",
        NodeType.FIXED_OBJECT,
        {"is_open": False, "is_dirty": False},
        ["move", "open", "close"],
        "wall",
    ),
    "machine": ObjectTemplate(
        "machine",
        "machine",
        "机器",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_dirty": False},
        ["move", "press", "brush"],
        "room",
    ),
    "medical_cart": ObjectTemplate(
        "medical_cart",
        "medical cart",
        "医疗推车",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["move", "pick", "place"],
        "room",
    ),
    "medical_form": ObjectTemplate(
        "medical_form",
        "medical form",
        "医疗表单",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "surface",
    ),
    "medicine_box": ObjectTemplate(
        "medicine_box",
        "medicine box",
        "药盒",
        NodeType.MOVABLE_OBJECT,
        {"is_open": False},
        ["pick", "place", "open", "close"],
        "shelf",
    ),
    "medicine_fridge": ObjectTemplate(
        "medicine_fridge",
        "medicine fridge",
        "药品冰箱",
        NodeType.FIXED_OBJECT,
        {},
        ["move"],
        "wall",
        capabilities=(OPENABLE, CLEANABLE, CONTAINMENT_BLOCKER),
    ),
    "milk": ObjectTemplate(
        "milk",
        "milk",
        "牛奶",
        NodeType.MOVABLE_OBJECT,
        {},
        [],
        "container",
        capabilities=(PICKABLE, OPENABLE, PERISHABLE),
    ),
    "nurse_uniform": ObjectTemplate(
        "nurse_uniform",
        "nurse uniform",
        "护士制服",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "container",
    ),
    "prescription_sheet": ObjectTemplate(
        "prescription_sheet",
        "prescription sheet",
        "处方单",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "surface",
    ),
    "printer": ObjectTemplate(
        "printer",
        "printer",
        "打印机",
        NodeType.FIXED_OBJECT,
        {"is_on": False, "is_running": False, "cycle_remaining": 0, "is_dirty": False, "count": 0, "amount": 0},
        ["move", "press", "brush", "place"],
        "table",
        capabilities=(SWITCHABLE, TIMED_DEVICE, WORKBENCH, FINITE_RESOURCE, PLACE_TARGET),
        resource_capacity={"count": 100, "amount": 20},
    ),
    "receipt": ObjectTemplate(
        "receipt",
        "receipt",
        "收据",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "surface",
    ),
    "refrigerated_medicine": ObjectTemplate(
        "refrigerated_medicine",
        "refrigerated medicine",
        "冷藏药品",
        NodeType.MOVABLE_OBJECT,
        {"temperature": "cold"},
        [],
        "container",
        capabilities=(PICKABLE, PERISHABLE),
    ),
    "shelf": ObjectTemplate(
        "shelf",
        "shelf",
        "货架",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False},
        ["move", "place"],
        "wall",
    ),
    "signboard": ObjectTemplate(
        "signboard",
        "signboard",
        "标牌",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False},
        ["move"],
        "wall",
    ),
    "stationery": ObjectTemplate(
        "stationery",
        "stationery",
        "文具",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "surface",
    ),
    "syringe": ObjectTemplate(
        "syringe",
        "syringe",
        "注射器",
        NodeType.MOVABLE_OBJECT,
        {},
        ["pick", "place"],
        "surface",
    ),
    "toilet_brush": ObjectTemplate(
        "toilet_brush",
        "toilet brush",
        "马桶刷",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place", "brush"],
        "bathroom",
    ),
    "wateringcan": ObjectTemplate(
        "wateringcan",
        "watering can",
        "浇水壶",
        NodeType.MOVABLE_OBJECT,
        {"has_water": True, "water_level": 100.0},
        ["pick", "place"],
        "surface",
    ),
    "toothbrush": ObjectTemplate(
        "toothbrush",
        "toothbrush",
        "牙刷",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place", "brush"],
        "surface",
    ),
    "toothpaste": ObjectTemplate(
        "toothpaste",
        "toothpaste",
        "牙膏",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "uses_left": 20},
        ["pick", "place"],
        "surface",
        capabilities=(PICKABLE, FINITE_RESOURCE),
        resource_capacity={"uses_left": 20},
    ),
    "trash_bin": ObjectTemplate(
        "trash_bin",
        "trash bin",
        "垃圾桶",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["pick", "place"],
        "room",
        capabilities=(PLACE_TARGET,),
    ),
    "vegetable": ObjectTemplate(
        "vegetable",
        "vegetable",
        "蔬菜",
        NodeType.MOVABLE_OBJECT,
        {"count": 1},
        [],
        "shelf",
        capabilities=(PICKABLE, PERISHABLE),
    ),
    "water_dispenser": ObjectTemplate(
        "water_dispenser",
        "water dispenser",
        "饮水机",
        NodeType.FIXED_OBJECT,
        {"is_on": True, "is_dirty": False, "fill_level": 1.0},
        ["move", "press"],
        "wall",
        capabilities=(FILLABLE,),
    ),
    "wheelchair": ObjectTemplate(
        "wheelchair",
        "wheelchair",
        "轮椅",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False},
        ["move", "pick", "place"],
        "room",
    ),
    "pillow": ObjectTemplate(
        "pillow",
        "pillow",
        "枕头",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "is_wet": False},
        [],
        PlacementSpec(mode="surface", allowed_parents=("bed", "sofa", "chair")),
        capabilities=(PICKABLE, CLEANABLE),
        family=ObjectFamily.FURNITURE_ACCESSORY,
    ),
    "painting": ObjectTemplate(
        "painting",
        "painting",
        "画",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False},
        [],
        PlacementSpec(mode="wall"),
        capabilities=(CLEANABLE,),
        family=ObjectFamily.DECORATION,
    ),
    "vase": ObjectTemplate(
        "vase",
        "vase",
        "花瓶",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "has_water": False, "water_level": 0.0},
        [],
        PlacementSpec(mode="surface", capacity=3),
        capabilities=(PICKABLE, PLACE_TARGET, CLEANABLE),
        family=ObjectFamily.CONTAINER,
    ),
    "mirror": ObjectTemplate(
        "mirror",
        "mirror",
        "镜子",
        NodeType.FIXED_OBJECT,
        {"is_dirty": False},
        [],
        PlacementSpec(mode="wall"),
        capabilities=(CLEANABLE,),
        family=ObjectFamily.DECORATION,
    ),
    "towel_holder": ObjectTemplate(
        "towel_holder",
        "towel holder",
        "毛巾架",
        NodeType.FIXED_OBJECT,
        {},
        [],
        PlacementSpec(mode="wall"),
        capabilities=(PLACE_TARGET,),
        family=ObjectFamily.FURNITURE_ACCESSORY,
    ),
    "towel": ObjectTemplate(
        "towel",
        "towel",
        "毛巾",
        NodeType.MOVABLE_OBJECT,
        {"is_dirty": False, "is_wet": False},
        [],
        PlacementSpec(mode="surface", allowed_parents=("towel_holder", "counter", "floor")),
        capabilities=(PICKABLE, CLEANABLE, FOLDABLE),
        family=ObjectFamily.CLEANING_TOOL,
    ),
}

def _candidate_template(
    semantic_type: str,
    name_cn: str,
    *,
    family: ObjectFamily,
    rooms: tuple[str, ...],
    parents: tuple[str, ...] = (),
    node_type: NodeType = NodeType.MOVABLE_OBJECT,
    capabilities: tuple[Capability, ...] = (PICKABLE,),
    states: Dict[str, Any] | None = None,
    mode: str = "surface",
    resource_capacity: Dict[str, float | int] | None = None,
) -> ObjectTemplate:
    """Build a current-action-compatible candidate catalog entry."""
    return ObjectTemplate(
        semantic_type,
        semantic_type.replace("_", " "),
        name_cn,
        node_type,
        states or {},
        [],
        PlacementSpec(mode=mode, allowed_rooms=rooms, allowed_parents=parents),
        capabilities=capabilities,
        family=family,
        resource_capacity=resource_capacity,
    )


# First release of dataset candidates whose semantics fit the current action
# and state space. Objects requiring domain systems remain deferred.
OBJECT_LIBRARY.update({
    "statue": _candidate_template("statue", "雕像", family=ObjectFamily.DECORATION,
        rooms=("bedroom", "kitchen", "living_room"), capabilities=(PICKABLE, CLEANABLE)),
    "keychain": _candidate_template("keychain", "钥匙链", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom", "living_room"), capabilities=(PICKABLE,)),
    "cellphone": _candidate_template("cellphone", "手机", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom", "kitchen", "living_room"), capabilities=(PICKABLE, CLEANABLE)),
    "bread": _candidate_template("bread", "面包", family=ObjectFamily.FOOD,
        rooms=("kitchen",), parents=("counter", "table"), capabilities=(PICKABLE, PERISHABLE), states={"is_dirty": False}),
    "tomato": _candidate_template("tomato", "番茄", family=ObjectFamily.FOOD,
        rooms=("kitchen",), parents=("counter", "table", "refrigerator"), capabilities=(PICKABLE, PERISHABLE), states={"is_dirty": False}),
    "sandwich": _candidate_template("sandwich", "三明治", family=ObjectFamily.FOOD,
        rooms=("kitchen",), parents=("counter", "table"), capabilities=(PICKABLE, PERISHABLE), states={"is_dirty": False}),
    "workbench": _candidate_template("workbench", "料理台", family=ObjectFamily.APPLIANCE,
        rooms=("kitchen",), parents=("counter", "table"), node_type=NodeType.FIXED_OBJECT,
        capabilities=(SWITCHABLE, TIMED_DEVICE, WORKBENCH, PLACE_TARGET),
        states={"is_on": False, "is_running": False, "cycle_remaining": 0}),
    "egg": _candidate_template("egg", "鸡蛋", family=ObjectFamily.FOOD,
        rooms=("kitchen",), parents=("counter", "refrigerator", "sink"), capabilities=(PICKABLE, PERISHABLE)),
    "fork": _candidate_template("fork", "叉子", family=ObjectFamily.UTENSIL,
        rooms=("kitchen",), parents=("counter", "drawer", "sink", "table"), capabilities=(PICKABLE, CLEANABLE)),
    "spoon": _candidate_template("spoon", "勺子", family=ObjectFamily.UTENSIL,
        rooms=("kitchen",), parents=("counter", "drawer", "sink", "table"), capabilities=(PICKABLE, CLEANABLE)),
    "ladle": _candidate_template("ladle", "汤勺", family=ObjectFamily.UTENSIL,
        rooms=("kitchen",), parents=("counter", "drawer", "table"), capabilities=(PICKABLE, CLEANABLE)),
    "peppershaker": _candidate_template("peppershaker", "胡椒瓶", family=ObjectFamily.CONTAINER,
        rooms=("kitchen",), parents=("counter", "table"), capabilities=(PICKABLE, CLEANABLE, FINITE_RESOURCE), states={"uses_left": 10}, resource_capacity={"uses_left": 10}),
    "saltshaker": _candidate_template("saltshaker", "盐瓶", family=ObjectFamily.CONTAINER,
        rooms=("kitchen",), parents=("counter", "table"), capabilities=(PICKABLE, CLEANABLE, FINITE_RESOURCE), states={"uses_left": 10}, resource_capacity={"uses_left": 10}),
    "plunger": _candidate_template("plunger", "马桶吸", family=ObjectFamily.CLEANING_TOOL,
        rooms=("bathroom",), parents=("floor",), capabilities=(PICKABLE,)),
    "scrubbrush": _candidate_template("scrubbrush", "清洁刷", family=ObjectFamily.CLEANING_TOOL,
        rooms=("bathroom",), parents=("floor",), capabilities=(PICKABLE, CLEANABLE)),
    "wateringcan": _candidate_template("wateringcan", "浇水壶", family=ObjectFamily.CONTAINER,
        rooms=("balcony", "kitchen", "living_room"), parents=("floor", "sink", "counter"),
        capabilities=(PICKABLE, PLACE_TARGET), states={"has_water": True, "water_level": 100.0}),
    "soapbar": _candidate_template("soapbar", "肥皂", family=ObjectFamily.CLEANING_TOOL,
        rooms=("bathroom",), parents=("bathtub", "counter", "sink"), capabilities=(PICKABLE, CLEANABLE)),
    "tissuebox": _candidate_template("tissuebox", "纸巾盒", family=ObjectFamily.CONTAINER,
        rooms=("bathroom", "bedroom", "living_room"), capabilities=(PICKABLE, PLACE_TARGET, CLEANABLE, FINITE_RESOURCE), states={"count": 100}, resource_capacity={"count": 100}),
    "dresser": _candidate_template("dresser", "梳妆柜", family=ObjectFamily.FURNITURE,
        rooms=("bathroom", "bedroom", "living_room"), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(OPENABLE, PLACE_TARGET, CLEANABLE), mode="room"),
    "bathtub": _candidate_template("bathtub", "浴缸", family=ObjectFamily.FURNITURE,
        rooms=("bathroom",), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(PLACE_TARGET, CLEANABLE), mode="room"),
    "bathtubbasin": _candidate_template("bathtubbasin", "浴缸盆", family=ObjectFamily.CONTAINER,
        rooms=("bathroom",), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(PLACE_TARGET, CLEANABLE), mode="room"),
    "newspaper": _candidate_template("newspaper", "报纸", family=ObjectFamily.MEDIA_DEVICE,
        rooms=("living_room",), capabilities=(PICKABLE, CLEANABLE)),
    "watch": _candidate_template("watch", "手表", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom", "living_room"), capabilities=(PICKABLE, CLEANABLE)),
    "tvstand": _candidate_template("tvstand", "电视柜", family=ObjectFamily.FURNITURE,
        rooms=("living_room",), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(PLACE_TARGET, CLEANABLE), mode="room"),
    "teddybear": _candidate_template("teddybear", "泰迪熊", family=ObjectFamily.DECORATION,
        rooms=("bedroom",), capabilities=(PICKABLE, CLEANABLE)),
    "basketball": _candidate_template("basketball", "篮球", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom",), capabilities=(PICKABLE,)),
    "tennisracket": _candidate_template("tennisracket", "网球拍", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom",), capabilities=(PICKABLE,)),
    "baseballbat": _candidate_template("baseballbat", "棒球棒", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom",), capabilities=(PICKABLE,)),
    "dumbbell": _candidate_template("dumbbell", "哑铃", family=ObjectFamily.PERSONAL_ITEM,
        rooms=("bedroom",), capabilities=(PICKABLE,)),
    "bottle": _candidate_template("bottle", "瓶子", family=ObjectFamily.CONTAINER,
        rooms=("kitchen",), parents=("counter", "table", "shelf"), capabilities=(PICKABLE, PLACE_TARGET, CLEANABLE)),
    "winebottle": _candidate_template("winebottle", "酒瓶", family=ObjectFamily.CONTAINER,
        rooms=("kitchen",), parents=("counter", "table", "refrigerator"), capabilities=(PICKABLE, PLACE_TARGET, CLEANABLE)),
    "roomdecor": _candidate_template("roomdecor", "房间装饰", family=ObjectFamily.DECORATION,
        rooms=("living_room",), parents=("floor",), capabilities=(PICKABLE, CLEANABLE)),
    "poster": _candidate_template("poster", "海报", family=ObjectFamily.DECORATION,
        rooms=("bedroom",), parents=("shelf",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(CLEANABLE,), mode="wall"),
    "ottoman": _candidate_template("ottoman", "脚凳", family=ObjectFamily.FURNITURE,
        rooms=("living_room",), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(PLACE_TARGET, CLEANABLE), mode="room"),
    "footstool": _candidate_template("footstool", "脚踏凳", family=ObjectFamily.FURNITURE,
        rooms=("bathroom", "bedroom"), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(PLACE_TARGET, CLEANABLE), mode="room"),
    "dogbed": _candidate_template("dogbed", "宠物窝", family=ObjectFamily.FURNITURE,
        rooms=("bedroom", "living_room"), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(PLACE_TARGET, CLEANABLE), mode="room"),
    "garbagebag": _candidate_template("garbagebag", "垃圾袋", family=ObjectFamily.CONTAINER,
        rooms=("bedroom", "kitchen"), parents=("floor",), capabilities=(PICKABLE, DUMPABLE)),
    "aluminumfoil": _candidate_template("aluminumfoil", "铝箔纸", family=ObjectFamily.UTENSIL,
        rooms=("kitchen",), parents=("shelf",), capabilities=(PICKABLE,)),
    "tabletopdecor": _candidate_template("tabletopdecor", "桌面装饰", family=ObjectFamily.DECORATION,
        rooms=("bedroom",), parents=("desk",), capabilities=(PICKABLE, CLEANABLE)),
    "vacuumcleaner": _candidate_template("vacuumcleaner", "吸尘器", family=ObjectFamily.CLEANING_TOOL,
        rooms=("bedroom",), parents=("floor",), capabilities=(PICKABLE,)),
    "laundryhamper": _candidate_template("laundryhamper", "洗衣篮", family=ObjectFamily.CONTAINER,
        rooms=("bathroom", "bedroom"), parents=("floor",), capabilities=(PICKABLE, PLACE_TARGET, OPENABLE), mode="room"),
    "coffeemachine": _candidate_template("coffeemachine", "咖啡机", family=ObjectFamily.APPLIANCE,
        rooms=("kitchen",), parents=("counter", "table"), node_type=NodeType.FIXED_OBJECT,
        capabilities=(SWITCHABLE, TIMED_DEVICE, WORKBENCH, CLEANABLE), states={"is_on": False, "is_running": False, "cycle_remaining": 0}),
    "coffee": _candidate_template("coffee", "咖啡", family=ObjectFamily.FOOD,
        rooms=("kitchen",), parents=("counter", "table"), capabilities=(PICKABLE, PERISHABLE), states={"is_dirty": False}),
    "spraybottle": _candidate_template("spraybottle", "喷雾瓶", family=ObjectFamily.CONTAINER,
        rooms=("bathroom", "kitchen"), parents=("counter", "sink", "table"), capabilities=(PICKABLE, PLACE_TARGET, FINITE_RESOURCE), states={"has_water": False, "uses_left": 0}, resource_capacity={"uses_left": 5}),
    "soapbottle": _candidate_template("soapbottle", "洗手液", family=ObjectFamily.CONTAINER,
        rooms=("bathroom", "kitchen"), parents=("counter", "sink", "table"), capabilities=(PICKABLE, PLACE_TARGET, FINITE_RESOURCE), states={"amount": 10}, resource_capacity={"amount": 10}),
    "clothesdryer": _candidate_template("clothesdryer", "烘干机", family=ObjectFamily.APPLIANCE,
        rooms=("bathroom",), parents=("floor",), node_type=NodeType.FIXED_OBJECT,
        capabilities=(SWITCHABLE, TIMED_DEVICE, OPENABLE, PLACE_TARGET, CONTAINMENT_BLOCKER, START_REQUIRES_CLOSED), states={"is_on": False, "is_running": False, "cycle_remaining": 0}, mode="room"),
    "cleaningcloth": _candidate_template("cleaningcloth", "抹布", family=ObjectFamily.CLEANING_TOOL,
        rooms=("bathroom", "kitchen"), parents=("counter", "sink", "table"), capabilities=(PICKABLE, CLEANABLE), states={"is_dirty": False, "is_wet": False}),
    "coffee_beans": _candidate_template("coffee_beans", "咖啡豆", family=ObjectFamily.FOOD,
        rooms=("kitchen",), parents=("counter", "table"), capabilities=(PICKABLE,)),
    "tissue_refill": _candidate_template("tissue_refill", "纸巾补充包", family=ObjectFamily.PERSONAL_ITEM, rooms=("bathroom", "bedroom")),
    "soap_refill": _candidate_template("soap_refill", "洗手液补充装", family=ObjectFamily.PERSONAL_ITEM, rooms=("bathroom", "kitchen")),
    "water_refill": _candidate_template("water_refill", "水补充物", family=ObjectFamily.PERSONAL_ITEM, rooms=("bathroom", "kitchen")),
    "pepper_refill": _candidate_template("pepper_refill", "胡椒补充包", family=ObjectFamily.FOOD, rooms=("kitchen",)),
    "salt_refill": _candidate_template("salt_refill", "盐补充包", family=ObjectFamily.FOOD, rooms=("kitchen",)),
    "toothpaste_refill": _candidate_template("toothpaste_refill", "牙膏补充装", family=ObjectFamily.PERSONAL_ITEM, rooms=("bathroom",)),
    "paper_pack": _candidate_template("paper_pack", "打印纸", family=ObjectFamily.OFFICE_SUPPLY, rooms=("office", "living_room")),
    "ink_cartridge": _candidate_template("ink_cartridge", "墨盒", family=ObjectFamily.OFFICE_SUPPLY, rooms=("office", "living_room")),
})


OBJECT_TYPE_ALIASES = {
    "book_stack": "book",
    "fridge": "refrigerator",
    "stationery_set": "stationery",
    "tv": "television",
}


def resolve_object_key(object_type: str) -> str:
    key = str(object_type or "").strip()
    return OBJECT_TYPE_ALIASES.get(key, key)


def get_object_spec(object_type: str, *, include_prior: bool = False) -> Dict[str, Any]:
    key = resolve_object_key(object_type)
    if key not in OBJECT_LIBRARY:
        result = {
            "semantic_type": object_type,
            "name": object_type.replace("_", " "),
            "name_cn": object_type,
            "node_type": NodeType.MOVABLE_OBJECT.value,
            "default_states": {},
            "interactive_actions": ["pick", "place"],
            "placement": "room",
        }
    else:
        spec = OBJECT_LIBRARY[key]
        result = spec.to_spec()
    if include_prior:
        # Priors are evidence for generation/placement, not runtime semantics.
        from .object_priors import get_object_prior

        prior = get_object_prior(key)
        if prior is not None:
            result["allowed_rooms"] = list(prior.allowed_rooms)
            result["allowed_parents"] = list(prior.allowed_parents)
            result["functional_class"] = list(prior.functional_class)
            result["prior_evidence_count"] = prior.evidence_count
    return result


def build_object_node(node_id: str, object_type: str, *, parent: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = resolve_object_key(object_type)
    if key in OBJECT_LIBRARY:
        return OBJECT_LIBRARY[key].instantiate(node_id, parent=parent, overrides=overrides)
    fallback = ObjectTemplate(
        semantic_type=object_type,
        name=object_type.replace("_", " "),
        name_cn=object_type,
        node_type=NodeType.MOVABLE_OBJECT,
        default_states={},
        interactive_actions=["pick", "place"],
        placement="room",
    )
    return fallback.instantiate(node_id, parent=parent, overrides=overrides)


def list_object_types() -> Iterable[str]:
    return OBJECT_LIBRARY.keys()


def get_object_template(name: str) -> Dict[str, Any]:
    spec = get_object_spec(name)
    return {
        "object_type": spec["semantic_type"],
        "affordances": list(spec["interactive_actions"]),
        "states": deepcopy(spec["default_states"]),
        "default_states": deepcopy(spec["default_states"]),
        "physical_properties": {"placement": spec["placement"]},
        "door_kind": spec.get("door_kind"),
        "blocks_visibility": spec.get("blocks_visibility"),
        "blocks_navigation": spec.get("blocks_navigation"),
        "blocks_containment": spec.get("blocks_containment"),
        "requires_closed_to_start": spec.get("requires_closed_to_start"),
        "composition": deepcopy(spec.get("composition") or {"components": []}),
    }


def list_available_objects() -> List[str]:
    return list(OBJECT_LIBRARY.keys())


def get_objects_for_room(room_type: str) -> List[str]:
    room_map = {
        "entrance": [
            "door",
            "button",
            "room_light",
            "rack",
            "seat",
            "shoes",
        ],
        "living_room": [
            "door",
            "button",
            "room_light",
            "air_conditioner",
            "fan",
            "seat",
            "table",
            "television",
            "remote",
            "book",
            "mug",
            "plant",
        ],
        "bedroom": [
            "door",
            "button",
            "room_light",
            "air_conditioner",
            "fan",
            "bed",
            "wardrobe",
            "book",
            "clothes",
        ],
        "bathroom": [
            "door",
            "button",
            "room_light",
            "sink",
            "toilet",
            "shower",
            "toothpaste",
        ],
        "kitchen": [
            "door",
            "button",
            "room_light",
            "sink",
            "refrigerator",
            "microwave",
            "stove",
            "table",
            "mug",
            "plate",
        ],
        "balcony": [
            "door",
            "button",
            "room_light",
            "washing_machine",
            "drying_rack",
            "clothes",
            "plant",
        ],
    }
    return list(room_map.get(room_type, []))
