# Home 世界模型设计

本文参考仓库现有的：

- [`task_planning_task_taxonomy.md`](related_works/task_planning_task_taxonomy.md)
- [`omnigibson_architecture_audit_20260919.md`](omnigibson_architecture_audit_20260919.md)

当前不重新建立一套分类，而是在已有结论上逐步细化 Home：

```text
Node / Edge          图的结构与关系真值
ObjectState          节点可组合的语义状态
Action               机器人主动执行的操作
TransitionRule       动作或条件触发的世界变化
System               水、电、温度等共享环境机制
Task                 对目标状态的描述与完成判断
```

当前优先细化前四项：`Node`、`Edge`、`ObjectState`、`Action`。`TransitionRule`、`System` 和 `Task` 只在需要说明边界时出现。

本轮进一步确定三个边界：

1. `Container` 是一种 Capability，不建立 `ContainerNode` 子类。
2. `ControlNode` 是一种 Node 角色；它可以远离被控设备，通过 `controls` Edge 建立控制关系。
3. 3D 几何、碰撞、结构和尺寸属于 Node 的物理/结构组件，不属于 State，也不作为随意的 metadata 字典。

## 1. Node

Node 是场景图中的实体实例，保存身份和静态结构信息：

```text
Node
  = id
  + semantic_type
  + node_type
  + template_reference
  + geometry
  + structure
  + states
  + metadata
```

Home 中的典型节点：

```text
robot
rag / mop / toilet_brush
toilet / sink / faucet
cup / wateringcan / water_kettle
lamp / light_button
room
```

Node 不应承担所有语义：

- “抹布在水槽里”不是抹布节点的布尔字段，而是 Edge。
- “抹布已打湿”是 ObjectState。
- “抹布可以清洁”是内禀能力。
- “把抹布放进水槽”是 Action。
- “水槽有水时抹布变湿”是 TransitionRule。

节点类型只表达结构角色，例如 `room`、`fixed_object`、`movable_object`、`control_object`、`robot` 和 `human`；不要为每一种玩法建立节点子类。

### 1.1 3D 与物理结构

Node 本身不实现碰撞检测，但应挂载明确的几何/结构描述：

```text
GeometrySpec
  ├─ visual_asset / mesh_reference
  ├─ collision_shape
  ├─ dimensions
  ├─ transform
  ├─ collision_layer / collision_mask
  └─ interaction_surfaces

StructureSpec
  ├─ component_slots
  ├─ shelves / drawers / levels
  ├─ doors / hinges / controls
  └─ anchors / mount_points
```

这些字段的边界如下：

| 内容 | 所属 | 说明 |
|---|---|---|
| 碰撞体形状 | `GeometrySpec` | box、sphere、mesh、compound 等几何碰撞表示 |
| 长宽高、包围盒 | `GeometrySpec` | 用于碰撞、放置、可达性和渲染布局 |
| 世界位置、旋转、缩放 | `GeometrySpec.transform` | 当前空间姿态；节点的父子关系仍由 Edge 表示 |
| 碰撞层/过滤掩码 | `GeometrySpec` | 区分实体碰撞、传感器、交互射线等 |
| 门、铰链、按钮、插槽 | `StructureSpec` + component Edge | 设备的可组合结构 |
| 柜子层数、抽屉、货架 | `StructureSpec` | 静态拓扑；是否能装东西由 Container Capability 决定 |
| 物体当前是否打开 | `ObjectState` | `is_open` 是动态状态，不是几何结构 |
| 门的当前角度/抽屉位移 | `ObjectState` + geometry projection | 状态驱动几何姿态更新 |

因此，“洗衣机有门、门有铰链、柜子有三层”属于结构描述；“门当前打开、抽屉当前拉出”属于状态；“放置物体是否超出边界”由几何校验和容量能力共同判断。

### 1.2 ControlNode

`ControlNode` 仍然是 Node 的一种结构角色，而不是设备的内部字段。控制器可以安装在设备上，也可以安装在墙上或其他位置：

```text
component_of(washer_button, washing_machine)  # 设备上的按钮
controls(washer_button, washing_machine)

controls(wall_switch, lamp)                   # 墙上远程开关
```

是否物理安装在设备上由 `component_of` 或空间 `on/in` Edge 表示；能控制什么由 `controls` Edge 表示。`ControlNode` 不直接保存 `controlled_device_id`，避免与 Edge 产生两份真值。

## 2. Edge

Edge 是节点之间的权威关系真值：

