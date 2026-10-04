from backend.adapter.animation.cues import visual_cues


def test_visual_cues_derive_from_runtime_states():
    assert visual_cues({"semantic_type": "washer", "states": {"is_running": True}}) == ["running_pulse"]
    assert visual_cues({"semantic_type": "room_light", "states": {"is_on": True}}) == ["emissive"]
    assert visual_cues({"semantic_type": "clothes", "states": {"is_wet": True, "is_broken": True}}) == ["water_droplets", "broken"]
    assert visual_cues({"semantic_type": "box", "physics_state": "falling", "states": {}}) == ["falling"]
    assert visual_cues({"semantic_type": "fan", "states": {"is_on": True}}) == ["airflow"]
    assert visual_cues({"semantic_type": "clothes", "states": {"is_wet": True, "cycle_remaining": 2}}) == ["water_droplets", "drying_bubbles"]
    assert visual_cues({"semantic_type": "milk", "states": {"temperature": "hot"}}) == ["steam"]


def test_visual_cues_prefer_declarative_asset_effects_and_capabilities():
    assert visual_cues({
        "semantic_type": "custom_machine",
        "capabilities": ["emissive", "airflow"],
        "visual_effects": ["custom_glow"],
        "states": {"is_on": True},
    }) == ["custom_glow", "airflow", "emissive"]


def test_visual_cues_do_not_require_semantic_type_for_declared_effects():
    assert visual_cues({
        "semantic_type": "asset_42",
        "visual_cues": ["steam"],
        "states": {},
    }) == ["steam"]
