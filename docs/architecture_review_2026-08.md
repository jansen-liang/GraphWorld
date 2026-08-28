# GraphWorld 当前代码架构梳理与重构建议

> 本文是一次架构审计，不是功能实现方案。除修复审计过程中发现的 `states.py` 重复参数语法错误外，本轮不继续修改运行时代码、模板或生成逻辑。

## 1. 结论先行

GraphWorld 当前实际上包含四条逐渐汇合、但尚未完全统一的链路：

```text
核心语义定义        backend/core
运行时仿真          backend/runtime
数据归一化与统计    backend/generation + backend/tools + backend/data
Web/API 与实验      backend/app + backend/experiments
```

当前最需要解决的不是继续增加物体模板，而是统一以下几个概念：

1. 一个对象的“身份、能力、状态、放置先验、运行时效果”目前分布在多个文件中，边界还不够稳定。
2. `states.py` 仍然是全局状态名集合，而对象实际需要的是按模板生成的局部状态表。
3. 外部数据统计已经产出，但房间图生成器尚未形成；对象放置不能先于房间图生成。
4. `EnvironmentSystem` 目前主要是时间推进器，不应继续扩张成所有环境和领域玩法的总类。
5. 外部标签、正式模板、alias、候选模板和 deferred 对象已经有归档意识，但还需要一个唯一的 canonical catalog 作为权威入口。

建议的长期主链路是：

```text
外部数据
  -> Ontology canonical labels
  -> RoomTypeSpec / ObjectTemplate / StateDefinition
  -> RoomGraphGenerator
  -> ObjectPlacementGenerator
  -> TaskCompiler
  -> PDDL / solvability validator
  -> Runtime Orchestrator
  -> Agent / Evaluation
```

## 2. 仓库模块职责

### 2.1 `backend/core`：领域模型与静态规则

`backend/core` 应当是整个系统的稳定语义内核。它不应该读取外部数据集，也不应该包含具体实验流程。

| 模块 | 当前职责 | 目标职责 |
|---|---|---|
| `actions.py` | 9 个动作枚举和动作说明 | 保持为唯一动作词汇表 |
| `action_schemas.py` | 动作绑定、前置条件和效果 | 保持为运行时动作合法性入口 |
| `states.py` | 全局状态枚举、状态说明、值归一化 | 演进为状态 schema，不直接给所有物体加全部状态 |
| `nodes.py` | Floor、Room、Object、Agent 节点数据结构 | 保持轻量，不承载复杂领域规则 |
| `edges.py` | 空间、包含、控制、动态关系枚举 | 保持关系词汇表和关系元数据 |
| `predicates.py` | 动作和任务使用的查询谓词 | 作为规则层的纯查询函数 |
| `effects.py` | 动作造成的基础图和状态修改 | 只做原子效果，复杂效果交给领域系统 |
| `domain_rules.py` | 洗衣、垃圾、容量等领域规则 | 逐步迁移到领域规则注册表 |
| `timed_transitions.py` | 洗衣、洗碗、晾晒等时间转移 | 逐步变成按系统注册的 transition |
| `scenegraph.py` | 静态 dict-backed SceneGraph | 作为构建/校验工具，不与运行时 SceneGraph 混名 |
| `assets/object_library.py` | 正式对象模板和能力 | ObjectTemplate 的 canonical registry |
| `assets/object_model.py` | ObjectFamily、SystemDependency、PlacementSpec、系统登记 | 模板、能力、系统依赖的 schema 层 |
| `assets/object_priors.py` | 外部数据的房间/parent/能力先验 | 只用于生成排序和候选约束，不做运行时动作验证 |
| `assets/object_catalog.py` | 外部标签归档 | 最终应成为唯一 external label -> canonical type/disposition 入口 |
| `assets/object_registry.py` | deferred 对象及其系统依赖 | deferred/候选对象的生命周期登记 |
| `assets/room_library.py` | 房间规格和家庭 floorplan | RoomTypeSpec、FloorplanTemplate 的 canonical registry |
| `assets/task_library.py` | 任务/技能及相关性 | 任务模板与技能的 canonical registry |
| `assets/npc_library.py` | NPC、活动、前置条件、效果、日程 | NPC 事件模板和活动先验的 canonical registry |

