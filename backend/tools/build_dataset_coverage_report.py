"""Build the cross-dataset coverage report for the generation pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backend/data/external_stats/dataset_coverage_report.md"))
    args = parser.parse_args()
    activity = json.loads(Path("backend/data/activity_stats.json").read_text(encoding="utf-8"))
    house = json.loads(Path("backend/data/house_json_stats.json").read_text(encoding="utf-8"))
    lines = [
        "# 外部数据覆盖审计",
        "",
        f"生成时间：`{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## 四条统计线",
        "",
        "| 统计线 | 当前证据 | 已得到什么 | 仍缺什么 | 是否可直接进入模板 |",
        "|---|---|---|---|---|",
        f"| ProcTHOR/AI2-THOR | 已安装数据库 + metadata | 4 类 Home 房间、对象、parent、能力；AI2-THOR 120 个家庭房间实例 | 多房间 house 语义邻接、Office 及领域房间 | 部分可用 |",
        f"| AI2-THOR house JSON | 11 个旧 house JSON | 39 个房间、21 门、33 窗、结构对象资产 | 房间 type 全为空，不能做语义房间统计 | 仅结构审计 |",
        f"| 3D-FRONT/3D-FUTURE | 当前未取得数据文件 | 已确认适合 Home/Office 布局先验 | 官方数据获取/许可、场景解析 | 暂不可用 |",
        f"| VirtualHome | 当前未取得数据文件 | 无可靠统计 | 活动、角色、房间、动作序列 | 暂不可用 |",
        f"| ALFRED | 本地仓库 JSON 2.1.0 | {activity['alfred']['records']} 条轨迹、7 类已识别任务模板、21975 条任务描述、131406 条高层步骤 | 部分目录 split 标识不属于任务类型；完整低层 plan/PDDL 需要 full dataset；它主要是 Home | 可用于任务候选 |",
        "| Hospital/Supermarket/Factory | GraphWorld 现有手工场景 | 已有领域 room/object/event 规则 | 外部真实领域数据先验 | 不能称为外部统计 |",
        "",
        "## ALFRED 结论",
        "",
        "ALFRED 可以补任务和动作序列，但不能补 GraphWorld 的医院、超市、工厂房间模板。它的任务主要是家庭环境中的 pick/place、clean、heat、cool、slice、look 等操作。",
        "",
        "当前高频任务模板包括：",
        "",
        "- `pick_two_obj_and_place`",
        "- `pick_and_place_simple`",
        "- `pick_and_place_with_movable_recep`",
        "- `pick_cool_then_place_in_recep`",
        "- `pick_heat_then_place_in_recep`",
        "- `pick_clean_then_place_in_recep`",
        "- `look_at_obj_in_light`",
        "",
        "## 3D 数据结论",
        "",
        "3D-FRONT/3D-FUTURE 不是普通 GitHub 代码仓库即可替代的数据。它们通常需要从官方渠道获取数据文件并遵守数据许可，因此当前不能凭代码仓库状态声称已经完成统计。下一步需要准备授权数据目录后运行 extractor。",
        "",
        "## 领域数据结论",
        "",
        "目前 Hospital、Supermarket、Factory 的数据来自 GraphWorld 自己的手工场景和事件库，不是外部真实数据统计。它们可以继续用于引擎验证，但必须在最终报告中标记为 `hand-authored/domain-rule`。",
        "",
        "## 总判断",
        "",
        "```text",
        "当前数据足够：Home 初版 RoomTypeSpec/ObjectTemplate、ALFRED 任务候选、自动放置规则原型",
        "当前数据不够：最终房间图、Office 布局、Hospital/Supermarket/Factory 外部模板、NPC 活动先验",
        "```",
        "",
        "因此不能把当前所有候选直接合并进 `backend/core`。应先合并通过 ontology/动作/可解性审核的 Home 子集，同时保留外部数据获取任务。",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