| Edge | 方向 | 含义 |
|---|---|---|
| `at` | 主体 → 房间/固定物体 | 主体的位置或当前交互位置 |
| `in` | 物体 → 容器/房间 | 物体位于内部 |
| `on` | 物体 → 表面 | 物体位于表面 |
| `held_by` | 物体 → 主体 | 物体被持有 |
| `near` | 主体 → 节点 | 满足局部交互距离 |
| `connected` | 房间 → 房间 | 导航拓扑连接 |
| `controls` | 控制器 → 设备 | 按钮、水龙头等控制设备 |
| `component_of` | 部件 → 设备 | 门、按钮、铰链等属于复合设备 |

基本原则：

1. 同一关系只保留一个权威来源。
2. 可移动物体同一时刻只能有一个权威位置关系：`in`、`on` 或 `held_by`。
3. `contains` 是 `in` 的反向查询，不重复保存另一份真值。
4. `pick` 和 `place` 通过增删 Edge 改变物体位置。
5. `controls`、`connected`、`component_of` 通常是静态结构边。

Home 示例：

```text
held_by(rag, robot)
in(rag, sink)
controls(faucet, sink)
controls(kettle_button, water_kettle)
controls(light_button, lamp)
component_of(flush_button, toilet)
```

OmniGibson 将 `Inside`、`OnTop` 等关系实现为 RelativeObjectState。GraphWorld 是显式场景图，因此需要规划、审计和回放的关系仍以 canonical Edge 为真值；RelativeState 可以作为查询和校验接口，但不能与 Edge 各自维护一份可写状态。

## 3. ObjectState

ObjectState 是附着在节点上的可组合语义，不建立大量对象继承类。Node 不再把 `states` 理解为无约束的普通字典，而是持有一个有类型的状态集合：

```text
StateSet
  = StateKey -> StateInstance

StateInstance
  = definition
  + value
  + value_type
  + constraints
  + provenance
```

状态定义负责说明“这个状态是什么”，状态实例负责保存“这个节点当前的值”。一个节点只挂载自己适用的状态，而不是拥有全部状态。

状态值类型至少包括：

```text
Boolean     true / false
Discrete    枚举或离散阶段，例如 cold / room / hot
Continuous  数值，例如 water_level、temperature、battery_level
Relational  依赖另一个节点的关系状态，例如 Inside / OnTop
```

`StateDefinition` 应声明适用的 semantic type 或 capability、值域、默认值、是否派生以及允许哪些动作/规则修改。`StateInstance` 负责当前值、校验、变化追踪和序列化。这样 `is_dirty`、`water_level` 和 `temperature` 都是同一状态系统中的不同类型，而不是散落的特殊字段。

### 3.1 AbsoluteState

只依赖当前节点：

```text
Open(toilet_lid)
Dirty(toilet)
Wet(rag)
Temperature(water_kettle)
ResourceLevel(rag)
BatteryLevel(robot)
ToggledOn(lamp)
```

对应现有 `states.py` 中的节点状态。第一阶段尽量复用已有权威定义：

| 需求 | 当前字段 |
|---|---|
| 脏/干净 | `is_dirty` |
| 湿/干 | `is_wet` |
| 工具可用次数 | `uses_left` |
| 水量 | `water_level`，`has_water` 作为兼容投影 |
| 温度 | `temperature` |
| 设备开关 | `is_on`、`is_running` |

不要同时增加 `wetness`、`cleaning_charge` 和 `uses_left` 等多套近义字段。先用：

```text
is_wet=true     工具已经打湿
uses_left=N     本次打湿后还可清洁 N 次
```

### 3.2 RelativeState

依赖两个节点：

```text
Inside(rag, sink)
OnTop(cup, table)
HeldBy(rag, robot)
Near(robot, toilet)
```

在 GraphWorld 中，这些状态通常由 Edge 提供真值。RelativeState 的作用是提供统一的：

```text
get_value(subject, object)
set_value(subject, object, value)
```

成功的 setter 最终仍应提交 Edge 增删，而不是维护另一份关系状态。也就是说，`StateInstance` 可以提供关系查询接口，但 Edge 是规划、回放和持久化的权威真值。

### 3.3 IntrinsicState / Capability

表示对象固有的可供性，运行时不能随意切换：

```text
pickable
cleanable
cleaning_tool
wettable
water_container
water_reservoir
openable
switchable
timed_device
```

