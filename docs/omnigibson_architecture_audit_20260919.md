# OmniGibson 架构审计：对象、状态与运行时转移

审计对象：Stanford BEHAVIOR/OmniGibson 文档与 `StanfordVL/OmniGibson` 源码（2026-09-19 拉取的主分支）。重点覆盖 `prims`、`objects`、`object_states`、`scenes`、`transition_rules.py`、`tasks` 和 `envs`。

## 1. 最重要的设计判断

OmniGibson 将三个容易混在一起的问题分开了：

1. `Prim/Object` 表示模拟器中的实体和物理结构；
2. `ObjectState` 表示实体当前具有的、可查询或可设置的语义状态；
3. `TransitionRule` 表示多个对象满足条件后，环境自动发生的离散转移。

因此，“洗衣机”是一个对象，“打开/关闭”是对象状态，“洗衣机启动后衣物变干”是 transition rule，而不是把这些都塞进一个巨大的对象类。

## 2. 顶层目录与职责

```text
prims             连接 USD/Isaac Sim 的底层实体、变换、刚体、关节
objects           在 Prim 之上组织可交互对象，并挂载 abilities/states
object_states     可组合的语义状态实现
robots            机器人实体、关节和机器人专属状态
controllers       将动作命令转换为机器人控制量
sensors           观测来源
systems           粒子、液体、布料等环境系统
scenes            场景对象注册、加载、重置和更新追踪
transition_rules  基于状态条件的环境自动转移
tasks             任务加载、观测、奖励和终止条件
envs              Gym 环境生命周期和 step/reset 编排
```

这不是简单的“节点图 + 动作列表”。它把物理承载、语义状态、外生过程、任务评价和环境循环分成了不同边界。

## 3. Prim 到 Object 的对象模型

核心继承链大致是：

```text
BasePrim
└── XFormPrim
    └── EntityPrim          # links / joints / articulation
        └── USDObject        # 所有可交互对象的统一接口
            ├── DatasetObject
            ├── PrimitiveObject
            └── LightObject
```

`USDObject` 的职责是加载 USD、保存名称和类别、维护 abilities，并在加载阶段准备 object states。它没有为每种语义能力建立深继承树。

对象构造时可以传入：

```python
abilities = {
    "openable": {...},
    "cookable": {...},
}
```

OmniGibson 根据 ability 找到对应 state 类型，补齐 state 的依赖，按拓扑顺序实例化，并检查对象/资产是否兼容。对象最终维护的是：

```python
obj.states: dict[state_class, state_instance]
```

这是一种“组合优于继承”的实现：同一个对象可以同时拥有 `Open`、`Toggle`、`Contains`、`Temperature` 等状态，而不需要同时继承多个互相冲突的类。

## 4. ObjectState 的统一接口

文档对外提供统一的 `get_value(...)` / `set_value(...)` API；源码内部由 `BaseObjectState` 的缓存、初始化、序列化和变化追踪逻辑支撑。

### 4.1 三种状态类型

```text
BaseObjectState
├── AbsoluteObjectState    # 只依赖当前对象
├── RelativeObjectState    # 依赖当前对象与另一个对象/系统
└── IntrinsicObjectState   # 固有能力或事实，不提供 getter/setter
```

| 类型 | 例子 | API 形态 | 语义 |
|---|---|---|---|
| Absolute | `Open`、`Temperature`、`Folded` | `get_value()` / `set_value(value)` | 对象自身的状态 |
| Relative | `OnTop`、`Inside`、`Covered`、`NextTo` | `get_value(other)` / `set_value(other, value)` | 当前对象与另一个对象之间的关系 |
| Intrinsic | `ParticleApplier` 等 | 不实现读写 | 对象固有能力，不能在运行时随意设置 |

这个划分很关键：`OnTop(A, B)` 不需要被硬编码成 `A` 或 `B` 的特殊字段，而是作为关系状态的实现；`Temperature(A)` 又可以是纯数值状态；`ParticleApplier(A)` 则是能力声明。

### 4.2 状态实例的生命周期

每个状态实例都绑定一个对象，并经历：

```text
prepare_object_states
  -> 依赖补齐与拓扑排序
  -> state.initialize()
  -> get_value / set_value
  -> cache / has_changed
  -> dump_state / load_state
```

几个值得借鉴的细节：

- 状态可以声明 `get_dependencies()` 和可选依赖，系统据此保证初始化顺序；
- `get_value` 不是每次都直接重新算，状态自带按模拟 timestep 的缓存；
- `set_value` 成功后调用 `obj.state_updated()`，场景会记录本步发生变化的对象；
- 状态可以是可持久化的，也可以是纯派生状态；
- setter 不保证“直接赋值”，例如 `OnTop.set_value(other, True)` 会采样姿态，直到关系满足或失败返回 `False`；
- 不支持读写的状态会明确抛出错误，而不是静默接受非法操作。

因此，状态 setter 实际上是一个经过语义校验的局部 transition，而不是普通属性写入。

## 5. Transition Rules 如何推进状态变化

`omnigibson/transition_rules.py` 的核心对象是 `TransitionRuleAPI` 和 `BaseTransitionRule`。

