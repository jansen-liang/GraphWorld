# GraphWorld 项目架构总纲

> 本文是当前架构与实现协议文档。代码以本文的 Core、Runtime、Adapter 边界为准；未决行为记录在 `docs/pending_decisions.md`。

## 1. 项目摘要

GraphWorld 面向楼宇级具身智能研究，包含三个任务：

### 任务一：楼宇级可交互物体数据集

构建包含楼层、房间、物体、设备、agent、空间关系、状态和演化规则的楼宇级场景资产。场景中的物体不是静态模型，而是可被观察、操作、组合和随时间演化的实体。

### 任务二：开放任务评价体系

在同一套场景和世界定义上评价智能体的场景理解、导航、状态推理、交互操作、多步任务、长期维护和扰动恢复能力。现有 `state_score`、`spatial_score`、`human_event_score` 以及长期运行实验属于这一任务。

### 任务三：多端集成应用

将场景和评价体系接入 Web、Unity、Isaac 三个运行端。三个运行端负责各自的可视化、输入、碰撞、动画和物理表现，共享同一套场景语义和动作协议。

## 2. 项目目录

```text
GraphWorld/
├── backend/
│   ├── core/
│   ├── generation/
│   ├── runtime/
│   └── adapter/
│
└── frontend/
    ├── web/       # Three.js 运行端
    ├── unity/     # Unity 运行端
    └── isaac/     # Isaac 运行端
```

## 3. Backend Core

`core` 只定义可序列化的世界概念，不实现 HTTP、数据库、Three.js、Unity 或 Isaac 逻辑。

### 3.1 `backend/core/node.py`

Node 的继承层级保持最小：

```text
Node
├── Floor
├── Room
├── Object
└── Agent
```

不要为门、桌子、抽屉、按钮、洗衣机、电梯或液体继续创建 Node 子类。它们都是 `Object` 或其他 Node 的组合配置。

#### `Node`

Node 表示世界中的一个实体，保存所有实体共有的身份和静态元数据：

```python
class Node:
    id: str
    node_type: NodeType
    role: str                 # root | component；Floor/Room/Agent 通常为 root
    semantic_type: str
    name: str
    template_id: str | None
    capabilities: set[str]
    metadata: dict[str, object]
```

公共方法只保留通用操作：

```python
@property
def node_type(self) -> NodeType: ...

def has_capability(self, name: str) -> bool: ...
def to_dict(self) -> dict: ...
@classmethod
def from_dict(cls, data: dict) -> "Node": ...
```

Node 不负责保存邻接列表、执行动作、判断碰撞或直接操作 mesh。邻接和实体关系属于 `Edge`，动作属于 `Action`，碰撞属于运行端。

#### `Floor`

Floor 描述楼层级空间和布局边界：

```python
class Floor(Node):
    shape: ShapeSpec
    size: SizeSpec
    transform: Transform
```

`shape` 和 `size` 是数据属性；`area` 是根据形状和尺寸计算出的只读派生属性：

```python
@property
def area(self) -> float: ...

def contains_point(self, point: Point) -> bool: ...
```

Floor 不保存房间列表。`floor contains room` 由图中的 Edge 表达。

#### `Room`

Room 描述具有空间语义的区域：

```python
class Room(Node):
    semantic_type: str       # bedroom / kitchen / corridor ...
    shape: ShapeSpec
    size: SizeSpec
    transform: Transform
```

Room 的 `area` 同样是只读派生属性。房间临接和房间门不放进 Room 的字段：

```text
floor --contains--> room
room_a --connected--> room_b
door --connects--> room_a
door --connects--> room_b
```

门是普通 `Object`，门是否阻塞通行由门的状态、关系属性和规则共同决定。

#### `Object`

普通物体和复合物体使用同一个 `Object` 类。复合与否由部件树决定，而不是由继承层级决定。

```python
class Object(Node):
    editable_source: object
    visual_reference: str | None
    collision_reference: str | None
    part_tree: PartTree
    capabilities: CapabilitySet
    states: StateSet
    process_bindings: tuple[dict[str, object], ...]
```

Object 本身就是物体资产的语义载体。它的可视资源、碰撞资源、部件树、状态和能力共同组成一个物体定义，不再额外建立一个与 Object 平行的 `ObjectAsset` 核心类：