这对应 GraphWorld 现有 ObjectTemplate 的 `capabilities`。因此 Capability 不需要成为与 Node、Edge 完全平行的新图实体；它是节点模板挂载的内禀语义。

其中 `container`、`water_container`、`water_reservoir` 都是能力，不是 Node 子类。能力可以携带参数：

```text
ContainerCapability
  ├─ accepted_types / accepted_capabilities
  ├─ capacity_volume
  ├─ max_load_kg
  ├─ storage_topology
  └─ access_requirements
```

容量的当前占用不放在 `ContainerNode` 中，而由容器能力参数、内容物 Edge 和容量/负载状态共同计算。

Home 需要补充或明确：

| 对象 | Capability |
|---|---|
| 抹布、拖把 | `pickable + wettable + cleaning_tool` |
| 马桶 | `flushable + cleanable` |
| 水槽 | `water_reservoir + place_target` |
| 水龙头 | `water_source_control + switchable` |
| 水壶 | `water_container + heater + timed_device` |
| 灯 | `light_source + switchable + energy_consumer` |
| 机器人 | `mover + battery` |

## 4. Action

Action 是主体可以主动选择的最小操作接口。Action 只检查前置条件并提交状态/边变化；自动发生的连锁效果属于 TransitionRule。

当前优先复用：

```text
move / pick / place / open / close
press / brush / dump / refill / wait
```

### 4.1 普通清洗

`brush` 的前置条件应扩展为：

```text
HeldBy(tool, robot)
tool has cleaning_tool
tool.is_wet = true
tool.uses_left > 0
target has cleanable
target.is_dirty = true
```

动作效果：

```text
target.is_dirty -> false
tool.uses_left -> tool.uses_left - 1
```

当 `uses_left=0` 时，`brush` 失败。机器人必须把工具放入有水的水槽。工具重新获得可用性应优先由 TransitionRule 表达：

```text
in(tool, sink)
AND sink.water_level > 0
AND tool has wettable
-> tool.is_wet = true
-> tool.uses_left = tool.capacity
-> sink.water_level decreases
```

暂时不新增专用 `wet_rag` 或 `refill_mop` 动作。

### 4.2 冲厕所

冲水与表面清洁是两个独立效果：

```text
press(flush_button)
-> TransitionRule 清除马桶内部污物并消耗水

brush(toilet)
-> 清除马桶表面污染并消耗工具 uses_left
```

“冲水 + 表面清洁”是 Task 的复合目标，不应合并成 `flush_and_clean` 动作。

### 4.3 水和热水

水量当前保存在容器/水源节点的 `water_level` 中，不创建每一单位水的可拾取节点：

```text
place(container, sink)
-> TransitionRule 转移水量

press(kettle_button)
-> 启动 timed process
-> temperature 上升

wait
-> 加热继续或水自然冷却
```

如果以后需要追踪水的来源、污染、混合和独立温度，再将水提升为 System 管理的物质实例；当前不要同时维护“水节点”和 `water_level` 两套真值。

### 4.4 灯光和电量

灯仍使用 `press`：

```text
press(light_button)
-> lamp.is_on 切换
-> TransitionRule / System 更新房间照度
-> 设备运行按时间消耗电量
```

观察置信度、移动速度和机器人耗电读取房间照度，但不增加 `improve_visibility` 或 `move_in_dark` 等专用动作。

## 5. 当前边界

当前 Home 设计遵循以下结构：

```text
Node / Edge       世界图的权威结构
ObjectState       有类型的状态定义与状态实例
Geometry/Structure 3D 几何、碰撞和静态组合结构
Action            机器人主动操作
TransitionRule    条件成立后的自动变化
System            水、电、温度等共享环境机制
Task              目标状态组合
```

下一步细化任何 Home 玩法时，依次回答：

1. 涉及哪些 Node？
2. 哪些关系应成为 canonical Edge？
3. 需要哪些 GeometrySpec / StructureSpec？
4. 需要哪些 Absolute、Relative 或 Intrinsic ObjectState？
5. 节点需要声明哪些 Capability 参数，例如容量、可接受类型和功率？
6. 机器人主动执行哪个已有 Action？
7. 哪些效果应由 TransitionRule 或 System 自动发生？

当前三个字段的归属也确定如下：

```text
parent              -> canonical Edge，不再作为 Node 的位置真值
inventory           -> held_by Edge + Container/Capacity 能力和状态计算
interactive_actions -> 由 Capability、State 和 ActionSchema 动态生成，不作为 Node 真值
```