### 2.2 `backend/runtime`：可执行世界

运行时的核心入口是 `backend/runtime/engine/runtime.py`：

```text
SceneGraph
  ├── nodes / edges
  ├── parent_of / room_of
  ├── world_state
  └── event_log

RobotActionSystem
HumanEventSystem
EnvironmentSystem
Perception
Orchestrator
```

当前 `EnvironmentSystem.advance_time()` 做三件事：

1. 执行 `apply_timed_transitions`；
2. 推进 `world_state.step`；
3. 刷新索引和运行时边。

因此它当前更准确的名字是“时间/定时转移推进器”。未来四层系统不应全部塞入这里。

建议目标：

```text
WorldRunner / Orchestrator
  -> TimeSystem
  -> ExternalEventSystem
  -> DomainTransitionSystem
  -> PerceptionSystem
  -> Evaluation hooks
```

初期只需要真正实现 `TimeSystem` 和 `SpaceSystem`。天气、温度、湿度、空气质量、照明、烹饪等先作为依赖声明和系统状态，不要创建没有规则的空实现。

### 2.3 `backend/generation` 与 `backend/tools`：数据生产链

当前生成相关代码主要分散在：

- `backend/generation/ontology/`：标签归一化和映射；
- `extract_external_stats.py`：ProcTHOR/AI2-THOR 统计提取；
- `compile_home_template_candidates.py`：候选编译；
- `build_generation_priors.py`：房间图、共现和 Office 先验；
- `build_object_prior_queue.py`：待审计队列；
- `build_object_catalog_report.py`：候选归档报告；
- `build_scene_variants.py`：现有场景变体修改。

当前还缺少两个正式生成器：

1. `RoomGraphGenerator`：从 RoomTypeSpec、FloorplanTemplate 和房间先验生成合法房间图；
2. `ObjectPlacementGenerator`：在已生成且已校验的房间图上，按 ObjectTemplate、ObjectPrior、容量和共现规则放置对象。

正确顺序必须是：

```text
统计先验
  -> 房间图生成
  -> 房间图校验
  -> 对象放置
  -> 对象/parent/容量校验
  -> 任务编译
```

`backend/data/generation_priors/room_graph.json` 目前只是历史手工场景的统计先验，不是房间图生成器的输出规范，也不是可直接当作房间图使用的实例。

### 2.4 `backend/app`：产品化 API 壳

`backend/app` 负责：

- FastAPI 路由；
- 数据库模型和 repository；
- 场景导入；
- Web runtime adapter；
- run/replay/metric 服务。

它不应定义对象、状态、动作或任务的语义。所有语义应从 `backend/core` 和 `backend/runtime` 获取。

### 2.5 `backend/experiments` 与 `run_experiment.py`

这一层负责实验记录、checkpoint、episode、图表和评估。它不应直接修改模板或场景生成规则。

当前工作区存在较多历史实验修改和 `__pycache__` 变更。后续提交时应把生成数据、实验产物和源码变更分开管理。

## 3. 当前数据模型

### 3.1 场景图

运行时场景的基本结构是：

```text
Scene
├── scene_name
├── nodes[]
│   ├── id
│   ├── node_type
│   ├── semantic_type
│   ├── parent
│   ├── states{}
│   └── interactive_actions[]
├── edges[]
└── world_state{}
```

动态位置主要通过 `parent_of` 和 `relation_of` 索引维护，再由运行时同步动态边。这一设计可以保留，但需要正式文档化为：

```text
静态结构：房间拓扑、楼层、固定控制关系
动态关系：in / on / held_by / near / at
节点状态：对象自身状态
世界状态：时间、事件、系统级状态
```

### 3.2 ObjectTemplate

当前目标 schema 为：

```text
ObjectTemplate
├── identity
│   ├── semantic_type
│   ├── name / name_cn
│   ├── node_type
│   └── variant_of
├── behavior
│   ├── family
│   ├── capabilities[]
│   └── required_systems[]
├── state
│   └── default_states{}
├── placement
│   └── PlacementSpec
└── derived compatibility fields
```

这里的 `ObjectPrior` 不属于模板身份，也不属于动作合法性。它的职责是：

```text
ObjectPrior
├── room_frequency
├── parent_frequency
├── observed_capabilities
├── evidence_count
└── source
```