```text
Object
├── editable_source       # box、mesh 或其他可编辑来源
├── visual_reference      # 资源引用，具体格式暂不规定
├── collision_reference
├── part_tree
├── capabilities
├── states
└── process_bindings
```

普通物体也必须有 `part_tree`，但它只有一个 root part：

```text
part_tree
└── root_link
```

复合物体只是拥有更多 link 和 joint：

```text
part_tree
└── root_link
    ├── fixed_link
    ├── revolute_link
    └── prismatic_link
```

#### `Agent`

Agent 继承 Node，也拥有部件树。agent 的身体、手、传感器和工具挂在同一个 `PartTree` 上：

```python
class Agent(Node):
    part_tree: PartTree
    embodiment: EmbodimentSpec
    control_profile: ControlProfile
```

Agent 的连续位置、姿态和速度属于运行时状态；手部是部件树中的 link，左右手的抓取由动态关系表示。

### 3.2 `backend/core/articulation.py`：部件树

部件树是 Object 和 Agent 的结构查询视图。唯一结构真值来自图中的可见 Node 和 structure Edge；`part_tree(graph)` 根据这些结构边构建无环、单父的树。它可以由 URDF、USD、Three.js 场景树或其他格式导入，但 Core 只保留自己的中间表示，不绑定某个资产格式。

```python
class PartTree:
    root_id: str
    links: dict[str, Link]
    joints: dict[str, Joint]
```

`Object` 不持久化一份可独立修改的 PartTree，而是提供查询方法：

```python
class Object(Node):
    def part_tree(self, graph) -> PartTree:
        ...
```

```python
class Link:
    id: str
    visual_ref: str | None
    collision_ref: str | None
    can_support: bool
    can_contain: bool
    max_items: int | None
    accepted_capabilities: tuple[str, ...]
    metadata: dict[str, object]
```

`Link` 是部件树中的唯一结构单元，承载与该部件直接相关的几何、运动和交互信息。承载能力不单独建立 `SurfaceSpec`：

- 任意 `Link` 都可以没有承载能力；
- 只有物体的 root link 具有承载能力时，才把该 link 的上表面作为临时放置面；
- 子 link 的承载能力表示该部件内部的容量/收纳位置；
- `can_support` 表示根节点上表面是否可以临时承载物体；
- `can_contain` 表示该 Link 是否是内部容纳节点；
- `max_items` 表示最多容纳的物体数量；
- `accepted_capabilities` 表示允许放入的物体能力，例如 `wearable`、`cleanable`；
- 当前已放入的对象数量仍由 runtime 的 `in` Edge 统计，不在 Link 内重复保存。

因此，临时放置和内部收纳都由同一组 Link 字段表达，区别来自 root/child 位置和容量配置，而不是不同的类。

```python
class Joint:
    id: str
    parent_link: str
    child_link: str
    joint_type: JointType
    axis: Vector3 | None
    origin: Transform
    limits: JointLimits | None
```

第一批 `JointType`：

```text
fixed       # 固定连接
revolute    # 有限旋转
continuous  # 无限旋转
prismatic   # 沿轴平移
```

没有运动部件的物体仍然有部件树，只是一个 root link，或 root 加若干 fixed joint。

部件树只描述结构和允许的运动，不保存当前动画进度。TF 计算使用：

```text
world(child)
  = world(parent)
  × joint.origin
  × joint.motion_state
```

结构定义保存局部变换；runtime 保存 joint state；snapshot 返回最终世界变换。child Node 不重复保存一份可写的世界坐标。

### 3.3 `backend/core/state.py`：状态卡片组合

Object 不通过继承得到“可开门”“可点亮”“可装液体”等状态，而是装载适用的状态卡片。

```python
class State:
    name: str
    value_type: StateValueType
    category: StateCategory
    value: object

    def validate(self, value: object) -> None: ...
    def set_value(self, value: object) -> StateChange: ...
    def to_dict(self) -> dict: ...
```

状态类型至少包括：

```text
BooleanState       true / false
DiscreteState      有限枚举或档位
ContinuousState    数值、位置、温度、进度
ResourceState      类型、数量、单位和约束
```

状态分类用于组织和约束，不用于创建对象子类：

```text
control       开关、开闭、模式
condition     脏、湿、损坏
quantity      容量、数量、剩余时间
spatial       位置和姿态的运行时投影
resource      液体、能源、材料等资源
```

