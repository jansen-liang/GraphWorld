"""Build a review queue for high-value external object priors."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.core.assets.object_library import resolve_object_key
from backend.core.assets.task_library import TASK_SKILLS
from backend.generation.ontology import load_ontology


TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
ACTIONABLE = {"needs_mapping", "needs_template", "needs_rule"}
STATUS_WEIGHT = {"needs_mapping": 20, "needs_template": 15, "needs_rule": 10, "ready": 3}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def task_references(ontology) -> Counter[str]:
    references: Counter[str] = Counter()
    for text in _strings(TASK_SKILLS):
        for token in TOKEN_RE.findall(text.lower()):
            normalized = ontology.normalize("objects", token)
            key = resolve_object_key(normalized or token)
            references[key] += 1
    return references


def skill_reference_names(object_names: list[str], ontology) -> dict[str, set[str]]:
    names = {name for name in object_names if name}
    result: dict[str, set[str]] = {name: set() for name in names}
    for skill in TASK_SKILLS:
        tokens = set(TOKEN_RE.findall(" ".join(_strings(skill)).lower()))
        for name in names:
            if name.lower() in tokens or any(ontology.normalize("objects", token) == name for token in tokens):
                result[name].add(str(skill.get("name")))
    return result


def build(audit_path: Path) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    ontology = load_ontology()
    references = task_references(ontology)
    reference_names = skill_reference_names(list(references), ontology)
    rows = []
    for row in audit["objects"]:
        status = row["status"]
        if status not in ACTIONABLE:
            continue
        object_type = row.get("object_type")
        raw_labels = row.get("raw_labels", [])
        matching_refs = sum(references.get(name, 0) for name in [object_type, *raw_labels] if name)
        evidence = int(row.get("evidence_count", 0) or 0)
        # Task references dominate frequency: a rare required object is still
        # more valuable to repair than a frequent decorative object.
        score = evidence + matching_refs * 100
        if status == "needs_mapping" and matching_refs:
            action = "add_ontology_mapping_then_reaudit"
        elif status == "needs_mapping":
            action = "review_mapping_or_defer"
        elif status == "needs_template":
            action = "design_object_template_then_validate"
        else:
            action = "review_allowed_rooms_parents_functional_class"
        names = [name for name in [object_type, *raw_labels] if name]
        matching_names = sorted({skill for name in names for skill in reference_names.get(name, set())})
        rows.append({
            "object_type": object_type,
            "raw_labels": raw_labels,
            "status": status,
            "priority_score": score,
            "evidence_count": evidence,
            "task_reference_count": matching_refs,
            "task_reference_names": matching_names,
            "allowed_rooms": row.get("allowed_rooms", []),
            "allowed_parents": row.get("allowed_parents", []),
            "functional_class": row.get("functional_class", []),
            "issues": row.get("issues", []),
            "recommended_action": action,
        })
    rows.sort(key=lambda item: (-item["priority_score"], -item["evidence_count"], item.get("object_type") or item["raw_labels"][0]))
    return {
        "schema_version": "0.1",
        "source_audit": str(audit_path),
        "policy": "priority_score = evidence_count + 100 * task_reference_count; task references dominate decorative frequency",
        "task_reference_counts": dict(references),
        "queue": rows,
    }


def markdown(result: dict[str, Any], limit: int = 40) -> str:
    lines = ["# Object Prior 处理队列", "", "排序规则：`evidence_count + 100 * task_reference_count`。任务引用优先于单纯出现频率。", "", "| 排名 | 对象 | 状态 | 分数 | 外部证据 | 任务引用 | 建议动作 |", "|---:|---|---|---:|---:|---:|---|"]
    for index, row in enumerate(result["queue"][:limit], 1):
        name = row.get("object_type") or ", ".join(row["raw_labels"])
        lines.append(f"| {index} | {name} | `{row['status']}` | {row['priority_score']} | {row['evidence_count']} | {row['task_reference_count']} | {row['recommended_action']} |")
    lines += ["", "## 处理顺序", "", "1. 优先处理有任务引用的对象。", "2. 再处理高频 `needs_mapping` 对象，补 ontology alias。", "3. 对映射后仍不存在的对象补 `ObjectTemplate`。", "4. 对已有模板但出现规则冲突的对象审查房间、parent 和功能能力。", "5. 低频且无任务引用对象进入 deferred，不阻塞当前生成器。", ""]
    return "\n".join(lines)


def manual_decisions(result: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row for row in result["queue"]
        if row["status"] in {"needs_mapping", "needs_template"}
    ]
    rows.sort(key=lambda item: (-item["evidence_count"], item.get("object_type") or item["raw_labels"][0]))
    return {
        "schema_version": "0.1",
        "purpose": "Objects that cannot be safely mapped to an existing core template without human semantic approval.",
        "decisions": [{
            "raw_labels": row["raw_labels"],
            "object_type": row.get("object_type"),
            "status": row["status"],
            "evidence_count": row["evidence_count"],
            "allowed_rooms": row.get("allowed_rooms", []),
            "allowed_parents": row.get("allowed_parents", []),
            "functional_class": row.get("functional_class", []),
            "task_reference_names": row.get("task_reference_names", []),
            "decision_needed": "选择已有模板映射、批准新增 ObjectTemplate，或标记 deferred/unsupported。",
        } for row in rows],
    }


def manual_markdown(payload: dict[str, Any]) -> str:
    lines = ["# 缺失模板人工决策清单", "", "以下对象无法在不改变语义的情况下自动映射到现有 `OBJECT_LIBRARY`。每项需要选择：复用已有模板、创建新模板，或 deferred/unsupported。", "", "| 原始对象 | 证据 | 房间 | parent | 功能 | 任务引用 |", "|---|---:|---|---|---|---|"]
    for row in payload["decisions"]:
        lines.append(f"| {', '.join(row['raw_labels'])} | {row['evidence_count']} | {', '.join(row['allowed_rooms'])} | {', '.join(row['allowed_parents'])} | {', '.join(row['functional_class'])} | {', '.join(row['task_reference_names']) or '-'} |")
    lines += ["", "## 决策字段", "", "- `reuse:<template>`：复用已有模板并补 alias。", "- `new_template`：进入 ObjectTemplate 设计。", "- `deferred`：暂不生成，仅保留外部统计。", "- `unsupported`：当前 GraphWorld 运行时不支持。", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=ROOT / "backend/data/generation_priors/object_prior_audit.json")
    parser.add_argument("--output", type=Path, default=ROOT / "backend/data/generation_priors/object_prior_queue.json")
    args = parser.parse_args()
    result = build(args.audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(result), encoding="utf-8")
    decisions = manual_decisions(result)
    decisions_path = args.output.with_name("manual_template_decisions.json")
    decisions_path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    decisions_path.with_suffix(".md").write_text(manual_markdown(decisions), encoding="utf-8")
    print(json.dumps({"queue_count": len(result["queue"]), "top": result["queue"][:10], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
