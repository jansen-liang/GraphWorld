from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RoomTypeSpec:
    room_type: str
    display_name: str
    display_name_cn: str
    function_role: str = "generic"
    area_range: Tuple[float, float] = (8.0, 18.0)
    aspect_ratio_range: Tuple[float, float] = (0.7, 1.8)
    requires_exterior_wall: bool = False
    can_be_central_hub: bool = False
    privacy_level: int = 1
    allowed_neighbors: List[str] = field(default_factory=list)
    required_neighbors: List[str] = field(default_factory=list)
    forbidden_neighbors: List[str] = field(default_factory=list)
    default_fixture_templates: List[str] = field(default_factory=list)
    default_movable_templates: List[str] = field(default_factory=list)
    default_human_activities: List[str] = field(default_factory=list)
    door_count_range: Tuple[int, int] = (1, 1)
    min_wall_length: float = 2.4
    allow_direct_outside: bool = False

    @property
    def default_fixtures(self) -> List[str]:
        return list(self.default_fixture_templates)

    @property
    def default_movable_objects(self) -> List[str]:
        return list(self.default_movable_templates)

    @property
    def activity_tags(self) -> List[str]:
        return list(self.default_human_activities)


@dataclass(frozen=True)
class FloorplanTemplate:
    template_id: str
    display_name: str
    room_sequence: List[str]
    required_adjacency: List[Tuple[str, str]] = field(default_factory=list)
    optional_adjacency: List[Tuple[str, str]] = field(default_factory=list)
    anchor_room: Optional[str] = None
    placement_hints: Dict[str, str] = field(default_factory=dict)

    @property
    def room_types(self) -> List[str]:
        return list(self.room_sequence)

    @property
    def room_order_hint(self) -> List[str]:
        return list(self.room_sequence)

    @property
    def required_edges(self) -> List[Tuple[str, str]]:
        return list(self.required_adjacency)

    @property
    def optional_edges(self) -> List[Tuple[str, str]]:
        return list(self.optional_adjacency)

    @property
    def hub_room(self) -> Optional[str]:
        return self.anchor_room

    @property
    def room_positions_hint(self) -> Dict[str, str]:
        return dict(self.placement_hints)


ROOM_LIBRARY: Dict[str, RoomTypeSpec] = {
    "entrance": RoomTypeSpec(
        room_type="entrance",
        display_name="Entrance",
        display_name_cn="玄关",
        function_role="entry_buffer",
        area_range=(4.0, 8.0),
        aspect_ratio_range=(0.8, 1.8),
        requires_exterior_wall=True,
        privacy_level=1,
        allowed_neighbors=["living_room"],
        required_neighbors=["living_room"],
        forbidden_neighbors=["bedroom", "bathroom", "kitchen"],
        default_fixture_templates=["door", "button", "room_light", "rack", "seat"],
        default_movable_templates=["shoes", "shoes", "shoes"],
        default_human_activities=["entry", "exit", "shoe_change"],
        door_count_range=(1, 2),
        min_wall_length=2.2,
        allow_direct_outside=True,
    ),
    "living_room": RoomTypeSpec(
        room_type="living_room",
        display_name="Living Room",
        display_name_cn="客厅",
        function_role="public_hub",
        area_range=(16.0, 28.0),
        aspect_ratio_range=(0.8, 2.0),
        requires_exterior_wall=True,
        can_be_central_hub=True,
        privacy_level=1,
        allowed_neighbors=["entrance", "bedroom", "bathroom", "kitchen", "balcony"],
        required_neighbors=["entrance"],
        default_fixture_templates=["door", "button", "room_light", "air_conditioner", "seat", "table", "television"],
        default_movable_templates=["remote", "book", "mug", "plant"],
        default_human_activities=["rest", "social", "watching_tv"],
        door_count_range=(2, 5),
        min_wall_length=3.0,
    ),
    "bedroom": RoomTypeSpec(
        room_type="bedroom",
        display_name="Bedroom",
        display_name_cn="卧室",
        function_role="private_rest",
        area_range=(10.0, 18.0),
        aspect_ratio_range=(0.8, 1.8),
        requires_exterior_wall=True,
        privacy_level=3,
        allowed_neighbors=["living_room", "bathroom", "balcony"],
        required_neighbors=["living_room"],
        forbidden_neighbors=["entrance", "kitchen"],
        default_fixture_templates=["door", "button", "room_light", "air_conditioner", "bed", "wardrobe"],
        default_movable_templates=["book", "clothes"],
        default_human_activities=["sleep", "rest", "dressing"],
        door_count_range=(1, 2),
        min_wall_length=2.8,
    ),
    "bathroom": RoomTypeSpec(
        room_type="bathroom",
        display_name="Bathroom",
        display_name_cn="浴室",
        function_role="sanitary_room",
        area_range=(5.0, 9.0),
        aspect_ratio_range=(0.7, 1.6),
        privacy_level=3,
        allowed_neighbors=["living_room", "bedroom"],
        forbidden_neighbors=["entrance", "kitchen", "balcony"],
        default_fixture_templates=["door", "button", "room_light", "sink", "toilet", "shower"],
        default_human_activities=["washing", "toilet"],
        door_count_range=(1, 1),
        min_wall_length=2.2,
    ),
    "kitchen": RoomTypeSpec(
        room_type="kitchen",
        display_name="Kitchen",
        display_name_cn="厨房",
        function_role="food_prep",
        area_range=(8.0, 14.0),
        aspect_ratio_range=(0.8, 1.8),
        requires_exterior_wall=True,
        privacy_level=2,
        allowed_neighbors=["living_room", "balcony"],
        required_neighbors=["living_room"],
        forbidden_neighbors=["entrance", "bedroom", "bathroom"],
        default_fixture_templates=["door", "button", "room_light", "sink", "refrigerator", "microwave", "stove", "table"],
        default_movable_templates=["mug", "plate"],
        default_human_activities=["cooking", "cleaning", "eating"],
        door_count_range=(1, 2),
        min_wall_length=2.8,
    ),
    "balcony": RoomTypeSpec(
        room_type="balcony",
        display_name="Balcony",
        display_name_cn="阳台",
        function_role="semi_outdoor_buffer",
        area_range=(5.0, 10.0),
        aspect_ratio_range=(1.0, 3.0),
        requires_exterior_wall=True,
        privacy_level=1,
        allowed_neighbors=["living_room", "kitchen", "bedroom"],
        forbidden_neighbors=["entrance", "bathroom"],
        default_fixture_templates=["door", "button", "room_light", "washing_machine"],
        default_movable_templates=["clothes", "plant"],
        default_human_activities=["laundry", "ventilation"],
        door_count_range=(1, 1),
        min_wall_length=2.4,
        allow_direct_outside=True,
    ),
}