状态定义和状态实例分开：

```python
class StateDefinition:
    name: str
    value_type: StateValueType
    category: StateCategory
    domain: tuple[object, ...]
    default: object

class StateSet:
    values: dict[str, State]

    def get(self, name: str) -> State | None: ...
    def set(self, name: str, value: object) -> StateChange: ...
```

例如一个 Object 可以组合：

```text
StateSet(
  is_open: BooleanState,
  mode: DiscreteState,
  temperature: ContinuousState,
  water: ResourceState,
)
```

状态的 `set_value` 只负责值域校验和生成变化记录，不负责播放动画、不负责修改 Edge、不负责执行其他对象的逻辑。跨对象变化由 Action、Rule 或 Process 统一处理。

### 3.4 `backend/core/edge.py`

Edge 是实体之间的关系事实，不为每种关系建立 Python 子类：

```python
class Edge:
    source_node_id: str
    source_link_id: str | None
    target_node_id: str
    target_link_id: str | None
    relation: RelationType
    properties: dict[str, object]
```

结构 Edge 使用显式的 parent/child 字段，避免依赖 source/target 的方向解释：

```json
{
  "relation": "structure",
  "parent": "base_link",
  "child": "wheel_link",
  "properties": {
    "joint_type": "continuous",
    "axis": [0, 1, 0],
    "origin": {},
    "limits": {}
  }
}
```

结构约束参考 URDF：每个 component 只能有一个结构父节点，root 没有父节点，结构边不能跨越不同 Object，结构图必须是无环单父树。进入仿真后结构边只读；编辑模式或生成阶段才允许修改。

第一批关系分类：

```text
structural   contains / component_of / attached_to / connects
spatial      in / on / at / near / held_by
control      controls
functional   仅在关系本身需要持久化时使用
```

`on`、`in`、`held_by` 是仿真中可变化的空间关系；`component_of`、`attached_to` 和部件树关系是编辑期结构关系。承载面是具有 `can_support` 的根 Link 的上表面，不需要独立的 `SurfaceSpec`。容纳位置是具有 `can_contain` 的 component Link。

动态空间关系可以引用 Link，并携带相对目标 Link 的局部变换：

```json
{
  "relation": "in",
  "source_node_id": "clothes",
  "target_node_id": "washer",
  "target_link_id": "drum",
  "properties": {
    "local_transform": {},
    "inserted_at": 120.5
  }
}
```

`in` 不跨级冗余：物体在容纳 Link 中即可通过结构和空间关系推导其所在房间；agent 在房间中即可推导其所在楼层。`held_by` 会删除物体原有的 `in/on` 关系，并建立到 agent 手部 Link 的动态固连关系。

功能关系优先由 `capabilities + states + rules` 推导，例如“某对象能清洁某目标”“某容器接受某类资源”，不因为一个功能例子就创建一个专用边类型或对象子类。

### 3.5 其他 Core 文件

```text
backend/core/
  node.py             # Node、Floor、Room、Object、Agent
  articulation.py     # PartTree、Link、Joint
  state.py            # State、StateDefinition、StateSet、四类状态
  edge.py             # Edge、关系类型、关系约束
  capability.py       # 能力卡片及参数约束
  action.py           # 语义动作及输入参数
  rule.py             # 通用前置条件、状态效果和事件规则
  transform.py        # Position、Rotation、Scale 等基础几何值
```

不要把具体门、按钮、液体、电梯等实现写进 `node.py`。它们只能由这些通用构件组合，并由 runtime 的规则或过程解释。

### 3.6 `backend/core/capability.py`：能力卡片

Capability 表达实体能够做什么或能够接受什么，不表达一次具体行为：

```python
class Capability:
    name: str
    parameters: dict[str, object]

    def accepts(self, value: object) -> bool: ...

class CapabilitySet:
    values: dict[str, Capability]

    def has(self, name: str) -> bool: ...
    def get(self, name: str) -> Capability | None: ...
```

典型能力包括 `pickable`、`graspable`、`openable`、`switchable`、`cleanable`、`washable`、`support_surface` 和 `receptacle`。能力参数可以描述可接受的类型、容量、运动范围或数量限制。

能力只参与 Action 的前置条件和 Rule 的条件判断。

