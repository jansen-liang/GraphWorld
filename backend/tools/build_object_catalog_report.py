"""Build the auditable external-label -> canonical object catalog report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from backend.core.assets.object_catalog import resolve_catalog_label
from backend.core.assets.object_library import OBJECT_LIBRARY


ROOT = Path(__file__).resolve().parents[2]


def build(input_path: Path) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    rows = []
    source_rows = payload.get("decisions") or payload.get("objects") or []
    for item in source_rows:
        labels = item.get("raw_labels") or [item.get("object_type")]
        for label in labels:
            if not label:
                continue
            resolution = resolve_catalog_label(label)
            rows.append({
                "raw_label": resolution.raw_label,
                "disposition": resolution.disposition.value,
                "canonical_type": resolution.canonical_type,
                "reason": resolution.reason,
                "evidence_count": int(item.get("evidence_count") or 0),
                "allowed_rooms": sorted(item.get("allowed_rooms") or []),
                "allowed_parents": list(item.get("allowed_parents") or []),
                "functional_class": sorted(item.get("functional_class") or item.get("functional_class_candidates") or []),
            })
    rows.sort(key=lambda row: (-row["evidence_count"], row["raw_label"]))
    counts = Counter(row["disposition"] for row in rows)
    return {
        "schema_version": "object-catalog-1",
        "canonical_template_count": len(OBJECT_LIBRARY),
        "external_candidate_count": len(rows),
        "disposition_counts": dict(sorted(counts.items())),
        "rows": rows,
        "policy": {
            "template": "已有正式 ObjectTemplate。",
            "alias": "外部名称合并到已有 canonical template。",
            "new_template_candidate": "当前语义可继续设计，但需要明确状态、能力和放置规则。",
            "deferred": "依赖尚未实现的领域系统，暂不进入生成运行时。",
            "unsupported": "不是当前运行时交互对象。",
        },
    }


def markdown(result: dict) -> str:
    lines = [
        "# Canonical Object Catalog Report", "",
        f"- 正式模板：`{result['canonical_template_count']}`",
        f"- 外部候选标签：`{result['external_candidate_count']}`", "",
        "| 归宿 | 数量 |", "|---|---:|",
    ]
    for key, value in result["disposition_counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines += ["", "| 外部标签 | 归宿 | canonical | 证据 | 房间 | parent | 原因 |", "|---|---|---|---:|---|---|---|"]
    for row in result["rows"]:
        lines.append(
            f"| {row['raw_label']} | `{row['disposition']}` | {row.get('canonical_type') or ''} | "
            f"{row['evidence_count']} | {', '.join(row['allowed_rooms'])} | "
            f"{', '.join(row['allowed_parents'])} | {row['reason']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "backend/data/generation_priors/home_candidates.json")
    parser.add_argument("--json-output", type=Path, default=ROOT / "backend/data/generation_priors/object_catalog_report.json")
    parser.add_argument("--markdown-output", type=Path, default=ROOT / "backend/data/generation_priors/object_catalog_report.md")
    args = parser.parse_args()
    result = build(args.input)
    args.json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"templates": result["canonical_template_count"], "candidates": result["external_candidate_count"], "dispositions": result["disposition_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
