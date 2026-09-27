# GraphWorld 架构调研与决策

## 0. 这份文档解决什么问题

GraphWorld 已经有可运行的 Python runtime、场景图、动作校验、任务库、NPC 事件和 Web 可视化。现在的风险不是“没有功能”，而是不同模块对对象、状态、关系和动作的职责理解可能逐渐分叉。

本调研先参考成熟系统，再决定 GraphWorld 如何演进。调研对象：

- OmniGibson / BEHAVIOR-1K
- Habitat-Sim / Habitat-Lab
- Unity Entities（ECS）
- VirtualHome
- GraphWorld 当前实现

本文只做架构决策，不修改 `Node`、`State` 或 `GeometrySpec` 实现。

## 1. 先看结论

GraphWorld 不应复制任何一个系统，而应采用一个混合架构：

```text
WorldGraph
  ├─ NodeRegistry       实体身份和静态类型
  ├─ EdgeRegistry       关系真值
  ├─ ObjectTemplate     能力、默认状态、放置约束
  ├─ StateRegistry      有类型状态定义和当前值
  ├─ ActionSchema       主体动作、前置条件、效果
  ├─ TransitionRules    条件触发的自动变化
  ├─ Systems            水、电、温度、容量、时间等共享机制
  └─ Task/Evaluation    目标、终止条件和长期评分
```

核心决策：

1. 继续使用 GraphWorld 的显式 `Node + Edge` 场景图；这是规划、回放和审计的权威表示。
2. 参考 OmniGibson，把对象状态从“散落字段”逐步升级为可组合、有类型、可追踪的 State 实例；不立即大规模重写。
3. 参考 Unity ECS，能力和状态采用组合，不为 `HotWaterMop`、`ElectricMop`、`SmartToilet` 建立深继承树。
4. 参考 Habitat，把模拟运行时、Agent/Action、Task/Evaluation、Renderer 分层；当前 Three.js 只是 Renderer Adapter。
5. 参考 VirtualHome，保留“程序/动作序列 + 状态图演化 + 独立渲染器”的可复现模式。
6. 参考 BEHAVIOR，把人类活动支持和长期后果放在 Task/Evaluation 层，而不是硬编码到单个动作。
7. Geometry、碰撞和 3D 结构作为 Node 的独立物理/表现组件，后续抽离；暂不让它们成为语义状态的替代品。

## 2. 研究问题

所有系统统一按以下十个问题比较：

1. 实体对象是什么？
2. 对象的 3D 几何和碰撞放在哪里？
3. 能力如何声明？
4. 状态如何定义和实例化？
5. 对象之间的关系如何表示？
6. 动作如何验证和执行？
7. 水、电、温度、容量属于什么系统？
8. 时间变化和自动规则放在哪里？
9. 任务和评分如何与运行时分离？
10. 哪些部分适合 GraphWorld，哪些不适合？

## 3. OmniGibson / BEHAVIOR

### 3.1 架构事实

OmniGibson 将物理实体、可交互对象、ObjectState、Systems、Transition Rules、Tasks 和 Environment 分开。它的关键不是某个具体类名，而是：

```text
Prim/Object          物理和实体结构
ObjectState          可查询/设置的语义状态
Ability / Intrinsic  对象固有能力
TransitionRule       条件满足后的环境转移
System               液体、粒子、布料等共享机制
Task                 目标、奖励、终止条件
Environment          step/reset 生命周期
```

ObjectState 进一步区分：

```text
AbsoluteObjectState  只依赖对象自身，如 Open、Temperature
RelativeObjectState  依赖两个对象，如 Inside、OnTop
IntrinsicObjectState 固有事实或能力，如 ParticleApplier
```

BEHAVIOR-1K 建立在 OmniGibson 之上，重点是人类中心的家庭活动、任务目标、真实偏好和长期活动评价，而不是新增另一套底层对象模型。

### 3.2 十个问题的答案

