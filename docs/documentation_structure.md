# GraphWorld 文档结构建议

GraphWorld 可以采用类似 OmniGibson 的分层文档，但栏目名称要围绕“符号世界模型、持续运行和机器人任务规划”组织。文档导航应区分三种内容：

- 用户如何安装和运行 GraphWorld；
- GraphWorld 的世界模型和运行时架构是什么；
- 如何定义任务、运行环境和评测实验。

Core 的目标类层级与分阶段迁移方案见：[GraphWorld Core 重构方案](./core_refactor_plan.md)。

## 建议的导航

```text
Documentation
├── Installation
├── Quickstart
├── Important Concepts
└── Examples

GraphWorld
├── Overview
├── Primitives
├── Nodes and Objects
├── Object States
├── Edges and Relations
├── Transition Rules
├── Scenes
├── Simulator
├── Tasks
├── Environments
├── Agents and Robots
├── Evaluation
└── API Reference
```

## 1. Documentation

### Installation

只说明环境依赖、Python 版本、LLM 配置、前端依赖和最小启动命令。不要在这里解释世界模型设计。

### Quickstart

用一个最小例子贯穿完整闭环：

```text
加载 home 场景
→ 查看 Node / Edge / ObjectState
→ 推进一个 NPC 事件
→ 生成维护目标
→ 执行一个机器人动作
→ 查看 WorldGraph commit 和评分变化
```

### Important Concepts

集中解释以下术语：

- persistent world；
- Node / Edge；
- Ability、Absolute State、Relative State；
- Action、TransitionRule、Goal；
- canonical truth、snapshot、delta、commit；
- world score、human score、blocking recovery。

### Examples

按可运行程度组织示例，而不是按代码文件组织：

- `laundry_and_restore`：洗衣、晾干、叠放和归位；
- `hospital_restock`：药品或床单补充；
- `npc_interruption`：人类事件打断机器人计划；
- `dynamic_replanning`：状态变化后重新规划；
- `fog_of_war`：局部可见图上的任务规划。

## 2. GraphWorld

### Overview

说明研究问题、系统边界、与静态 RTP benchmark 的区别，以及 GraphWorld 的持续运行循环：

```text
World state → external events → goal generation → planning
→ abstract actions → validated commit → evaluation
```

入口内容可由现有 [GraphWorld 总体说明](./GraphWorld.md) 和 [任务/图审计](./graphworld_task_graph_audit_20260917.md) 整理而来。

### Primitives

对应最底层且稳定的 ID、类型、状态快照、delta、event log 和时间步。不引入 OmniGibson 的 USD/关节细节；GraphWorld 的 primitive 是符号运行时基元。

### Nodes and Objects

说明 `Node`、`PlaceNode`、`ObjectNode`、`AgentNode` 的最小继承关系，以及 ability 组合方式。`Fixed`、`Movable`、`Container`、`Control` 应作为 ability，而不是大量 Node 子类。

### Object States

说明 OmniGibson 启发的状态组件：

```text
ObjectState
├── AbsoluteState
└── RelativeState
```

静态能力由 `ObjectNode.abilities` 表达，不再另建 `IntrinsicState`，避免重复真值。

这里定义状态 getter、受控 setter/propose、依赖、缓存、连续值和序列化。蒸汽量、血量、温度、湿度等属于状态，不要求视觉特效。

### Edges and Relations

说明统一 `Edge` 类、canonical relations、反向查询、时效性、基数约束，以及 RelativeState 和 Edge 的分工：

```text
RelativeState → EdgeDelta → validate → WorldGraph.commit()
```

入口内容为 [3.3 抽象边体系](./graphworld_task_graph_audit_20260917.md)。

### Transition Rules

说明环境如何在机器人动作之外自动变化：候选筛选、动态条件、transition、对象增删、状态更新和事件生成。现有 [OmniGibson 架构审计](./omnigibson_architecture_audit_20260919.md) 可作为设计依据。

### Scenes

说明五类基础场景、profile、房间拓扑、对象模板、NPC 和场景初始化。数据统计入口是 [dataset_statistics](./dataset_statistics.md)。

### Simulator

说明 `WorldGraph`、时间推进、snapshot、delta、commit、缓存失效、回放和恢复。这里描述符号运行时，不把低层控制器和物理仿真混入核心概念。

### Tasks

建议任务文档内部固定为：

```text
Tasks
├── Description
├── Goal and Success Conditions
├── Usage
│   ├── Specifying a Goal
│   ├── Online Goal Generation
│   └── Dynamic Replanning
└── Task Registry
```

任务是目标、前置条件、成功谓词、优先级、截止时间和评价信息，不等同于一个动作序列。

### Environments

建议环境文档内部固定为：

```text
Environments
├── Description
├── Configuration
├── Usage
│   ├── Reset and Step
│   ├── External Events
│   └── Partial Observability
└── Environment Profiles
```

环境负责生命周期和时间循环；任务负责目标、奖励和终止判断；TransitionRule 负责外生状态演化。

### Agents and Robots

说明机器人观察、抽象动作、动作合法性、规划器、记忆和恢复。关节角度、控制器和真实执行器不是 GraphWorld 符号核心的必要组成。

### Evaluation

集中放长期 world/human 分数、state/spatial/human 曲线、任务成功率、恢复率、阻塞时间、成本和消融实验协议。现有 [benchmark protocol](./benchmark_protocol_design.md) 和 [human blocking recovery](./human_blocking_recovery_definition.md) 属于这一章。

### API Reference

按稳定公共接口组织，而不是按内部目录罗列：

```text
Node / Edge
ObjectState
WorldGraph
ActionSchema
TransitionRule
GoalInstance
Task
Environment
```

## 3. 现有文档的迁移映射

| 新栏目 | 当前主要来源 |
|---|---|
| Overview | `docs/GraphWorld.md`、`README.md` |
| Nodes / Objects / Edges | `docs/graphworld_task_graph_audit_20260917.md` |
| Object States | `docs/state_system_design.md`、`docs/omnigibson_architecture_audit_20260919.md` |
| Scenes | `docs/object_and_environment_design.md`、`docs/dataset_statistics.md` |
| Tasks | `docs/benchmark_protocol_design.md`、`docs/related_works/task_planning_task_taxonomy.md` |
| Transition Rules / Simulator | `docs/omnigibson_architecture_audit_20260919.md`、`docs/architecture_review_2026-08.md` |
| Environments | `docs/web_platform_refactor_plan.md`、`docs/GraphWorld_代码论文精读总结.md` |
| Evaluation | `docs/diagnostic_metrics_800_v2_summary.md`、`docs/human_blocking_recovery_definition.md`、`docs/freeze_validation_2026-08.md` |
| Related Work | `docs/related_works/` |

## 4. 迁移原则

1. 先建立导航和稳定页面名，再迁移正文；
2. 研究审计、实验记录和临时报告保留在 `Research Notes`，不塞进用户 API 文档；
3. 每个核心概念只保留一个 canonical 页面，其他文档链接过去；
4. 代码 API、架构说明、教程和实验结果分开；
5. 不为了模仿 OmniGibson 而引入不属于 GraphWorld 的物理模拟、关节控制或视觉特效栏目。
