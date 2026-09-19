# GraphWorld Core 重构方案

目标不是把 GraphWorld 改造成完整物理模拟器，而是把 core 变成一个可审计、可回放、可持续运行的符号世界内核。重构的关键是区分：继承、组合、数据注册和运行时服务。

## 1. 先看清楚四种关系

GraphWorld 中“抽象层级”不应该只有一棵继承树，而应由四种机制共同组成：

```text
继承 inheritance       表示实体类别的稳定差异
组合 composition       表示对象拥有哪些状态和能力
注册 registry           表示可扩展的状态、动作、规则和模板
服务 service            表示世界如何校验、提交和推进变化
```

这是最容易混淆的地方。`Foldable` 不应该自动变成一个 Node 子类；`FoldedState` 是状态组件；`fold` 是动作；“洗衣后逐渐变干”是 transition rule；`WorldGraph.commit()` 才是统一修改入口。

## 2. 最终类层级

### 2.1 Node：只表达“是什么”

```text
Node
├── PlaceNode
├── ObjectNode
└── AgentNode
    ├── RobotNode
    └── HumanNode
```

这棵树足够表达当前 GraphWorld 的结构差异：空间、物体、行动者。`RobotNode` 和 `HumanNode` 之所以保留子类，是因为它们确实有不同的运行时接口；例如机器人有抽象动作 schema，人类有 schedule 引用。

不建议继续建立：

```text
FixedObjectNode / MovableObjectNode / ContainerNode / DoorNode /
FoldableNode / CleanableNode / TransportNode
```

这些是能力、状态或语义类型，不是必须用继承表达的身份差异。

Node 的最小接口：

```python
class Node:
    id: str
    semantic_type: str
    metadata: dict[str, Any]
    states: dict[str, ObjectState]

    def get_state(self, name, *args): ...
    def request_state_change(self, name, *args): ...
    def has_state(self, name): ...
    def to_dict(self): ...
```

Node 不直接实现 `pick/open/fold`，也不直接增删 Edge。

### 2.2 ObjectState：用组合表达“现在怎样”和“能做什么”

```text
ObjectState
├── AbsoluteState       # 一个 Node：open, wetness, temperature
└── RelativeState       # 两个 Node：inside, on, held_by, near
```

GraphWorld 不需要照搬 OmniGibson 的 `IntrinsicObjectState`。`openable/foldable/can_emit` 已由 `ObjectNode.abilities` 表达；再创建 intrinsic state 会形成两份能力真值。模板中的 ability 是静态声明，运行时据此决定应挂载哪些动态状态组件。

状态是挂载对象上的组件，而不是 Node 的子类：

```text
washing_machine : ObjectNode
├── OpenState
├── ToggleState
├── CycleState
└── RemainingTimeState

clothes : ObjectNode
├── WetnessState
├── CleanlinessState
├── FoldedState
└── InsideState       # RelativeState，关系真值落在 Edge
```

状态组件的最小接口：

```python
class ObjectState:
    owner_id: str
    dependencies: set[str]

    def is_compatible(self, world): ...
    def get_value(self, *args): ...
    def propose(self, *args) -> StateDelta | EdgeDelta: ...
```

`propose()` 只提出变化，不直接修改世界。这样 getter、setter、动作、环境规则和回放都能走同一条提交路径。

### 2.3 Edge：统一表达关系事实

```python
class Edge:
    source_id: str
    target_id: str
    relation: str
    category: str
    attributes: dict[str, Any]
    valid_from: float | None
    valid_to: float | None

    def is_valid_at(self, time): ...
    def get_attribute(self, name, default=None): ...
    def to_dict(self): ...
```

不要为每种关系建立 Edge 子类。`part_of`、`connected_to`、`inside`、`on`、`held_by`、`controls` 都是同一个 `Edge` 的 `relation` 值。

推荐只保存 canonical 方向：

```text
child --part_of--> parent       # contains 是查询反向
object --held_by--> agent       # holds/carries 是查询反向
object --inside--> container
object --on--> surface
```

`RelativeState` 负责关系语义和变化提议，`Edge` 负责持久化关系真值：

