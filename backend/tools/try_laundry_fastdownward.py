from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.nodes import Robot, Room
from backend.core.assets.object_library import build_object_node
from backend.runtime.engine import Orchestrator


OUT_DIR = ROOT / "backend" / "tmp" / "laundry_fd"
DEFAULT_SCENE = ROOT / "backend" / "data" / "sg_output" / "simple_graph" / "simple_home_mini.json"


def expected_plan(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the runtime trace with IDs from the actual scene, not stale fixtures."""
    by_semantic = {str(n.get("semantic_type")): str(n["id"]) for n in scene["nodes"]}
    robot = next(str(n["id"]) for n in scene["nodes"] if n.get("node_type") == "robot")
    clothes = by_semantic.get("clothes", "dirty_clothes")
    washer = by_semantic.get("washing_machine", "washing_machine_01")
    rack = by_semantic.get("drying_rack", "drying_rack_01")
    wardrobe = by_semantic.get("wardrobe", "wardrobe_01")
    room = next(str(n["id"]) for n in scene["nodes"] if n.get("node_type") == "room")
    return [
        {"action": "pick", "agent": robot, "object": clothes},
        {"action": "open", "agent": robot, "target": washer},
        {"action": "place", "agent": robot, "object": clothes, "target": washer},
        {"action": "close", "agent": robot, "target": washer},
        {"action": "press", "agent": robot, "target": washer},
        {"action": "open", "agent": robot, "target": washer},
        {"action": "pick", "agent": robot, "object": clothes},
        {"action": "place", "agent": robot, "object": clothes, "target": rack},
        {"action": "pick", "agent": robot, "object": clothes},
        {"action": "open", "agent": robot, "target": wardrobe},
        {"action": "place", "agent": robot, "object": clothes, "target": wardrobe},
        {"action": "fold", "agent": robot, "target": clothes},
        {"action": "close", "agent": robot, "target": wardrobe},
    ]


def build_mini_scene() -> dict[str, Any]:
    room = Room("laundry_room", semantic_type="room", name="laundry room", name_cn="洗衣房").to_dict()
    robot = Robot("robot_01", parent="laundry_room").to_dict()
    clothes = build_object_node(
        "dirty_clothes",
        "clothes",
        parent="laundry_room",
        overrides={"states": {"is_dirty": True, "is_wet": False, "folded": False}},
    )
    washer = build_object_node("washing_machine_01", "washing_machine", parent="laundry_room")
    # This deliberately uses the semantic type expected by timed drying rules.
    drying_rack = build_object_node(
        "drying_rack_01",
        "rack",
        parent="laundry_room",
        overrides={"semantic_type": "drying_rack", "name": "drying rack", "name_cn": "晾衣架"},
    )
    wardrobe = build_object_node("wardrobe_01", "wardrobe", parent="laundry_room")
    return {
        "scene_name": "mini_laundry",
        "world_state": {"step": 0, "event_log": []},
        "nodes": [room, robot, clothes, washer, drying_rack, wardrobe],
        "edges": [],
    }


def load_scene(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        scene = json.loads(path.read_text(encoding="utf-8"))
        # Existing generated home graphs intentionally contain no robot.  For
        # symbolic solvability validation, add a temporary actor in memory and
        # seed one laundry item as dirty/unfolded; the source JSON is untouched.
        if not any(str(n.get("node_type") or "") == "robot" for n in scene.get("nodes", [])):
            room_ids = {str(n["id"]) for n in scene.get("nodes", []) if n.get("node_type") == "room"}
            room_id = "bedroom" if "bedroom" in room_ids else next(iter(room_ids), "living_room")
            scene.setdefault("nodes", []).append(Robot("robot_01", parent=room_id).to_dict())
        clothes = next((n for n in scene.get("nodes", []) if n.get("semantic_type") == "clothes"), None)
        if clothes is not None:
            clothes.setdefault("states", {}).update({"is_dirty": True, "is_wet": False, "folded": False})
        if str(scene.get("scene_name") or "") == "simple_home_1f":
            keep_ids = {
                "robot_01", "bedroom", "bathroom", "balcony", "washer_bathroom",
                "washer_bathroom_door", "drying_rack_balcony", "wardrobe_bedroom",
                "wardrobe_bedroom_door", str(clothes.get("id") if clothes else ""),
            }
            scene["nodes"] = [n for n in scene.get("nodes", []) if str(n.get("id")) in keep_ids]
            scene["scene_name"] = "home_laundry_validation"
        return scene
    return build_mini_scene()


def pddl_name(node_id: str) -> str:
    return node_id.replace("_", "-")


def write_pddl(scene: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    domain = out_dir / "domain.pddl"
    problem = out_dir / "problem.pddl"
    domain.write_text(
        """(define (domain graphworld-laundry-mini)
  (:requirements :strips :typing :negative-preconditions)
  (:types
    node
    room fixed_object movable_object robot - node
  )
  (:predicates
    (at ?r - robot ?x - node)
    (in ?o - movable_object ?x - node)
    (holding ?r - robot ?o - movable_object)
    (handempty ?r - robot)
    (open ?x - fixed_object)
    (dirty ?o - movable_object)
    (wet ?o - movable_object)
    (folded ?o - movable_object)
    (washer ?x - fixed_object)
    (drying-rack ?x - fixed_object)
    (wardrobe ?x - fixed_object)
    (container ?x - fixed_object)
  )

  (:action move
    :parameters (?r - robot ?from - node ?to - node)
    :precondition (at ?r ?from)
    :effect (and (not (at ?r ?from)) (at ?r ?to))
  )

  (:action pick-from-room
    :parameters (?r - robot ?o - movable_object ?loc - room)
    :precondition (and (at ?r ?loc) (in ?o ?loc) (handempty ?r))
    :effect (and (not (in ?o ?loc)) (not (handempty ?r)) (holding ?r ?o))
  )

  (:action pick-from-container
    :parameters (?r - robot ?o - movable_object ?loc - fixed_object)
    :precondition (and (at ?r ?loc) (in ?o ?loc) (handempty ?r) (container ?loc) (open ?loc))
    :effect (and (not (in ?o ?loc)) (not (handempty ?r)) (holding ?r ?o))
  )

  (:action pick-from-surface
    :parameters (?r - robot ?o - movable_object ?loc - fixed_object)
    :precondition (and (at ?r ?loc) (in ?o ?loc) (handempty ?r) (not (container ?loc)))
    :effect (and (not (in ?o ?loc)) (not (handempty ?r)) (holding ?r ?o))
  )

  (:action open
    :parameters (?r - robot ?x - fixed_object)
    :precondition (at ?r ?x)
    :effect (open ?x)
  )

  (:action close
    :parameters (?r - robot ?x - fixed_object)
    :precondition (and (at ?r ?x) (open ?x))
    :effect (not (open ?x))
  )

  (:action place-in-room
    :parameters (?r - robot ?o - movable_object ?x - room)
    :precondition (and (at ?r ?x) (holding ?r ?o))
    :effect (and (not (holding ?r ?o)) (handempty ?r) (in ?o ?x))
  )

  (:action place-on-surface
    :parameters (?r - robot ?o - movable_object ?x - fixed_object)
    :precondition (and (at ?r ?x) (holding ?r ?o) (not (container ?x)))
    :effect (and (not (holding ?r ?o)) (handempty ?r) (in ?o ?x))
  )

  (:action place-in-washer
    :parameters (?r - robot ?o - movable_object ?x - fixed_object)
    :precondition (and (at ?r ?x) (holding ?r ?o) (washer ?x) (open ?x))
    :effect (and (not (holding ?r ?o)) (handempty ?r) (in ?o ?x))
  )

  (:action place-in-wardrobe
    :parameters (?r - robot ?o - movable_object ?x - fixed_object)
    :precondition (and (at ?r ?x) (holding ?r ?o) (wardrobe ?x) (open ?x) (folded ?o))
    :effect (and (not (holding ?r ?o)) (handempty ?r) (in ?o ?x))
  )

  (:action press-washer
    :parameters (?r - robot ?o - movable_object ?w - fixed_object)
    :precondition (and (at ?r ?w) (washer ?w) (in ?o ?w) (not (open ?w)) (dirty ?o))
    :effect (and (not (dirty ?o)) (wet ?o) (not (folded ?o)))
  )

  (:action dry
    :parameters (?r - robot ?o - movable_object ?rack - fixed_object)
    :precondition (and (at ?r ?rack) (drying-rack ?rack) (in ?o ?rack) (wet ?o))
    :effect (not (wet ?o))
  )

  (:action fold
    :parameters (?r - robot ?o - movable_object ?loc - node)
    :precondition (and (at ?r ?loc) (in ?o ?loc) (not (dirty ?o)) (not (wet ?o)))
    :effect (folded ?o)
  )
)
""",
        encoding="utf-8",
    )
    objects: dict[str, list[str]] = {"robot": [], "room": [], "fixed_object": [], "movable_object": []}
    init = []
    for node in scene["nodes"]:
        node_id = str(node["id"])
        node_type = str(node.get("node_type") or "")
        semantic = str(node.get("semantic_type") or "")
        if node_type in objects:
            objects[node_type].append(pddl_name(node_id))
        parent = str(node.get("parent") or "")
        if node_type == "robot":
            init.append(f"(at {pddl_name(node_id)} {pddl_name(parent)})")
            init.append(f"(handempty {pddl_name(node_id)})")
        elif node_type == "movable_object":
            init.append(f"(in {pddl_name(node_id)} {pddl_name(parent)})")
            states = node.get("states") or {}
            if states.get("is_dirty"):
                init.append(f"(dirty {pddl_name(node_id)})")
            if states.get("is_wet"):
                init.append(f"(wet {pddl_name(node_id)})")
            if states.get("folded"):
                init.append(f"(folded {pddl_name(node_id)})")
        elif semantic in {"washer", "washing_machine"}:
            init.append(f"(washer {pddl_name(node_id)})")
        elif semantic == "drying_rack":
            init.append(f"(drying-rack {pddl_name(node_id)})")
        elif semantic in {"wardrobe", "cabinet"}:
            init.append(f"(wardrobe {pddl_name(node_id)})")
        if node_type == "fixed_object" and node.get("blocks_containment"):
            init.append(f"(container {pddl_name(node_id)})")
    clothes_object = next((pddl_name(str(node["id"])) for node in scene["nodes"] if str(node.get("semantic_type")) == "clothes"), "dirty-clothes")
    wardrobe_object = next((pddl_name(str(node["id"])) for node in scene["nodes"] if str(node.get("semantic_type")) in {"wardrobe", "cabinet"}), "wardrobe-01")
    problem.write_text(
        f"""(define (problem mini-laundry-problem)
  (:domain graphworld-laundry-mini)
  (:objects
    {' '.join(objects['robot'])} - robot
    {' '.join(objects['room'])} - room
    {' '.join(objects['fixed_object'])} - fixed_object
    {' '.join(objects['movable_object'])} - movable_object
  )
  (:init
    {' '.join(init)}
  )
  (:goal (and
    (not (dirty {clothes_object}))
    (not (wet {clothes_object}))
    (folded {clothes_object})
    (in {clothes_object} {wardrobe_object})
  ))
)
""",
        encoding="utf-8",
    )
    return domain, problem


def find_fast_downward(cli_arg: str | None) -> str | None:
    candidates = [
        cli_arg,
        os.environ.get("FAST_DOWNWARD"),
        shutil.which("fast-downward.py"),
        shutil.which("fast-downward"),
        shutil.which("downward"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate).resolve())
        if candidate and shutil.which(candidate):
            return candidate
    return None


def run_fast_downward(fd: str | None, domain: Path, problem: Path, out_dir: Path, *, build: str = "laundry") -> dict[str, Any]:
    if not fd:
        return {"ok": False, "reason": "Fast Downward not found. Pass --fast-downward or set FAST_DOWNWARD."}
    plan_file = out_dir / "sas_plan"
    cmd = [fd, "--build", build, "--plan-file", str(plan_file), str(domain), str(problem), "--search", "astar(lmcut())"]
    result = subprocess.run(cmd, cwd=out_dir, text=True, capture_output=True, timeout=60, check=False)
    return {
        "ok": result.returncode == 0 and plan_file.exists(),
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "plan": plan_file.read_text(encoding="utf-8") if plan_file.exists() else "",
    }


def replay_runtime(scene: dict[str, Any]) -> list[dict[str, Any]]:
    if str(scene.get("scene_name") or "") != "mini_laundry":
        # Full home replay requires a room-aware plan executor; this script's
        # runtime trace is intentionally limited to the deterministic mini
        # laundry fixture.
        return []
    if not any(str(n.get("semantic_type") or "") == "washing_machine" for n in scene.get("nodes", [])) and not any(str(n.get("semantic_type") or "") == "washer" for n in scene.get("nodes", [])):
        return []
    orchestrator = Orchestrator(scene)
    graph = orchestrator.graph
    trace = []
    clothes_id = next(str(n["id"]) for n in scene["nodes"] if n.get("semantic_type") == "clothes")
    plan = expected_plan(scene)
    for idx, action in enumerate(plan):
        result = orchestrator.step([action])
        trace.append(
            {
                "idx": idx,
                "action": action,
                "ok": result["robot_actions"][0]["ok"],
                "reason": result["robot_actions"][0].get("reason", ""),
                "clothes": copy.deepcopy((graph.nodes.get(clothes_id) or {}).get("states", {})),
                "parent": graph.parent_of.get(clothes_id),
                "relation": graph.relation_of.get(clothes_id),
            }
        )
        if action["action"] == "press":
            for _ in range(3):
                orchestrator.step([])
        target = graph.nodes.get(str(action.get("target") or "")) or {}
        if action["action"] == "place" and str(target.get("semantic_type") or "") == "drying_rack":
            for _ in range(3):
                orchestrator.step([])
        if not trace[-1]["ok"]:
            break
    return trace


def summarize_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": node["id"],
            "semantic_type": node.get("semantic_type"),
            "node_type": node.get("node_type"),
            "parent": node.get("parent"),
            "states": node.get("states"),
            "interactive_actions": node.get("interactive_actions"),
        }
        for node in scene["nodes"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast-downward", help="Path to fast-downward.py/fast-downward/downward.")
    parser.add_argument("--fd-build", default="laundry", help="Fast Downward build to use.")
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE, help="Scene graph JSON to use.")
    args = parser.parse_args()

    scene = load_scene(args.scene)
    domain, problem = write_pddl(scene, OUT_DIR)
    fd_result = run_fast_downward(find_fast_downward(args.fast_downward), domain, problem, OUT_DIR, build=args.fd_build)
    runtime_trace = replay_runtime(scene)
    report = {
        "scene_summary": summarize_scene(scene),
        "pddl": {"domain": str(domain), "problem": str(problem)},
        "fast_downward": fd_result,
        "runtime_trace": runtime_trace,
    }
    report_path = OUT_DIR / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
