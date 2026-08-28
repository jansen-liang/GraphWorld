"""Audit external object priors against GraphWorld ontology and core contracts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.core.assets.object_library import OBJECT_LIBRARY, resolve_object_key
from backend.core.assets.object_priors import load_object_priors
from backend.generation.ontology import load_ontology


FUNCTIONS = {"pickupable", "receptacle", "openable", "toggleable", "moveable"}
FUNCTION_TO_CAPABILITY = {
    "pickupable": "pickable",
    "receptacle": "place_target",
    "openable": "openable",
    "toggleable": "switchable",
    "moveable": "moveable",
}
FUNCTION_TO_ACTION = {
    "pickupable": "pick",
    "receptacle": "place",
    "openable": "open",
    "toggleable": "press",
    "moveable": "move",
}
STRUCTURAL_PARENTS = {"floor", "room", "agent", "human", "robot"}
NON_OBJECT_TYPES = {"floor", "room", "human", "robot"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_true(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, dict) and int(value.get("true", 0) or 0) > int(value.get("false", 0) or 0)


def _merge_stats(stats_dir: Path, ontology) -> dict[str, dict[str, Any]]:
    """Merge source rows while retaining source evidence and raw labels."""
    merged: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "raw_labels": set(), "rooms": Counter(), "parents": Counter(),
        "functions": set(), "evidence_count": 0, "sources": set(),
    })
    for filename, source in (
        ("procthor_stats.json", "procthor"),
        ("ai2thor_stats.json", "ai2thor"),
    ):
        path = stats_dir / filename
        if not path.exists():
            continue
        data = _read(path)
        for row in data.get("room_object_stats", []):
            raw = str(row.get("object_type") or "").strip()
            if raw.lower() in NON_OBJECT_TYPES:
                continue
            normalized = ontology.normalize("objects", raw)
            key = normalized or f"unmapped::{raw.lower()}"
            item = merged[key]
            item["raw_labels"].add(raw)
            item["rooms"][str(row.get("room_type") or "")] += int(row.get("count", 0) or 0)
            item["evidence_count"] += int(row.get("count", 0) or 0)
            item["sources"].add(source)
        for row in data.get("object_parent_stats", []):
            raw = str(row.get("object_type") or "").strip()
            if raw.lower() in NON_OBJECT_TYPES:
                continue
            normalized = ontology.normalize("objects", raw)
            key = normalized or f"unmapped::{raw.lower()}"
            item = merged[key]
            item["raw_labels"].add(raw)
            item["parents"][str(row.get("parent_type") or "")] += int(row.get("count", 0) or 0)
            item["sources"].add(source)
        for row in data.get("object_capability_stats", []):
            raw = str(row.get("object_type") or "").strip()
            if raw.lower() in NON_OBJECT_TYPES:
                continue
            normalized = ontology.normalize("objects", raw)
            key = normalized or f"unmapped::{raw.lower()}"
            item = merged[key]
            item["raw_labels"].add(raw)
            item["functions"].update(field for field in FUNCTIONS if _is_true(row.get(field)))
            item["sources"].add(source)
    return merged


def _audit_one(key: str, evidence: dict[str, Any], ontology) -> dict[str, Any]:
    if key.startswith("unmapped::"):
        return {
            "object_type": None,
            "raw_labels": sorted(evidence["raw_labels"]),
            "status": "needs_mapping",
            "evidence_count": evidence["evidence_count"],
            "sources": sorted(evidence["sources"]),
            "allowed_rooms": sorted(evidence["rooms"]),
            "allowed_parents": [name for name, _ in evidence["parents"].most_common()],
            "functional_class": sorted(evidence["functions"]),
            "issues": ["ontology_mapping_missing"],
        }
    template_key = resolve_object_key(key)
    if template_key not in OBJECT_LIBRARY:
        return {
            "object_type": key,
            "raw_labels": sorted(evidence["raw_labels"]),
            "status": "needs_template",
            "evidence_count": evidence["evidence_count"],
            "sources": sorted(evidence["sources"]),
            "allowed_rooms": sorted(evidence["rooms"]),
            "allowed_parents": [name for name, _ in evidence["parents"].most_common()],
            "functional_class": sorted(evidence["functions"]),
            "issues": ["core_object_template_missing"],
        }

    template = OBJECT_LIBRARY[template_key]
    unknown_rooms = sorted(room for room in evidence["rooms"] if ontology.normalize("rooms", room) is None)
    unknown_parents = sorted(
        parent for parent in evidence["parents"]
        if parent not in STRUCTURAL_PARENTS and ontology.normalize("objects", parent) is None
    )
    capabilities = {cap.name for cap in template.capabilities}
    actions = set(template.interactive_actions)
    unsupported = sorted(
        function for function in evidence["functions"]
        if FUNCTION_TO_CAPABILITY[function] not in capabilities
        and FUNCTION_TO_ACTION[function] not in actions
    )
    issues = []
    if unknown_rooms:
        issues.append("room_rule_unmapped")
    if unknown_parents:
        issues.append("parent_rule_unmapped")
    if unsupported:
        issues.append("functional_class_not_supported")
    return {
        "object_type": template_key,
        "raw_labels": sorted(evidence["raw_labels"]),
        "status": "ready" if not issues else "needs_rule",
        "evidence_count": evidence["evidence_count"],
        "sources": sorted(evidence["sources"]),
        "allowed_rooms": sorted(evidence["rooms"]),
        "allowed_parents": [name for name, _ in evidence["parents"].most_common()],
        "functional_class": sorted(evidence["functions"]),
        "core_capabilities": sorted(capabilities),
        "core_actions": sorted(actions),
        "unknown_rooms": unknown_rooms,
        "unknown_parents": unknown_parents,
        "unsupported_functional_class": unsupported,
        "issues": issues,
    }


def audit(stats_dir: Path) -> dict[str, Any]:
    ontology = load_ontology()
    merged = _merge_stats(stats_dir, ontology)
    rows = [_audit_one(key, evidence, ontology) for key, evidence in sorted(merged.items())]
    external_keys = {row["object_type"] for row in rows if row["object_type"]}
    for object_type in sorted(set(OBJECT_LIBRARY) - external_keys):
        rows.append({"object_type": object_type, "raw_labels": [], "status": "no_external_prior", "evidence_count": 0, "sources": [], "issues": ["external_evidence_missing"]})
    rows.sort(key=lambda row: (row["status"], row.get("object_type") or row["raw_labels"][0]))
    status_counts = Counter(row["status"] for row in rows)
    return {
        "schema_version": "0.2",
        "stats_dir": str(stats_dir),
        "ontology_version": ontology.version,
        "core_object_count": len(OBJECT_LIBRARY),
        "external_prior_count": len(merged),
        "audited_object_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "objects": rows,
        "policy": {
            "ready": "已有 core 模板，且房间、parent、功能先验都能被当前 ontology/runtime 解释。",
            "needs_mapping": "外部标签尚未映射到 ontology，不进入模板生成。",
            "needs_template": "已映射或可识别，但 OBJECT_LIBRARY 没有对应模板。",
            "needs_rule": "有模板，但房间/parent/功能先验仍需规则审查。",
            "no_external_prior": "core 模板存在，但当前外部数据没有证据；不能据此判定不合理。",
        },
        "note": "审计只生成报告，不修改 backend/core；外部先验不是运行时动作合法性。",
    }


def markdown(result: dict[str, Any]) -> str:
    lines = ["# Object Prior Audit", "", "本报告审计外部 ProcTHOR/AI2-THOR 先验能否接入 GraphWorld，不会自动修改 core。", "", "## 汇总", "", f"- 外部先验对象：`{result['external_prior_count']}`", f"- 审计对象总数（含无外部证据 core 模板）：`{result['audited_object_count']}`", "", "| 状态 | 数量 | 含义 |", "|---|---:|---|"]
    descriptions = result["policy"]
    for status, count in result["status_counts"].items():
        lines.append(f"| `{status}` | {count} | {descriptions[status]} |")
    lines += ["", "## 需要处理的对象", "", "| 对象 | 状态 | 证据 | 房间 | parent | 功能 | 问题 |", "|---|---|---:|---|---|---|---|"]
    for row in result["objects"]:
        if row["status"] in {"ready", "no_external_prior"}:
            continue
        name = row.get("object_type") or ", ".join(row.get("raw_labels", []))
        lines.append(f"| {name} | `{row['status']}` | {row.get('evidence_count', 0)} | {', '.join(row.get('allowed_rooms', []))} | {', '.join(row.get('allowed_parents', []))} | {', '.join(row.get('functional_class', []))} | {', '.join(row.get('issues', []))} |")
    lines += ["", "## 判定边界", "", "- `ready` 只表示可以进入候选生成阶段，不表示已经自动写入 `ObjectTemplate`。", "- `needs_template` 与 `needs_mapping` 是最优先的补齐项。", "- `needs_rule` 需要人工确认 `allowed_rooms`、`allowed_parents` 和 `functional_class`，然后再做任务/PDDL 可解性验证。", "- 当前家庭数据不能证明 Office、Hospital、Supermarket、Factory 的领域先验。", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats-dir", type=Path, default=ROOT / "backend/data/external_stats")
    parser.add_argument("--output", type=Path, default=ROOT / "backend/data/generation_priors/object_prior_audit.json")
    args = parser.parse_args()
    result = audit(args.stats_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"audited_object_count": result["audited_object_count"], "external_prior_count": result["external_prior_count"], "status_counts": result["status_counts"], "output": str(args.output)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
