# GraphWorld 任务、图数据与 HSG-RTP 对比审计

日期：2026-09-17

## 1. 结论先行

当前 GraphWorld 已经不是一个“静态场景图上完成给定任务”的系统。它实现的是：NPC 日程和环境过程持续改变图状态，机器人从状态偏离与人类流程前置条件中发现维护目标，再通过合法动作闭环恢复世界。

但“任务数量”必须分层统计：

| 层级 | 当前数量 | 含义 |
|---|---:|---|
| Runtime 原子动作 | 10 | `move/pick/place/open/close/press/brush/fold/dump/refill` |
| 显式程序技能 | 12 | `task_library.py` 中有名称、触发条件、目标和阶段的闭环技能 |
| 通用高层目标族 | 7 | `maintain_order/restore_initial_position/clean/close/dispose_food/empty_cup/laundry_clothes`；其中部分由 12 个技能细化 |
| NPC 角色 | 13 | 家庭 1，医院/超市/办公室/工厂各 3 |
| 基础场景中的可移动对象实例 | 52 | 家庭 17、医院 11、超市 11、办公室 3、工厂 10；每个都可形成动态归位任务 |
| 场景 JSON | 20 | 5 个 base scene + 15 个变体文件；论文 profile 实验取每类场景的 `normal/compact/spread` 三档，共 15 个条件实例 |

因此，对外最准确的说法不是“只有 12 个任务”，而是：**12 个显式闭环技能 + 1 个按对象实例化的通用归位 schema + 通用状态维护目标，在 5 类持续场景中由运行时事件反复实例化。**

## 2. 逐场景任务与动作链

下面的“动作链”省略跨房间时重复出现的 `move(room)` 和结构门 `open(door)`，只保留任务主干；实际执行会由当前拓扑和容器状态补齐导航、开门与关门动作。

### 2.1 家庭

人类活动链：起床 -> 穿衣 -> 洗漱 -> 早餐 -> 离家 -> 回家 -> 晚餐 -> 夜间洗漱 -> 睡眠。它会弄脏床、厕所、厨具和表面，打开设备，产生腐败食物、满杯、脏湿未折衣物，并移动日用品。

| 机器人任务 | 触发/目标 | 主动作链 |
|---|---|---|
| 洗衣、晾干、折叠并收回 | 衣物脏/湿/未折叠；终态为衣柜内、干净、干燥、已折叠 | `pick cloth -> open washer -> place in washer -> close washer -> press washer -> 时间 tick 至洗完 -> pick -> place on drying_rack -> 时间 tick 至晾干 -> fold -> pick -> open wardrobe -> place -> close wardrobe` |
| 处理腐败或烧焦食物 | 食物 `is_rotten/is_burnt`；完成处置并归还垃圾桶 | `pick food -> place in trash_bin -> pick trash_bin -> move garbage_station -> dump -> move bin_home -> place bin` |
| 倒空杯子 | 杯子 `fill_level>0/is_full` | `pick cup -> move sink -> dump` |
| 清洁表面/器具 | 任意可清洁节点 `is_dirty=true` | `move target -> brush target` |
| 关闭遗留设备/容器/门 | `is_open=true` | `move target -> close target` |
| 日用品归位 | 17 个 movable 的 parent 偏离初始 parent | `move current_location -> pick object -> move initial_parent -> [open container] -> place -> [close container]` |

归位对象包括鞋 3、冷藏食品 3、碗、衣服 3、文具、书、马桶刷、椅子、牙刷、杯子和牙膏。

### 2.2 医院

人类活动链覆盖挂号、候诊、问诊、开方、取药、输液、换床单、清床、补给和离院。这里的核心不是普通清洁，而是恢复下一次医疗流程的前置条件。