### 3.7 `backend/core/action.py`：智能体动作请求

Action 是智能体或前端提交的一次意图。键盘事件本身不是语义动作，只有在前端命中目标后才翻译为带目标信息的 Action 请求。

```python
class Action:
    actor_id: str
    action_type: str
    target_id: str | None
    link_id: str | None
    hand: str | None
    hit_point: Point | None
    hit_normal: Vector3 | None
    parameters: dict[str, object]

    def check_preconditions(self, world) -> list[str]: ...
    def execute(self, world) -> ActionResult: ...
```

执行链固定为：

```text
InputEvent
  → 命中目标后构造 Action
  → check_preconditions
  → execute
  → StateChange / EdgeChange / ProcessEvent
  → snapshot delta
```

第一批动作按通用意图定义：`MoveAction`、`InteractAction`、`PickAction`、`PlaceAction`、`ReleaseAction`、`RaiseHandAction`、`LowerHandAction`。没有射线命中时，Q/E 仍然是 Action，但目标为空；它只改变 agent 手部表现或相关状态，不改变目标 Link、Edge 或其他物体。

### 3.8 `backend/core/rule.py`：被动触发和连带效果

Rule 不是智能体请求，而是满足条件后自动产生的变化。Rule 也不绑定某个具体设备类。

```python
class Rule:
    id: str
    trigger: Trigger
    conditions: tuple[Condition, ...]
    effects: tuple[Effect, ...]

    def matches(self, event, world) -> bool: ...
    def apply(self, event, world) -> RuleResult: ...
```

Rule 分成两种通用形态：

1. 直接触发规则：某个事件直接产生状态或边变化；
2. 连带过程规则：某个变化启动或推进另一个 Process。

两种规则都通过 `Effect` 产生统一的 `StateChange`、`EdgeChange` 或 `ProcessEvent`：

```python
class Effect:
    def apply(self, world) -> list[WorldChange]: ...
```

动画不在 Rule 内直接调用。Rule 只产生状态、边或过程变化；前端观察变化后，依据 Link/Joint 和状态映射播放动画。

### 3.9 Action、Rule、State 和动画的关系

```text
Q/E + ray hit
  → Action
  → 前置条件
  → Action Effect
  → StateChange / EdgeChange
  → 前端根据状态变化播放动画

时间/事件/过程触发
  → Rule
  → StateChange / EdgeChange / ProcessEvent
  → 前端根据变化播放动画
```

backend 不需要知道播放哪一段 Three.js 动画。backend 只需要返回哪个状态变了、哪个边变了、哪个过程开始/结束，以及相关的 Link/Joint 状态。

对于不属于关节运动的表现（发光、气流、蒸汽、水滴、破损等），资产可以声明 `visual_effects`。runtime 根据当前状态和能力导出活跃的 `visual_cues`，snapshot 中只传输稳定的 cue 名称，各个前端决定材质、粒子和动画的具体实现。历史场景的 semantic fallback 只作为迁移兼容，不是新资产的扩展方式。

所有动作、规则和过程都必须经过同一个提交路径：

```text
Action / Rule / Process
  → WorldChange[]
  → validate
  → atomic commit
  → event log
  → snapshot delta
```

`WorldChange` 至少包括：

```text
state_changes
edge_added
edge_removed
nodes_removed
process_events
```

资源对象的体积变为 `0` 时，runtime 通过同一事务删除该 Node 及其相关 Edge，并在 delta 中返回 `nodes_removed` 和 `edges_removed`。前端据此移除表现对象，而不是把它当成一个仍然存在的空对象。

持续时间过程使用统一的 `Process`，不为具体设备创建专用基类：

```python
class Process:
    id: str
    owner_id: str
    status: str
    started_at: float
    duration: float
    progress: float
    consumed_resources: tuple[dict, ...]
    completion_effects: tuple[dict, ...]
    interruption_policy: dict
```

过程开始时消耗的资源不会因为中途停止而自动恢复；过程是否完成、被中断或失败由统一状态和效果记录表达。

### 3.10 `ActionResolver`：从交互意图解析具体动作

`ActionResolver` 是输入层和具体 Action 之间的唯一解析层。前端只提交 `InteractEvent`，不根据目标名称自行决定是开门、拾取、放置或资源转移。

