from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field, replace
from typing import Dict, List

from backend.core.state import DISCRETE_STATE_SPACE


HOME_NPC_LIBRARY: List[Dict[str, str]] = [
    {
        "id": "human_resident",
        "name": "white_collar_worker",
        "name_cn": "普通白领",
        "role": "resident",
        "parent": "bed_bedroom",
        "room": "bedroom",
        "activity": "sleeping",
        "persona": "weekday_office_worker",
    }
]


HOSPITAL_NPC_LIBRARY: List[Dict[str, str]] = [
    {
        "id": "patient_1",
        "name": "patient",
        "name_cn": "病人",
        "role": "patient",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "away",
        "persona": "hospital_patient",
    },
    {
        "id": "nurse_1",
        "name": "nurse",
        "name_cn": "护士",
        "role": "nurse",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "off_shift",
        "persona": "hospital_nurse",
    },
    {
        "id": "doctor_1",
        "name": "doctor",
        "name_cn": "医生",
        "role": "doctor",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "off_shift",
        "persona": "hospital_doctor",
    },
]


SUPERMARKET_NPC_LIBRARY: List[Dict[str, str]] = [
    {
        "id": "customer_1",
        "name": "customer",
        "name_cn": "顾客",
        "role": "customer",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "store_away",
        "persona": "supermarket_customer",
    },
    {
        "id": "cashier_1",
        "name": "cashier",
        "name_cn": "收银员",
        "role": "cashier",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "store_off_shift",
        "persona": "supermarket_cashier",
    },
    {
        "id": "stocker_1",
        "name": "stocker",
        "name_cn": "理货员",
        "role": "stocker",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "store_off_shift",
        "persona": "supermarket_stocker",
    },
]


OFFICE_NPC_LIBRARY: List[Dict[str, str]] = [
    {
        "id": "office_worker_1",
        "name": "office_worker",
        "name_cn": "办公室员工",
        "role": "office_worker",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "office_away",
        "persona": "office_worker",
    },
    {
        "id": "manager_1",
        "name": "manager",
        "name_cn": "经理",
        "role": "manager",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "office_off_shift",
        "persona": "office_manager",
    },
    {
        "id": "visitor_1",
        "name": "visitor",
        "name_cn": "访客",
        "role": "visitor",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "office_away",
        "persona": "office_visitor",
    },
]


FACTORY_NPC_LIBRARY: List[Dict[str, str]] = [
    {
        "id": "worker_1",
        "name": "factory_worker",
        "name_cn": "工人",
        "role": "factory_worker",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "factory_off_shift",
        "persona": "factory_worker",
    },
    {
        "id": "quality_inspector_1",
        "name": "quality_inspector",
        "name_cn": "质检员",
        "role": "quality_inspector",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "factory_off_shift",
        "persona": "quality_inspector",
    },
    {
        "id": "maintenance_1",
        "name": "maintenance_worker",
        "name_cn": "维修员",
        "role": "maintenance_worker",
        "parent": "outside_home",
        "room": "outside_home",
        "activity": "factory_off_shift",
        "persona": "maintenance_worker",
    },
]


@dataclass(frozen=True)
class ScheduleEntry:
    start_min: int
    end_min: int
    target_parent: str
    target_room: str
    activity: str


@dataclass(frozen=True)
class EventPrecondition:
    kind: str
    precondition_id: str = ""
    target: str = ""
    semantic_type: str = ""
    semantic_types: tuple[str, ...] = ()
    state: str = ""
    value: object = True
    states: dict[str, object] = field(default_factory=dict)
    match_states: dict[str, object] = field(default_factory=dict)
    relation: str = ""
    relation_not: str = ""
    parent: str = ""
    room: str = ""
    description: str = ""
    recoverable: bool = False

    def __post_init__(self) -> None:
        _validate_event_state_keys(
            self.event_label,
            states=self.states,
            match_states=self.match_states,
            state=self.state,
        )

    @property
    def event_label(self) -> str:
        return f"EventPrecondition({self.kind}:{self.target or self.semantic_type})"


@dataclass(frozen=True)
class EventEffect:
    kind: str
    timing: str = "every_step"
    target: str = ""
    semantic_type: str = ""
    state: str = ""
    value: object = True
    states: dict[str, object] = field(default_factory=dict)
    match_states: dict[str, object] = field(default_factory=dict)
    match_parent: str = ""
    parent: str = ""
    parent_options: tuple[str, ...] = ()
    parent_index_offset: int = 0
    parent_index_mode: str = "step"
    relation: str = ""
    relation_options: tuple[str, ...] = ()
    relation_not: str = ""
    room: str = ""
    states_by_parent: dict[str, dict[str, object]] = field(default_factory=dict)
    transient_states_by_index: dict[int, dict[str, object | None]] = field(default_factory=dict)
    amount: float = 0.0
    min_value: float | None = None
    max_value: float | None = None
    threshold_state: str = ""
    threshold_op: str = ""
    threshold_value: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        _validate_event_state_keys(
            self.event_label,
            states=self.states,
            match_states=self.match_states,
            state=self.state,
            threshold_state=self.threshold_state,
            states_by_parent=self.states_by_parent,
            transient_states_by_index=self.transient_states_by_index,
        )

    @property
    def event_label(self) -> str:
        return f"EventEffect({self.kind}:{self.target or self.semantic_type})"


def _validate_event_state_keys(
    label: str,
    *,
    states: dict[str, object] | None = None,
    match_states: dict[str, object] | None = None,
    state: str = "",
    threshold_state: str = "",
    states_by_parent: dict[str, dict[str, object]] | None = None,
    transient_states_by_index: dict[int, dict[str, object | None]] | None = None,
) -> None:
    allowed = set(DISCRETE_STATE_SPACE)
    keys = set(states or {}) | set(match_states or {})
    if state:
        keys.add(str(state))
    if threshold_state:
        keys.add(str(threshold_state))
    for nested in (states_by_parent or {}).values():
        keys.update(nested)
    for nested in (transient_states_by_index or {}).values():
        keys.update(nested)
    invalid = sorted(keys - allowed)
    if invalid:
        raise ValueError(f"{label} uses states outside DISCRETE_STATE_SPACE: {invalid}")


@dataclass(frozen=True)
class EventSpec:
    event_id: str
    duration: int = 1
    value_drivers: tuple[str, ...] = ()
    activity_pattern: str = ""
    description: str = ""
    preconditions: tuple[EventPrecondition, ...] = field(default_factory=tuple)
    effects_on_success: tuple[EventEffect, ...] = field(default_factory=tuple)
    effects_on_failure: tuple[EventEffect, ...] = field(default_factory=tuple)


VALUE_BODILY_NEED = "bodily_need"
VALUE_HEALTH_SAFETY = "health_safety"
VALUE_ROLE_DUTY = "role_duty"
VALUE_SOCIAL_COORDINATION = "social_coordination"
VALUE_CREATIVE_IMPROVEMENT = "creative_improvement"


PATTERN_PRESENCE = "presence"
PATTERN_EQUIP_ROLE_ITEM = "equip_role_item"
PATTERN_RETRIEVE_USE_DISPLACE = "retrieve_use_displace"
PATTERN_CONSUME_RESOURCE = "consume_resource"
PATTERN_SERVICE_FLOW = "service_flow"
PATTERN_CLEAN_OR_DIRTY_SURFACE = "clean_or_dirty_surface"
PATTERN_REPLENISH_RESOURCE = "replenish_resource"


def make_event(
    event_id: str,
    *,
    duration: int = 1,
    values: tuple[str, ...] = (),
    pattern: str = "",
    description: str = "",
    preconditions: tuple[EventPrecondition, ...] = (),
    effects: tuple[EventEffect, ...] = (),
    failure_effects: tuple[EventEffect, ...] = (),
) -> EventSpec:
    return EventSpec(
        event_id=event_id,
        duration=duration,
        value_drivers=values,
        activity_pattern=pattern,
        description=description,
        preconditions=preconditions,
        effects_on_success=effects,
        effects_on_failure=failure_effects,
    )


def be_at_event(
    event_id: str,
    parent: str,
    *,
    relation: str = "at",
    values: tuple[str, ...] = (),
    pattern: str = PATTERN_PRESENCE,
    description: str = "",
) -> EventSpec:
    return make_event(
        event_id,
        values=values,
        pattern=pattern,
        description=description,
        effects=(EventEffect("move_actor", parent=parent, relation=relation),),
    )


def require_node(**kwargs: object) -> EventPrecondition:
    return EventPrecondition("has_node", **kwargs)


def require_semantics(*semantic_types: str, **kwargs: object) -> EventPrecondition:
    return EventPrecondition("has_semantics", semantic_types=tuple(semantic_types), **kwargs)


def move_actor(parent: str, *, relation: str = "near") -> EventEffect:
    return EventEffect("move_actor", parent=parent, relation=relation)