| 机器人任务 | 目标 | 主动作链 |
|---|---|---|
| 补回处方单 | 处方单回到门诊初始位置 | `pick prescription_sheet -> move clinic -> place initial_parent` |
| 补回药盒 | 药盒回药房 | `pick medicine_box -> move pharmacy -> place initial_parent` |
| 冷藏药归冰箱 | 药品回 `medicine_fridge` | `pick refrigerated_medicine -> move fridge -> open -> place -> close` |
| 处理医疗废物 | 废物进入医疗废物桶 | `pick medical_waste -> move medical_waste_bin -> place` |
| 收集脏床单 | 脏床单进入脏布草桶 | `pick dirty_sheet -> move linen_bin -> place` |
| 补充干净床单 | 干净床单回供应柜 | `pick clean_sheet -> move supply_cabinet -> [open] -> place -> [close]` |
| 归还轮椅 | 轮椅回入口初始位置 | `pick/move wheelchair -> move entrance -> place` |
| 清洁候诊座椅 | 候诊区座椅干净 | `move seats_waiting_area -> brush` |
| 清洁检查床 | 检查床干净 | `move exam_bed -> brush` |
| 其他医疗物资归位 | 医疗车、制服、白大褂、表单等恢复初始 parent | 通用 `pick -> navigate -> place` |

医院是当前显式技能最完整的场景：12 个技能中有 9 个医院专用技能。

### 2.3 超市

人类活动链：顾客进店 -> 取车 -> 选生鲜 -> 选冷藏品 -> 结账 -> 离店；收银员准备/扫码；理货员持续检查。事件会移动购物车、商品和货箱，并改变货架/冷柜/收银区状态。

| 机器人任务 | 目标 | 主动作链 |
|---|---|---|
| 归还购物车 | `cart_entrance -> entrance` | `pick/move cart -> move entrance -> place` |
| 生鲜补位 | 蔬菜、水果回 `shelf_produce` | `pick item -> move produce_area -> place shelf_produce` |
| 干货补位 | 饮料回 `shelf_dry_goods` | `pick drink -> move shelf_area -> place shelf_dry_goods` |
| 冷藏品归位 | 牛奶、果汁回冷柜 | `pick item -> move cold_storage -> open fridge -> place -> close` |
| 货箱归位 | 两个 box 回初始 shelf/room | `pick box -> navigate -> place` |
| 清洁和关闭 | 对人类使用后产生的脏表面、打开容器执行恢复 | `move -> brush/close` |

这些任务当前主要依赖通用 `restore_initial_position`，还没有像医院那样注册成独立命名技能。

### 2.4 办公室

人类活动链：员工到岗 -> 专注工作 -> 团队会议 -> 访客接待；经理评审并参加会议。事件会移动会议用书、报告和杯子，消耗办公/茶水资源并弄脏工作表面。

| 机器人任务 | 目标 | 主动作链 |
|---|---|---|
| 会议用书归位 | `book -> table_meeting_room` | `pick book -> move meeting_room -> place table` |
| 报告归档 | `report -> cabinet_manager_office` | `pick report -> move manager_office -> open cabinet -> place -> close` |
| 茶水杯恢复 | 杯子倒空/清洁/回 `counter_pantry` | `pick cup -> move sink -> dump -> [brush when dirty] -> pick -> place counter` |
| 资源补充 | 打印纸、墨、饮水等有限资源出现兼容 supply 时 | `pick supply -> move device -> refill(target,supply)` |
| 环境维护 | 清洁桌面、关闭设备、恢复被移动对象 | `brush/close` 或通用归位链 |

### 2.5 工厂

人类活动链：穿戴 PPE -> 装载零件 -> 运行装配 -> 质量检查 -> 设备维护 -> 交接班。任务之间存在强依赖：装配需要零件箱就位，质检需要成品到工作台，交接需要质量记录归档，维护需要工具箱在控制室柜中。

