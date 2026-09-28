# GraphWorld 核心架构规范

状态：规范文档。

本文是 `backend/core` 的唯一实现依据。其他架构、审计和原型文档只作
历史参考；新代码必须遵守本文。

## 1. 总体边界

GraphWorld 只有一个后端权威世界模型，前端可以有多个适配器：

```text
输入适配器（Three.js / Unity / Isaac Sim）
    -> InteractionRequest
    -> InteractionResolver
    -> Action
    -> MutationPipeline
    -> WorldGraph（Node + Edge + State）
    -> Systems / Rules
    -> WorldSnapshot + WorldDelta
    -> 表现适配器
```

渲染器不能拥有业务真值。它可以维护相机、网格、物理句柄、动画和锁定
状态，但不能决定动作是否合法，也不能直接修改世界状态。

## 2. 六个核心概念

### Node 和 Edge

`Node` 是实体实例。`Edge` 是实体之间关系的唯一真值。

```text
component_of(washer_door, washer)
controls(washer_start_button, washer)
in(shirt, washer_slot)
held_by(detergent_bottle, robot)
affects_temperature(air_conditioner, kitchen)
```

Node 保存身份、语义类型、节点类型、能力、几何、结构和当前状态。
运行时不能再把 `parent`、`child`、`inventory` 当作第二套关系真值。

Edge 是值对象，可以验证和分类自身，但不能自己修改图。修改图必须由
`WorldGraph` 完成，并通过 `MutationPipeline` 提交。

### Capability

Capability 描述实体“能够做什么”或“能够参与什么机制”。

```text
pickable
place_target
openable
liquid_container
liquid_receiver
light_emitter
powered_device
temperature_actuator
timed_device
```

Capability 不是当前结果。`light_emitter` 表示物体具备发光能力，
`is_on` 才表示它当前正在发光。

### State

State 描述当前事实，并由状态注册表校验。

```text
is_open
is_on
is_running
cycle_remaining
water_level
liquid_level
temperature
target_temperature
```

状态只能通过统一变更入口修改。每次修改都要产生 delta，并记录来源。

### Action 和 MutationPipeline

Action 是规范化的语义动作，例如 `open`、`place`、`press`、`pour`、
`set_temperature`。鼠标和键盘输入不是 Action，而是先解析成 Action。

`MutationPipeline` 是修改世界的唯一公共入口：

1. 绑定主体、目标、物体和参数；
2. 检查 ActionSchema 和 Capability；
3. 检查状态、关系、几何、资源和访问条件；
4. 产生 `StateDelta`、`EdgeDelta` 和实体变化；
5. 调用相关 System 或安排 Rule；
6. 返回 `WorldDelta` 和 transition 事件。

Node 是数据记录，不能实现 `washer.start()` 或 `lamp.turn_on()` 这类设备
行为。

### Composition 和 TemporalRule

Composition 描述静态拓扑：

```text
washer
  -> washer_door
  -> washer_detergent_drawer
  -> washer_slot
  -> washer_start_button
```

`component_of`、`hinge_of`、`slides_in` 都是 Edge。门是否打开、抽屉是否
拉出，是 State 加上表现层投影，不是结构本身。

TemporalRule 描述动作或时间触发的条件转移。它必须是声明式和可复用的，
不能在里面不断增加按设备名称分支。

### System

System 负责多个对象共享、持续运行的机制：

```text
LiquidSystem
EnergySystem
LightingSystem
ThermalSystem
CapacitySystem
TimeSystem
```

Action 可以触发 System，但 System 也可以由时间、环境或其他 System 触发。
因此，状态转移不只来自 Action。

## 3. `backend/core` 目标目录

```text
backend/core/
  model.py              Node、Edge 和关系值对象
  world_graph.py        canonical 图存储、查询和修改
  capabilities.py       Capability 定义和注册表
  states.py             State 定义和校验
  actions.py            Action 类型和 ActionSchema 注册表
  mutation.py           MutationPipeline、StateDelta、EdgeDelta、WorldDelta
  interaction.py        输入意图 -> canonical Action
  composition.py        静态复合结构和 materialization
  placement.py          几何、容量、承载、容积和碰撞校验

  systems/
    __init__.py
    liquid.py            液体类型、转移、液位和容器
    energy.py            电源、功率、耗电和断电
    lighting.py          发光、受光、方向和遮挡
    thermal.py           房间温度、制冷、制热和热交换
    capacity.py          体积、承载、可接受能力和 storage slot
    time.py              世界时钟和 System 调度

  rules/
    __init__.py
    temporal.py          声明式延迟和持续状态转移
    process.py           设备过程的启动、完成和取消
    natural.py           天气、衰减、变脏、新鲜度等自然变化

  assets/
    object_library.py    canonical 物体模板和能力声明
    object_catalog.py    外部标签 -> canonical 类型
    object_priors.py     生成和布局统计，只能用于先验
    room_library.py      房间模板和布局先验
    task_library.py      任务目标和评估定义
```