| 问题 | OmniGibson / BEHAVIOR 的做法 |
|---|---|
| 1. 实体对象是什么？ | Prim/实体之上是 USDObject、DatasetObject、PrimitiveObject、Robot 等可交互对象。对象通过组合挂载 abilities/states，不靠每个语义对象一个深继承树。 |
| 2. 3D 几何和碰撞？ | Prim、USD 资产、Transform、刚体、关节和物理后端；语义状态不替代几何和碰撞。 |
| 3. 能力如何声明？ | abilities/intrinsic states 声明对象固有可供性，并可触发对应状态依赖。 |
| 4. 状态如何定义？ | ObjectState 类注册后按依赖拓扑初始化；状态实例绑定对象，提供 `get_value`/`set_value`、缓存、变化追踪和序列化。 |
| 5. 关系如何表示？ | 关系可作为 RelativeObjectState，例如 Inside、OnTop；连续/物理关系由状态查询，规划所需关系由语义状态统一读取。 |
| 6. 动作如何验证？ | Robot controller / task action 产生控制，状态 setter 和模拟器物理验证结果；动作不是直接写任意字段。 |
| 7. 水、电、温度、容量？ | 液体/粒子等由 Systems 管理；Temperature、Contains 等是 ObjectState；容量和承载由对象状态、物理和规则共同约束。 |
| 8. 时间变化/规则？ | TransitionRuleAPI 先筛静态候选，再检查动态条件，执行 transition，可更新状态、创建或删除对象。 |
| 9. 任务/评分？ | Task 层定义对象加载、观测、奖励、成功和终止；Environment 负责 step/reset，不让 Task 代替模拟器。 |
| 10. 对 GraphWorld 的价值？ | 最值得采用“ObjectState + TransitionRule + System”分层；不适合照搬 USD/Isaac/完整连续物理依赖。 |

## 4. Habitat-Sim / Habitat-Lab

### 4.1 架构事实

Habitat-Sim 是高速、物理可选的 3D simulator，负责场景、机器人、传感器、渲染和刚体机制；Habitat-Lab 是高层实验框架，负责任务、Agent、训练、评测和人类交互。

其重要分层是：

```text
Habitat-Sim
  场景加载、3D 资产、传感器、机器人、物理和渲染

Habitat-Lab
  Task、Episode、Agent、Action、Observation、Measure、训练和评测
```

### 4.2 十个问题的答案

| 问题 | Habitat 的做法 |
|---|---|
| 1. 实体对象是什么？ | Scene/Stage、物体、ArticulatedObject、Robot、Agent；高层任务通过 simulator API 操作它们。 |
| 2. 3D 几何和碰撞？ | Habitat-Sim 的场景资产、CAD/URDF、Transform、传感器和 Bullet 刚体/关节。 |
| 3. 能力如何声明？ | Agent 配置、机器人模型、动作空间和传感器配置；不是用一个通用语义 Capability Registry 表达所有家务能力。 |
| 4. 状态如何定义？ | Simulator 保存物理/场景状态；Task、Measure 和 Observation 读取需要的状态。高层状态没有 OmniGibson 那样统一的 ObjectState 注册表。 |
| 5. 关系如何表示？ | 主要通过场景层级、对象句柄、空间查询和物理状态访问；任务层通常不以 GraphWorld 风格的 typed Edge 作为唯一世界真值。 |
| 6. 动作如何验证？ | Agent action space 转成 simulator 控制；物理、碰撞和可达性在模拟器执行时验证。 |
| 7. 水、电、温度、容量？ | 不是 Habitat 的核心通用语义；需要任务或环境扩展自行实现。 |
| 8. 时间变化/规则？ | Environment step 驱动 simulator physics 和任务更新；一般规则由 simulator/task 扩展实现。 |
| 9. 任务/评分？ | Habitat-Lab 的 Task、Measure、Reward、Termination 与 simulator 分离。 |
| 10. 对 GraphWorld 的价值？ | 采用 Simulator/Task/Measure 分层和 Renderer/Observation 解耦；不把 Habitat 的导航导向模型当作家庭资源语义模型。 |

## 5. Unity Entities / ECS

### 5.1 架构事实

Unity ECS 的核心是数据导向组合：

```text
Entity       身份句柄
Component    纯数据
System       读取/修改组件的逻辑
World        实体和系统的运行容器
```

一个实体可以同时拥有 Transform、Physics、Render、Health、Inventory 等组件；系统按组件查询批量处理。能力不是深继承，而是“拥有某个组件/数据”的结果。

### 5.2 十个问题的答案

