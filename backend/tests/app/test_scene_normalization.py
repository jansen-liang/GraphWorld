from backend.app.runtime.scene_importer import normalize_legacy_scene


def test_normalize_legacy_scene_upgrades_nodes_at_adapter_boundary():
    scene = {
        "nodes": [
            {"id": "floor", "node_type": "fixed_object", "semantic_type": "floor", "parent": None},
            {"id": "room", "node_type": "space", "semantic_type": "bedroom", "child": []},
            {"id": "chair", "node_type": "fixed_object", "semantic_type": "chair"},
            {"id": "robot", "node_type": "robot", "semantic_type": "robot"},
        ],
        "edges": [],
    }

    upgraded = normalize_legacy_scene(scene)

    assert (upgraded["schema_version"], upgraded["id_namespace"]) == (2, "editor")
    assert [node["node_type"] for node in upgraded["nodes"]] == ["floor", "room", "object", "agent"]
    assert all(node["id"] == node["editor_id"] for node in upgraded["nodes"])
    assert all("parent" not in node and "child" not in node for node in upgraded["nodes"])
