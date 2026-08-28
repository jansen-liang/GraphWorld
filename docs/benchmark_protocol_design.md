# GraphWorld Benchmark 设计概要

GraphWorld 不把 benchmark 设计成“一条固定指令让 agent 完成”，而是让 agent 在一个持续变化、部分可观的人类世界中长期行动。

核心评测问题是：

> agent 能否理解规则、观察世界、记住经验、发现问题、安排任务，并通过行动长期维持世界正常运行？

## 1. 输入给 Agent 的 Prompt

每个 episode 开始时，先给 agent 一份固定的游戏说明；之后每执行一步，再给一份新的状态 prompt。

### 1.1 游戏说明

游戏说明回答“这个世界是怎么运行的”，包括：

- 游戏目标：维持世界状态、人类活动和空间秩序，获得尽可能高的长期分数；
- 分数规则：`state`、`spatial`、`human` 以及总分如何计算；
- 世界规则：时间如何推进，NPC 和设备如何变化，episode 何时结束；
- 观测规则：只能看到附近区域，容器需要打开后才能看到内部；
- 动作规则：每种动作的用途、参数、前置条件、效果、成本和失败原因；
- 输出规则：每次选择一个合法动作，不得编造不存在的动作或对象。

动作说明必须足够具体。例如：

```text
动作：place(object, destination)
用途：把手中的物体放到目标位置
前置条件：机器人持有 object；destination 可见且支持放置
效果：物体与机器人的持有关系解除，并建立 object 到 destination 的位置关系
失败：未持有物体、目标不可见、目标不支持放置
```

### 1.2 每一步的状态 Prompt

每轮 prompt 包含：

```text
当前时间和剩余预算
当前分数和本轮分数变化
机器人位置、手中物品和自身状态
当前局部观测：房间、物体、关系和可见状态
最近发生的环境事件和待处理任务
过去若干步的行动日志
Agent 自己保存的记忆
当前可执行的候选动作
上一步动作的执行结果
```

三种信息要明确区分：

```text
当前观测：现在看到了什么
历史日志：过去每一步实际发生了什么
Agent 记忆：agent 自己总结并保存的规律或经验
```

历史日志由系统自动记录；Agent 记忆由 agent 主动维护。例如“洗衣流程需要先关门再启动”“某个 NPC 通常在固定时间取药”。记忆可能错误或过期，不能把隐藏真值自动写入记忆。

Agent 最终只需要输出一个动作：

```json
{"action_id": "open:washer_01", "reason": "start laundry process"}
```

后端负责验证动作、执行动作、推进 NPC 和环境、计算分数，并把新的状态 prompt 返回给 agent。

## 2. Benchmark 怎么设计

一个 benchmark 实例由以下因素组合而成：

```text
能力模式 × 任务类型 × 难度因素 × 动态世界 × 自动评测
```

### 2.1 能力模式：测什么

**反应（Reactive）**：给 agent 明确任务，测试它能否理解任务并完成多步动作。

**能动（Proactive）**：不给完整任务列表，只让 agent 负责维护世界；agent 需要从异常、人类事件和资源变化中发现问题并决定做什么。

**预见（Anticipatory）**：要求 agent 预测未来后果、NPC 行为和未知状态，并提前行动。

### 2.2 任务类型：做什么

- 清洁 `clean`：污染状态恢复；
- 制作 `make`：原料或部件形成目标产物；
- 迁移 `relocate`：物体位置、容器归属或布局改变；
- 操作 `operate`：门、设备、容器等状态改变；
- 交互 `interact`：人与机器人之间发生交付、协作或信息事件；
- 导航 `navigate`：机器人到达目标位置或探索未知区域。

同一个实例需要同时标注能力模式和任务类型，例如：

```text
任务类型：relocate
能力模式：proactive
难度：L3
```

### 2.3 难度因素：有多难

- 任务来源：明确指令到环境自主涌现；
- 动态性：静态状态到持续变化；
- 可观测性：全可见到局部可见；
- 任务链长度：单步到多阶段；
- 外部扰动：无 NPC 干扰到持续扰动；
- 任务竞争：单任务到多任务冲突；
- 后果跨度：立即反馈到延迟后果；
- 环境新颖性：已知模板到未见环境。

这些因素可以组合成 L1-L5：

```text
L1：明确目标、单步、完全观测
L2：多步任务、轻微状态变化
L3：存在外部扰动或任务中断
L4：多任务竞争、时间和资源约束
L5：部分可观、延迟后果、未来推演、未见环境
```

### 2.4 世界、任务和评测

每个实例由动态世界、随机种子和任务/事件生成规则确定。世界内部保存完整的 True Graph，但 agent 只能获得局部 Observation；History 和 Agent Memory 分开记录。