| 问题 | Unity ECS 的做法 |
|---|---|
| 1. 实体对象是什么？ | Entity 是轻量 ID；语义由多个 Component 组合。GameObject/Authoring 主要用于创作和烘焙。 |
| 2. 3D 几何和碰撞？ | Transform、Mesh/Render、Physics Collider、RigidBody、Joint 等组件。 |
| 3. 能力如何声明？ | 通过拥有组件、标签组件、数据组件和系统查询表达；没有必须继承某个能力基类。 |
| 4. 状态如何定义？ | Component 是可序列化/可批处理的数据；System 负责状态转移。 |
| 5. 关系如何表示？ | Entity 引用、Buffer、Child/Parent、LinkedEntityGroup 或自定义关系组件；复杂语义关系通常要自己建立数据结构。 |
| 6. 动作如何验证？ | Command/组件写入，由 System 在确定的更新阶段处理；物理系统负责碰撞，游戏系统负责语义校验。 |
| 7. 水、电、温度、容量？ | 作为组件数据和独立 Systems；Unity ECS 不替应用定义水或家务语义。 |
| 8. 时间变化/规则？ | System 按 update order、时间和查询条件推进。 |
| 9. 任务/评分？ | 由业务系统或任务系统实现，与 ECS World 解耦。 |
| 10. 对 GraphWorld 的价值？ | 采用组合优于继承、数据和系统分离；不把 ECS 的性能导向存储直接当作 GraphWorld 的可审计 typed graph。 |

## 6. VirtualHome

### 6.1 架构事实

VirtualHome 明确把家庭活动拆成两个部分：

```text
Program          动作程序/动作序列
EnvironmentGraph 场景对象和关系
```

它同时提供两个执行器：Unity Simulator 负责视频和视觉表现，Evolving Graph 负责 Python 中的图状态演化。README 明确说明：给定 program 和 graph，模拟器执行程序并生成视频或一系列演化图。

### 6.2 十个问题的答案

| 问题 | VirtualHome 的做法 |
|---|---|
| 1. 实体对象是什么？ | Graph 中的带实例 ID 的房间、家具、物体和角色。 |
| 2. 3D 几何和碰撞？ | Unity Simulator 中由 Unity 场景和资产承载；Evolving Graph 可以脱离 Unity 运行。 |
| 3. 能力如何声明？ | 由对象属性、动作前置条件、资源文件和可执行程序规则表达，能力不是独立强类型 registry。 |
| 4. 状态如何定义？ | 图节点/边及其状态列表随 program 执行演化。 |
| 5. 关系如何表示？ | Environment Graph 直接表示位置、持有、开关等关系。 |
| 6. 动作如何验证？ | 程序动作带前置条件；Evolving Graph 做符号执行，Unity 执行视觉/物理表现。 |
| 7. 水、电、温度、容量？ | 可通过图状态和动作规则扩展，但不是其最核心的统一资源系统。 |
| 8. 时间变化/规则？ | 程序执行导致图演化；新版本也包含时间管理、昼夜和光照能力。 |
| 9. 任务/评分？ | Activity 是 program，环境图和执行器分离；RL 环境另提供 episode/reward 接口。 |
| 10. 对 GraphWorld 的价值？ | 直接采用“符号图状态 + 可替换 Unity renderer”的思路；不照搬其较弱的连续资源/状态类型系统。 |

## 7. 四套系统的综合对照

| 维度 | OmniGibson/BEHAVIOR | Habitat | Unity ECS | VirtualHome | GraphWorld 决策 |
|---|---|---|---|---|---|
| 实体 | Object + states | Simulator objects | Entity + components | Graph instance | Node + ObjectTemplate |
| 3D | USD/Isaac/物理 | CAD/URDF/Bullet | Transform/Collider/Physics | Unity scene | 先保留现有 layout，后抽 `GeometrySpec` |
| 能力 | abilities/intrinsic states | agent/action config | component/query | object/action rules | ObjectTemplate.capabilities |
| 状态 | ObjectState 三分类 | sim/task state | Component data | graph state | typed StateRegistry，逐步升级实例化 |
| 关系 | RelativeState | scene/object handles | entity refs/buffers | graph edges | canonical typed Edge |
| 动作 | controller + state setter | action space + sim | commands + systems | program instructions | ActionSchema + validator |
| 共享系统 | transition/system | simulator step | systems | graph/time rules | water/energy/temp/capacity/time systems |
| 任务 | Task/reward/termination | Task/Measure | 外部业务系统 | Program/RL episode | Task library + active goal + evaluation |
| 最值得借鉴 | 状态/规则分层 | simulator/task 分离 | 组合优于继承 | 图与渲染分离 | 融合四者，不迁移引擎 |