| 机器人任务 | 目标 | 主动作链 |
|---|---|---|
| PPE 归还 | 安全装备回入口柜 | `pick safety_gear -> move entrance -> open cabinet -> place -> close` |
| 零件箱供料/归位 | warehouse/workshop/assembly 的 box 回正确工位 | `pick box -> navigate -> place machine/shelf/workshop` |
| 成品送检或入库 | 成品在工作台与仓库间恢复流程所需位置 | `pick finished_product -> move workshop/warehouse -> place` |
| 质量记录归档 | 记录回控制室柜，供质检/交接使用 | `pick quality_record -> move control_room -> open cabinet -> place -> close` |
| 工具箱归还 | 维护后工具箱回控制室柜 | `pick toolkit -> move control_room -> open cabinet -> place -> close` |
| 推车归位 | 两辆 cart 回 workshop/warehouse | `pick/move cart -> navigate -> place` |
| 工位清洁与设备复位 | 工作台脏、柜门开、设备状态偏离 | `move -> brush/close/press` |

## 3. 当前图数据的特点

### 3.1 图是可执行状态机

GraphWorld 的实际运行对象可以写成：

```text
WorldGraph_t = (V, E_static, E_dynamic_t, S_t, P_t, H_t, L_t)
```

- `V`：实体节点；
- `E_static`：房间连通、结构包含、部件和控制关系；
- `E_dynamic_t`：当前位置、容器、表面、持有、穿戴等关系；
- `S_t`：对象离散/数值状态；
- `P_t`：洗衣、晾干、腐败、设备周期等时间过程；
- `H_t`：NPC 日程及其前置条件/效果；
- `L_t`：事件日志、阻塞案例和评分历史。

这比普通 scene graph 多出的核心不是节点种类，而是 **时间、外生转移、合法动作、过程和评价共用同一状态语义**。

### 3.2 建议的抽象节点体系

借鉴 OmniGibson 后，**图元素模型**的顶层只保留 `Node` 和 `Edge`：`Node` 表示“世界中有什么”，`Edge` 表示“实体之间有什么关系”。这不表示整个 core 只能有两个基类；`ObjectState`、`ActionSchema`、`TransitionRule` 和 `Goal` 是与图元素平行的运行时抽象族，但它们不继承 Node/Edge。物体状态不继续扩展 Node 的继承树，而是作为可组合的 `ObjectState` 组件挂载到 Node 上。

#### `Node` 基类

```python
class Node:
    id: str
    semantic_type: str
    state_instances: dict[str, ObjectState]
    metadata: dict[str, Any]

    def get_state(self, state_name, *args): ...
    def request_state_change(self, state_name, *args): ...
    def has_state(self, name): ...
    def to_dict(self): ...
```

`id` 是稳定身份，`semantic_type` 表示语义类别，`state_instances` 保存该节点支持的状态组件，`metadata` 只保存名称、来源等描述信息。`request_state_change()` 不直接改字典，而是让状态组件生成待校验的 `StateDelta/EdgeDelta`，再由世界统一提交。

#### Node 的最小继承树

```text
Node
├── PlaceNode       # scene / zone / floor / room
├── ObjectNode      # 家具、设备、工具、耗材、运输载体等
└── AgentNode
    ├── RobotNode
    └── HumanNode
```

各类只在确实拥有不同数据或行为时增加内容：

| 类 | 新增属性 | 新增方法 |
|---|---|---|
| `PlaceNode` | `place_level`（scene/zone/floor/room） | `get_occupants(world)`；通过 Edge 查询，不在节点内维护 `children` |
| `ObjectNode` | `abilities`（如 movable/openable/container/foldable） | `supports(ability)`；ability 决定可挂载哪些 ObjectState |
| `AgentNode` | `role` | `holds(world)`；通过 `held_by` Edge 派生，不保存第二份 inventory 真值 |
| `RobotNode` | `action_schema_ids` | `available_actions(world)`；只暴露抽象动作，不负责关节控制 |
| `HumanNode` | `schedule_id` | `current_activity(time)`；具体日程推进由 schedule/event 模块负责 |

