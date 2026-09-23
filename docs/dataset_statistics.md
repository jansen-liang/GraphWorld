# GraphWorld 数据集统计与特点

本文统计 `backend/data/sg_output/simple_graph` 中的静态场景 JSON，并把静态数据、运行时 schema 和实验输出分开。统计可通过以下命令复现：

```bash
python backend/tools/summarize_scene_dataset.py --format markdown
python backend/tools/summarize_scene_dataset.py --format json
```

## 1. 统计口径

GraphWorld 当前包含 5 个基础场景域：家庭、医院、超市、办公室和工厂。每个场景域包含一个基础场景以及 `compact_cleaning`、`normal_logistics`、`spread_device` 三个 profile，因此共有 20 个静态场景实例。

Profile 是在相同语义场景上的拓扑、对象分布和任务压力变体，不能表述成 20 个独立场景域。`backend/data/experiments` 下的 replay、metrics 和 checkpoint 是运行结果，也不计入静态数据集规模。

## 2. 总体规模

| 指标 | 当前数量 | 说明 |
| --- | ---: | --- |
| 基础场景域 | 5 | home、hospital、supermarket、office、factory |
| 静态场景实例 | 20 | 5 个 base + 15 个 profile variant |
| 节点记录 | 1,020 | 包含不同 profile 中重复出现的实体 |
| 边记录 | 1,227 | 包含不同 profile 中重复出现的关系 |
| 唯一节点 ID | 235 | 跨 profile 去重 |
| 房间节点记录 | 156 | 跨实例累计 |
| 唯一房间 ID | 29 | 跨 profile 去重 |
| 语义类型 | 80 | 包含 room、floor、human |
| 对象语义类型 | 77 | 排除 room、floor、human、robot |
| 对象模板（历史静态统计） | 72 | 该报告生成时的 `OBJECT_LIBRARY` 快照；不是当前模板总数 |
| 状态维度 | 18 | 运行时 schema 支持；静态 JSON 实际出现 14 种 |
| 状态赋值记录 | 1,623 | 所有节点 `states` 字段累计 |
| JSON 声明动作 | 12 | 运行时核心实际支持 9 种 |
| JSON 关系类型 | 9 | 关系枚举定义 18 种，其中 7 种有评分规格 |
| NPC 事件类型 | 56 | 包含 34 个前置条件和 290 个成功/失败效果 |
| 角色日程 | 14 | 共 99 个日程项，覆盖全部 56 种事件 |

节点类型分布为：635 个 `fixed_object`、217 个 `movable_object`、156 个 `room` 和 12 个静态 `human` 节点。机器人以及多数场景的人类角色会在运行开始时注入，因此静态 JSON 数量不等于 episode 中的实际 actor 数量。

对象目录已在后续版本扩展到 **115 个正式模板**。对象名称、外部标签映射和暂缓候选以 [`backend/data/generation_priors/object_catalog_report.md`](../backend/data/generation_priors/object_catalog_report.md) 为准；本节的 72 是历史场景快照，不能用来判断当前对象库是否缺少模板。

## 3. 基础场景

| 场景 | 节点 | 边 | 房间 | 场景内语义类型 | 场景内状态维度 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Factory | 37 | 43 | 8 | 21 | 7 |
| Home | 75 | 92 | 7 | 40 | 14 |
| Hospital | 72 | 89 | 10 | 33 | 9 |
| Office | 34 | 39 | 7 | 20 | 9 |
| Supermarket | 34 | 39 | 7 | 21 | 9 |
| 合计 | 252 | 302 | 39 | 跨场景去重后 77 | 跨场景去重后 14 |

Home 的状态和对象覆盖最丰富，Hospital 的空间规模最大。Office、Supermarket 和 Factory 更紧凑，主要通过领域对象、NPC 工作流和 profile 压力形成差异。

## 4. 状态、动作与关系

运行时定义 18 个状态维度：

```text
cycle_remaining, fill_level, folded, is_blocked, is_broken,
is_burnt, is_cooked, is_dirty, is_frozen, is_full, is_on,
is_open, is_pressed, is_rotten, is_wet, is_wilted,
temperature, vitality
```

静态场景实际覆盖其中 14 个；`is_blocked`、`is_broken`、`is_burnt`、`is_frozen` 尚未实例化。这意味着 schema 能表达这些状态，但当前数据不能评测相关能力。

核心运行时支持 9 种机器人动作：

```text
move, pick, place, press, open, close, brush, fold, dump, wait
```

场景 JSON 与核心 `ActionType` 现在统一为 9 个可执行动作：`move`、`pick`、`place`、`press`、`open`、`close`、`brush`、`fold`、`dump`。

静态 JSON 使用 9 种关系：`at`、`connected`、`contains`、`controls`、`in`、`inside_room`、`near`、`on`、`part_of`。其中 `inside_room` 和 `part_of` 不在当前 `SpatialRelation` 枚举内，是需要统一的 schema 缺口。

## 5. 数据特色

GraphWorld 的主要特色不是场景数量，而是同一个图同时承担数据表示和运行时状态：