## 8. GraphWorld 当前代码对照

### 8.1 已有

| 目标架构 | 当前实现 | 证据 |
|---|---|---|
| Node 类型 | `NodeType` 和 `Node` 子类 | `backend/core/nodes.py` |
| Edge | typed edge 类、`SceneGraph.edges`、关系工厂 | `backend/core/edges.py`、`scenegraph.py` |
| ObjectTemplate | 语义类型、family、capabilities、默认状态、placement | `backend/core/assets/object_library.py` |
| Capability | `Capability` 数据类，附带 states/actions/properties | `object_library.py` |
| State registry | `DiscreteState`、`StateSpec`、`StateDefinition`、归一化 | `backend/core/states.py` |
| Action | `ActionType`、`ActionSpec`、`ActionSchema`、前置条件和效果 | `actions.py`、`action_schemas.py` |
| Resource | resource pool、dispense、consume、finite resources | `resources.py`、相关 runtime |
| Process | recipe、timed device、process events | `processes.py`、runtime |
| Transition log | action/process/timed/human/rule transition envelopes | `transitions.py` |
| Task | task library、active goals、maintenance goals | `task_library.py`、`maintenance_goals.py` |
| Renderer feedback | visual cues、前端 Three.js | `embodied_scene_capability_progress.md`、frontend |

### 8.2 缺失或部分实现

| 目标架构 | 当前问题 | 影响 |
|---|---|---|
| ObjectState 实例 | 当前主要是 `states: dict[str, Any]`，registry 有定义但未形成完整状态对象生命周期 | setter、依赖、缓存、变化追踪分散在 runtime |
| Node/Edge 真值统一 | `Node` 仍有 `parent`，Robot 仍有 `inventory`，SceneGraph 又有 edges | 同一关系存在多套表示，迁移时容易不一致 |
| Capability 与动作 | ObjectTemplate 会由 capability 汇总 `interactive_actions`，但 Node 也保存动作列表 | 候选动作来源不够单一 |
| GeometrySpec | layout/physical geometry 已有，但还不是统一的渲染无关组件协议 | Three.js、未来 Unity 可能各自解释布局 |
| 结构组件 | composition 已能生成门、按钮、铰链、槽位，但和 Node/Edge/Geometry 的公共模型还没有完全统一 | 设备结构逻辑存在专用分支 |
| RelativeState | `in/on/held_by/near/controls` 主要是 Edge/父映射查询，尚未有统一 state API | 关系查询和动作校验接口不完全一致 |
| System | 水、时间、过程已有分散规则；家庭电力、机器人电量、照度系统尚未统一 | 资源权衡暂不能贯穿所有动作 |
| 3D physics | 当前主要是离散几何/容量/碰撞校验，不是连续刚体模拟 | 适合长期 benchmark，但不等价于高保真物理 |

### 8.3 当前存在的冲突

```text
Node.parent             vs  SceneGraph/parent_of/Edge
Robot.inventory         vs  held_by Edge
interactive_actions     vs  Capability.actions + ActionSchema candidates
states dict             vs  StateDefinition/StateSpec
layout geometry         vs  renderer-specific interpretation
```

这些不是立即删除项，而是迁移目标。现阶段应先定义兼容读写和唯一真值方向，再逐步减少重复字段。

## 9. 十个问题对 GraphWorld 的最终回答

### 1. 实体对象是什么？

`ObjectTemplate` 定义类别和默认能力；`Node/ObjectInstance` 是场景中的具体实体；`SceneGraph` 注册节点和边。Node 子类只表达稳定结构角色，不表达清洁、加热等玩法。

### 2. 3D 几何和碰撞放在哪里？

放在 Node 的独立 `GeometrySpec` / `StructureSpec` 层，由当前 layout 和未来 Renderer Adapter 消费。它不属于 State，也不能由 Unity Transform 单独成为语义真值。

### 3. 能力如何声明？

由 `ObjectTemplate.capabilities` 声明，Capability 携带可选参数：容量、接受类型、功率、工具消耗、结构要求等。不要建立能力专用深继承树。

### 4. 状态如何定义和实例化？

保留 `StateDefinition/StateSpec` 作为 registry；逐步引入 `StateInstance`，分 Absolute、Relative、Intrinsic 三类。旧快照仍可投影成 `states` 字典以兼容 API。