```python
class InteractEvent:
    actor_id: str
    hand: str
    target_node_id: str | None
    target_link_id: str | None
    hit_point: Point | None
    hit_normal: Vector3 | None
    input: str = "interact"

class ActionResolver:
    def resolve(self, event: InteractEvent, world) -> Action | None: ...
```

解析时只读取通用世界信息：

```text
actor
held object in selected hand
target node / target link
target capabilities
target states
target relations
```

解析顺序不是按 `semantic_type == "door"` 之类的物体特判，而是按能力、状态和关系匹配：

```text
没有目标
  → RaiseHandAction

目标具有可抓取能力，且手为空
  → PickAction

手中有物体，且目标 Link 具有 `can_support`
  → PlaceAction

手中有物体，且目标 Link 具有 `can_contain`，并满足 `accepted_capabilities`
  → PlaceAction 或 ResourceTransferAction

手为空，且目标具有 `openable`，当前未打开
  → OpenAction

手为空，且目标具有 `openable`，当前已打开
  → CloseAction

手为空，且目标具有 `switchable` / `control` 能力
  → ControlAction

没有匹配的能力、状态或关系
  → rejected action / no-op result
```

ActionResolver 首先判断选中的手是否为空，再判断目标能力和状态。手中有物体时，不能打开抽屉、门或其他普通控制目标；只有目标声明了接受该持有物体所提供资源的能力和规则时，才允许资源转移类动作。最终动作取决于：

```text
actor
+ selected hand
+ held object capabilities
+ target link capabilities
+ target states
+ control / functional relations
+ registered rules
```

因此，持有一个可转移资源的物体时，命中接受该资源的容纳 Link，可以解析为资源转移动作；持有普通物体时，命中普通物体则不会自动触发其他交互。这个差异由能力和规则决定，不由某个具体物体类决定。

`ActionResolver` 只负责选择和构造 Action，不执行 Action。执行仍然经过：

```text
ActionResolver.resolve()
  → Action.check_preconditions()
  → Action.execute()
  → WorldRuntime.commit()
```

## 4. Frontend 运行端

三个前端都实现同一个最小输入模型。它们可以使用不同的渲染和物理库，但不能各自维护一套世界语义。

### 4.1 键盘输入

```text
W / A / S / D
  → agent 的连续移动输入
  → 运行端碰撞/物理处理
  → 发送标准化 movement event

Q / E
  → 左手 / 右手交互输入
  → 作用于当前射线命中的交互目标
  → 发送标准化 interaction event
```

WASD 只表达移动意图，不直接修改 backend 的坐标。agent 的部件树用于表现身体和手；当前世界位置由 runtime 和运行端物理同步。

Q/E 不在前端决定“这是开门、按按钮还是拾取”。前端只提交：

```text
actor_id
hand: left | right
target_id
hit_point
hit_normal
input: interact
```

具体动作由 backend 根据目标能力、状态、关系和规则决定。

### 4.2 鼠标射线和交互高亮

鼠标光标对应一条射线。前端每帧或按需执行：

```text
camera + cursor
  → raycast
  → 取第一个有效命中
  → 映射到 node / link
  → 更新本地 highlight
```

高亮和描边完全属于前端表现，不发送给 backend：

- 命中按钮时高亮按钮部件；
- 命中门板时高亮门部件或交互面；
- 移开后清除高亮；
- 无有效目标时不显示交互提示。

射线命中需要携带的稳定信息：

```text
node_id
link_id
point
normal
distance
```

高亮只使用这些信息改变材质、描边或 UI，不改变 Node、State 或 Edge。

### 4.3 交互事件链

```text
鼠标射线命中
  → 前端高亮
Q/E 按下
  → 前端提交 actor + hand + hit 信息
  → backend 根据能力/状态/关系选择 Action
  → backend 返回 state/edge/process delta
  → 前端读取 delta
  → 根据 PartTree 播放关节动画或视觉效果
```

前端只负责把状态变化映射成表现：

- revolute 状态变化映射为角度动画；
- prismatic 状态变化映射为位移动画；
- Boolean/Discrete 状态变化映射为材质、灯光或效果；
- 连续资源状态映射为液面、进度或强度变化。

如果前端物理产生碰撞、接触或下落结果，再通过 adapter 回传物理事件，不能只修改本地 mesh 后不通知 backend。

