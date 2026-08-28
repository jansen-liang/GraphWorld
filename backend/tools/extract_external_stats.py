"""Extract structured room/object priors from ProcTHOR and AI2-THOR data.

The extractor intentionally reads JSON databases and metadata exports only. It
does not start Unity or download 3D assets, so it is suitable for a repeatable
ontology/statistics build step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.generation.ontology import load_ontology


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "backend/data/external_stats"
ROOM_FIELDS = {
    "inKitchens": "kitchen",
    "inLivingRooms": "living_room",
    "inBedrooms": "bedroom",
    "inBathrooms": "bathroom",
}
CAPABILITY_FIELDS = (
    "pickupable",
    "receptacle",
    "openable",
    "toggleable",
    "moveable",
    "isInteractable",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def increment_nested(table: dict[str, Counter[str]], left: str, right: str) -> None:
    table.setdefault(left, Counter())[right] += 1


def normalize_object(ontology: Any, value: Any) -> str | None:
    return ontology.normalize("objects", value) or str(value or "").strip().lower()


def default_procthor_root() -> Path:
    import procthor

    return Path(procthor.__file__).resolve().parent / "databases"


def resolve_database_root(root: Path) -> Path:
    direct = root / "placement-annotations.json"
    nested = root / "procthor" / "databases" / "placement-annotations.json"
    if direct.exists():
        return root
    if nested.exists():
        return root / "procthor" / "databases"
    raise FileNotFoundError(f"ProcTHOR placement database not found under {root}")


def extract_procthor(root: Path, ontology: Any) -> dict[str, Any]:
    database = resolve_database_root(root)
    placement_path = database / "placement-annotations.json"
    receptacles_path = database / "receptacles.json"
    asset_path = database / "asset-database.json"
    placement = read_json(placement_path)
    receptacles = read_json(receptacles_path)
    assets = read_json(asset_path) if asset_path.exists() else {}

    room_objects: dict[str, Counter[str]] = {}
    room_presence: dict[str, Counter[str]] = {}
    capabilities: dict[str, dict[str, Any]] = {}
    for object_type, row in placement.get("instances", {}).items():
        canonical = normalize_object(ontology, object_type)
        for field, room in ROOM_FIELDS.items():
            count = int(placement.get(field, {}).get(object_type, 0) or 0)
            if count:
                room_objects.setdefault(room, Counter())[canonical] += count
                room_presence.setdefault(room, Counter())[canonical] += 1
        capabilities[canonical] = {
            "pickupable": bool(placement.get("isPickupable", {}).get(object_type, False)),
            "receptacle": object_type in receptacles,
            "openable": None,
            "toggleable": None,
            "moveable": None,
            "source": "procthor.placement-annotations",
        }

    parent_counts: dict[str, Counter[str]] = {}
    for parent, children in receptacles.items():
        parent_canonical = normalize_object(ontology, parent)
        for child, value in children.items():
            child_canonical = normalize_object(ontology, child)
            count = int((value or {}).get("count", 0) or 0)
            if count:
                parent_counts.setdefault(child_canonical, Counter())[parent_canonical] += count

    room_rows = []
    for room, objects in sorted(room_objects.items()):
        for object_type, count in objects.most_common():
            room_rows.append(
                {
                    "room_type": room,
                    "object_type": object_type,
                    "count": count,
                    "room_object_presence_records": room_presence[room][object_type],
                    "source": "ProcTHOR placement-annotations.json",
                }
            )
    parent_rows = [
        {
            "object_type": obj,
            "parent_type": parent,
            "relation": "inside_or_on",
            "count": count,
            "source": "ProcTHOR receptacles.json",
        }
        for obj, parents in sorted(parent_counts.items())
        for parent, count in parents.most_common()
    ]
    asset_counts = {normalize_object(ontology, key): len(value) for key, value in assets.items()}
    return {
        "source": "ProcTHOR",
        "source_root": str(root),
        "source_revision": git_revision(root),
        "files": {
            "placement_annotations": {"path": str(placement_path), "sha256": sha256(placement_path)},
            "receptacles": {"path": str(receptacles_path), "sha256": sha256(receptacles_path)},
        },
        "room_object_stats": room_rows,
        "object_parent_stats": parent_rows,
        "object_capability_stats": [
            {"object_type": obj, **data, "asset_count": asset_counts.get(obj, 0)}
            for obj, data in sorted(capabilities.items())
        ],
        "room_graph": {
            "available": False,
            "reason": "These databases contain room-weight priors, not multi-room house instances or room adjacency edges.",
        },
        "license": "ProcTHOR and AI2-THOR are distributed under their upstream licenses; verify terms before redistribution. This output contains derived aggregate statistics, not copied assets.",
    }


def extract_ai2thor_metadata(path: Path, ontology: Any) -> dict[str, Any]:
    payload = read_json(path)
    room_objects: dict[str, Counter[str]] = {}
    room_scenes: Counter[str] = Counter()
    parents: dict[str, Counter[str]] = {}
    capabilities: dict[str, dict[str, Counter[Any]]] = {}
    scene_count = 0
    excluded_room_groups: list[str] = []

    # ProcTHOR's bundled AI2-THOR metadata is {room family: [scene objects]}.
    if isinstance(payload, dict) and all(isinstance(value, list) for value in payload.values()):
        scene_groups = payload.items()
    else:
        scene_groups = [("unknown", payload if isinstance(payload, list) else [])]
    for raw_room, scenes in scene_groups:
        if raw_room == "robothor":
            excluded_room_groups.append(raw_room)
            continue
        room = ontology.normalize("rooms", raw_room) or raw_room.rstrip("s").lower()
        for objects in scenes:
            if not isinstance(objects, list):
                continue
            scene_count += 1
            room_scenes[room] += 1
            by_id: dict[str, str] = {}
            for item in objects:
                if not isinstance(item, dict):
                    continue
                obj = normalize_object(ontology, item.get("objectType") or item.get("name"))
                if not obj:
                    continue
                by_id[str(item.get("objectId") or item.get("name") or obj)] = obj
                room_objects.setdefault(room, Counter())[obj] += 1
                bucket = capabilities.setdefault(obj, {field: Counter() for field in CAPABILITY_FIELDS})
                for field in CAPABILITY_FIELDS:
                    bucket[field][bool(item.get(field, False))] += 1
            for item in objects:
                if not isinstance(item, dict):
                    continue
                obj = normalize_object(ontology, item.get("objectType") or item.get("name"))
                for parent_id in item.get("parentReceptacles") or []:
                    parent = by_id.get(str(parent_id))
                    if parent:
                        parents.setdefault(obj, Counter())[parent] += 1

    room_rows = [
        {
            "room_type": room,
            "object_type": obj,
            "count": count,
            "scene_count": room_scenes[room],
            "frequency_per_scene": round(count / room_scenes[room], 6),
            "source": "AI2-THOR metadata via ProcTHOR database",
        }
        for room, objects in sorted(room_objects.items())
        for obj, count in objects.most_common()
    ]
    parent_rows = [
        {"object_type": obj, "parent_type": parent, "relation": "inside_or_on", "count": count,
         "source": "AI2-THOR parentReceptacles"}
        for obj, values in sorted(parents.items())
        for parent, count in values.most_common()
    ]
    capability_rows = []
    for obj, fields in sorted(capabilities.items()):
        row: dict[str, Any] = {"object_type": obj, "source": "AI2-THOR metadata"}
        for field, counts in fields.items():
            row[field] = {
                "true": counts[True], "false": counts[False], "observations": sum(counts.values())
            }
        capability_rows.append(row)
    return {
        "source": "AI2-THOR metadata",
        "source_file": str(path),
        "source_revision": git_revision(path.parents[4] if len(path.parents) > 4 else path.parent),
        "file_sha256": sha256(path),
        "scene_count": scene_count,
        "room_counts": dict(room_scenes),
        "excluded_room_groups": excluded_room_groups,
        "room_object_stats": room_rows,
        "object_parent_stats": parent_rows,
        "object_capability_stats": capability_rows,
        "room_graph": {
            "available": False,
            "reason": "This metadata export is grouped by single room family; it has no multi-room scene adjacency graph.",
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report(path: Path, combined: dict[str, Any], manifest: dict[str, Any]) -> None:
    lines = ["# 外部数据统计报告", "", "## 数据源", "", f"- 生成时间：`{manifest['generated_at_utc']}`", f"- ontology 版本：`{manifest['ontology_version']}`", "- 原始数据未复制进仓库；输出仅包含派生统计。", "- 许可：ProcTHOR、AI2-THOR 和 PRIOR 的原始数据/代码许可仍需按上游条款执行。", ""]
    for name, data in combined.items():
        lines += [f"## {name}", ""]
        if "room_object_stats" in data:
            by_room: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in data["room_object_stats"]:
                by_room[row["room_type"]].append(row)
            for room, rows in sorted(by_room.items()):
                top = ", ".join(f"{r['object_type']} ({r['count']})" for r in rows[:12])
                lines.append(f"- **{room}**：{top}")
        if "room_counts" in data:
            lines.append("- 房间样本数：" + ", ".join(f"{k}={v}" for k, v in sorted(data["room_counts"].items())))
        graph = data.get("room_graph", {})
        lines.append(f"- 房间共现/邻接：`{'可用' if graph.get('available') else '不可用'}`；{graph.get('reason', '')}")
        capabilities = data.get("object_capability_stats", [])
        pickupable = [r["object_type"] for r in capabilities if r.get("pickupable") is True or (isinstance(r.get("pickupable"), dict) and r["pickupable"].get("true", 0))]
        lines.append(f"- 可拾取对象类别：{', '.join(pickupable[:30]) or '未提供'}")
        lines.append("")
    lines += ["## 结论与未覆盖项", "", "- ProcTHOR 与随包 AI2-THOR metadata 均主要覆盖 Kitchen、LivingRoom、Bedroom、Bathroom；不能据此推导 Hospital、Supermarket、Factory 的领域房间。", "- 当前输入不含多房间 house 实例，因此房间邻接和跨房间共现被明确标记为不可用，不应当当作零频率。", "- 统计是 RoomTypeSpec/ObjectTemplate 的外部先验，仍需 GraphWorld 的任务规则、状态转移和 PDDL/可解性验证。", "- 未映射对象保留为原始归一化标签，后续应补 ontology mapping 后再生成 core 模板。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def markdown_report(combined: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        "# 外部数据集统计报告",
        "",
        "本报告由 `backend.tools.extract_external_stats` 自动生成。统计读取结构化 JSON，不启动 Unity，也不复制 3D 资产。",
        "",
        "## 数据源与范围",
        "",
        f"- extractor version: `{manifest['extractor_version']}`",
        f"- ontology version: `{manifest['ontology_version']}`",
        f"- generated at (UTC): `{manifest['generated_at_utc']}`",
        "- ProcTHOR: placement annotations、receptacles、asset database，以及包内随附的 AI2-THOR object metadata。",
        "- AI2-THOR：本轮使用 ProcTHOR 包内的 AI2-THOR metadata 导出；独立 AI2-THOR 源码仓库不包含完整可直接统计的房屋数据集。",
        "- AI2-THOR 的 `robothor` 场景族不作为房间类型，已从房间先验中排除。",
        "- 许可：原始数据仍受 ProcTHOR/AI2-THOR 上游许可约束；本仓库只保存派生聚合结果。",
        "",
        "## 核心统计",
        "",
        "| 数据源 | 房间实例 | 房间类型 | 房间-对象记录 | parent 记录 | capability 对象 | 房间图 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    pt = combined["procthor"]
    lines.append(
        f"| ProcTHOR | 先验库 | {len({row['room_type'] for row in pt['room_object_stats']})} | "
        f"{len(pt['room_object_stats'])} | {len(pt['object_parent_stats'])} | "
        f"{len(pt['object_capability_stats'])} | 不可用 |"
    )
    if "ai2thor" in combined:
        ai = combined["ai2thor"]
        lines.append(
            f"| AI2-THOR metadata | {ai['scene_count']} | {len(ai['room_counts'])} | "
            f"{len(ai['room_object_stats'])} | {len(ai['object_parent_stats'])} | "
            f"{len(ai['object_capability_stats'])} | 不可用 |"
        )
    lines += [
        "",
        "## 房间内对象先验",
        "",
        "ProcTHOR 的 `count` 是 placement annotation 中的对象实例聚合，不是本次生成的房屋数量。AI2-THOR metadata 的 `frequency_per_scene` 是每类房间实例中的平均对象出现次数。",
        "",
        "| 房间 | ProcTHOR 总实例 | AI2-THOR metadata 房间实例 | AI2-THOR 对象记录 |",
        "|---|---:|---:|---:|",
    ]
    ai_rooms = combined.get("ai2thor", {}).get("room_counts", {})
    pt_room_rows = defaultdict(int)
    for row in pt["room_object_stats"]:
        pt_room_rows[row["room_type"]] += row["count"]
    ai_room_rows = defaultdict(int)
    for row in combined.get("ai2thor", {}).get("room_object_stats", []):
        ai_room_rows[row["room_type"]] += row["count"]
    for room in sorted(set(pt_room_rows) | set(ai_rooms)):
        lines.append(f"| {room} | {pt_room_rows[room]} | {ai_rooms.get(room, 0)} | {ai_room_rows[room]} |")

    lines += [
        "",
        "## 可直接复用的先验",
        "",
        "- `allowed_rooms`：可从四类家庭房间的对象出现统计初始化，但应设置最小出现次数/置信度阈值。",
        "- `allowed_parents`：可从 ProcTHOR `receptacles.json` 和 AI2-THOR `parentReceptacles` 合并得到；两者是候选关系先验，不是 GraphWorld 运行时合法性的最终判定。",
        "- `functional_class` / capability：当前数据可以支持 `pickupable`、`receptacle`、`openable`、`toggleable`、`moveable` 等字段的观察统计；GraphWorld 仍需把它们映射到现有动作和状态闭环。",
        "",
        "## 明确缺口",
        "",
        "- ProcTHOR 数据库只提供四类家庭房间的对象放置权重；不能直接推导 Hospital、Supermarket、Factory 的真实领域房间先验。",
        "- 本轮两个输入都没有多房间 house 实例及门/连接边，因此没有生成房间共现或邻接统计；不能用单房间 metadata 伪造房间图。",
        "- AI2-THOR metadata 中的 `robothor` 是机器人场景族，不应直接作为 GraphWorld 房间类型。",
        "- 外部 capability 只是观察先验，任务是否可解仍要经过 GraphWorld 规则和 PDDL/规划器验证。",
        "",
        "## 产物",
        "",
        "- `backend/data/external_stats/procthor_stats.json`",
        "- `backend/data/external_stats/ai2thor_stats.json`",
        "- `backend/data/external_stats/external_stats.json`",
        "- `backend/data/external_stats/source_manifest.json`",
        "- `backend/data/external_stats/procthor_room_object_counts.json` / `procthor_room_object_probabilities.json`",
        "- `backend/data/external_stats/procthor_object_parent_counts.json` / `procthor_object_capability_stats.json`",
        "- `backend/data/external_stats/ai2thor_room_object_counts.json` / `ai2thor_room_object_probabilities.json`",
        "- `backend/data/external_stats/ai2thor_object_parent_counts.json` / `ai2thor_object_capability_stats.json`",
        "",
        "重新生成：",
        "",
        "```bash",
        "/home/swzz/anaconda3/gra/bin/python -m backend.tools.extract_external_stats \\",
        "  --procthor-root /path/to/ProcTHOR \\",
        "  --ai2thor-metadata /path/to/ai2thor-object-metadata.json",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--procthor-root", type=Path, default=None, help="ProcTHOR checkout root or its databases directory.")
    parser.add_argument("--ai2thor-metadata", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    ontology = load_ontology()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    procthor_root = args.procthor_root or default_procthor_root()
    ai2thor_metadata = args.ai2thor_metadata or (resolve_database_root(procthor_root) / "ai2thor-object-metadata.json")
    procthor = extract_procthor(procthor_root, ontology)
    write_json(output / "procthor_stats.json", procthor)
    combined: dict[str, Any] = {"procthor": procthor}
    if ai2thor_metadata and ai2thor_metadata.exists():
        ai2thor = extract_ai2thor_metadata(ai2thor_metadata, ontology)
        write_json(output / "ai2thor_stats.json", ai2thor)
        combined["ai2thor"] = ai2thor
    manifest = {
        "extractor": "backend.tools.extract_external_stats",
        "extractor_version": "0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ontology_version": ontology.version,
        "sources": {
            "procthor": {"root": str(procthor_root), "revision": git_revision(procthor_root)},
            "ai2thor_metadata": ({"path": str(ai2thor_metadata), "sha256": sha256(ai2thor_metadata)} if ai2thor_metadata and ai2thor_metadata.exists() else None),
        },
        "room_graph_available": False,
        "room_graph_note": "No source supplied in this run contains multi-room adjacency edges.",
        "license": "Upstream ProcTHOR/AI2-THOR/PRIOR licenses apply; derived aggregate statistics only.",
    }
    # Stable split artifacts let template generation consume one concern at a time.
    for source_name, data in combined.items():
        prefix = source_name.lower().replace(" ", "_")
        rows = data.get("room_object_stats", [])
        write_json(output / f"{prefix}_room_object_counts.json", rows)
        totals: Counter[str] = Counter()
        for row in rows:
            totals[row["room_type"]] += int(row.get("count", 0))
        probabilities = [
            {**row, "probability": round(row["count"] / totals[row["room_type"]], 8) if totals[row["room_type"]] else 0.0}
            for row in rows
        ]
        write_json(output / f"{prefix}_room_object_probabilities.json", probabilities)
        write_json(output / f"{prefix}_object_parent_counts.json", data.get("object_parent_stats", []))
        write_json(output / f"{prefix}_object_capability_stats.json", data.get("object_capability_stats", []))
    write_json(output / "source_manifest.json", manifest)
    write_json(output / "external_stats.json", combined)
    write_report(output / "external_room_statistics.md", combined, manifest)
    (output / "external_dataset_statistics.md").write_text(
        markdown_report(combined, manifest), encoding="utf-8"
    )
    print(json.dumps({"output": str(output), "sources": list(combined)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