```text
RelativeState.get_value(other)
    -> 查询 Edge 或计算带缓存的派生关系

RelativeState.propose(other, value)
    -> EdgeDelta(add/remove)
    -> WorldGraph.validate()
    -> WorldGraph.commit()
```

### 2.4 服务类：不进入 Node/Edge 继承树

```text
WorldGraph
├── nodes: NodeRegistry
├── edges: EdgeIndex
├── state_cache
└── commit(delta)

WorldGraphValidator
ActionExecutor
TransitionEngine
GoalGenerator
```

这些是服务对象，不是世界实体。它们不应继承 Node，也不应被放进 `nodes.py`。

## 3. 当前代码到目标代码的映射

| 当前代码 | 问题 | 目标处理 |
|---|---|---|
| `nodes.Node` | 字段包含 `states`、`parent`、动作列表，职责过多 | 保留身份/元数据/状态组件；`parent` 改为 Edge 查询 |
| `Floor`、`Room` | 当前是 Node 子类 | 合并为 `PlaceNode(place_level=...)` |
| `FixedObject`、`MovableObject`、`ControlObject` | 用继承表达能力差异 | 合并为 `ObjectNode`，能力进入 `abilities` |
| `Robot`、`Human` | 有不同运行时语义 | 保留为 `AgentNode` 子类 |
| `edges.BaseEdge` 及多个 Edge 子类 | 关系承载类型与语义关系重复 | 统一为 `Edge`；保留 `create_edge()` 兼容旧输入 |
| `states.StateDefinition` / `StateSpec` | 目前偏全局 schema | 演进为 `ObjectState` registry + definition schema |
| `predicates.py` | 直接读取 dict 和 `parent_of` | 改为查询 `WorldGraph`、Node、Edge 和 State API |
| `effects.py` | 直接修改 dict | 改为生成 `StateDelta/EdgeDelta` |
| `action_schemas.py` | 前置条件和效果已集中，是较好的入口 | 保留；效果改为 delta，最后统一 commit |
| `timed_transitions.py` | 时间规则集中但函数化 | 迁移为注册式 `TransitionRule` |
| `processes.py`、`domain_rules.py` | 领域规则和时间规则分散 | 迁移到 `TransitionEngine` 的 rule registry |
| `scenegraph.py` | dict-backed 图与 runtime 概念重叠 | 改为 `WorldGraph` 的构造/导入适配器 |

## 4. 推荐的 core 目录

```text
backend/core/
├── ontology.py          # NodeType、semantic types、abilities、relation names
├── node.py              # Node、PlaceNode、ObjectNode、AgentNode
├── edge.py              # 统一 Edge、canonical relation、EdgeIndex
├── state/
│   ├── base.py          # ObjectState、Absolute/Relative
│   ├── registry.py      # 状态注册与依赖排序
│   └── builtin.py       # Open、Wetness、Inside、HeldBy 等
├── delta.py             # StateDelta、EdgeDelta、WorldDelta
├── world.py             # WorldGraph、snapshot、commit、历史
├── validation.py        # 类型、基数、容量、访问条件和逆关系检查
├── actions/
│   ├── schema.py        # ActionSchema、前置条件
│   └── executor.py      # validate -> propose -> commit
├── transitions/
│   ├── base.py          # TransitionRule
│   ├── engine.py        # 候选筛选、条件检查、规则执行
│   └── builtin.py       # 洗衣、补货、腐败、NPC 外生规则
├── goals.py             # GoalSchema、GoalInstance、在线目标生成
└── assets/              # ObjectTemplate、RoomType、Task/NPC registry
```

## 5. 一次变化应该怎样流动

机器人动作和环境自动变化必须共用同一条路径：

```text
Action / TransitionRule
    ↓
读取 Node、State、Edge
    ↓
产生 StateDelta + EdgeDelta
    ↓
WorldGraphValidator
    ↓
WorldGraph.commit()       # 原子提交
    ↓
清理缓存 / 写 EventLog
    ↓
GoalGenerator 观察新状态
```

例：机器人把衣服放进洗衣机：