def set_states(target: str, **states: object) -> EventEffect:
    return EventEffect("set_state", target=target, states=states)


def move_item(
    target: str = "",
    *,
    semantic_type: str = "",
    parent: str = "",
    relation: str = "in",
    timing: str = "period_start",
    match_parent: str = "",
    states: dict[str, object] | None = None,
    room: str = "",
    match_states: dict[str, object] | None = None,
    relation_not: str = "",
) -> EventEffect:
    return EventEffect(
        "move_matching_node",
        timing=timing,
        target=target,
        semantic_type=semantic_type,
        parent=parent,
        relation=relation,
        match_parent=match_parent,
        states=states or {},
        room=room,
        match_states=match_states or {},
        relation_not=relation_not,
    )


def change_level(
    target: str,
    state: str,
    amount: float,
    *,
    timing: str = "period_start",
    min_value: float | None = None,
    max_value: float | None = None,
    threshold_state: str = "",
    threshold_op: str = "",
    threshold_value: float = 0.0,
) -> EventEffect:
    return EventEffect(
        "increment_state",
        timing=timing,
        target=target,
        state=state,
        amount=amount,
        min_value=min_value,
        max_value=max_value,
        threshold_state=threshold_state,
        threshold_op=threshold_op,
        threshold_value=threshold_value,
    )