它只影响“生成时更倾向如何放置”。

### 3.3 状态系统的目标模型

每个实例应该拥有一个由模板生成的局部状态表：

```text
ObjectInstance
├── template_id
├── states
│   ├── control states
│   ├── condition states
│   ├── quantity states
│   ├── thermal states
│   ├── material states
│   └── life states
└── state provenance / transition metadata
```

全局状态注册表只定义“状态是什么”，不能意味着所有对象都拥有该状态。

建议状态分类：

| 类别 | 例子 | 典型适用对象 |
|---|---|---|
| control | `is_open`, `is_on`, `is_pressed` | 门、柜子、设备、按钮 |
| condition | `is_dirty`, `is_wet`, `is_broken`, `folded`, `is_blocked` | 表面、衣物、设备、通道 |
| quantity | `fill_level`, `is_full`, `cycle_remaining` | 容器、垃圾桶、洗衣机 |
| thermal | `temperature`, `thermal_phase`, `is_boiling` | 食物、液体、锅具、热源 |
| material | `is_cooked`, `is_burnt`, `is_frozen`, `is_rotten` | 食材、食品、可变质物 |
| life | `vitality`, `is_wilted` | 植物和生物对象 |

温度应当是物理源状态；`warm`、`hot`、`boiling` 应是离散阶段或派生状态，不应该被无条件写到所有对象上。是否允许沸腾，至少需要：

```text
对象具有 liquid 或 cookable 能力
对象具有 temperature 状态
对象处于热源/烹饪系统作用范围
temperature >= boiling_point(material, pressure)
```

这意味着 `chair`、`book`、`statue` 不应出现 `is_boiling`，而 `water`、`soup`、`pot` 可以在相应系统启用后出现。

### 3.4 Capability 与 State 的关系

能力不等于状态：

```text
Capability: cleanable
  -> 允许拥有 is_dirty
  -> 允许 brush 改变 is_dirty

Capability: cookable
  -> 允许拥有 temperature / is_cooked / is_burnt
  -> 需要 CookingSystem 才能产生加热转移

Capability: liquid
  -> 允许拥有 fill/temperature/boiling 相关状态

Capability: openable
  -> 允许拥有 is_open
  -> 允许 open/close
```

模板应通过 capability 声明状态资格；状态系统负责校验；领域系统负责产生实际转移。

## 4. 四层系统架构

系统按四层组织，而不是按每个状态或每个物体各写一个系统：

```text
Layer 1: Foundation
├── Time
└── Space

Layer 2: Derived Environment
├── DayNight
└── Season

Layer 3: Environment Effects
├── Weather
├── Climate (temperature / humidity / ventilation)
└── AirQuality

Layer 4: Domain Effects
├── Cooking
├── Lighting
├── ToolUse
├── Consumption
├── Media
├── Alarm
└── Payment
```

依赖方向：

```text
Time -> DayNight / Season -> Weather
Space -> reachability / room containment
Weather + Space -> Climate / AirQuality
Time + Temperature -> Cooking
Space + DayNight -> Lighting
```

对象只声明 `required_systems`，不在 `ObjectTemplate` 内写环境传播、沸腾、照明或支付逻辑。

## 5. 任务与 NPC 链路

当前任务相关逻辑分成：

- `task_library.py`：任务/技能定义；
- `maintenance_goals.py`：根据场景状态寻找维护目标；
- `goal_lifecycle.py`：目标快照、完成和冲突；
- `npc_library.py`：活动、前置条件、效果和日程；
- `runtime/engine/runtime.py`：执行人类事件效果；
- `schedule.py`：按时间产生计划活动。

目标架构应为：

```text
Activity / Task Template
  -> Preconditions
  -> Required entities / capabilities
  -> Action plan or PDDL problem
  -> Expected effects
  -> Solvability check
  -> Runtime event / robot goal
```

当前最大风险是任务、NPC 事件和对象模板之间仍有字符串语义耦合。例如事件直接写 `target="sink_kitchen"` 和状态名字，缺少统一的实体需求检查。生成任务前应先检查：

```text
required semantic type exists
required capability exists
required room exists
required parent/target exists
action schema can express the plan
```

## 6. 数据构建 Pipeline

最终数据生成 pipeline 应整理为：

