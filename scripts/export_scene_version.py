#!/usr/bin/env python3
"""Export a scene version from the Web scene database as a repository asset."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.session import SessionLocal
from backend.app.repositories.scene_repo import SceneRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_id", nargs="?")
    parser.add_argument("--all", action="store_true", help="Export every scene version in the database.")
    parser.add_argument("--version", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "backend/data/scene_versions",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        repo = SceneRepository(db)
        if args.all:
            versions = [version for scene in repo.list_scenes() for version in repo.list_versions(scene.id)]
        elif args.scene_id:
            versions = repo.list_versions(args.scene_id)
            if not versions:
                raise SystemExit(f"Scene not found: {args.scene_id}")
            versions = [next((item for item in versions if item.version == args.version), versions[0])]
        else:
            raise SystemExit("Provide SCENE_ID or --all")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for version in versions:
        output = args.output_dir / f"{version.scene_id}__v{version.version}.json"
        output.write_text(json.dumps(version.source_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