### 4.4 前端代码目录建议

```text
frontend/web/src/
  input/
    keyboard.ts       # WASD/Q/E 输入映射
    pointer.ts        # 鼠标和光标
    raycast.ts        # 射线和命中结果
  rendering/
    scene.ts          # snapshot 到 Three.js 场景
    partTree.ts       # Link/Joint 到 Object3D
    highlight.ts      # 高亮和描边
    effects.ts        # 状态驱动的视觉效果
  physics/
    collision.ts      # 碰撞和运动结果
    contact.ts        # 接触/下落事件
  protocol/
    events.ts         # 标准化输入和物理事件
    transform.ts      # Z-up 协议坐标到 Three.js Y-up 的显式适配
```

Unity 和 Isaac 使用同样的概念分层：输入、射线/命中、部件树表现、高亮、物理、协议适配分别实现，不复制 backend 的 Node、State、Edge 和 Rule。

## 5. 判断新需求应该放在哪里

```text
实体类别                     → Node 继承层级
物体/agent 的部件结构         → PartTree / Link / Joint
可复用的物体组成              → Object 的组合属性
当前值                        → State
可接受什么/能做什么            → Capability
实体之间的事实关系            → Edge
有阶段、有时间、有队列的变化    → Process / StateMachine
一次用户或 agent 意图           → Action
条件触发的自动变化             → Rule
mesh、材质、描边、粒子表现      → Frontend rendering
碰撞、接触、重力、下落          → Frontend physics
```

最终原则：新增一个物体时，优先新增模板和组合配置；新增一个行为时，优先新增通用 Action、Rule 或 Process；新增一个前端时，只新增输入、表现、物理和 adapter。除非出现稳定的结构身份差异，否则不新增 Node 子类。

## 6. 实现前置协议

这一节固定 Core、Runtime 和三个前端之间必须一致的基础协议。

### 6.1 `Transform`

GraphWorld 使用一套与具体引擎无关的规范坐标：

```text
单位：米
坐标：右手坐标系，Z 轴向上
旋转：四元数 [x, y, z, w]
缩放：无量纲 [x, y, z]
```

```python
class Transform:
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: tuple[float, float, float]
```

约定：

- `Joint.origin` 保存关节坐标系相对父 Link 的局部变换；
- runtime 保存关节的动态位置、速度和目标值；
- snapshot 返回每个 Node 的最终世界变换；
- 前端将规范坐标转换到自己的引擎坐标，不能修改 backend 的语义单位；
- 所有位置、尺寸、速度和距离字段使用米，时间使用秒。

```text
world_transform(child)
  = world_transform(parent)
  × joint.origin
  × joint.motion_transform
```

对于 root Node，`world_transform` 由场景初始布局或 runtime 状态直接提供。component Node 不保存独立可写的世界坐标。

当前阶段的新 Object 资产统一把 root Link 的局部原点放在物体外包围盒中心。这样 `world_transform.position` 表示物体几何中心，旋转围绕中心进行，放置到地面或承载面时由运行端用半高计算支撑高度。component Link 不采用这一强制约定：门铰链、抽屉滑轨、关节轴和容纳 Link 的原点仍由 `Joint.origin` 或 Link 的局部容纳定义决定。

### 6.2 `WorldChange`

所有 Action、Rule、Process 和物理确认都只能产生 `WorldChange`，不能直接修改 World 中的字典。

```python
class WorldChange:
    change_type: str
    change_id: str
    source: str
    payload: dict[str, object]
```

`change_type` 使用明确的联合类型：

```text
node_added
node_updated
node_removed
edge_added
edge_updated
edge_removed
state_changed
joint_state_changed
process_started
process_updated
process_finished
process_interrupted
```

示例：

```json
{
  "change_type": "state_changed",
  "change_id": "chg_001",
  "source": "action:open_door",
  "payload": {
    "node_id": "door_1",
    "state": "is_open",
    "old_value": false,
    "new_value": true
  }
}
```

```json
{
  "change_type": "edge_added",
  "change_id": "chg_002",
  "source": "action:place",
  "payload": {
    "source_node_id": "shoe_1",
    "target_node_id": "table_1",
    "target_link_id": "root",
    "relation": "on",
    "properties": {
      "local_transform": {}
    }
  }
}
```