### 5. 对象之间的关系如何表示？

需要规划、回放和审计的关系由 canonical typed Edge 保存；RelativeState 只提供查询/校验视图。`parent`、`inventory` 最终不再是独立真值。

### 6. 动作如何验证和执行？

通过 `ActionSchema` 验证能力、状态、边、几何、容量和资源，再提交统一 transition delta。Action 不直接修改渲染器或任意字典。

### 7. 水、电、温度、容量属于什么系统？

它们是跨对象的 Systems；单个容器的水量/温度仍是 State，容量约束来自 Capability + Edge + Geometry。家庭电力和机器人电池应沿用资源更新/transition 机制。

### 8. 时间变化和自动规则放在哪里？

放入 TransitionRule、timed Process 和 Environment tick。规则应分静态候选筛选、动态条件和 transition result，不塞进 Node 子类。

### 9. 任务和评分如何与运行时分离？

Task 只定义目标、绑定、成功/终止和评分读取；runtime 负责状态转移。当前 `task_library` 和 `maintenance_goals` 已有基础，但长期资源评分还需完善。

### 10. 哪些适合 GraphWorld，哪些不适合？

适合：显式图、可解释状态、离散/声明式规则、长期运行、批量实验、任务回放和资源审计。

不适合直接承担：高保真液体、连续布料、复杂刚体接触、低层机器人控制和照片级渲染。需要时通过 Renderer/Physics Adapter 接入，不改变 GraphWorld 的语义真值。

## 10. 架构决策记录

### 采用

- OmniGibson 的 ObjectState（Absolute/Relative/Intrinsic）思想。
- OmniGibson 的 TransitionRule 和 System 分层。
- Habitat 的 Simulator 与 Task/Measure/Agent 分离。
- Unity ECS 的组合优于继承、数据与系统分离。
- VirtualHome 的程序/图演化/Unity 渲染解耦。
- BEHAVIOR 的人类中心任务和长期活动评价方向。

### 不采用

- 不把 Unity、USD 或 Isaac Sim 引入现有 runtime。
- 不把 Transform parent 当作 GraphWorld 关系真值。
- 不为每种设备和工具建立 Python 深继承类。
- 不把每个水单位、每个电量单位建成独立 Node。
- 不在 Action 中直接写渲染状态或绕过 validator。

### 暂缓

- 完整 `StateInstance` 迁移：先保留旧 `states` 快照兼容。
- 统一 `GeometrySpec`：先完成协议和字段映射，再改渲染器。
- 家庭电网/机器人电池/照度系统：先定义资源语义和评分，再实现动作扣减。
- 连续物理适配：只有研究问题确实需要时才接入外部模拟器。

## 11. 后续顺序

```text
1. 保持现有运行时行为，冻结本决策文档
2. 画出 Node / Edge / Template / State / Action 的字段归属表
3. 给 parent、inventory、interactive_actions 标出兼容真值方向
4. 定义 StateInstance 的最小接口，但不立即替换所有 states dict
5. 定义 GeometrySpec 和 renderer-neutral snapshot
6. 让 Three.js 读取统一快照
7. 再实现普通清洗、冲厕所、水温和电量等新规则
```

## 12. 主要资料

- OmniGibson 文档：[Prims](https://behavior.stanford.edu/omnigibson/prims.html)、[Object States](https://behavior.stanford.edu/omnigibson/object_states.html)、[Transition Rules](https://behavior.stanford.edu/omnigibson/transition_rules.html)
- OmniGibson/BEHAVIOR 代码与论文：[BEHAVIOR-1K GitHub](https://github.com/StanfordVL/BEHAVIOR-1K)
- Habitat：[Habitat-Sim GitHub](https://github.com/facebookresearch/habitat-sim)、[Habitat-Lab GitHub](https://github.com/facebookresearch/habitat-lab)
- Unity：[Entities package manual](https://docs.unity3d.com/Packages/com.unity.entities@latest/)、[DOTS samples](https://github.com/Unity-Technologies/EntityComponentSystemSamples)
- VirtualHome：[GitHub README](https://github.com/xavierpuigf/virtualhome)、[VirtualHome documentation](http://virtual-home.org/documentation/)
- GraphWorld 当前实现：`backend/core/`、`backend/runtime/`、`docs/related_works/task_planning_task_taxonomy.md`