```text
Step 1  外部数据 extractor
        ProcTHOR / AI2-THOR / 其他数据集
        输出原始统计，不修改 core

Step 2  Ontology normalization
        raw label -> canonical room/object/action/state

Step 3  Schema audit
        检查 canonical label 是否有 RoomTypeSpec/ObjectTemplate

Step 4  Prior compilation
        room frequency / parent frequency / co-occurrence / capability prior

Step 5  Room graph generation
        RoomTypeSpec + FloorplanTemplate + room prior

Step 6  Room graph validation
        连通性、邻接约束、禁邻接、入口、领域可达性

Step 7  Object placement
        ObjectTemplate + ObjectPrior + 空间规则 + 容量规则 + 任务需求

Step 8  Task compilation
        根据对象、状态、NPC 活动编译任务

Step 9  Solvability validation
        action validator / PDDL / 反例检查

Step 10 Runtime packaging
        输出可供 Orchestrator、Web API、Agent 和评估读取的 scene JSON
```

核心原则：

- 统计先验不直接成为运行时规则；
- 外部标签不直接成为模板；
- 模板没有对应对象/容器/设备时，任务不能生成；
- 任务没有可执行动作链时，场景不能进入正式数据集；
- 每一步生成都应保留 provenance，能追溯到数据源和规则。

## 7. 当前主要问题清单

### P0：必须先处理

1. `states.py` 的状态 schema 还没有真正成为对象局部状态表生成器。
2. `ObjectTemplate`、节点实例和历史手工 scene JSON 的状态字段没有完全统一。
3. 房间图生成器缺失；`room_graph.json` 只是统计先验。
4. 任务/PDDL 可解性检查尚未成为生成 pipeline 的强制关卡。
5. 模板、alias、candidate、deferred 的最终 catalog 需要唯一权威入口。

### P1：随后处理

1. `runtime/engine/runtime.py` 中的 EnvironmentSystem 需要和领域 transition 解耦。
2. `domain_rules.py`、`timed_transitions.py` 和 `npc_library.py` 中的状态字符串需要引用统一 StateDefinition。
3. `allowed_rooms`、`allowed_parents`、`functional_class` 应明确区分模板硬约束和数据集软先验。
4. 旧 scene JSON、Web adapter、runtime scene schema 应统一版本号。

### P2：后续优化

1. 将大型 catalog 从单个 Python 文件拆为 schema 数据 + registry loader。
2. 为每个模板和状态补单元测试与生成快照测试。
3. 将生成数据、实验输出、缓存和 `__pycache__` 从源码变更中分离。
4. 3D 接入时只增加 asset binding 层，不改变符号世界的核心语义。

## 8. 推荐重构顺序

本次不立即执行，建议后续按以下顺序：

```text
1. 冻结当前动作集合和场景 JSON schema
2. 冻结 canonical ontology 和 object catalog
3. 设计 StateDefinition / ObjectStateTable
4. 让 ObjectTemplate 通过 capability 生成合法状态表
5. 统一 runtime / scene preparation / NPC event 的状态校验
6. 实现 RoomGraphGenerator
7. 实现 ObjectPlacementGenerator
8. 实现 TaskCompiler + solvability validator
9. 再实现 Cooking / Climate 等领域系统
10. 最后重新生成正式数据并重跑 agent
```

其中第 3 步完成前，不应继续随意增加 `temperature`、`boiling`、`freshness` 等状态名；第 6 步完成前，不应做依赖房间图的物体自动放置；第 8 步完成前，不应把外部候选批量宣布为正式可用对象。

## 9. 当前文件权威性建议

短期内建议按以下优先级理解代码：

```text
动作语义       backend/core/actions.py + action_schemas.py
状态语义       backend/core/states.py
对象模板       backend/core/assets/object_library.py
对象系统依赖   backend/core/assets/object_model.py + object_registry.py
房间模板       backend/core/assets/room_library.py
任务/NPC        backend/core/assets/task_library.py + npc_library.py
运行时         backend/runtime/engine/runtime.py
ontology       backend/generation/ontology/
外部先验       backend/data/external_stats/
生成先验       backend/data/generation_priors/
```

历史 `backend/data/sg_output/simple_graph/*.json` 应被视为 baseline fixture，不应继续作为新生成器的唯一模板来源。

