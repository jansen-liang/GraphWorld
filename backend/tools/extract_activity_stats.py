"""Extract activity/action priors from local VirtualHome or ALFRED files.

This intentionally supports common JSON/JSONL exports without downloading
datasets. It reports ``data_available=false`` when a source directory is not
provided, rather than claiming that no activities exist.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def records(root: Path):
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            if path.suffix.lower() == ".jsonl":
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        yield path, json.loads(line)
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    for item in payload:
                        yield path, item
                else:
                    yield path, payload
        except (OSError, ValueError, UnicodeDecodeError):
            continue


def extract(source: str, root: Path | None) -> dict[str, Any]:
    if root is None or not root.exists():
        return {"source": source, "data_available": False, "records": 0, "actions": {}, "activities": {}, "note": "未提供本地数据目录；没有把缺失数据当成零统计。"}
    actions: Counter[str] = Counter()
    activities: Counter[str] = Counter()
    rooms: Counter[str] = Counter()
    task_types: Counter[str] = Counter()
    task_descriptions: Counter[str] = Counter()
    high_level_steps: Counter[str] = Counter()
    scene_objects: Counter[str] = Counter()
    action_words = re.compile(r"\b(pick|pickup|put|place|open|close|clean|slice|heat|cool|toggle|turn|go|walk|move|look|take|drop)\b", re.I)
    task_type_by_id: dict[str, str] = {}
    split_path = root.parent / "splits" / "oct21.json"
    if split_path.exists():
        try:
            split_payload = json.loads(split_path.read_text(encoding="utf-8"))
            for entries in split_payload.values():
                for entry in entries:
                    task_path = str(entry.get("task", ""))
                    if "/" in task_path:
                        task_type_by_id[task_path.rsplit("/", 1)[1]] = task_path.split("/", 1)[0].split("-", 1)[0]
        except (OSError, ValueError):
            pass
    files = 0
    row_count = 0
    for path, item in records(root):
        files += 1
        row_count += 1
        values = item if isinstance(item, dict) else {"value": item}
        if isinstance(values.get("turk_annotations"), dict):
            for ann in values["turk_annotations"].get("anns") or []:
                if not isinstance(ann, dict):
                    continue
                if ann.get("task_desc"):
                    task_descriptions[str(ann["task_desc"])] += 1
                for desc in ann.get("high_descs") or []:
                    high_level_steps[str(desc).strip()] += 1
                    for word in action_words.findall(str(desc)):
                        actions[word.lower()] += 1
            scene = values.get("scene") or {}
            if scene.get("floor_plan"):
                rooms[str(scene["floor_plan"])] += 1
            for pose in scene.get("object_poses") or []:
                if isinstance(pose, dict) and pose.get("objectName"):
                    scene_objects[str(pose["objectName"]).split("_", 1)[0]] += 1
            task_id = str(values.get("task_id") or "")
            if task_id:
                path_parts = path.relative_to(root).parts
                directory_type = path_parts[-3].split("-", 1)[0] if len(path_parts) >= 3 else ""
                fallback = directory_type if directory_type not in {"tests_seen", "tests_unseen", "train", "valid_seen", "valid_unseen"} else ""
                task_type = task_type_by_id.get(task_id, fallback)
                if task_type:
                    task_types[task_type] += 1
            continue
        raw_actions = values.get("actions") or values.get("high_desc_actions") or values.get("plan") or values.get("action")
        if isinstance(raw_actions, list):
            for action in raw_actions:
                label = action.get("action") if isinstance(action, dict) else str(action)
                actions[label] += 1
        elif raw_actions:
            actions[str(raw_actions)] += 1
        for key in ("activity", "task", "task_type", "instruction"):
            if values.get(key):
                activities[str(values[key])] += 1
                break
        for key in ("room", "room_type", "scene", "scene_name"):
            if values.get(key):
                rooms[str(values[key])] += 1
                break
    return {"source": source, "data_available": True, "root": str(root), "files_scanned": files, "records": row_count, "actions": actions, "activities": activities, "rooms": rooms, "task_types": task_types, "task_descriptions": task_descriptions, "high_level_steps": high_level_steps, "scene_objects": scene_objects, "note": "动作/活动先验，不用于推导房间几何。"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--virtualhome-root", type=Path)
    parser.add_argument("--alfred-root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("backend/data/activity_stats.json"))
    args = parser.parse_args()
    result = {"virtualhome": extract("VirtualHome", args.virtualhome_root), "alfred": extract("ALFRED", args.alfred_root)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = args.output.with_name("activity_statistics.md")
    lines = ["# VirtualHome / ALFRED 活动统计", "", "本报告只统计活动、任务和动作先验，不用于推导房间几何。", ""]
    for name, data in result.items():
        lines += [f"## {name}", "", f"- 数据可用：`{data['data_available']}`", f"- 记录数：`{data['records']}`"]
        if data["data_available"]:
            lines.append("- 高频任务类型：" + ", ".join(f"{k} ({v})" for k, v in sorted(data.get("task_types", {}).items(), key=lambda x: -x[1])[:20]))
            lines.append("- 高频动作词：" + ", ".join(f"{k} ({v})" for k, v in sorted(data.get("actions", {}).items(), key=lambda x: -x[1])[:20]))
            lines.append("- 高频对象：" + ", ".join(f"{k} ({v})" for k, v in sorted(data.get("scene_objects", {}).items(), key=lambda x: -x[1])[:20]))
        lines.append(f"- 说明：{data['note']}")
        lines.append("")
    lines += ["## 用途", "", "- ALFRED 统计用于任务模板、动作序列和前置条件候选。", "- VirtualHome 统计用于 NPC 活动、角色日程和活动-房间关联候选。", "- 两者都不能替代 ProcTHOR/3D-FRONT 的房间和物体空间统计。", ""]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: {"data_available": value["data_available"], "records": value["records"]} for key, value in result.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
