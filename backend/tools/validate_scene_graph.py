"""Validate a generated scene graph and emit gameplay metadata.

The validator is deliberately planner-independent: it provides a deterministic
capability lower bound for every graph. A PDDL validator can consume the same
metadata and replace ``planner`` with solved/unsolved counts later.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.core.assets.object_library import OBJECT_LIBRARY

TASK_REQUIREMENTS: dict[str, set[str]] = {
    "clean": {"cleanable", "cleaning_tool"},
    "laundry": {"washer", "clothes", "drying_rack"},
    "food_disposal": {"food", "trash_bin"},
    "serve_food": {"food", "plate_or_bowl"},
    "carry_non_food": {"capacity_holder_non_food"},
    "make_coffee": {"coffeemachine", "mug", "coffee_resource"},
    "water_plant": {"plant", "water_source"},
    "print_document": {"printer", "paper_resource"},
}

FOOD = {"food", "fruit", "vegetable", "drink", "juice", "milk", "egg", "bread"}


def infer_scene_domain(data: dict[str, Any]) -> str:
    explicit = str(data.get("scene_domain") or data.get("domain") or "").strip().lower()
    if explicit in {"home", "office", "hospital", "supermarket", "factory"}:
        return explicit
    name = str(data.get("scene_name") or "").lower()
    return next((item for item in ("hospital", "supermarket", "factory", "office", "home") if item in name), "home")


def validate(data: dict[str, Any]) -> dict[str, Any]:
    nodes = list(data.get("nodes") or (data.get("node") or {}).values())
    type_counts = Counter(str(n.get("semantic_type") or n.get("type") or "unknown") for n in nodes)
    family_counts = Counter()
    for n in nodes:
        family = n.get("family")
        if not family:
            family = getattr(OBJECT_LIBRARY.get(str(n.get("semantic_type") or n.get("type") or "")), "family", "generic")
        family_counts[str(getattr(family, "value", family))] += 1
    capabilities = {str(c) for n in nodes for c in (n.get("capabilities") or [])}
    semantics = set(type_counts)
    if any(s in semantics for s in FOOD):
        capabilities.add("food")
    if any(s in semantics for s in {"plate", "bowl"}):
        capabilities.add("plate_or_bowl")
    if any(s in semantics for s in {"box", "cart"}):
        capabilities.add("capacity_holder_non_food")
    if any(s in semantics for s in {"mug", "cup"}):
        capabilities.add("mug")
    if any(s in semantics for s in {"coffee_beans", "coffee", "water"}):
        capabilities.add("coffee_resource")
    if any(s in semantics for s in {"paper", "tissuebox", "printer"}):
        capabilities.add("paper_resource")
    if any(s in semantics for s in {"sink", "faucet", "wateringcan", "spraybottle"}):
        capabilities.add("water_source")
    if "plant" in semantics:
        capabilities.add("plant")
    if "clothes" in semantics:
        capabilities.add("clothes")
    if "trash_bin" in semantics:
        capabilities.add("trash_bin")
    if "washer" in semantics or "washing_machine" in semantics:
        capabilities.add("washer")
    if "drying_rack" in semantics:
        capabilities.add("drying_rack")
    if "coffeemachine" in semantics or "coffee_machine" in semantics:
        capabilities.add("coffeemachine")
    if "printer" in semantics:
        capabilities.add("printer")
    if "cleanable" in capabilities or any(n.get("states", {}).get("is_dirty") is not None for n in nodes):
        capabilities.add("cleanable")
    if any(s in semantics for s in {"vacuumcleaner", "scrubbrush", "cleaning_tool"}):
        capabilities.add("cleaning_tool")
    candidates = sorted(name for name, req in TASK_REQUIREMENTS.items() if req <= capabilities)
    npcs = sum(1 for n in nodes if str(n.get("node_type") or "").lower() in {"npc", "human", "agent"} or n.get("is_npc"))
    return {
        "schema_version": "scene_metadata.v1",
        "scene_name": data.get("scene_name"),
        "scene_domain": infer_scene_domain(data),
        "node_count": len(nodes),
        "room_count": sum(1 for n in nodes if str(n.get("node_type") or "").lower() == "room"),
        "npc_count": npcs,
        "object_type_counts": dict(sorted(type_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "task_candidates": candidates,
        "task_candidate_count": len(candidates),
        "verified_task_kinds": [],
        "verified_task_count": 0,
        "supported_task_kinds": [],
        "planner": {"status": "required", "solved_task_count": 0, "unsolved_task_kinds": candidates, "command": None},
        "validation": {"errors": [], "warnings": []},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    data = json.loads(args.scene.read_text(encoding="utf-8"))
    metadata = validate(data)
    output = args.metadata or args.scene.with_name(args.scene.stem + ".metadata.json")
    output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