`Fixed/Movable/Control/Container/Surface/Transport` 目前都不应成为子类，因为它们主要是能力组合，而不是拥有独立数据结构和行为的对象种类。例如冰箱可以是：

```text
ObjectNode(
  semantic_type = refrigerator,
  abilities = {container, openable, switchable, temperature_controlled}
)
```

只有未来某类对象出现无法由 ability/state 表达的独有属性和方法时，才新增 Node 子类。

#### `ObjectState`：Node 的运行时组件

`ObjectState` 是运行时组件，不是第三种图顶层实体。参考 OmniGibson，将状态分为三类：

```text
ObjectState
├── AbsoluteState     # 单个节点自身：open、temperature、wetness、cleanliness
└── RelativeState     # 两个节点之间：inside、on、held_by、near
```

OmniGibson 还定义了 `IntrinsicObjectState`。GraphWorld 当前不必照搬这一层，因为 `openable/foldable/can_emit` 已由 `ObjectNode.abilities` 表达；同时保留 ability 和 IntrinsicState 会形成两份能力真值。模板 ability 作为静态声明，运行时据此决定挂载哪些动态状态组件。

最小接口为：

```python
class ObjectState:
    owner_id: str
    dependencies: set[str]

    def is_compatible(self, world): ...
    def get_value(self, *args): ...
    def propose(self, *args) -> StateDelta | EdgeDelta: ...
```

- `AbsoluteState` 的值进入 Node 状态快照，例如 `wetness(clothes)=0.8`；
- `RelativeState` 提供关系的查询和修改语义，但关系真值由 Edge 保存；
- 状态可以声明依赖、缓存和连续值，因此蒸汽量、血量、温度、湿度等无需视觉渲染，也能参与规则、规划和评价。

Node 自身不实现 `pick/open/fold`。机器人动作和环境规则调用状态组件，由它们检查语义并产生 delta。

### 3.3 建议的抽象边体系

OmniGibson 主要用 `RelativeObjectState` 表达对象关系；GraphWorld 是显式图世界，因此应进一步把经过验证、需要规划和审计的关系保存为 Edge。Edge 是关系的 canonical truth，RelativeState 是关系的语义接口。

Edge 顶层只保留一个实现，不为 `inside/on/controls` 分别建立空壳子类：

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

`source_id/target_id/relation/category` 是结构字段；`attributes` 保存距离、容量、置信度或阻塞原因；有效时间支持动态关系、回放和因果追踪。世界相关的合法性检查放在 `WorldGraphValidator` 中，不让 Edge 自己承担整个世界的校验职责。

#### 最小 canonical relation 集合

| 类别 | canonical relation | 说明 |
|---|---|---|
| 层次/组成 | `part_of` | child → parent；`contains` 作为反向查询，不重复存储 |
| 拓扑/可达 | `connected_to` | 对称关系；属性保存距离、门和当前是否阻塞 |
| 放置/定位 | `inside`、`on`、`at` | 动态主位置关系；`in/located_in` 归一化为 canonical 名称 |
| 邻近 | `near` | 可由空间状态派生；仅在需要离散规划时提交为 Edge |
| 持有/穿戴 | `held_by`、`worn_by` | 动态且互斥；`holds/carries` 作为反向查询 |
| 控制/依赖 | `controls`、`powered_by` | 表达按钮、设备、门和供能依赖 |
| 任务/过程 | `requires`、`produces`、`restores`、`blocks` | 连接 Goal/Process/Event 与实体 |

关系分类只是 `category` 的取值，不是新的类。反向关系通过索引查询生成，例如 `A part_of B` 可以查询为 `B contains A`，但不再存第二条可独立修改的边。

#### Edge 与 RelativeState 的分工

```text
RelativeState.get_value(other)
    -> 查询 canonical Edge，或计算尚未持久化的派生关系

RelativeState.propose(other, True/False)
    -> 返回 EdgeDelta(add/remove)
    -> WorldGraphValidator 校验
    -> WorldGraph.commit() 原子提交
```