```text
remove clothes --held_by--> robot
add    clothes --inside--> washing_machine
```

例：洗衣过程推进：

```text
update clothes.wetness
update clothes.cleanliness
update washing_machine.remaining_time
if finished:
    update washing_machine.cycle
    emit GoalInstance(fold_and_store)
```

动作不直接改 dict，规则也不直接改 dict。所有变化都可验证、可记录、可回放。

## 6. 分阶段迁移，不一次重写

### Phase 0：冻结现有行为

为当前 `action_schemas`、`timed_transitions`、场景加载和 replay 增加回归测试，记录旧状态快照和动作结果。

### Phase 1：引入 canonical WorldGraph

新增 `WorldGraph`、统一 `Edge`、validator 和 `WorldDelta`，先通过 adapter 读取现有 dict 状态；旧 runtime 仍可运行。

### Phase 2：改造 Node 和 Edge

把 `Floor/Room` 映射到 `PlaceNode`，把三类 object Node 映射到 `ObjectNode + abilities`，把多个 Edge 子类映射到统一 Edge。保留反序列化兼容，不立即删除旧类名。

### Phase 3：把状态变成组件

先实现 `OpenState`、`WetnessState`、`FoldedState`、`InsideState`、`HeldByState`。`states.py` 中已有定义继续作为 schema 和迁移层，状态实例逐步替代裸字典。

### Phase 4：把动作和效果改成 delta

`action_schemas.py` 保留前置条件，但 `effect_*` 函数不再原地修改 state，而是返回 `WorldDelta`，统一交给 `commit()`。

### Phase 5：迁移 transition rules

将 `timed_transitions.py`、`processes.py`、`domain_rules.py` 逐个包装成 `TransitionRule`，先保持行为一致，再拆分候选筛选、动态条件和 transition。

### Phase 6：切换 runtime 入口

`runtime/engine` 只调用 `WorldGraph.step()`、`ActionExecutor` 和 `TransitionEngine`。完成 replay/metrics 适配后，最后删除旧的 `parent_of` 直接写入路径。

## 7. 一个判断标准

以后新增功能时可以按下面的问题决定放在哪里：

```text
它是什么实体？             -> Node / semantic_type
它具有什么能力？           -> ObjectNode.abilities
它现在是什么状态？         -> AbsoluteState
它和谁有什么关系？         -> RelativeState + canonical Edge
谁触发了变化？             -> Action 或 TransitionRule
如何保证变化合法？         -> WorldGraphValidator
如何提交、回放和评分？     -> WorldGraph.commit / EventLog
```

如果一个新功能需要同时修改 Node、Edge、动作和规则四个地方，通常说明边界还没有拆清楚；应该优先定义状态、关系和 delta，再接入执行器。

## 8. 2D 场景布局与可视化

GraphWorld 虽然是符号世界，也可以拥有可编辑的 2D 空间布局。关键是把“语义图”和“几何布局”分开，而不是把所有坐标都塞进 Node 状态。

```text
Semantic WorldGraph             Layout2D
├── Node / Edge                 ├── FloorLayout
├── ObjectState                 ├── RoomGeometry
└── Action / Transition         ├── DoorPlacement
                                └── ObjectPlacement
          \                    /
           SceneInstance / Editor
```

### 8.1 模板属性与实例布局分离

当前 `RoomTypeSpec` 已经包含 `area_range`、`aspect_ratio_range`、`door_count_range` 和邻接约束。这些是房间类型的生成规则，不是某个房间实例的实际几何。

```python
class RoomTypeSpec:
    area_range: tuple[float, float]
    aspect_ratio_range: tuple[float, float]
    door_count_range: tuple[int, int]
    allowed_neighbors: list[str]
    required_neighbors: list[str]
```

具体场景实例使用离散栅格。`grid_size` 给出每个 cell 对应的米数，但运行时位置以整数 cell 为真值：

```python
class RoomGeometry:
    room_id: str
    grid_x: int
    grid_y: int
    width_cells: int
    depth_cells: int

    @property
    def area(self) -> float:
        return width_cells * depth_cells * grid_size**2
```