NPC_EVENT_LIBRARY: dict[str, EventSpec] = {
    "sleeping": EventSpec(
        event_id="sleeping",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="bed_bedroom", relation="at"),
            EventEffect("set_state", target="bed_bedroom", states={"is_dirty": True}),
            EventEffect("set_state", target="light_bedroom", states={"is_on": False}),
        ),
    ),
    "waking_up": EventSpec(
        event_id="waking_up",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="bed_bedroom", relation="at"),
            EventEffect("set_state", target="light_bedroom", states={"is_on": True}),
            EventEffect("set_state", target="button_bedroom", states={"is_pressed": True, "is_on": True}),
        ),
    ),
    "getting_dressed": EventSpec(
        event_id="getting_dressed",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="home_clean_clothes_available",
                semantic_type="clothes",
                room="bedroom",
                states={"is_dirty": False, "is_wet": False, "folded": True},
                relation_not="worn_by",
                description="No clean clothes available.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="wardrobe_bedroom", relation="near"),
            EventEffect("set_state", target="wardrobe_bedroom", states={"is_open": True}),
            EventEffect("set_state", target="wardrobe_bedroom_door", states={"is_open": True}),
            EventEffect(
                "move_matching_node",
                timing="period_start",
                semantic_type="clothes",
                room="bedroom",
                match_states={"is_dirty": False, "is_wet": False, "folded": True},
                relation_not="worn_by",
                parent="human",
                relation="worn_by",
            ),
        ),
    ),
    "washing_up_morning": EventSpec(
        event_id="washing_up_morning",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_semantics",
                precondition_id="home_bathroom_supplies_ready_morning",
                semantic_types=("toothbrush", "toothpaste", "cup"),
                room="bathroom",
                description="Bathroom supplies are unavailable.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="sink_bathroom", relation="near"),
            EventEffect("set_state", target="light_bathroom", states={"is_on": True}),
            EventEffect("set_state", target="button_bathroom", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="faucet_bathroom", states={"is_on": True}),
            EventEffect(
                "move_matching_node",
                target="toothbrush_bathroom",
                parent_options=("sink_bathroom", "faucet_bathroom", "sink_bathroom", "toilet_bathroom"),
                parent_index_offset=1,
                relation="on",
            ),
            EventEffect(
                "move_matching_node",
                target="cup_bathroom",
                parent_options=("sink_bathroom", "faucet_bathroom", "sink_bathroom"),
                parent_index_offset=3,
                relation="on",
            ),
            EventEffect("set_state", target="sink_bathroom", states={"is_full": True, "fill_level": 1.0}),
            EventEffect("set_state", target="cup_bathroom", states={"is_dirty": True, "is_wet": True, "fill_level": 0.3}),
            EventEffect("set_state", timing="period_start", target="toilet_bathroom", states={"is_dirty": True}),
            EventEffect("set_state", target="human", state="is_dirty", value=False),
        ),
    ),
    "washing_up_night": EventSpec(
        event_id="washing_up_night",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_semantics",
                precondition_id="home_bathroom_supplies_ready_night",
                semantic_types=("toothbrush", "toothpaste", "cup"),
                room="bathroom",
                description="Bathroom supplies are unavailable.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="sink_bathroom", relation="near"),
            EventEffect("set_state", target="light_bathroom", states={"is_on": True}),
            EventEffect("set_state", target="button_bathroom", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="faucet_bathroom", states={"is_on": True}),
            EventEffect(
                "move_matching_node",
                target="toothbrush_bathroom",
                parent_options=("sink_bathroom", "faucet_bathroom", "sink_bathroom", "toilet_bathroom"),
                parent_index_offset=1,
                relation="on",
            ),
            EventEffect(
                "move_matching_node",
                target="cup_bathroom",
                parent_options=("sink_bathroom", "faucet_bathroom", "sink_bathroom"),
                parent_index_offset=3,
                relation="on",
            ),
            EventEffect("set_state", target="sink_bathroom", states={"is_full": True, "fill_level": 1.0}),
            EventEffect("set_state", target="cup_bathroom", states={"is_dirty": True, "is_wet": True, "fill_level": 0.4}),
            EventEffect("set_state", timing="period_start", target="toilet_bathroom", states={"is_dirty": True}),
            EventEffect("move_worn_node", timing="period_start", semantic_type="clothes", parent="bathroom", relation="in", states={"is_dirty": True, "folded": False}),
        ),
    ),
    "breakfast": EventSpec(
        event_id="breakfast",
        duration=1,
        preconditions=(
            EventPrecondition("has_node", semantic_type="food", description="No food available."),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="coffee_table_living_room", relation="near"),
            EventEffect("set_state", target="light_kitchen", states={"is_on": True}),
            EventEffect("set_state", target="button_kitchen", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="fridge_kitchen", states={"is_open": True}),
            EventEffect("set_state", target="door_fridge_kitchen", states={"is_open": True}),
            EventEffect("set_state", target="microwave_kitchen", states={"is_on": True, "is_open": True, "cycle_remaining": 1}),
            EventEffect("set_state", target="microwave_kitchen_button", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="counter_kitchen", states={"is_dirty": True}),
            EventEffect("set_state", target="milk_fridge_kitchen", states={"temperature": "room", "is_rotten": True}),
            EventEffect("set_state", target="juice_fridge_kitchen", states={"temperature": "room", "is_rotten": True}),
            EventEffect("set_state", target="vegetables_fridge_kitchen", states={"temperature": "room", "is_rotten": True}),
            EventEffect("set_state", target="stove_kitchen", states={"is_on": True, "is_dirty": True}),
            EventEffect("set_state", target="sink_kitchen", states={"is_dirty": True, "fill_level": 0.4}),
            EventEffect("move_matching_node", timing="period_start", target="bowls_dishwasher_kitchen", parent="coffee_table_living_room", relation="on", states={"is_dirty": True}),
            EventEffect("move_matching_node", timing="period_start", target="food_living_room", parent="coffee_table_living_room", relation="on", states={"is_rotten": True}),
            EventEffect("move_matching_node", timing="period_start", target="plate_living_room", parent="coffee_table_living_room", relation="on", states={"is_dirty": True}),
            EventEffect("move_matching_node", timing="period_start", target="cup_living_room", parent="coffee_table_living_room", relation="on", states={"is_dirty": True}),
        ),
    ),
    "leaving_home": EventSpec(
        event_id="leaving_home",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="home_shoes_ready_at_entrance",
                semantic_type="shoes",
                room="entrance",
                states={"is_dirty": False, "is_wet": False},
                relation_not="worn_by",
                description="No shoes available to leave home.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_matching_node", timing="period_start", semantic_type="shoes", room="entrance", match_states={"is_dirty": False, "is_wet": False}, relation_not="worn_by", parent="human", relation="worn_by"),
            EventEffect("set_state", target="door_entrance", states={"is_open": True}),
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "eating": EventSpec(
        event_id="eating",
        duration=1,
        preconditions=(
            EventPrecondition("has_node", semantic_type="food", description="No food available."),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="coffee_table_living_room", relation="near"),
            EventEffect("set_state", target="light_living_room", states={"is_on": True}),
            EventEffect("set_state", target="button_living_room", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="tv_living_room", states={"is_on": True}),
            EventEffect("set_state", target="dishwasher_kitchen", states={"is_open": True, "is_dirty": True}),
            EventEffect("set_state", target="dishwasher_kitchen_door", states={"is_open": True}),
            EventEffect("set_state", target="sink_kitchen", states={"is_dirty": True, "fill_level": 0.6}),
            EventEffect("increment_state", timing="period_start", target="trash_bin_living_room", state="fill_level", amount=0.35, max_value=1.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.75),
            EventEffect("set_state", target="coffee_table_living_room", states={"is_dirty": True}),
            EventEffect("set_state", target="sofa_living_room", states={"is_dirty": True}),
            EventEffect("set_state", target="dishwasher_kitchen_button", states={"is_pressed": True, "is_on": True}),
            EventEffect("move_matching_node", timing="period_start", target="bowls_dishwasher_kitchen", parent="coffee_table_living_room", relation="on", states={"is_dirty": True}),
            EventEffect("move_matching_node", timing="period_start", target="food_living_room", parent="coffee_table_living_room", relation="on", states={"is_rotten": True}),
            EventEffect("move_matching_node", timing="period_start", target="plate_living_room", parent="coffee_table_living_room", relation="on", states={"is_dirty": True}),
            EventEffect("move_matching_node", timing="period_start", target="cup_living_room", parent="coffee_table_living_room", relation="on", states={"is_dirty": True}),
        ),
    ),
    "returning_home": EventSpec(
        event_id="returning_home",
        duration=1,
        effects_on_success=(
            EventEffect("set_state", target="door_entrance", states={"is_open": True}),
            EventEffect("set_state", target="light_entrance", states={"is_on": True}),
            EventEffect("set_state", target="button_entrance", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="bench_entrance", states={"is_dirty": True}),
            EventEffect("set_state", target="shoe_rack_entrance", states={"is_dirty": True}),
            EventEffect("move_actor", parent="shoe_rack_entrance", relation="near"),
            EventEffect(
                "move_worn_node",
                timing="period_start",
                semantic_type="shoes",
                parent_options=("shoe_rack_entrance", "living_room"),
                parent_index_mode="day",
                relation_options=("on", "in"),
                states={"is_dirty": True},
                states_by_parent={
                    "shoe_rack_entrance": {},
                    "living_room": {},
                },
            ),
            EventEffect("move_actor", parent="sofa_living_room", relation="near"),
        ),
    ),
    "waiting_for_dinner": EventSpec(
        event_id="waiting_for_dinner",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="sofa_living_room", relation="near"),
        ),
    ),
    "resting_home": EventSpec(
        event_id="resting_home",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="sofa_living_room", relation="near"),
        ),
    ),
    "away_at_work": EventSpec(
        event_id="away_at_work",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "hospital_away": EventSpec(
        event_id="hospital_away",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "hospital_off_shift": EventSpec(
        event_id="hospital_off_shift",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "patient_register": EventSpec(
        event_id="patient_register",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="hospital_registration_form_ready",
                target="medical_form_registration",
                parent="counter_registration",
                description="No registration form available.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="counter_registration", relation="near"),
            EventEffect("set_state", target="computer_registration", states={"is_on": True}),
            EventEffect("set_state", target="door_registration", states={"is_open": True}),
            EventEffect("set_state", target="light_registration", states={"is_on": True}),
            EventEffect("set_state", target="button_registration", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="counter_registration", states={"is_dirty": True, "fill_level": 0.3}),
            EventEffect("set_state", target="printer_registration", states={"is_on": True}),
            EventEffect("move_matching_node", target="medical_form_registration", parent="counter_registration", relation="on"),
        ),
    ),
    "patient_wait": EventSpec(
        event_id="patient_wait",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="seats_waiting_area", relation="near"),
            EventEffect("set_state", target="queue_screen_waiting_area", states={"is_on": True}),
            EventEffect("set_state", target="light_waiting_area", states={"is_on": True}),
            EventEffect("set_state", target="button_waiting_area", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="door_waiting_area", states={"is_open": True}),
            EventEffect("set_state", target="bench_lobby", states={"is_dirty": True}),
            EventEffect("increment_state", timing="period_start", target="bench_lobby", state="fill_level", amount=0.2, max_value=1.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.8),
            EventEffect("set_state", timing="period_start", target="seats_waiting_area", states={"is_dirty": True}),
        ),
    ),
    "patient_consult": EventSpec(
        event_id="patient_consult",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="exam_bed_clinic_1", relation="near"),
            EventEffect("set_state", target="exam_bed_clinic_1", states={"is_dirty": True}),
            EventEffect("set_state", target="door_outpatient_clinic_1", states={"is_open": True}),
            EventEffect("set_state", target="light_outpatient_clinic_1", states={"is_on": True}),
            EventEffect("set_state", target="button_outpatient_clinic_1", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="desk_clinic_1", states={"is_dirty": True, "fill_level": 0.3}),
        ),
    ),
    "patient_take_medicine": EventSpec(
        event_id="patient_take_medicine",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="hospital_patient_has_prescription",
                semantic_type="prescription_sheet",
                parent="patient_1",
                description="Patient has no prescription.",
                recoverable=True,
            ),
            EventPrecondition(
                "has_node",
                precondition_id="hospital_pharmacy_medicine_box_ready",
                target="medicine_box_pharmacy",
                parent="pharmacy",
                description="No medicine box available at pharmacy.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="shelf_pharmacy", relation="near"),
            EventEffect("set_state", target="door_pharmacy", states={"is_open": True}),
            EventEffect("set_state", target="light_pharmacy", states={"is_on": True}),
            EventEffect("set_state", target="button_pharmacy", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="shelf_pharmacy", states={"is_dirty": True, "fill_level": 0.4}),
            EventEffect("increment_state", timing="period_start", target="shelf_pharmacy", state="fill_level", amount=-0.25, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.8),
            EventEffect("move_matching_node", target="medicine_box_pharmacy", parent="patient_1", relation="carried_by"),
        ),
    ),
    "patient_infusion": EventSpec(
        event_id="patient_infusion",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="hospital_patient_has_infusion_medicine",
                target="refrigerated_medicine_pharmacy",
                parent="patient_1",
                description="Infusion medicine was not delivered to patient.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="treatment_bed_treatment_room", relation="near"),
            EventEffect("set_state", target="treatment_bed_treatment_room", states={"is_dirty": True}),
            EventEffect("set_state", target="door_treatment_room", states={"is_open": True}),
            EventEffect("set_state", target="light_treatment_room", states={"is_on": True}),
            EventEffect("set_state", target="button_treatment_room", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="trash_bin_corridor_main", states={"fill_level": 0.3}),
            EventEffect("move_matching_node", target="used_syringe_treatment_room", parent="treatment_bed_treatment_room", relation="on", states={"is_dirty": True}),
            EventEffect("increment_state", timing="period_start", target="medical_waste_bin_treatment_room", state="fill_level", amount=0.35, max_value=1.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.75),
        ),
    ),
    "patient_leave": EventSpec(
        event_id="patient_leave",
        duration=1,
        effects_on_success=(
            EventEffect("move_matching_node", target="prescription_sheet_clinic_1", match_parent="patient_1", parent="prescription_return_lobby", relation="on"),
            EventEffect("move_matching_node", target="medicine_box_pharmacy", match_parent="patient_1", parent="supply_zone_lobby", relation="on"),
            EventEffect("move_matching_node", target="refrigerated_medicine_pharmacy", match_parent="patient_1", parent="supply_zone_lobby", relation="on", states={"temperature": "cold"}),
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "doctor_prepare": EventSpec(
        event_id="doctor_prepare",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="locker_staff_room", relation="near"),
            EventEffect("move_matching_node", target="doctor_coat_staff_room", parent="doctor_1", relation="worn_by"),
        ),
    ),
    "doctor_call_patient": EventSpec(
        event_id="doctor_call_patient",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="desk_clinic_1", relation="near"),
            EventEffect("set_state", target="queue_screen_waiting_area", states={"is_on": True}),
            EventEffect("set_state", target="computer_clinic_1", states={"is_on": True}),
            EventEffect("set_state", target="desk_clinic_1", states={"is_dirty": True, "fill_level": 0.2}),
        ),
    ),
    "doctor_examine_patient": EventSpec(
        event_id="doctor_examine_patient",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="exam_bed_clinic_1", relation="near"),
            EventEffect("set_state", target="computer_clinic_1", states={"is_on": True}),
            EventEffect("set_state", target="exam_bed_clinic_1", states={"is_dirty": True}),
            EventEffect("set_state", target="desk_clinic_1", states={"is_dirty": True, "fill_level": 0.4}),
        ),
    ),
    "doctor_prescribe": EventSpec(
        event_id="doctor_prescribe",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="hospital_blank_prescription_ready",
                target="prescription_sheet_clinic_1",
                parent="outpatient_clinic_1",
                description="No blank prescription sheet available.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="desk_clinic_1", relation="near"),
            EventEffect("set_state", target="printer_registration", states={"is_on": True}),
            EventEffect("set_state", target="computer_clinic_1", states={"is_on": True}),
            EventEffect("move_matching_node", target="prescription_sheet_clinic_1", parent="patient_1", relation="has"),
        ),
    ),
    "nurse_prepare": EventSpec(
        event_id="nurse_prepare",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="locker_staff_room", relation="near"),
            EventEffect("set_state", target="locker_staff_room", states={"is_open": True}),
            EventEffect("set_state", target="light_staff_room", states={"is_on": True}),
            EventEffect("set_state", target="button_staff_room", states={"is_pressed": True, "is_on": True}),
            EventEffect("set_state", target="door_staff_room", states={"is_open": True}),
            EventEffect("move_matching_node", target="nurse_uniform_staff_room", parent="nurse_1", relation="worn_by"),
        ),
    ),
    "nurse_round": EventSpec(
        event_id="nurse_round",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="treatment_bed_treatment_room", relation="near"),
        ),
    ),
    "nurse_deliver_medicine": EventSpec(
        event_id="nurse_deliver_medicine",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="hospital_refrigerated_medicine_ready",
                target="refrigerated_medicine_pharmacy",
                parent="medicine_fridge_pharmacy",
                description="No refrigerated medicine available.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="medical_cart_treatment_room", relation="near"),
            EventEffect("set_state", target="medicine_fridge_pharmacy", states={"is_open": True, "temperature": "cold"}),
            EventEffect("set_state", target="refrigerated_medicine_pharmacy", states={"temperature": "room"}),
            EventEffect("increment_state", timing="period_start", target="medicine_fridge_pharmacy", state="fill_level", amount=-0.25, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.8),
            EventEffect("set_state", target="medical_cart_treatment_room", states={"fill_level": 0.6, "is_full": False}),
            EventEffect("move_matching_node", target="refrigerated_medicine_pharmacy", parent="patient_1", relation="assigned_to", states={"temperature": "room"}),
        ),
    ),
    "nurse_change_bed_sheet": EventSpec(
        event_id="nurse_change_bed_sheet",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="hospital_clean_sheet_ready",
                target="clean_sheet_storage",
                parent="supply_cabinet_treatment_room",
                description="No clean bed sheet available.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="treatment_bed_treatment_room", relation="near"),
            EventEffect("set_state", target="supply_cabinet_treatment_room", states={"is_open": True}),
            EventEffect("move_matching_node", target="clean_sheet_storage", parent="treatment_bed_treatment_room", relation="on", states={"is_dirty": False, "folded": False}),
            EventEffect("move_matching_node", target="dirty_sheet_treatment_room", parent="dirty_linen_bin_treatment_room", relation="in", states={"is_dirty": True}),
            EventEffect("increment_state", timing="period_start", target="dirty_linen_bin_treatment_room", state="fill_level", amount=0.5, max_value=1.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.75),
            EventEffect("set_state", target="treatment_bed_treatment_room", states={"is_dirty": False}),
        ),
    ),
    "nurse_clean_bed": EventSpec(
        event_id="nurse_clean_bed",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="treatment_bed_treatment_room", relation="near"),
            EventEffect("set_state", target="treatment_bed_treatment_room", states={"is_dirty": False}),
        ),
    ),
    "nurse_restock_supplies": EventSpec(
        event_id="nurse_restock_supplies",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="medical_cart_treatment_room", relation="near"),
            EventEffect("set_state", target="supply_cabinet_treatment_room", states={"is_open": True}),
            EventEffect("set_state", target="medical_cart_treatment_room", states={"is_full": True, "fill_level": 1.0}),
        ),
    ),
    "store_away": EventSpec(
        event_id="store_away",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "store_off_shift": EventSpec(
        event_id="store_off_shift",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "customer_enter": EventSpec(
        event_id="customer_enter",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="entrance", relation="at"),
            EventEffect("set_state", target="display_checkout", states={"is_on": True}),
        ),
    ),
    "customer_take_cart": EventSpec(
        event_id="customer_take_cart",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="store_cart_ready_at_entrance",
                target="cart_entrance",
                parent="entrance",
                description="No shopping cart at entrance.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="cart_entrance", relation="near"),
            EventEffect("move_matching_node", timing="period_start", target="cart_entrance", match_parent="entrance", parent="customer_1", relation="pushed_by"),
        ),
    ),
    "customer_shop_produce": EventSpec(
        event_id="customer_shop_produce",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="store_produce_shelf_stocked",
                target="fruit_produce_1",
                parent="shelf_produce",
                description="No fruit on produce shelf.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="shelf_produce", relation="near"),
            EventEffect("move_matching_node", timing="period_start", target="fruit_produce_1", match_parent="shelf_produce", parent="customer_1", relation="in_cart"),
            EventEffect("set_state", target="fruit_produce_2", states={"is_rotten": True, "temperature": "warm"}),
            EventEffect("set_state", target="vegetable_produce_1", states={"is_rotten": True, "temperature": "warm"}),
            EventEffect("set_state", target="vegetable_produce_2", states={"is_rotten": True, "temperature": "warm"}),
            EventEffect("increment_state", timing="period_start", target="shelf_produce", state="fill_level", amount=-0.25, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.95),
            EventEffect("set_state", target="table_staff_room", states={"is_dirty": True, "fill_level": 0.2}),
        ),
    ),
    "customer_shop_cold": EventSpec(
        event_id="customer_shop_cold",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="store_cold_milk_stocked",
                target="milk_cold_storage_1",
                parent="fridge_cold_storage",
                description="No milk in cold fridge.",
                recoverable=True,
            ),
            EventPrecondition(
                "has_node",
                precondition_id="store_cold_fridge_closed",
                target="fridge_cold_storage",
                states={"is_open": False},
                description="Cold fridge was left open.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="fridge_cold_storage", relation="near"),
            EventEffect("set_state", target="fridge_cold_storage", states={"is_open": True}),
            EventEffect("move_matching_node", timing="period_start", target="milk_cold_storage_1", match_parent="fridge_cold_storage", parent="customer_1", relation="in_cart", states={"temperature": "room"}),
            EventEffect("set_state", target="juice_cold_storage_1", states={"temperature": "room", "is_rotten": True}),
            EventEffect("increment_state", timing="period_start", target="fridge_cold_storage", state="fill_level", amount=-0.35, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.95),
            EventEffect("increment_state", timing="period_start", target="box_cold_storage", state="fill_level", amount=-0.2, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.95),
        ),
    ),
    "customer_checkout": EventSpec(
        event_id="customer_checkout",
        duration=1,
        preconditions=(
            EventPrecondition("has_node", target="fruit_produce_1", parent="customer_1", description="Customer has no produce to checkout."),
            EventPrecondition("has_node", target="milk_cold_storage_1", parent="customer_1", description="Customer has no cold item to checkout."),
            EventPrecondition("has_node", target="cart_entrance", parent="customer_1", description="Customer has no cart to return."),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="counter_checkout", relation="near"),
            EventEffect("set_state", target="display_checkout", states={"is_on": True}),
            EventEffect("set_state", target="counter_checkout", states={"is_dirty": True, "fill_level": 0.5}),
            EventEffect("set_state", target="table_checkout", states={"is_dirty": True, "fill_level": 0.4}),
            EventEffect("set_state", target="seat_staff_room", states={"is_dirty": True}),
            EventEffect("set_state", target="trash_bin_checkout", states={"is_on": True}),
            EventEffect("increment_state", timing="period_start", target="trash_bin_checkout", state="fill_level", amount=0.35, max_value=1.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.75),
            EventEffect("move_matching_node", timing="period_start", target="cart_entrance", match_parent="customer_1", parent="cart_return_checkout", relation="near"),
            EventEffect("move_matching_node", timing="period_start", target="fruit_produce_1", match_parent="customer_1", parent="receiving_dock_staff_room", relation="in", states={"is_rotten": False}),
            EventEffect("move_matching_node", timing="period_start", target="milk_cold_storage_1", match_parent="customer_1", parent="receiving_dock_staff_room", relation="in", states={"is_rotten": False, "temperature": "cold"}),
        ),
    ),
    "customer_leave_store": EventSpec(
        event_id="customer_leave_store",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="outside_home", relation="at"),
        ),
    ),
    "cashier_prepare": EventSpec(
        event_id="cashier_prepare",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="store_checkout_counter_clean",
                target="counter_checkout",
                states={"is_dirty": False},
                description="Checkout counter is dirty.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="counter_checkout", relation="near"),
            EventEffect("set_state", target="display_checkout", states={"is_on": True}),
            EventEffect("set_state", target="counter_checkout", states={"is_dirty": True, "fill_level": 0.2}),
        ),
    ),
    "cashier_scan_items": EventSpec(
        event_id="cashier_scan_items",
        duration=1,
        preconditions=(
            EventPrecondition(
                "has_node",
                precondition_id="store_checkout_display_ready",
                target="display_checkout",
                states={"is_on": True},
                description="Checkout display is not ready.",
                recoverable=True,
            ),
        ),
        effects_on_success=(
            EventEffect("move_actor", parent="counter_checkout", relation="near"),
            EventEffect("set_state", target="counter_checkout", states={"is_dirty": True, "fill_level": 0.6}),
            EventEffect("increment_state", timing="period_start", target="trash_bin_checkout", state="fill_level", amount=0.2, max_value=1.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.75),
        ),
    ),
    "stocker_inspect": EventSpec(
        event_id="stocker_inspect",
        duration=1,
        effects_on_success=(
            EventEffect("move_actor", parent="shelf_dry_goods", relation="near"),
            EventEffect("set_state", target="cabinet_staff_room", states={"is_open": True}),
            EventEffect("set_state", target="cabinet_staff_room", states={"fill_level": 0.1}),
            EventEffect("increment_state", timing="period_start", target="shelf_dry_goods", state="fill_level", amount=-0.2, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.95),
            EventEffect("increment_state", timing="period_start", target="shelf_snacks", state="fill_level", amount=-0.2, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.95),
            EventEffect("increment_state", timing="period_start", target="box_shelf_stock", state="fill_level", amount=-0.25, min_value=0.0, threshold_state="is_full", threshold_op=">=", threshold_value=0.95),
            EventEffect("set_state", target="drink_shelf_1", states={"temperature": "warm", "is_rotten": True}),
            EventEffect("set_state", target="drink_shelf_2", states={"temperature": "warm", "is_rotten": True}),
        ),
    ),
    "office_away": be_at_event("office_away", "outside_home", values=(VALUE_ROLE_DUTY,), description="office actor is outside work"),
    "office_off_shift": be_at_event("office_off_shift", "outside_home", values=(VALUE_BODILY_NEED,), description="office staff are off shift"),
    "office_worker_arrive": make_event(
        "office_worker_arrive",
        values=(VALUE_ROLE_DUTY,),
        pattern=PATTERN_PRESENCE,
        description="worker arrives and starts the workday",
        effects=(
            move_actor("desk_open_office_1"),
            set_states("computer_open_office_1", is_on=True),
            set_states("desk_open_office_1", is_dirty=True, fill_level=0.4),
            set_states("seat_open_office_1", is_dirty=True),
            set_states("desk_open_office_2", is_dirty=True, fill_level=0.5),
            set_states("seat_open_office_2", is_dirty=True),
        ),
    ),
    "office_focus_work": make_event(
        "office_focus_work",
        values=(VALUE_CREATIVE_IMPROVEMENT, VALUE_ROLE_DUTY),
        pattern=PATTERN_RETRIEVE_USE_DISPLACE,
        description="worker creates documents and leaves work materials on the desk",
        preconditions=(
            require_node(
                precondition_id="office_report_template_filed",
                target="report_open_office",
                parent="cabinet_manager_office",
                description="No filed report template available.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("desk_open_office_1"),
            set_states("cabinet_manager_office", is_open=True),
            move_item("report_open_office", match_parent="cabinet_manager_office", parent="desk_open_office_1", relation="on"),
            set_states("desk_open_office_1", is_dirty=True, fill_level=0.7),
            set_states("computer_open_office_1", is_on=True),
            set_states("printer_open_office", is_on=True),
        ),
    ),
    "office_team_meeting": make_event(
        "office_team_meeting",
        values=(VALUE_SOCIAL_COORDINATION, VALUE_ROLE_DUTY),
        pattern=PATTERN_SERVICE_FLOW,
        description="team uses the meeting room for coordination",
        preconditions=(
            require_node(
                precondition_id="office_report_on_worker_desk",
                target="report_open_office",
                parent="desk_open_office_1",
                description="No report prepared on the worker desk.",
                recoverable=True,
            ),
            require_node(
                precondition_id="office_clean_pantry_cup_ready",
                target="cup_pantry",
                parent="counter_pantry",
                description="No clean pantry cup available for the meeting.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("table_meeting_room"),
            move_item("report_open_office", match_parent="desk_open_office_1", parent="table_meeting_room", relation="on"),
            move_item("cup_pantry", match_parent="counter_pantry", parent="table_meeting_room", relation="on", states={"is_dirty": True}),
            set_states("table_meeting_room", is_dirty=True, fill_level=0.6),
            set_states("seat_meeting_room", is_dirty=True),
            set_states("display_meeting_room", is_on=True),
            set_states("counter_pantry", is_dirty=True, fill_level=0.4),
        ),
    ),
    "office_manager_review": make_event(
        "office_manager_review",
        values=(VALUE_ROLE_DUTY, VALUE_CREATIVE_IMPROVEMENT),
        pattern=PATTERN_SERVICE_FLOW,
        description="manager reviews report and marks follow-up work",
        effects=(
            move_actor("desk_manager_office"),
            set_states("computer_manager_office", is_on=True),
            set_states("desk_manager_office", is_dirty=True, fill_level=0.5),
            set_states("cabinet_manager_office", is_open=True),
        ),
    ),
    "office_visitor_help": make_event(
        "office_visitor_help",
        values=(VALUE_SOCIAL_COORDINATION,),
        pattern=PATTERN_SERVICE_FLOW,
        description="visitor receives help, consuming shared office resources",
        preconditions=(
            require_node(
                precondition_id="office_shared_cup_ready",
                target="cup_pantry",
                parent="counter_pantry",
                description="No clean shared cup available for visitor help.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("counter_pantry"),
            set_states("counter_pantry", is_dirty=True, fill_level=0.8),
            set_states("water_dispenser_pantry", is_on=True),
            set_states("fridge_pantry", is_open=True, fill_level=0.1),
            set_states("microwave_pantry", is_on=True, is_open=True, fill_level=0.2, cycle_remaining=1),
            set_states("cup_pantry", is_dirty=True, is_wet=True),
        ),
    ),
    "office_leave": make_event(
        "office_leave",
        values=(VALUE_ROLE_DUTY,),
        pattern=PATTERN_PRESENCE,
        description="worker leaves after work, leaving materials for the robot to reset",
        effects=(
            move_actor("outside_home", relation="at"),
            set_states("computer_open_office_1", is_on=False),
            set_states("display_meeting_room", is_on=True),
            set_states("sink_restroom", is_on=True, fill_level=0.4),
            set_states("toilet_restroom", is_on=True, fill_level=0.3),
            set_states("plant_entrance", vitality=0.6, is_wilted=True),
            set_states("plant_manager_office", vitality=0.6, is_wilted=True),
        ),
    ),
    "factory_off_shift": make_event(
        "factory_off_shift",
        values=(VALUE_BODILY_NEED,),
        pattern=PATTERN_PRESENCE,
        description="factory actor is off shift and leaves used safety gear for reset",
        effects=(
            move_actor("outside_home", relation="at"),
            move_item(
                "safety_gear_entrance",
                match_parent="worker_1",
                parent="entrance",
                relation="near",
            ),
            set_states("fridge_break_room", is_open=True, fill_level=0.1),
            set_states("table_break_room", is_dirty=True, fill_level=0.4),
            set_states("toilet_restroom", is_on=True, fill_level=0.3),
            set_states("computer_control_room", is_on=False),
            set_states("display_control_room", is_on=False),
            set_states("water_dispenser_break_room", is_on=False),
        ),
    ),
    "factory_worker_prepare": make_event(
        "factory_worker_prepare",
        values=(VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY),
        pattern=PATTERN_EQUIP_ROLE_ITEM,
        description="worker equips protective gear before entering production",
        preconditions=(
            require_node(
                precondition_id="factory_safety_gear_ready",
                target="safety_gear_entrance",
                parent="cabinet_entrance",
                description="No safety gear available in the entrance cabinet.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("cabinet_entrance"),
            move_item("safety_gear_entrance", match_parent="cabinet_entrance", parent="worker_1", relation="worn_by"),
            set_states("cabinet_entrance", is_open=True, fill_level=0.1, is_full=True),
            set_states("button_assembly_line", is_pressed=True, is_on=True),
        ),
    ),
    "factory_load_parts": make_event(
        "factory_load_parts",
        values=(VALUE_ROLE_DUTY,),
        pattern=PATTERN_RETRIEVE_USE_DISPLACE,
        description="worker moves warehouse parts onto the assembly line",
        preconditions=(
            require_node(
                precondition_id="factory_parts_box_ready_on_shelf",
                target="box_warehouse_1",
                parent="shelf_warehouse",
                description="No ready parts available on the warehouse shelf.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("shelf_warehouse"),
            set_states("cabinet_control_room", is_open=True),
            move_item("box_warehouse_1", match_parent="shelf_warehouse", parent="machine_assembly_line", relation="near"),
            set_states("box_warehouse_1", is_full=True),
            set_states("box_warehouse_2", is_full=True),
            set_states("shelf_warehouse", is_full=True),
            change_level("shelf_warehouse", "fill_level", -0.2, min_value=0.0),
            change_level("box_warehouse_1", "fill_level", -0.25, min_value=0.0),
            change_level("box_workshop_parts", "fill_level", -0.15, min_value=0.0),
            change_level("box_warehouse_2", "fill_level", -0.2, min_value=0.0),
        ),
    ),
    "factory_run_assembly": make_event(
        "factory_run_assembly",
        values=(VALUE_ROLE_DUTY,),
        pattern=PATTERN_SERVICE_FLOW,
        description="assembly line runs and produces an item for inspection",
        preconditions=(
            require_node(
                precondition_id="factory_assembly_line_loaded",
                target="box_warehouse_1",
                parent="machine_assembly_line",
                description="Assembly line has no loaded parts.",
                recoverable=True,
            ),
            require_node(
                precondition_id="factory_previous_product_stored",
                target="finished_product_assembly",
                parent="warehouse",
                description="Previous product has not been stored.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("machine_assembly_line"),
            set_states("machine_assembly_line", is_on=True),
            set_states("button_assembly_line", is_pressed=True, is_on=True),
            set_states("display_control_room", is_on=True),
            move_item("finished_product_assembly", timing="period_start", match_parent="warehouse", parent="table_workshop", relation="on"),
            move_item("box_warehouse_1", timing="period_end", match_parent="machine_assembly_line", parent="warehouse", relation="in"),
            set_states("table_workshop", is_dirty=True, fill_level=0.6, is_full=True),
            set_states("box_assembly_line_parts", is_full=True),
            set_states("box_workshop_parts", is_full=True),
            change_level("box_assembly_line_parts", "fill_level", -0.2, min_value=0.0),
            change_level("box_workshop_parts", "fill_level", -0.2, min_value=0.0),
        ),
    ),
    "factory_quality_check": make_event(
        "factory_quality_check",
        values=(VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY),
        pattern=PATTERN_SERVICE_FLOW,
        description="inspector checks produced item and creates records",
        preconditions=(
            require_node(
                precondition_id="factory_uninspected_product_ready",
                target="finished_product_assembly",
                parent="table_workshop",
                description="No uninspected product available.",
                recoverable=True,
            ),
            require_node(
                precondition_id="factory_quality_record_template_filed",
                target="quality_record_control",
                parent="cabinet_control_room",
                description="No filed quality record template available.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("table_workshop"),
            set_states("computer_control_room", is_on=True),
            set_states("display_control_room", is_on=True),
            set_states("table_workshop", is_dirty=True, fill_level=0.8),
            move_item("finished_product_assembly", match_parent="table_workshop", parent="warehouse", relation="in"),
            move_item("quality_record_control", match_parent="cabinet_control_room", parent="computer_control_room", relation="near"),
        ),
    ),
    "factory_maintenance_check": make_event(
        "factory_maintenance_check",
        values=(VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY),
        pattern=PATTERN_CLEAN_OR_DIRTY_SURFACE,
        description="maintenance worker checks equipment and leaves tools out",
        preconditions=(
            require_node(
                precondition_id="factory_maintenance_toolkit_ready",
                target="toolkit_workshop",
                parent="cabinet_control_room",
                description="No maintenance toolkit available in control room cabinet.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("machine_assembly_line"),
            set_states("machine_assembly_line", is_on=False),
            set_states("button_control_room", is_pressed=True, is_on=True),
            set_states("sink_restroom", is_on=True, fill_level=0.3),
            set_states("cabinet_control_room", is_open=True, fill_level=0.1),
            move_item("toolkit_workshop", match_parent="cabinet_control_room", parent="machine_assembly_line", relation="near"),
        ),
    ),
    "factory_shift_handover": make_event(
        "factory_shift_handover",
        values=(VALUE_SOCIAL_COORDINATION, VALUE_ROLE_DUTY),
        pattern=PATTERN_SERVICE_FLOW,
        description="workers coordinate at shift handover",
        preconditions=(
            require_node(
                precondition_id="factory_quality_record_ready_for_handover",
                target="quality_record_control",
                parent="cabinet_control_room",
                description="Quality record has not been filed for handover.",
                recoverable=True,
            ),
        ),
        effects=(
            move_actor("display_control_room"),
            set_states("display_control_room", is_on=True),
            set_states("table_break_room", is_dirty=True, fill_level=0.7),
            set_states("seat_break_room", is_dirty=True),
            set_states("fridge_break_room", is_open=False, fill_level=0.3),
            set_states("water_dispenser_break_room", is_on=False),
        ),
    ),
}


EVENT_VALUE_MODEL: dict[str, tuple[tuple[str, ...], str, str]] = {
    # Home: bodily life rhythms create hygiene, clothing, food, and clutter side effects.
    "sleeping": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "resting to maintain basic bodily function"),
    "waking_up": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "transitioning from rest into daily activity"),
    "getting_dressed": ((VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY), PATTERN_EQUIP_ROLE_ITEM, "equipping clean clothes to be socially ready"),
    "washing_up_morning": ((VALUE_BODILY_NEED, VALUE_HEALTH_SAFETY), PATTERN_RETRIEVE_USE_DISPLACE, "personal hygiene using bathroom supplies"),
    "washing_up_night": ((VALUE_BODILY_NEED, VALUE_HEALTH_SAFETY), PATTERN_RETRIEVE_USE_DISPLACE, "night hygiene that produces dirty worn clothes"),
    "breakfast": ((VALUE_BODILY_NEED,), PATTERN_CONSUME_RESOURCE, "food consumption that dirties dishes and leaves residue"),
    "eating": ((VALUE_BODILY_NEED,), PATTERN_CONSUME_RESOURCE, "meal consumption that dirties dishes and leaves residue"),
    "leaving_home": ((VALUE_ROLE_DUTY,), PATTERN_EQUIP_ROLE_ITEM, "leaving for work after equipping shoes"),
    "returning_home": ((VALUE_BODILY_NEED, VALUE_ROLE_DUTY), PATTERN_RETRIEVE_USE_DISPLACE, "returning home and shedding worn items"),
    "waiting_for_dinner": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "waiting/resting before a meal"),
    "resting_home": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "resting in the living area"),
    "away_at_work": ((VALUE_ROLE_DUTY,), PATTERN_PRESENCE, "being away to satisfy work role obligations"),
    # Hospital: safety dominates, with role duties supporting patient care.
    "hospital_away": ((VALUE_HEALTH_SAFETY,), PATTERN_PRESENCE, "patient is outside the hospital flow"),
    "hospital_off_shift": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "staff are off shift"),
    "patient_register": ((VALUE_HEALTH_SAFETY,), PATTERN_SERVICE_FLOW, "entering the care process"),
    "patient_wait": ((VALUE_HEALTH_SAFETY,), PATTERN_SERVICE_FLOW, "waiting in the clinical queue"),
    "patient_consult": ((VALUE_HEALTH_SAFETY,), PATTERN_SERVICE_FLOW, "receiving diagnosis"),
    "patient_take_medicine": ((VALUE_HEALTH_SAFETY,), PATTERN_CONSUME_RESOURCE, "receiving prescribed medicine"),
    "patient_infusion": ((VALUE_HEALTH_SAFETY,), PATTERN_SERVICE_FLOW, "receiving treatment"),
    "patient_leave": ((VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY), PATTERN_RETRIEVE_USE_DISPLACE, "leaving after care and returning hospital materials to circulation"),
    "doctor_prepare": ((VALUE_ROLE_DUTY,), PATTERN_EQUIP_ROLE_ITEM, "equipping doctor role clothing"),
    "doctor_call_patient": ((VALUE_ROLE_DUTY, VALUE_HEALTH_SAFETY), PATTERN_SERVICE_FLOW, "coordinating clinical service flow"),
    "doctor_examine_patient": ((VALUE_ROLE_DUTY, VALUE_HEALTH_SAFETY), PATTERN_SERVICE_FLOW, "performing clinical examination"),
    "doctor_prescribe": ((VALUE_ROLE_DUTY, VALUE_HEALTH_SAFETY), PATTERN_SERVICE_FLOW, "creating treatment instructions"),
    "nurse_prepare": ((VALUE_ROLE_DUTY,), PATTERN_EQUIP_ROLE_ITEM, "equipping nurse role clothing"),
    "nurse_round": ((VALUE_ROLE_DUTY, VALUE_HEALTH_SAFETY), PATTERN_SERVICE_FLOW, "checking treatment area readiness"),
    "nurse_deliver_medicine": ((VALUE_ROLE_DUTY, VALUE_HEALTH_SAFETY), PATTERN_SERVICE_FLOW, "delivering medicine to the patient"),
    "nurse_change_bed_sheet": ((VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY), PATTERN_CLEAN_OR_DIRTY_SURFACE, "maintaining hygiene by replacing linen"),
    "nurse_clean_bed": ((VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY), PATTERN_CLEAN_OR_DIRTY_SURFACE, "restoring treatment bed cleanliness"),
    "nurse_restock_supplies": ((VALUE_HEALTH_SAFETY, VALUE_ROLE_DUTY), PATTERN_REPLENISH_RESOURCE, "maintaining clinical supply continuity"),
    # Supermarket: shoppers satisfy material needs; staff maintain service and resource continuity.
    "store_away": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "customer is outside the store"),
    "store_off_shift": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "store worker is off shift"),
    "customer_enter": ((VALUE_BODILY_NEED,), PATTERN_SERVICE_FLOW, "entering the shopping flow"),
    "customer_take_cart": ((VALUE_BODILY_NEED,), PATTERN_RETRIEVE_USE_DISPLACE, "taking a cart to acquire goods"),
    "customer_shop_produce": ((VALUE_BODILY_NEED,), PATTERN_CONSUME_RESOURCE, "selecting shelf produce"),
    "customer_shop_cold": ((VALUE_BODILY_NEED, VALUE_HEALTH_SAFETY), PATTERN_CONSUME_RESOURCE, "selecting cold-chain food"),
    "customer_checkout": ((VALUE_BODILY_NEED, VALUE_ROLE_DUTY), PATTERN_SERVICE_FLOW, "checking out goods and creating restock/cleanup work"),
    "customer_leave_store": ((VALUE_BODILY_NEED,), PATTERN_PRESENCE, "leaving after shopping"),
    "cashier_prepare": ((VALUE_ROLE_DUTY,), PATTERN_SERVICE_FLOW, "maintaining checkout readiness"),
    "cashier_scan_items": ((VALUE_ROLE_DUTY,), PATTERN_SERVICE_FLOW, "processing checkout service"),
    "stocker_inspect": ((VALUE_ROLE_DUTY,), PATTERN_REPLENISH_RESOURCE, "checking shelf stock readiness"),
}