任务可以由外部指令给出，也可以由异常、人类日程、资源变化和设备事件自动产生。正式任务需要通过逻辑可解性、时间可行性和可玩性检查。

每个实例记录：

- 总分以及 `state/spatial/human` 分项；
- 任务类型专属指标；
- 问题发现率和发现延迟；
- 任务完成率、恢复率和动作合法率；
- 时间、资源和路径成本；
- 失败原因分布。

每个配置使用多个随机种子，并与 no-robot、规则型 agent、reactive agent 和 full-observation oracle 比较。

GraphWorld 最终评测的是：

```text
在持续变化的人类世界中，agent 能否理解规则、利用观测和记忆，
发现并编排任务，预测后果，并长期维持世界运行。

## 5. 数据集程序化构造 Pipeline

本节只讨论 benchmark/data 的批量构造，不讨论持续自主能力评价体系、自进化学习方法或集成应用。GraphWorld 的生成方式参考 ProcTHOR 的“先生成房屋拓扑、再生成对象布置”思路，但输出目标是可规划的动态场景图，而不是渲染用 3D 房屋。

### 5.1 两阶段生成

```text
场景域 profile
  -> 房间拓扑生成器
  -> 房间节点 + 邻接/门/可达边
  -> 房间级固定物体布置
  -> 房间级可移动物体、容器、资源布置
  -> NPC 与初始状态采样
  -> 候选任务实例生成
  -> PDDL 编译/求解
  -> 失败修复或剔除
  -> graph.json + metadata.json + PDDL 证据
```

第一阶段只决定“有哪些房间、房间如何连接”；第二阶段才在每个房间内放置物体。对象不能跨越房间 profile 随机放置，必须满足 `allowed_rooms`、`allowed_parents`、容量和场景域约束。

### 5.2 场景域和房间拓扑

生成器输入不是一个自由房间列表，而是场景域和 floorplan profile：

```json
{
  "scene_domain": "home",
  "floorplan_template": "hub_home",
  "room_count_range": [4, 7],
  "required_rooms": ["living_room", "kitchen", "bathroom"],
  "optional_rooms": ["bedroom", "balcony"],
  "topology_constraints": {
    "connected": true,
    "required_adjacency": [["living_room", "kitchen"]]
  }
}
```

五个场景域分别维护自己的房间词汇和拓扑 profile：Home、Office、Hospital、Supermarket、Factory。`room_library.py` 中的 `room_types_for_scene(domain)` 是房间类型入口；`build_generation_priors.py` 产出的 room graph 统计只作为采样先验，不能替代邻接合法性校验。

### 5.3 房间内对象布置

对象布置按以下顺序执行：

1. 放置房间必需 fixture（例如厨房的水槽、冰箱，装配线的机器）。
2. 按对象先验采样可移动物体和资源，并选择合法 parent。
3. 写入初始状态、容量、资源和 `in/on/at` 关系。
4. 根据任务需求反向补齐缺失对象，再添加随机对象丰富场景。

对象先验来自三部分的合并：核心模板声明、GraphWorld 场景统计、ProcTHOR/AI2-THOR 的 room-object 频率。外部频率只能影响概率，不能绕过任务前置条件。例如 `plate` 必须有食品承载语义，`box/cart` 必须有非食品承载语义。

### 5.4 任务验证是数据质量门槛

生成器先产生候选任务集合；每个候选任务实例都必须单独编译 PDDL problem 并调用规划器。只有成功得到 plan 的实例才写入 `verified_task_instances`。因此：

```text
对象出现 != 任务可玩
候选任务 != 已验证任务
verified_task_count = 成功 PDDL plan 的任务实例数
```

失败原因（缺对象、不可达、容量冲突、资源不足、编译错误、无解、超时）必须保留。生成器可根据失败原因重新采样/修复场景，但达到最大重试次数后应剔除该任务或丢弃整个场景。

### 5.5 数据集输出契约

每个场景目录至少包含：

```text
scene.json                 # True Graph、房间拓扑、对象和 NPC
metadata.json              # seed、域、房间/对象/NPC 计数、验证结果
tasks/<task_instance>/
  problem.pddl
  plan.out
  result.json
```

`metadata.json` 必须记录 `generator_version`、`seed`、`scene_domain`、`floorplan_template`、`room_instances`、`object_type_counts`、`npc_count`、`task_candidate_count`、`verified_task_count`、`verified_task_instances` 和 planner 版本。数据集索引只收录通过结构校验且达到 PDDL 发布门槛的场景。

### 5.6 与项目四个部分的边界

```text
持续自主能力评价体系  <- 使用数据集，不定义生成算法
benchmark 和数据集     <- 本节：拓扑生成、对象布置、任务 PDDL 验证
自进化学习方法         <- 训练/评测 agent，不修改静态生成契约
集成与应用             <- 读取 graph/metadata，不改变数据集真值
```
```