第一版只支持轴对齐矩形房间。房间拖动和缩放必须对齐 cell；编辑完成并发布后，几何在 runtime 中不可移动。相邻房间必须直接共墙，不能以间隔和虚线代替拓扑。每面墙最多一个连接，因此矩形房间最多四个门。`area` 是派生值，不另存。

### 8.2 门不是房间里的一个数字

`door_count` 只能用于生成约束。实际门必须有明确位置和连接对象：

```python
class DoorPlacement:
    door_id: str
    room_a_id: str
    room_b_id: str
    wall_a: str                 # north / east / south / west
    offset_cells: int           # 沿 room_a 墙面的栅格偏移
    width_cells: int
```

门本身仍是 `ObjectNode(semantic_type="door")`，因为它具有 `OpenState`，并可能阻塞导航和可见性。门的墙面位置属于 `Layout2D`；门连接哪两个房间属于拓扑关系。

推荐只保存门到房间的连接关系，然后派生房间邻接：

```text
door_1 --connects--> room_a
door_1 --connects--> room_b

derived: room_a --connected_to--> room_b
```

这样不会同时维护 `room.neighbors`、`connected_to Edge` 和 `door endpoints` 三份可能冲突的真值。当前兼容旧数据时仍保留房间间 `connected` Edge，但发布校验要求它与共墙和门端点一致。走廊是一种 Room Node；走廊与相邻房间的共墙上使用开放通道，不创建 Door Node。

### 8.3 物体模板和物体实例

物体模板保存默认物理尺寸和容量：

```python
class ObjectGeometrySpec:
    width: float
    depth: float
    height: float
    mass: float | None

class CapacitySpec:
    max_load: float | None
    max_items: int | None
    usable_width: float | None
    usable_depth: float | None
    usable_height: float | None
```

场景实例只保存位置和必要覆盖值：

```python
class ObjectPlacement:
    object_id: str
    parent_id: str              # room / surface / container
    grid_x: int                 # 所属房间内的相对 cell
    grid_y: int
    width_cells: int
    depth_cells: int
    rotation: float = 0.0
```

物体模板仍可用米制保存默认物理尺寸，实例化到场景时按 `grid_size` 向上换算为 footprint cell。固定设备需要二维 footprint；小型可移动物可以只占一个 cell，避免伪精确建模。

### 8.4 “承载量”应该拆成什么

若只评估抽象抓取，机器人至少需要：

```text
robot.max_payload >= object.mass
robot.hand_capacity >= number_of_held_objects
```

若评估“把箱子放到有空间的货架层”，仅有重量承载量不够，还需要一个空间容量。最小模型可以不用做 3D packing，只检查：

```text
shelf_level.remaining_load >= box.mass
shelf_level.remaining_area >= box.footprint_area
```

如果论文还要评价地面到四层货架的 reachability，则再增加离散高度带：

```text
shelf_level.height_band in {low, middle, high}
height_band in robot.reachable_bands
```

这不需要关节角度、末端轨迹或夹爪闭合量。若 GraphWorld 不声称评测 reachability，可以暂时只做负载和空间容量；但那时四层货架对规划器只是四个容量不同的候选位置，不能再把“末端可达性”作为被测能力。

### 8.5 语义关系与 2D 坐标的一致性

语义关系仍由 Edge 作为真值，二维布局只承担空间约束：

```text
table --inside--> living_room
box --on--> shelf_level_2
robot --at--> storage_room
```

`ObjectPlacement.parent_id` 是布局索引，不是第二份可独立修改的语义关系。编辑器保存时必须转换成 `WorldDelta`，由 validator 原子更新 Edge 和布局：

```text
drag object
  -> propose LayoutDelta + EdgeDelta
  -> bounds / overlap / parent compatibility validation
  -> commit
```

至少检查：