def _apply_event_value_model() -> None:
    for event_id, (values, pattern, description) in EVENT_VALUE_MODEL.items():
        spec = NPC_EVENT_LIBRARY.get(event_id)
        if spec:
            NPC_EVENT_LIBRARY[event_id] = replace(
                spec,
                value_drivers=values,
                activity_pattern=pattern,
                description=description,
            )


_apply_event_value_model()


ROLE_SCHEDULES: dict[str, list[ScheduleEntry]] = {
    "resident_workday": [
        ScheduleEntry(0, 6 * 60, "bed_bedroom", "bedroom", "sleeping"),
        ScheduleEntry(6 * 60, 6 * 60 + 30, "bed_bedroom", "bedroom", "waking_up"),
        ScheduleEntry(6 * 60 + 30, 7 * 60, "wardrobe_bedroom", "bedroom", "getting_dressed"),
        ScheduleEntry(7 * 60, 7 * 60 + 30, "sink_bathroom", "bathroom", "washing_up_morning"),
        ScheduleEntry(7 * 60 + 30, 8 * 60, "coffee_table_living_room", "living_room", "breakfast"),
        ScheduleEntry(8 * 60, 8 * 60 + 30, "entrance", "entrance", "leaving_home"),
        ScheduleEntry(8 * 60 + 30, 18 * 60, "outside_home", "outside_home", "away_at_work"),
        ScheduleEntry(18 * 60, 18 * 60 + 30, "living_room", "living_room", "returning_home"),
        ScheduleEntry(18 * 60 + 30, 20 * 60, "sofa_living_room", "living_room", "waiting_for_dinner"),
        ScheduleEntry(20 * 60, 21 * 60, "coffee_table_living_room", "living_room", "eating"),
        ScheduleEntry(21 * 60, 22 * 60, "sink_bathroom", "bathroom", "washing_up_night"),
        ScheduleEntry(22 * 60, 24 * 60, "bed_bedroom", "bedroom", "sleeping"),
    ],
    "resident_weekend": [
        ScheduleEntry(0, 7 * 60 + 30, "bed_bedroom", "bedroom", "sleeping"),
        ScheduleEntry(7 * 60 + 30, 8 * 60, "bed_bedroom", "bedroom", "waking_up"),
        ScheduleEntry(8 * 60, 8 * 60 + 30, "wardrobe_bedroom", "bedroom", "getting_dressed"),
        ScheduleEntry(8 * 60 + 30, 9 * 60, "sink_bathroom", "bathroom", "washing_up_morning"),
        ScheduleEntry(9 * 60, 10 * 60, "coffee_table_living_room", "living_room", "breakfast"),
        ScheduleEntry(10 * 60, 12 * 60 + 30, "sofa_living_room", "living_room", "resting_home"),
        ScheduleEntry(12 * 60 + 30, 13 * 60 + 30, "coffee_table_living_room", "living_room", "eating"),
        ScheduleEntry(13 * 60 + 30, 19 * 60, "sofa_living_room", "living_room", "resting_home"),
        ScheduleEntry(19 * 60, 20 * 60, "coffee_table_living_room", "living_room", "eating"),
        ScheduleEntry(20 * 60, 21 * 60, "sink_bathroom", "bathroom", "washing_up_night"),
        ScheduleEntry(21 * 60, 24 * 60, "bed_bedroom", "bedroom", "sleeping"),
    ],
    "patient": [
        ScheduleEntry(0, 8 * 60, "outside_home", "outside_home", "hospital_away"),
        ScheduleEntry(8 * 60, 8 * 60 + 10, "counter_registration", "registration", "patient_register"),
        ScheduleEntry(8 * 60 + 10, 8 * 60 + 50, "seats_waiting_area", "waiting_area", "patient_wait"),
        ScheduleEntry(8 * 60 + 50, 9 * 60 + 20, "exam_bed_clinic_1", "outpatient_clinic_1", "patient_consult"),
        ScheduleEntry(9 * 60 + 20, 9 * 60 + 40, "seats_waiting_area", "waiting_area", "patient_wait"),
        ScheduleEntry(9 * 60 + 40, 9 * 60 + 50, "shelf_pharmacy", "pharmacy", "patient_take_medicine"),
        ScheduleEntry(9 * 60 + 50, 10 * 60, "seats_waiting_area", "waiting_area", "patient_wait"),
        ScheduleEntry(10 * 60, 11 * 60, "treatment_bed_treatment_room", "treatment_room", "patient_infusion"),
        ScheduleEntry(11 * 60, 11 * 60 + 20, "outside_home", "outside_home", "patient_leave"),
        ScheduleEntry(11 * 60 + 20, 24 * 60, "outside_home", "outside_home", "hospital_away"),
    ],
    "doctor": [
        ScheduleEntry(0, 7 * 60 + 50, "outside_home", "outside_home", "hospital_off_shift"),
        ScheduleEntry(7 * 60 + 50, 8 * 60 + 20, "locker_staff_room", "staff_room", "doctor_prepare"),
        ScheduleEntry(8 * 60 + 20, 8 * 60 + 50, "desk_clinic_1", "outpatient_clinic_1", "doctor_call_patient"),
        ScheduleEntry(8 * 60 + 50, 9 * 60 + 20, "exam_bed_clinic_1", "outpatient_clinic_1", "doctor_examine_patient"),
        ScheduleEntry(9 * 60 + 20, 9 * 60 + 30, "desk_clinic_1", "outpatient_clinic_1", "doctor_prescribe"),
        ScheduleEntry(9 * 60 + 30, 17 * 60, "desk_clinic_1", "outpatient_clinic_1", "doctor_call_patient"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "hospital_off_shift"),
    ],
    "nurse": [
        ScheduleEntry(0, 7 * 60 + 40, "outside_home", "outside_home", "hospital_off_shift"),
        ScheduleEntry(7 * 60 + 40, 8 * 60 + 10, "locker_staff_room", "staff_room", "nurse_prepare"),
        ScheduleEntry(8 * 60 + 10, 9 * 60 + 30, "treatment_bed_treatment_room", "treatment_room", "nurse_round"),
        ScheduleEntry(9 * 60 + 30, 9 * 60 + 40, "medical_cart_treatment_room", "treatment_room", "nurse_deliver_medicine"),
        ScheduleEntry(9 * 60 + 40, 10 * 60, "treatment_bed_treatment_room", "treatment_room", "nurse_round"),
        ScheduleEntry(10 * 60, 10 * 60 + 10, "treatment_bed_treatment_room", "treatment_room", "nurse_change_bed_sheet"),
        ScheduleEntry(10 * 60 + 10, 11 * 60, "treatment_bed_treatment_room", "treatment_room", "nurse_clean_bed"),
        ScheduleEntry(11 * 60, 12 * 60, "medical_cart_treatment_room", "treatment_room", "nurse_restock_supplies"),
        ScheduleEntry(12 * 60, 17 * 60, "treatment_bed_treatment_room", "treatment_room", "nurse_round"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "hospital_off_shift"),
    ],
    "customer": [
        ScheduleEntry(0, 8 * 60, "outside_home", "outside_home", "store_away"),
        ScheduleEntry(8 * 60, 8 * 60 + 10, "entrance", "entrance", "customer_enter"),
        ScheduleEntry(8 * 60 + 10, 8 * 60 + 20, "cart_entrance", "entrance", "customer_take_cart"),
        ScheduleEntry(8 * 60 + 20, 8 * 60 + 30, "shelf_produce", "produce_area", "customer_shop_produce"),
        ScheduleEntry(8 * 60 + 30, 8 * 60 + 40, "fridge_cold_storage", "cold_storage", "customer_shop_cold"),
        ScheduleEntry(8 * 60 + 40, 8 * 60 + 50, "counter_checkout", "checkout_area", "customer_checkout"),
        ScheduleEntry(8 * 60 + 50, 9 * 60, "outside_home", "outside_home", "customer_leave_store"),
        ScheduleEntry(9 * 60, 24 * 60, "outside_home", "outside_home", "store_away"),
    ],
    "cashier": [
        ScheduleEntry(0, 7 * 60 + 50, "outside_home", "outside_home", "store_off_shift"),
        ScheduleEntry(7 * 60 + 50, 8 * 60 + 30, "counter_checkout", "checkout_area", "cashier_prepare"),
        ScheduleEntry(8 * 60 + 30, 9 * 60, "counter_checkout", "checkout_area", "cashier_scan_items"),
        ScheduleEntry(9 * 60, 17 * 60, "counter_checkout", "checkout_area", "cashier_prepare"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "store_off_shift"),
    ],
    "stocker": [
        ScheduleEntry(0, 7 * 60 + 40, "outside_home", "outside_home", "store_off_shift"),
        ScheduleEntry(7 * 60 + 40, 17 * 60, "shelf_dry_goods", "shelf_area", "stocker_inspect"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "store_off_shift"),
    ],
    "office_worker": [
        ScheduleEntry(0, 8 * 60, "outside_home", "outside_home", "office_away"),
        ScheduleEntry(8 * 60, 8 * 60 + 30, "desk_open_office_1", "open_office", "office_worker_arrive"),
        ScheduleEntry(8 * 60 + 30, 10 * 60, "desk_open_office_1", "open_office", "office_focus_work"),
        ScheduleEntry(10 * 60, 11 * 60, "table_meeting_room", "meeting_room", "office_team_meeting"),
        ScheduleEntry(11 * 60, 12 * 60, "desk_open_office_1", "open_office", "office_focus_work"),
        ScheduleEntry(12 * 60, 13 * 60, "counter_pantry", "pantry", "office_visitor_help"),
        ScheduleEntry(13 * 60, 17 * 60, "desk_open_office_1", "open_office", "office_focus_work"),
        ScheduleEntry(17 * 60, 17 * 60 + 30, "outside_home", "outside_home", "office_leave"),
        ScheduleEntry(17 * 60 + 30, 24 * 60, "outside_home", "outside_home", "office_away"),
    ],
    "manager": [
        ScheduleEntry(0, 8 * 60 + 30, "outside_home", "outside_home", "office_off_shift"),
        ScheduleEntry(8 * 60 + 30, 10 * 60, "desk_manager_office", "manager_office", "office_manager_review"),
        ScheduleEntry(10 * 60, 11 * 60, "table_meeting_room", "meeting_room", "office_team_meeting"),
        ScheduleEntry(11 * 60, 17 * 60, "desk_manager_office", "manager_office", "office_manager_review"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "office_off_shift"),
    ],
    "visitor": [
        ScheduleEntry(0, 12 * 60, "outside_home", "outside_home", "office_away"),
        ScheduleEntry(12 * 60, 13 * 60, "counter_pantry", "pantry", "office_visitor_help"),
        ScheduleEntry(13 * 60, 24 * 60, "outside_home", "outside_home", "office_away"),
    ],
    "factory_worker": [
        ScheduleEntry(0, 7 * 60 + 40, "outside_home", "outside_home", "factory_off_shift"),
        ScheduleEntry(7 * 60 + 40, 8 * 60, "cabinet_entrance", "entrance", "factory_worker_prepare"),
        ScheduleEntry(8 * 60, 9 * 60, "shelf_warehouse", "warehouse", "factory_load_parts"),
        ScheduleEntry(9 * 60, 11 * 60, "machine_assembly_line", "assembly_line", "factory_run_assembly"),
        ScheduleEntry(11 * 60, 12 * 60, "display_control_room", "control_room", "factory_shift_handover"),
        ScheduleEntry(12 * 60, 17 * 60, "machine_assembly_line", "assembly_line", "factory_run_assembly"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "factory_off_shift"),
    ],
    "quality_inspector": [
        ScheduleEntry(0, 9 * 60 + 30, "outside_home", "outside_home", "factory_off_shift"),
        ScheduleEntry(9 * 60 + 30, 11 * 60, "table_workshop", "workshop", "factory_quality_check"),
        ScheduleEntry(11 * 60, 12 * 60, "display_control_room", "control_room", "factory_shift_handover"),
        ScheduleEntry(12 * 60, 17 * 60, "table_workshop", "workshop", "factory_quality_check"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "factory_off_shift"),
    ],
    "maintenance_worker": [
        ScheduleEntry(0, 10 * 60, "outside_home", "outside_home", "factory_off_shift"),
        ScheduleEntry(10 * 60, 12 * 60, "machine_assembly_line", "assembly_line", "factory_maintenance_check"),
        ScheduleEntry(12 * 60, 17 * 60, "machine_assembly_line", "assembly_line", "factory_maintenance_check"),
        ScheduleEntry(17 * 60, 24 * 60, "outside_home", "outside_home", "factory_off_shift"),
    ],
}

