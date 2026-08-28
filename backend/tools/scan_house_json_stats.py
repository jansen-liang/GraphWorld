"""Scan available AI2-THOR-style house JSONs for structural priors."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def scan(root: Path) -> dict[str, Any]:
    files = 0
    rooms = Counter()
    doors = 0
    windows = 0
    object_types = Counter()
    room_sizes = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("rooms"), list):
            continue
        files += 1
        for room in payload["rooms"]:
            if not isinstance(room, dict):
                continue
            rooms[str(room.get("type") or "unknown")] += 1
            polygon = room.get("floorPolygon") or []
            if polygon:
                room_sizes.append(len(polygon))
        doors += len(payload.get("doors") or [])
        windows += len(payload.get("windows") or [])
        for obj in payload.get("objects") or []:
            if isinstance(obj, dict) and obj.get("assetId"):
                object_types[str(obj["assetId"])] += 1
    return {"root": str(root), "house_files": files, "rooms": rooms, "doors": doors, "windows": windows, "object_assets": object_types, "room_polygon_vertex_count": {"min": min(room_sizes) if room_sizes else None, "max": max(room_sizes) if room_sizes else None}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = scan(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"house_files": result["house_files"], "rooms": sum(result["rooms"].values()), "doors": result["doors"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
