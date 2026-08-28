"""Generate a first pure-node GraphWorld scene."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.generation.symbolic_scene_generator import generate_scene


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("home", "office", "hospital", "supermarket", "factory"), required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--optional-rooms", type=int, default=0)
    parser.add_argument("--npcs", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scene = generate_scene(args.domain, seed=args.seed, optional_rooms=args.optional_rooms, npc_count=args.npcs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scene, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scene": str(args.output), "nodes": len(scene["nodes"]), "edges": len(scene["edges"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