DEFAULT_ROLE = "resident"


def get_default_npcs(scene_type: str) -> List[Dict[str, str]]:
    if scene_type == "hospital":
        return HOSPITAL_NPC_LIBRARY
    if scene_type == "supermarket":
        return SUPERMARKET_NPC_LIBRARY
    if scene_type == "office":
        return OFFICE_NPC_LIBRARY
    if scene_type == "factory":
        return FACTORY_NPC_LIBRARY
    return HOME_NPC_LIBRARY


def _is_workday(day: int) -> bool:
    return ((max(1, int(day)) - 1) % 7) < 5


def schedule_for_role(role: str, day: int = 1) -> list[ScheduleEntry]:
    if role == "resident":
        resolved = "resident_workday" if _is_workday(day) else "resident_weekend"
        return ROLE_SCHEDULES[resolved]
    if not _is_workday(day):
        if role in {"office_worker", "visitor"}:
            return [ScheduleEntry(0, 24 * 60, "outside_home", "outside_home", "office_away")]
        if role == "manager":
            return [ScheduleEntry(0, 24 * 60, "outside_home", "outside_home", "office_off_shift")]
        if role in {"factory_worker", "quality_inspector", "maintenance_worker"}:
            return [ScheduleEntry(0, 24 * 60, "outside_home", "outside_home", "factory_off_shift")]
    return ROLE_SCHEDULES.get(role, ROLE_SCHEDULES["resident_workday"])