```text
scene objects
    ↓ static candidate filters
active rules
    ↓ dynamic conditions
rule.step()
    ↓ transition(object_candidates)
state updates / add objects / remove objects
```

### 5.1 静态候选与动态条件分离

- `ObjectCandidateFilter` 只描述不会在运行中改变的属性，例如类别、ability、名称；
- `RuleCondition` 描述运行时条件，例如 `ToggledOn == True`、`Open == False`、容器内有足够物体；
- 场景变化后，`refresh_rules()` 重新计算候选并维护 active rule 集合；
- 每个仿真步调用 `TransitionRuleAPI.step()`，满足条件才执行 `transition()`。

这避免了每个规则每一步都扫描所有对象，也避免把静态资产筛选和动态状态判断混成一个谓词。

### 5.2 Transition 的结果不是只有状态值

规则可以返回 `TransitionResults`：

- 更新现有对象状态；
- 创建新对象并加入场景；
- 删除已有对象；
- 在下一次 transition step 延迟设置新对象状态或执行 callback。

因此它能够表达腐败、烹饪、洗衣机/烘干机、粒子生成等“状态改变伴随实体增删”的环境过程。

## 6. Scene、Task、Environment 的调用顺序

`Scene` 负责对象 registry、对象加载/删除、重置，以及 `updated_state_objects` 追踪；它不是任务规划器。

`BaseTask` 负责：

- 加载任务相关对象；
- 创建 observation space；
- 创建 reward functions 和 termination conditions；
- 每步计算任务完成、成功和奖励。

`Environment.step()` 负责编排：

```text
convert robot action
  -> pre-step action processing
  -> simulator physics step
  -> render
  -> task termination/reward/observation
```

这意味着任务成功判定和环境物理推进是两个层次：task 不直接替代 simulator，也不负责实现所有状态转移。

## 7. 对 GraphWorld/HSG-RTP 的直接启发

### 7.1 Node 不应承载全部语义

现有 `Node` 可以保留身份、静态类型、基础状态和元数据；但像 `openable`、`folded`、`dirty`、`inside(A,B)` 不宜都变成 Node 的字段或 Node 子类。可以引入一个轻量的 `ObjectState` 组合层：

```text
Node
└── state_instances: StateKey -> ObjectState
                         ├── AbsoluteState
                         ├── RelativeState
                         └── IntrinsicState
```

节点子类仍然只表达结构差异；能力和状态通过组合挂载。

### 7.2 Edge 与 RelativeState 的关系

GraphWorld 的 `in/on/held_by/near/controls` 可以有两种来源：

- 持久的 canonical edge：关系本身是图事实；
- 相对状态的派生查询：状态根据物理/空间信息判断关系是否成立。

建议采用“一个真值来源、多个视图”：对需要规划和审计的关系，将成功 setter 的结果提交成 canonical edge；对昂贵或连续的几何关系，允许 RelativeState 动态计算，并通过事件/缓存投影到图视图，避免同时维护两份可写真值。

### 7.3 TransitionRule 应成为环境动力学层

GraphWorld 当前的 NPC effects、环境过程和 maintenance goal 可以拆成：

```text
candidate filter      # 哪些对象/场景可能触发规则
dynamic condition     # 当前状态是否满足
transition            # 改状态、加边/删边、创建/删除对象、生成事件
```

机器人动作是显式 action；transition rule 是动作之外的环境自动演化。两者都通过同一个 validator/commit 接口修改 WorldGraph，规划器只观察提交后的 canonical state。

### 7.4 建议的最小迁移版本

不要一次复制 OmniGibson 的全部物理层。GraphWorld 可以先实现：

1. `ObjectState` 注册表：状态类声明适用对象、依赖和 getter/setter；
2. 绝对/相对/内禀三种基类；
3. `TransitionRule`：静态候选筛选 + 动态条件 + transition result；
4. `WorldGraph.commit(delta)`：统一提交 Node 状态和 Edge 增删；
5. `updated_entities` 与 timestep cache：支持在线任务生成和增量评价。

第一批状态只需覆盖 `Open`、`Clean`、`Folded`、`Inside/OnTop`、`HeldBy`、`ResourceLevel`，不需要引入完整 Isaac Sim 物理模拟。

## 8. 与当前 3.2/3.3 设计的关系

这项调研不推翻“顶层只有 Node 和 Edge”的结论，反而补上了一个缺失层：

```text
Node / Edge          结构与关系真值
ObjectState          可组合的语义状态与状态查询/设置
TransitionRule       外生或条件触发的状态转移
Action / Task        机器人动作、目标和评价
Environment          时间步与生命周期编排
```

换言之，`ObjectState` 和 `TransitionRule` 不应被误认为第三、第四个图顶层实体类；它们是作用于 Node/Edge 的运行时语义层。

## 9. 参考入口

- 文档：[Object States](https://behavior.stanford.edu/omnigibson/object_states.html)，特别是 Runtime、Adding Object States 和三种 state 类型。
- 源码：`omnigibson/objects/usd_object.py`
- 源码：`omnigibson/object_states/object_state_base.py`
- 源码：`omnigibson/transition_rules.py`
- 源码：`omnigibson/scenes/scene_base.py`
- 源码：`omnigibson/tasks/task_base.py`
- 源码：`omnigibson/envs/env_base.py`