例如 `InsideState(clothes).propose(washing_machine, True)` 不直接修改衣服字段，而是产生：

```text
remove: clothes --held_by--> robot
add:    clothes --inside--> washing_machine
```

这里必须坚持一个真值来源：

- `inside/on/held_by` 等关系以 Edge 为准；
- RelativeState 负责查询、推导、约束和生成 EdgeDelta；
- `parent_of/relation_of/room_of/inventory` 只是 Edge 的查询索引或派生视图；
- 几何推导出的 `near/touching` 若不提交，只能作为带 timestep 的缓存，不能成为另一份可写真值。

#### 统一状态提交路径

机器人动作和环境 TransitionRule 使用同一条修改路径：

```text
Action / TransitionRule
    -> StateDelta + EdgeDelta
    -> validate（类型、前置条件、互斥、容量、基数、时间）
    -> atomic commit
    -> invalidate state cache
    -> append EventLog
    -> trigger online Goal generation
```

图校验器至少执行：

- 节点和 relation 类型兼容；
- 一个可移动物同一时刻只有一个主位置关系；
- `inside/on` 与 `held_by` 通常互斥；
- 容器容量、开关状态和访问条件满足；
- 对称关系和反向查询一致；
- 已失效 Edge 不参与当前规划和任务前置条件判断。

因此，Edge 不只是图的静态连线，而是 GraphWorld 区别于 OmniGibson 纯 RelativeState 表达的关键：它让动态关系可以被规划器读取、被 evaluator 审计、被 replay 重放，并与连续或离散 ObjectState 一起构成符号世界快照。

### 3.4 建议新增非物理节点

若要真正表达“动态任务生成”，仅靠实体节点和状态字段还不够。建议将下列对象也纳入统一 IR：

- `ActivitySchema`：人类活动及其前置条件、成功/失败效果；
- `ProcessInstance`：已启动的洗衣、晾干、打印等时间过程；
- `GoalInstance`：从状态债务生成的机器人目标，含 trigger、deadline、priority、status；
- `ResourceAccount`：库存、容量、消耗和补充；
- `EventInstance`：已经发生的外生事件和因果来源。

它们可以是独立 registry，也可以投影为图节点。关键是拥有稳定 ID 和显式引用，而不是把所有语义埋在字符串 prompt 中。

## 4. 与 HSG-RTP 的区别

| 维度 | HSG-RTP | GraphWorld | 判断 |
|---|---|---|---|
| 研究问题 | 给定自然语言任务的多房间/多楼层长程闭环规划 | 持续扰动下自主发现和调度维护任务 | 核心问题不同，互补而非重复 |
| 时间范围 | 一个任务 episode 内持久更新 HSG | 多日程/多事件持续运行，任务反复到达 | GraphWorld 更强调世界时间 |
| 任务来源 | 离线结构化任务生成，任务开始时已给定 | 当前图状态和人类活动前置条件在线产生目标 | 最大区别 |
| 图层次 | `scene/zone/floor/room/object/component/agent/transport` | `floor/room/fixed/movable/control/robot/human` | HSG-RTP 层次更完整 |
| 关系本体 | hierarchical/spatial/logical/agentic 四类 canonical IR | physical/logical + 多种运行时位置关系 | HSG-RTP 分类更干净；GraphWorld 动态关系更丰富 |
| 状态语义 | 对象状态与已验证 action commit；历史版本 | 25 个注册状态、NPC 效果、环境过程、世界日志和基准状态 | GraphWorld 世界动力学更完整 |
| 动作 | `goto/pick/place/scan/press/wait` | 10 种动作，增加 open/close/brush/fold/dump/refill | GraphWorld 维护操作覆盖更广；HSG 有 scan/wait/elevator |
| 规划结构 | 全局房间级子任务 + 局部单步动作，显式恢复/重规划 | active goal + skill phases + LLM/规则动作选择 | HSG-RTP 规划器更系统 |
| 评价 | Task/Subtask/Action SR、序列相似度、恢复 | state/spatial/human 长期曲线、blocking recovery | 两套指标测量对象不同，可组合 |