def _stable_seed(*parts: object) -> int:
    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _is_shuffleable_activity(activity: str) -> bool:
    name = str(activity or "")
    idle_markers = (
        "away",
        "off_shift",
        "sleeping",
        "leave",
        "leaving",
        "enter",
        "returning",
        "prepare",
    )
    return bool(name) and not any(marker in name for marker in idle_markers)


def randomized_schedule_for_role(role: str, day: int, actor_id: str, seed: int) -> list[ScheduleEntry]:
    base = list(schedule_for_role(role, day))
    shuffleable_indices = [
        index
        for index, entry in enumerate(base)
        if _is_shuffleable_activity(entry.activity)
    ]
    if len(shuffleable_indices) < 2:
        return base
    rng = random.Random(_stable_seed("schedule_shuffle", seed, role, actor_id, day))
    shuffled_payloads = [
        (base[index].target_parent, base[index].target_room, base[index].activity)
        for index in shuffleable_indices
    ]
    rng.shuffle(shuffled_payloads)
    randomized = list(base)
    for index, (target_parent, target_room, activity) in zip(shuffleable_indices, shuffled_payloads):
        original = base[index]
        randomized[index] = replace(
            original,
            target_parent=target_parent,
            target_room=target_room,
            activity=activity,
        )
    return randomized


def planned_activity(
    role: str,
    minute: int,
    day: int = 1,
    *,
    schedule_mode: str = "fixed",
    schedule_seed: int = 0,
    actor_id: str = "",
) -> tuple[str, str, str]:
    normalized = minute % (24 * 60)
    schedule = (
        randomized_schedule_for_role(role, day, actor_id, schedule_seed)
        if schedule_mode == "stochastic"
        else schedule_for_role(role, day)
    )
    for entry in schedule:
        if entry.start_min <= normalized < entry.end_min:
            return (entry.target_parent, entry.target_room, entry.activity)
    fallback = schedule[-1]
    return (fallback.target_parent, fallback.target_room, fallback.activity)


def get_event_spec(event_id: str) -> EventSpec | None:
    return NPC_EVENT_LIBRARY.get(str(event_id or ""))