Runtime 对一批变化执行：

```text
collect changes
→ validate all changes
→ atomic commit
→ append event log
→ produce delta
```

任意一个变化校验失败，整批变化不提交。`node_removed` 必须同时产生相关 `edge_removed`，资源 Node 的删除不能留下悬空关系。

### 6.3 Snapshot 和 Delta

Snapshot 是某个 revision 的完整可重建世界；Delta 是从一个 revision 到下一个 revision 的有序变化。

```python
class WorldSnapshot:
    session_id: str
    scene_id: str
    revision: int
    time_seconds: float
    nodes: list[dict]
    edges: list[dict]
    processes: list[dict]
    events: list[dict]
    coordinate_system: dict
```

Node snapshot 至少包含：

```text
id
node_type
role
semantic_type
states
capabilities
world_transform
visibility
collision_enabled
joint_states      # component Node 或拥有 joint 的 Object
```

Snapshot 顶层的 `coordinate_system` 固定描述协议坐标：

```json
{
  "units": "m",
  "handedness": "right",
  "up_axis": "z",
  "rotation": "quaternion_xyzw"
}
```

```python
class WorldDelta:
    session_id: str
    base_revision: int
    revision: int
    time_seconds: float
    changes: list[WorldChange]
    nodes_added: list[dict]
    nodes_removed: list[str]
    edges_added: list[dict]
    edges_removed: list[dict]
```

规则：

- 前端只能应用 `base_revision` 与本地 revision 相同的 Delta；
- revision 不连续时，前端请求完整 Snapshot；
- Delta 保持提交顺序，不能由前端重新排序；
- 过程产物或其他运行时实体通过 `nodes_added`（并同时包含 `node_added` change）加入；
- `nodes_removed` 和 `edges_removed` 是显式字段，不能用空对象或 `visible=false` 代替删除；
- `visibility` 和 `collision_enabled` 是 backend 返回的语义呈现状态，前端只负责映射到引擎。

### 6.4 `InputEvent`

输入事件描述客户端意图或物理结果，不直接等同于 Action。

```python
class InputEvent:
    event_id: str
    session_id: str
    actor_id: str
    sequence: int
    timestamp: float
    event_type: str
    phase: str
    payload: dict[str, object]
```

`event_type`：

```text
key
pointer_interact
movement
physics
```

`phase`：

```text
pressed
released
sampled
completed
```

约定：

- Q/E 按下只发送一次 `key + pressed`；
- Q/E 松开只发送一次 `key + released`；
- 长按不重复产生 `InteractEvent`；
- WASD 可以发送连续 `movement + sampled`，也可以发送按下/松开事件，由 adapter 统一成移动输入；
- 鼠标命中信息只在 `pointer_interact + pressed` 时提交给 ActionResolver；
- `sequence` 在一个 session 内由客户端单调递增；
- runtime 按 `event_id` 去重，并拒绝已经处理过的旧 sequence；
- 除同一 `event_id` 的重传外，新的事件不得复用已处理的 sequence；
- timestamp 用客户端采样时间，runtime 另外记录接收时间。

交互 payload：

```text
hand
target_node_id
target_link_id
hit_point
hit_normal
```

物理 payload：

```text
node_id
link_id
world_transform
linear_velocity
angular_velocity
contact_ids
```

### 6.5 Joint State 和最终世界变换

静态结构来自 Node 和 structure Edge；动态关节状态来自 runtime。runtime 不把动态角度写回结构 Edge。

```python
class JointState:
    joint_id: str
    position: float | tuple[float, ...]
    velocity: float | tuple[float, ...]
    target: float | tuple[float, ...] | None
    motion_status: str
```

`motion_status` 可使用：

```text
static
moving
settled
blocked
```

每次 snapshot：

1. runtime 从 root world transform、structure Edge、joint origin、joint state 和 local transform 计算 TF；
2. 对每个 component Node 输出最终 `world_transform`；
3. 对有运动关节的 Object 输出 `joint_states`；
4. 前端按 Node ID 和 Link ID 映射到自己的渲染对象；
5. 前端负责插值、碰撞和物理表现，不反写静态结构。

这样 backend 的状态、结构和最终世界变换是可重建的，Web、Unity 和 Isaac 可以使用不同的动画和物理实现，但读取同一份语义结果。