1. **持续动态世界，而非独立 episode。** 人类日程、设备周期和机器人动作连续改变同一个世界，任务从状态偏离和人类活动阻塞中产生，而不是每轮由外部重新给定。
2. **图原生闭环。** 房间、对象、设备、人类和机器人共享层次化图；感知、动作合法性、状态转移、事件和评分都读取并修改同一份图状态。
3. **状态、空间和人类活动联合评测。** 指标不仅判断某个任务是否完成，还持续计算状态健康度、物体空间秩序和人类事件成功率，并记录阻塞是否被机器人恢复。
4. **跨领域。** 除家庭外，还覆盖医院、超市、办公室和工厂的补给、清洁、归档、物流及设备工作流。
5. **可控压力变体。** 三种 profile 在保持领域语义的同时改变对象集中度、物流距离和设备链长度，便于做受控消融。
6. **可审计。** JSON 场景、事件前置条件/效果、动作 schema 和评分矩阵都是显式符号结构，能够追溯一次失败来自哪个状态、关系或人类前置条件。

## 6. 与相关数据集的区别

| 维度 | GraphWorld | AI2-THOR / ProcTHOR | ALFRED / BEHAVIOR-1K | VirtualHome / Habitat 3.0 |
| --- | --- | --- | --- | --- |
| 核心单位 | 持续演化的动态图世界 | 可交互 3D 场景或程序化房屋 | 给定任务或活动 episode | 活动程序或人机共居仿真 |
| 任务来源 | 人类活动产生的偏离和阻塞 | 通常由上层任务定义 | 数据集明确给定目标 | 脚本、任务或人类行为配置 |
| 时间范围 | 多步持续维护，不要求任务后重置 | 多为 episode 内交互 | 以任务成功为终点 | 支持动态人类，但通常仍按任务评测 |
| 场景域 | 5 个生活与工作域 | 主要是家庭室内 | 主要是家庭日常活动 | 家庭或人机共居为主 |
| 世界表示 | 可执行层次图、状态和关系 | 3D 几何、物理和对象 metadata | 任务谓词、视觉和物理状态 | 活动程序、3D 状态或 avatar |
| 评价重点 | 长期状态、空间秩序、人类事件、阻塞恢复 | 导航和对象交互 | 任务成功率与执行效率 | 活动完成或人机协作 |
| 主要优势 | 长期维护闭环、跨域、因果可审计 | 视觉真实性、物理与大规模生成 | 活动规模和任务复杂度 | 人类行为及具身共处 |
| 主要短板 | 场景少、手工构建、暂无高保真 3D | 长期自主任务发现较弱 | 通常依赖外部给定任务 | 统一长期维护评分较弱 |

因此，GraphWorld 更适合定位为 **动态图运行时与长期维护 benchmark**，而不是与 ProcTHOR、3D-FRONT 或 BEHAVIOR-1K 比拼原始场景/活动数量。它与这些数据集更接近互补关系：其他系统提供视觉资产、物理环境或活动语料，GraphWorld 提供长期状态演化、任务涌现和统一评测闭环。

## 7. 当前数据缺口

统计同时暴露出以下问题：

- 5 个基础场景仍然偏少，15 个 profile 是受控变体而非新领域实例。
- 按对象 alias 解析后，16 种场景对象语义没有对应 `OBJECT_LIBRARY` 模板，12 个已注册模板没有在场景中实例化。
- 非家庭房间尚未完整进入统一 `ROOM_LIBRARY`；当前只有 6 个家庭房间模板。
- 4 个状态维度未被任何静态场景覆盖。
- 当前动作声明与核心动作 schema 已统一为 9 种；后续新增动作必须同时补齐 `ActionType`、validator、transition 和任务使用场景。
- `inside_room/part_of` 与关系枚举不一致。
- 当前完整性检查未发现重复节点 ID、缺失 parent 或悬空边，但还缺少 object-room compatibility、状态可达性和事件覆盖率验证。

下一阶段的数据工作应优先补齐 schema 一致性和自动 coverage report，再扩展场景数量。否则简单增加 JSON 文件会放大已有 taxonomy 与运行时不一致的问题。

## 8. 外部 Object Prior 审计

外部统计先通过以下命令审计，再进入模板候选，不会自动修改 `backend/core`：

```bash
/home/swzz/anaconda3/gra/bin/python -m backend.tools.audit_object_priors \
  --stats-dir backend/data/external_stats \
  --output backend/data/generation_priors/object_prior_audit.json
```

输出同时包含 JSON 和 Markdown 报告。状态含义如下：

- `ready`：已有 core 模板，房间、parent 和功能先验能被当前 ontology/runtime 解释。
- `needs_mapping`：外部标签尚未映射到 ontology。
- `needs_template`：对象可识别，但 `OBJECT_LIBRARY` 中没有模板。
- `needs_rule`：已有模板，但房间、parent 或功能能力仍需规则审查。
- `no_external_prior`：core 模板存在，但当前外部数据没有证据。