HOME_ROOM_TYPE_REGISTRY = ROOM_LIBRARY

# Room types are scoped by scene domain. The home registry above remains the
# default compatibility set; domain registries drive procedural generation.
SCENE_DOMAIN_ROOM_TYPES: Dict[str, Tuple[str, ...]] = {
    "home": tuple(ROOM_LIBRARY),
    "office": ("open_office", "meeting_room", "manager_office", "pantry", "restroom", "corridor_main"),
    "hospital": ("lobby", "registration", "waiting_area", "outpatient_clinic", "treatment_room", "pharmacy", "staff_room", "corridor_main"),
    "supermarket": ("produce_area", "shelf_area", "checkout_area", "cold_storage", "warehouse", "corridor_main"),
    "factory": ("assembly_line", "workshop", "warehouse", "control_room", "break_room", "receiving_dock"),
}

SCENE_DOMAINS = tuple(SCENE_DOMAIN_ROOM_TYPES)


def room_types_for_scene(scene_domain: str) -> Tuple[str, ...]:
    """Return the canonical room vocabulary for a scene domain."""
    key = str(scene_domain or "").strip().lower()
    if key not in SCENE_DOMAIN_ROOM_TYPES:
        raise KeyError(f"Unknown scene domain: {scene_domain}")
    return SCENE_DOMAIN_ROOM_TYPES[key]

FLOORPLAN_LIBRARY: Dict[str, FloorplanTemplate] = {
    "hub_home": FloorplanTemplate(
        template_id="hub_home",
        display_name="Hub Home",
        room_sequence=["entrance", "living_room", "bedroom", "bathroom", "kitchen", "balcony"],
        required_adjacency=[
            ("entrance", "living_room"),
            ("living_room", "bedroom"),
            ("living_room", "bathroom"),
            ("living_room", "kitchen"),
            ("living_room", "balcony"),
        ],
        optional_adjacency=[("bedroom", "bathroom"), ("kitchen", "balcony")],
        anchor_room="living_room",
        placement_hints={
            "entrance": "west",
            "bedroom": "north",
            "bathroom": "east",
            "kitchen": "south",
            "balcony": "south_east",
        },
    )
}

HOME_FLOORPLAN_TEMPLATES = FLOORPLAN_LIBRARY


def get_room_spec(room_type: str) -> RoomTypeSpec:
    if room_type not in ROOM_LIBRARY:
        raise KeyError(f"Unknown room type: {room_type}")
    return ROOM_LIBRARY[room_type]


def get_room_type_spec(room_type: str) -> RoomTypeSpec | None:
    return ROOM_LIBRARY.get(room_type)


def get_room_type_registry() -> Dict[str, RoomTypeSpec]:
    return ROOM_LIBRARY


def list_room_types() -> List[str]:
    return list(ROOM_LIBRARY.keys())


def get_floorplan_template(template_id: str) -> FloorplanTemplate:
    if template_id not in FLOORPLAN_LIBRARY:
        raise KeyError(f"Unknown floorplan template: {template_id}")
    return FLOORPLAN_LIBRARY[template_id]


def get_home_floorplan_template(template_id: str) -> FloorplanTemplate | None:
    return FLOORPLAN_LIBRARY.get(template_id)


def get_floorplan_template_registry() -> Dict[str, FloorplanTemplate]:
    return FLOORPLAN_LIBRARY


def list_floorplan_templates() -> List[str]:
    return list(FLOORPLAN_LIBRARY.keys())


def list_home_floorplan_templates() -> List[str]:
    return list_floorplan_templates()
