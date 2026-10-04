"""Canonical object-model building blocks for GraphWorld generation.

Object semantics, placement evidence, and optional gameplay systems are kept
separate.  Runtime nodes may still receive derived legacy-shaped fields, but
templates no longer store placement priors as core semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ObjectFamily(str, Enum):
    STRUCTURAL = "structural"
    FURNITURE = "furniture"
    FURNITURE_ACCESSORY = "furniture_accessory"
    CONTAINER = "container"
    APPLIANCE = "appliance"
    LIGHTING = "lighting"
    FOOD = "food"
    COOKWARE = "cookware"
    UTENSIL = "utensil"
    CLEANING_TOOL = "cleaning_tool"
    DECORATION = "decoration"
    PERSONAL_ITEM = "personal_item"
    MEDICAL_SUPPLY = "medical_supply"
    OFFICE_SUPPLY = "office_supply"
    MEDIA_DEVICE = "media_device"
    ALARM_DEVICE = "alarm_device"
    ENVIRONMENT_CONTROL = "environment_control"
    GENERIC = "generic"


class SystemDependency(str, Enum):
    # Foundation systems already represented by the runtime or scene graph.
    TIME = "time"
    SPACE = "space"
    # World/environment systems. These may be declared before their runtime
    # implementation exists so object release can be gated explicitly.
    ENVIRONMENT = "environment"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    WEATHER = "weather"
    SEASON = "season"
    DAY_NIGHT = "day_night"
    AIR_QUALITY = "air_quality"
    # Domain effect systems.
    COOKING = "cooking"
    LIGHTING = "lighting"
    TOOL_USE = "tool_use"
    CONSUMPTION = "consumption"
    MEDIA = "media"
    ALARM = "alarm"
    PAYMENT = "payment"


class SystemStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    PLANNED = "planned"
    DEFERRED = "deferred"


class SystemLayer(str, Enum):
    FOUNDATION = "foundation"
    DERIVED_ENVIRONMENT = "derived_environment"
    ENVIRONMENT_EFFECTS = "environment_effects"
    DOMAIN_EFFECTS = "domain_effects"


@dataclass(frozen=True)
class SystemSpec:
    """Small architecture registry entry, not an implementation of a system."""

    name: SystemDependency
    layer: SystemLayer
    status: SystemStatus
    depends_on: tuple[SystemDependency, ...] = ()
    world_state_keys: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "layer": self.layer.value,
            "status": self.status.value,
            "depends_on": [item.value for item in self.depends_on],
            "world_state_keys": list(self.world_state_keys),
            "description": self.description,
        }


# Keep the initial architecture intentionally small. A future implementation
# can split a planned entry into modules without changing object templates.
SYSTEM_REGISTRY: dict[SystemDependency, SystemSpec] = {
    SystemDependency.TIME: SystemSpec(
        SystemDependency.TIME, SystemLayer.FOUNDATION, SystemStatus.PARTIAL,
        world_state_keys=("step", "time_min", "minutes_per_step", "day"),
        description="Clock progression and calendar position.",
    ),
    SystemDependency.SPACE: SystemSpec(
        SystemDependency.SPACE, SystemLayer.FOUNDATION, SystemStatus.IMPLEMENTED,
        world_state_keys=("nodes", "edges", "parent_of", "room_of"),
        description="Containment, room topology, reachability, and visibility.",
    ),
    SystemDependency.SEASON: SystemSpec(
        SystemDependency.SEASON, SystemLayer.DERIVED_ENVIRONMENT, SystemStatus.PLANNED,
        depends_on=(SystemDependency.TIME,),
        world_state_keys=("season",), description="Calendar-derived season.",
    ),
    SystemDependency.DAY_NIGHT: SystemSpec(
        SystemDependency.DAY_NIGHT, SystemLayer.DERIVED_ENVIRONMENT, SystemStatus.PARTIAL,
        depends_on=(SystemDependency.TIME,),
        world_state_keys=("day_phase",), description="Time-derived day/night phase.",
    ),
    SystemDependency.WEATHER: SystemSpec(
        SystemDependency.WEATHER, SystemLayer.ENVIRONMENT_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.TIME, SystemDependency.SEASON),
        world_state_keys=("weather",), description="Outdoor weather profile.",
    ),
    SystemDependency.ENVIRONMENT: SystemSpec(
        SystemDependency.ENVIRONMENT, SystemLayer.ENVIRONMENT_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.SPACE, SystemDependency.WEATHER),
        world_state_keys=("ventilation",), description="Shared environmental exchange.",
    ),
    SystemDependency.TEMPERATURE: SystemSpec(
        SystemDependency.TEMPERATURE, SystemLayer.ENVIRONMENT_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.ENVIRONMENT,),
        world_state_keys=("room_temperature",), description="Room temperature dynamics.",
    ),
    SystemDependency.HUMIDITY: SystemSpec(
        SystemDependency.HUMIDITY, SystemLayer.ENVIRONMENT_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.ENVIRONMENT,),
        world_state_keys=("room_humidity",), description="Room humidity dynamics.",
    ),
    SystemDependency.AIR_QUALITY: SystemSpec(
        SystemDependency.AIR_QUALITY, SystemLayer.ENVIRONMENT_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.SPACE, SystemDependency.ENVIRONMENT),
        world_state_keys=("room_air_quality",), description="Pollution and ventilation effects.",
    ),
    SystemDependency.LIGHTING: SystemSpec(
        SystemDependency.LIGHTING, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.SPACE, SystemDependency.DAY_NIGHT),
        world_state_keys=("room_lighting",), description="Light sources and room illumination.",
    ),
    SystemDependency.COOKING: SystemSpec(
        SystemDependency.COOKING, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.TIME, SystemDependency.TEMPERATURE),
        world_state_keys=("cooking",), description="Heat sources, cookware, and food state.",
    ),
    SystemDependency.TOOL_USE: SystemSpec(
        SystemDependency.TOOL_USE, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        world_state_keys=("tool_effects",), description="Tool-to-target state transitions.",
    ),
    SystemDependency.CONSUMPTION: SystemSpec(
        SystemDependency.CONSUMPTION, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        world_state_keys=("resources",), description="Uses and depletion of consumables.",
    ),
    SystemDependency.MEDIA: SystemSpec(
        SystemDependency.MEDIA, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        world_state_keys=("audio",), description="Playback and sound effects.",
    ),
    SystemDependency.ALARM: SystemSpec(
        SystemDependency.ALARM, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        depends_on=(SystemDependency.TIME,),
        world_state_keys=("alarms",), description="Scheduled alarms and notifications.",
    ),
    SystemDependency.PAYMENT: SystemSpec(
        SystemDependency.PAYMENT, SystemLayer.DOMAIN_EFFECTS, SystemStatus.PLANNED,
        world_state_keys=("transactions",), description="Payment interactions.",
    ),
}


def system_spec(system: SystemDependency | str) -> SystemSpec:
    return SYSTEM_REGISTRY[SystemDependency(system)]


@dataclass(frozen=True)
class PlacementSpec:
    """Generation constraints, separate from object runtime semantics."""

    mode: str = "room"
    allowed_rooms: tuple[str, ...] = ()
    allowed_parents: tuple[str, ...] = ()
    preferred_parents: tuple[str, ...] = ()
    capacity: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allowed_rooms": list(self.allowed_rooms),
            "allowed_parents": list(self.allowed_parents),
            "preferred_parents": list(self.preferred_parents),
            "capacity": self.capacity,
        }


@dataclass(frozen=True)
class ObjectFamilySpec:
    family: ObjectFamily
    required_systems: tuple[SystemDependency, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "required_systems": [item.value for item in self.required_systems],
        }


def infer_family(semantic_type: str, node_type: Any, capability_names: set[str]) -> ObjectFamily:
    key = str(semantic_type).lower()
    if key in {"door", "button", "knob"}:
        return ObjectFamily.STRUCTURAL if key == "door" else ObjectFamily.APPLIANCE
    if key in {"air_conditioner", "fan", "refrigerator", "medicine_fridge", "microwave", "stove", "washer", "washing_machine", "dishwasher", "machine", "printer", "dispenser", "water_dispenser", "hand_sanitizer_dispenser", "faucet", "shower"}:
        return ObjectFamily.APPLIANCE
    if key in {"room_light"}:
        return ObjectFamily.LIGHTING
    if key in {"fruit", "vegetable", "drink", "juice", "milk", "refrigerated_medicine"}:
        return ObjectFamily.FOOD
    if key in {"doctor_coat", "nurse_uniform", "clothes", "shoes", "toothbrush", "toothpaste"}:
        return ObjectFamily.PERSONAL_ITEM
    if key in {"medical_cart", "medical_form", "medicine_box", "prescription_sheet", "syringe", "wheelchair"}:
        return ObjectFamily.MEDICAL_SUPPLY
    if key in {"computer", "display", "stationery", "receipt", "locker"}:
        return ObjectFamily.OFFICE_SUPPLY
    if "pickable" in capability_names:
        return ObjectFamily.CONTAINER if "place_target" in capability_names else ObjectFamily.PERSONAL_ITEM
    if key in {"book", "remote", "box", "plant"}:
        return ObjectFamily.FURNITURE_ACCESSORY
    if key in {"rack", "shoe_rack", "seat", "chair", "table", "coffee_table", "counter", "desk", "drawer", "sofa", "bed", "wardrobe", "cabinet", "sink", "toilet", "shelf", "signboard", "drying_rack", "rack"}:
        return ObjectFamily.FURNITURE
    return ObjectFamily.GENERIC