- 所有位置和尺寸都是整数 cell，房间不重叠；
- 每条房间 `connected` Edge 的两端确实共墙；
- 非走廊连接恰好有一个共享 Door Node，走廊连接没有门；
- 每面墙最多一个门，每个矩形房间最多四门；
- 门位于有效的共同墙段，并具有指向两个房间的 `connects` Edge；
- 固定物体 footprint 位于所属房间内；
- 固定物体之间没有非法重叠；
- 可移动物的 parent 与 `inside/on/held_by` Edge 一致；
- 容器/表面的负载、数量和可用面积不超限。

### 8.6 用户搭建场景的编辑流程

```text
1. 从数据库选择 SceneTemplate，或选择已有 SceneVersion 作为起点
2. 创建草稿；后端加载场景的楼层、允许房间和默认规则
3. 从该场景的 RoomTemplate catalog 选择房间，并设置栅格长宽
4. 将房间拖到栅格位置并形成共墙；在共同墙上放一个共享 Door Node，走廊使用无门开口
5. 选中房间，从该房间可用的 ObjectTemplate catalog 拖入家具和设备
6. 放置可移动物，并选择 on/inside 关系
7. 自动校验尺寸、碰撞、容量、门和图连通性
8. 发布为新的不可变 SceneVersion
9. 启动 runtime，并在同一布局上显示状态和机器人移动
```

前端应提供两个独立视图：

- `Floorplan View`：按离散栅格显示共墙房间、共享门和物体，用于搭建和运行观察；
- `Graph View`：显示 Node、Edge、状态和控制依赖，用于理解规划与因果。

当前 `SceneGraphCanvas` 使用 force-directed graph，只适合作为 Graph View，不能承担平面图编辑。应新增独立的 `FloorplanCanvas`，两种视图通过相同 node ID 联动选中。

### 8.7 编辑器目录应从数据库读取

网页不能在前端硬编码“家庭、客厅、冰箱、沙发、洗衣机”等选项。目录是三级选择，正确的数据流是：

```text
core built-in registries / curated external data
    -> catalog sync/import
    -> database versioned catalog
    -> select SceneTemplate
    -> query allowed RoomTemplates
    -> select room instance
    -> query compatible ObjectTemplates
    -> Scene Builder palette
    -> scene instance
    -> immutable SceneVersion snapshot
```

当前 Web 数据库只保存 `Scene`、`SceneVersion`、`SceneNode` 和 `SceneEdge`；房间和物体模板仍在 Python registry 中。建议增加：

```text
SceneTemplate
├── id / version / domain
├── display names
├── floor constraints
├── allowed room template ids
└── default rules / runtime profile

RoomTypeTemplate
├── id / version / domain
├── display names
├── area and aspect constraints
├── adjacency constraints
└── default object template ids

ObjectTemplateRecord
├── id / version / semantic_type
├── abilities / state schema
├── default geometry
├── capacity
├── placement constraints
└── visual asset or icon reference
```

前端通过 API 拉取：

```text
GET /catalog/scenes
GET /catalog/scenes/{scene_template_id}/room-types
GET /catalog/object-templates?scene_template_id=home&room_type=living_room
GET /catalog/object-templates/{template_id}
```

这里需要区分：

- `SceneTemplate`：数据库中可供用户选择的场景类型或蓝图，例如 home、hospital；
- `Scene`：用户创建的一个场景项目；
- `SceneVersion`：该项目某次发布后的不可变快照；
- `RoomTypeTemplate/ObjectTemplateRecord`：在选定场景下可添加的房间和物体目录。

如果用户选择的是已有 `SceneVersion`，编辑器应先复制成新草稿，不能直接修改旧版本。

场景编辑建议区分草稿和发布版本：

```text
POST  /scene-drafts
PATCH /scene-drafts/{id}
POST  /scene-drafts/{id}/validate
POST  /scene-drafts/{id}/publish
```

发布时生成不可变的 `SceneVersion`，并保存所引用的 `template_id + template_version`，同时快照任务运行必需的尺寸、能力、状态 schema 和容量。这样 catalog 后续更新不会改变旧场景和旧实验结果。

如果模板来自外部数据集，也应先经过 ontology normalization、能力补全和人工/规则审计后导入 catalog；浏览器不应直接读取外部数据库并把原始 label 当作可执行物体。
