# 外部数据集统计报告

本报告由 `backend.tools.extract_external_stats` 自动生成。统计读取结构化 JSON，不启动 Unity，也不复制 3D 资产。

## 数据源与范围

- extractor version: `0.1`
- ontology version: `0.1`
- generated at (UTC): `2026-08-22T08:31:06.297802+00:00`
- ProcTHOR: placement annotations、receptacles、asset database，以及包内随附的 AI2-THOR object metadata。
- AI2-THOR：本轮使用 ProcTHOR 包内的 AI2-THOR metadata 导出；独立 AI2-THOR 源码仓库不包含完整可直接统计的房屋数据集。
- AI2-THOR 的 `robothor` 场景族不作为房间类型，已从房间先验中排除。
- 许可：原始数据仍受 ProcTHOR/AI2-THOR 上游许可约束；本仓库只保存派生聚合结果。

## 核心统计

| 数据源 | 房间实例 | 房间类型 | 房间-对象记录 | parent 记录 | capability 对象 | 房间图 |
|---|---:|---:|---:|---:|---:|---|
| ProcTHOR | 先验库 | 4 | 168 | 359 | 108 | 不可用 |
| AI2-THOR metadata | 120 | 4 | 208 | 424 | 116 | 不可用 |

## 房间内对象先验

ProcTHOR 的 `count` 是 placement annotation 中的对象实例聚合，不是本次生成的房屋数量。AI2-THOR metadata 的 `frequency_per_scene` 是每类房间实例中的平均对象出现次数。

| 房间 | ProcTHOR 总实例 | AI2-THOR metadata 房间实例 | AI2-THOR 对象记录 |
|---|---:|---:|---:|
| bathroom | 48 | 30 | 1083 |
| bedroom | 69 | 30 | 1228 |
| kitchen | 87 | 30 | 2088 |
| living_room | 64 | 30 | 1271 |

## 可直接复用的先验

- `allowed_rooms`：可从四类家庭房间的对象出现统计初始化，但应设置最小出现次数/置信度阈值。
- `allowed_parents`：可从 ProcTHOR `receptacles.json` 和 AI2-THOR `parentReceptacles` 合并得到；两者是候选关系先验，不是 GraphWorld 运行时合法性的最终判定。
- `functional_class` / capability：当前数据可以支持 `pickupable`、`receptacle`、`openable`、`toggleable`、`moveable` 等字段的观察统计；GraphWorld 仍需把它们映射到现有动作和状态闭环。

## 明确缺口

- ProcTHOR 数据库只提供四类家庭房间的对象放置权重；不能直接推导 Hospital、Supermarket、Factory 的真实领域房间先验。
- 本轮两个输入都没有多房间 house 实例及门/连接边，因此没有生成房间共现或邻接统计；不能用单房间 metadata 伪造房间图。
- AI2-THOR metadata 中的 `robothor` 是机器人场景族，不应直接作为 GraphWorld 房间类型。
- 外部 capability 只是观察先验，任务是否可解仍要经过 GraphWorld 规则和 PDDL/规划器验证。

## 产物

- `backend/data/external_stats/procthor_stats.json`
- `backend/data/external_stats/ai2thor_stats.json`
- `backend/data/external_stats/external_stats.json`
- `backend/data/external_stats/source_manifest.json`
- `backend/data/external_stats/procthor_room_object_counts.json` / `procthor_room_object_probabilities.json`
- `backend/data/external_stats/procthor_object_parent_counts.json` / `procthor_object_capability_stats.json`
- `backend/data/external_stats/ai2thor_room_object_counts.json` / `ai2thor_room_object_probabilities.json`
- `backend/data/external_stats/ai2thor_object_parent_counts.json` / `ai2thor_object_capability_stats.json`

重新生成：

```bash
/home/swzz/anaconda3/gra/bin/python -m backend.tools.extract_external_stats \
  --procthor-root /path/to/ProcTHOR \
  --ai2thor-metadata /path/to/ai2thor-object-metadata.json
```