新的业务代码不能再创建第二套动作分发器、关系修改器、资源系统或设备
生命周期系统。

## 4. 图修改 API

关系和节点修改必须收拢到 `WorldGraph`：

```python
graph.add_edge(source_id, target_id, relation, properties={})
graph.remove_edge(source_id, target_id, relation)
graph.replace_position_edge(object_id, parent_id, relation)
graph.set_state(node_id, state_name, value, source=...)
graph.spawn_node(node)
graph.remove_node(node_id)
```

这些方法负责检查节点是否存在、关系方向、重复边、位置边唯一性和状态
定义，并在 canonical 数据改变后刷新临时索引。

`relationship_ops.py` 只是旧字典状态迁移期间的兼容辅助层，不是新的架构
层。新代码不能继续依赖它；迁移完成后应删除它。

## 5. Systems 和 Rules

### LiquidSystem

液体使用带类型的连续液位，而不是特殊的布尔值：

```text
liquid_type: laundry_detergent
liquid_level: 420
liquid_capacity: 500
```

通用 `pour` Action 检查源容器、目标接收器、开启状态、类型兼容、可达性、
源液位和目标容量，然后原子地生成一次液体转移 delta。

### EnergySystem

用电物体声明功率需求和可选电源关系。System 负责检查供电、消耗电量，
并在能量不足时产生断电 transition。设备不能直接扣全局电量。

### LightingSystem

发光物体在 `geometry` 或 `structure` 中声明光学参数：

```text
direction
spread_degrees
range_m
intensity
shape
```

`is_on` 和 `is_powered` 决定是否发光。后端可以记录房间或目标是否被照亮；
阴影、射线和真实灯光由 Three.js、Unity 或 Isaac Sim 适配器实现。

### ThermalSystem

房间温度属于房间 Node。空调拥有 `temperature_actuator` 能力，并通过
`affects_temperature` Edge 指向房间。每个时间步，System 综合室外温度、
房间热交换、门窗状态、目标温度和设备功率，计算房间温度变化。

空调 Action 不能直接写房间温度。

### CapacitySystem

Storage slot 声明尺寸、承载、接受的能力和液体容量。`place` 和 `pour`
都调用该 System，设备不能重复实现容积校验。

### TimeSystem

推进世界时钟，并以确定顺序调用 process、temporal、natural、energy、
liquid、lighting 和 thermal 更新。

## 6. 适配器协议

每个渲染器都消费相同的快照，产生相同的输入结构：

```text
WorldSnapshot -> AdapterScene
AdapterInput  -> InteractionRequest
```

`InteractionRequest` 可以携带目标 ID、命中点、表面法线、相机射线、距离、
手部和碰撞信息，但不能携带客户端直接修改状态的命令。

Three.js 是当前适配器。Unity 和 Isaac Sim 可以在不改变 Node、Edge、Action
和 System 语义的前提下接入。

## 7. 标准示例

### 洗衣机和洗衣液

```text
component_of(washer_door, washer)
component_of(washer_detergent_drawer, washer)
component_of(washer_slot, washer)
controls(washer_start_button, washer)
```

洗衣液瓶是 `liquid_container`，洗衣液抽屉是 `liquid_receiver`：

```text
pick bottle
open bottle
open drawer
pour bottle -> drawer
close drawer
place clothes -> washer_slot
close washer door
press washer_start_button
```

启动洗衣机要求主门关闭、抽屉关闭、存在可洗衣物，并且抽屉液位足够。
启动后由 process/temporal Rule 推进衣物状态。

### 空调

```text
affects_temperature(air_conditioner, room)
```

`press` 修改空调执行器状态，`EnergySystem` 检查和提供电力，`ThermalSystem`
在时间推进中修改房间温度。渲染器只把运行状态表现为空气流动、声音和温度
界面。

## 8. 禁止事项

- 渲染器不能持有业务真值。
- 不能直接写 `node.parent`、`node.child` 或 `node.inventory`。
- 共享机制不能按设备名称增加分支。
- 新代码不能创建第二个关系修改辅助层。
- Action 处理器不能直接实现持续的液体、热量或能量模拟。
- 不能为每个设备或玩法建立 Node 子类。
- 不能同时维护两套独立事实，例如 `fill_level` 和 `water_level`。

## 9. 新功能分类规则

写代码前必须先分类：

```text
实体或关系？       -> Node / Edge
静态能力？          -> Capability
当前事实？          -> State
用户或 Agent 意图？ -> Action
静态部件拓扑？      -> Composition
共享持续效果？      -> System
条件和状态转移？    -> Rule
视觉或物理细节？    -> Adapter
```

如果一个功能无法归类，应该先补充架构概念，而不是添加局部特判。
