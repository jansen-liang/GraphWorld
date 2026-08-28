from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.generation.ontology import load_ontology


NON_OBJECT_TYPES = {"floor", "human", "robot", "room"}


def collect(scene_dir: Path) -> dict:
    ontology = load_ontology()
    raw = {category: set() for category in ("rooms", "objects", "relations", "actions")}
    files = sorted(scene_dir.glob("*.json"))
    for path in files:
        scene = json.loads(path.read_text(encoding="utf-8"))
        for node in scene.get("nodes") or []:
            semantic = str(node.get("semantic_type") or "")
            if node.get("node_type") == "room":
                raw["rooms"].add(str(node.get("id") or semantic))
            elif semantic and semantic not in NON_OBJECT_TYPES:
                raw["objects"].add(semantic)
            for action in node.get("interactive_actions") or []:
                raw["actions"].add(str(action))
        for edge in scene.get("edges") or []:
            if edge.get("relation"):
                raw["relations"].add(str(edge["relation"]))

    audits = []
    for category in ("rooms", "objects", "relations"):
        audits.extend(item.to_dict() for item in ontology.audit_values(category, raw[category]))
    audits.extend(item.to_dict() for item in ontology.audit_action_values(raw["actions"]))
    status = Counter(str(item["status"]) for item in audits)
    return {
        "ontology_version": ontology.version,
        "scene_dir": str(scene_dir),
        "scene_files": len(files),
        "raw_counts": {category: len(values) for category, values in raw.items()},
        "status_counts": dict(sorted(status.items())),
        "audits": audits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit GraphWorld scene labels against the canonical ontology.")
    parser.add_argument(
        "--scene-dir",
        type=Path,
        default=ROOT / "backend" / "data" / "sg_output" / "simple_graph",
    )
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    args = parser.parse_args()
    report = collect(args.scene_dir)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"ontology={report['ontology_version']} scenes={report['scene_files']}")
    print("raw_counts=" + json.dumps(report["raw_counts"], ensure_ascii=False, sort_keys=True))
    print("status_counts=" + json.dumps(report["status_counts"], ensure_ascii=False, sort_keys=True))
    for item in report["audits"]:
        if item["status"] not in {"mapped"}:
            print(
                f"{item['category']}: {item['raw_value']} -> "
                f"{item['normalized_value'] or '-'} [{item['status']}] {item['detail']}"
            )


if __name__ == "__main__":
    main()