结论：两者“图的底层实体表示”确实有大量重叠，但创新点不在多几个节点或边。HSG-RTP 强在 **层次图 IR、全局/局部规划、动作提交与恢复**；GraphWorld 强在 **可执行人类日程、环境过程、在线任务到达和长期评价**。

## 5. 合并方案

不建议直接把两个仓库的数据类互相 import。建议建立一个版本化的 `WorldGraph IR`，两边都通过 adapter 使用：

```text
WorldGraph IR
├── ontology: canonical node/relation/state/trait definitions
├── snapshot: V + E + S at time t
├── transition: action/event/process -> validated delta
├── activity: preconditions + effects + temporal policy
├── goal: trigger + success predicate + priority/deadline/status
└── view adapters
    ├── HSG global view: zone/floor/room topology
    ├── HSG local view: current room + object tokens
    └── GraphWorld runtime view: dynamic state + schedules + metrics
```

分三步合并最稳妥：

1. **先统一 ontology，不改 planner。** 复用 HSG-RTP 的 canonical node types、四类 edge category、alias normalization 和 validation；保留 GraphWorld 的 states、traits、actions、processes 和 NPC events。
2. **再把 GraphWorld snapshot 投影成 HSG 双视图。** 全局规划器负责选房间级维护子任务，局部规划器负责动作；GraphWorld engine 仍是唯一状态转移真值源。
3. **最后统一任务 IR。** 把 GraphWorld 的 12 个 skill 和通用 restore 转成 `GoalSchema/GoalInstance`，让 HSG-RTP 的 planner 接受在线 goal queue，而不是只接受一次性 instruction。

最值得复用的具体模块：

- 从 HSG-RTP 取：`CanonicalGraph/CanonicalNode/CanonicalEdge`、relation aliases、zone/floor/transport/component、global/local view、preview-validate-commit、recovery/replan。
- 从 GraphWorld 取：typed states、capability traits、合法动作 schema、timed processes、NPC schedules/events、baseline-delta debt、长期评分和 blocking recovery。

## 6. 当前最需要补的建模缺口

1. 12 个显式技能严重偏向医院；超市、办公室和工厂主要靠通用归位，论文中的“任务多样性”会被质疑。
2. `clean/close/dry/fold/refill` 虽能作为高层 option 或合法动作出现，但没有统一 `GoalSchema`、成功谓词、阶段和统计口径。
3. 任务到达目前隐含在状态偏离扫描中，没有显式 `GoalInstance` 队列，因此难以严格统计 arrival、等待、抢占、恢复、截止时间和 starvation。
4. 当前 base scene 的 52 个 movable 实例能反复产生任务，但语义组合仍由有限 hand-authored event/skill 决定；应避免宣传成“无限新任务语义”。
5. 建议下一版优先新增超市补货、办公室归档/资源补充、工厂供料/送检/交接四组声明式技能，并让任务统计直接从 registry 自动生成。

## 7. 事实来源

- GraphWorld：`backend/core/nodes.py`、`edges.py`、`states.py`、`actions.py`、`action_schemas.py`、`assets/task_library.py`、`assets/npc_library.py`、`runtime/agent/maintenance_goals.py`、五个 base scene JSON。
- HSG-RTP：`README_zh-CN.md`、`graph_ir/ontology.py`、`graph_ir/graph.py`、`graph_ir/compilers.py`、`HLR_dataset/models/nodes.py`、`edges.py`、`pipeline/utils/state_manager.py`、`task_generator.py`。
- 文献定位：`docs/related_works/literature-search-20260917-dynamic-rtp/`。
