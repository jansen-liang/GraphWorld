# GraphWorld 交互与生命周期架构

## 核心原则

玩家或 NPC 产生的是输入或意图，不是业务动作。世界运行时根据目标能力、当前状态、手部状态、空间关系和命中信息，解析出规范化的 canonical action，再执行状态和关系转移。

```text
InputEvent / AgentIntent
        -> AffordanceResolver
        -> CanonicalAction
        -> Preconditions
        -> StateDelta / RelationDelta
        -> EventLog + visual feedback
```

3D 层只负责射线命中、距离、遮挡、碰撞、手部位置和动画；GraphWorld runtime 负责能力、状态、关系、前置条件、时间过程、任务和评分。玩家与 Agent 共用同一套 resolver 和 transition engine。

## 四个稳定层级

### Object / Agent

对象和智能体都由几何、能力、状态和关系组成。

Agent 的几何层声明碰撞体、身高、可达距离和手部/操作器数量；能力层声明能否抓取、承载、使用工具以及是否需要双手；状态层记录当前姿态、每只手持有什么、当前操作；关系层记录 `held_by`、`inside`、`on` 等空间事实。

双手关系使用 `held_by`（默认右手）、`held_by_left` 和 `held_by_both`。普通物体只占用请求指定的手；声明 `two_hand_required` 的物体必须同时占用左右手，任何已占用手位都会使新的抓取解析失败。

### Capability

能力描述“能做什么或能参与什么”，例如 `pickable`、`place_target`、`openable`、`washable`、`cookable`、`cleanable`、`timed_device`。能力不是当前结果，也不包含当前进度。

### State

状态描述当前事实，例如 `is_open`、`is_running`、`cycle_remaining`、`is_dirty`、`is_wet`、`temperature`、`water_level`、`vitality`。状态变化必须通过通用 transition 执行。

### Composition / TemporalRule

复合物体由 `component_of`、`hinge_of`、`slides_in` 和 storage slot 组成。时间规则描述触发过程、自然变化、持续时间、当前进度、完成效果和中断条件。它不是新的状态类别；它驱动状态转移。

## 输入和解析

玩家输入只包括 `move`、`look`、`interact_primary`、`interact_secondary`、`grab`、`release` 等。输入携带目标命中点、距离和手部快照，但不直接写入 `open`、`pick` 或 `place`。

resolver 按以下信息推导结果：

```text
目标能力 + 玩家能力 + 手部状态 + 当前状态 + 空间关系 + 命中面
```

例如：

- 空手命中关闭的 `openable` 目标 -> `open`
- 空手命中可抓取物体 -> `pick`
- 手持物体命中可承载 slot -> `place`
- 手持清洁工具命中脏且可清洁目标 -> `brush`
- 运行中设备的门 -> 拒绝 `open`

canonical action 仍然保留，用于规划、验证、回放、评分和事件日志；它只是世界内部语义，不是玩家 UI 的输入协议。

## 承载和设备

承载面必须是具体 slot，声明内部尺寸、容量、网格和允许的物体能力。放置时先检查体积和容量，再根据命中平面网格计算中心位置，建立 `slot -> object` 的包含关系。

设备通过通用配置声明：接受哪些能力、需要哪些资源、哪些组件运行时锁定、每个状态变化的周期以及完成效果。设备运行时锁门；启动前置条件由能力和状态检查统一处理，不在前端按设备名称分支。

## 时间推进

统一入口为：

```python
advance_time(world, elapsed_steps)
```

它推进共享时钟，执行触发过程和自然过程。每个过程由“规则 + 当前进度 + 状态效果”构成：例如衣服进入洗衣机后快速变湿，完整周期后变干净；花瓶水位自然下降，花朵 vitality 随缺水降低；食物新鲜度最终转为变质或腐烂。

## 当前验收闭环

- 脏衣服可被拿起、放入洗衣机 slot。
- 洗衣机门未关闭或缺少必需资源时不能启动。
- 运行中设备门不能打开。
- 洗衣周期推进后衣服变干净并保持独立的湿状态。
- 衣服可放到晾衣架具体层面，按体积、容量和网格放置。
- 冰箱和微波炉遵守各自的承载能力，不能放入不兼容物体。
- 水槽水位按连续数值变化，并映射到六档视觉表现。
- 湿毛巾才可作为清洁工具使用；食物新鲜度随时间变化。
- 第三人称可见智能体身体和双手，仿真默认显示天花板，界面卡片不互相遮挡。
- 场景布局可由对象拓扑、槽位和规则模板批量生成，而不是逐物体手调。

## 禁止事项

不得在交互解析、时间推进或渲染逻辑中新增按单个语义物体散落的特判。新增行为必须通过能力、状态、关系、复合拓扑或 TemporalRule 配置表达，并由通用 resolver / transition engine 执行。

## 实现状态与验收顺序

当前实现已经具备统一 resolver、复合物体槽位、设备门锁、洗衣液前置条件、洗衣/晾晒声明式周期、连续水位和食物 freshness 生命周期。验收按最小闭环执行：

1. 脏衣服具有 `washable + is_dirty`，放入 washer 的 slot；门关闭且有 `laundry_detergent` 后启动。
2. `on_start` 立即把衣服变湿，周期完成只把 `is_dirty` 变为 false；运行期间门的 `open` 请求被拒绝。
3. 湿衣服放入具有 `contained_temporal_profile` 的承载面，周期完成后变干；同一机制可复用于烘干机或其他支持面。
4. 微波炉的 slot 只接受 `cookable`，完成效果由 profile 改变温度/熟度；冰箱和其他容器只由 slot 的 accepted capabilities 决定接收范围。
5. 水槽用 `water_level: 0..100` 保存连续值，`has_water`/六档显示是派生视图，不是第二套水量事实。
6. 食物以 `freshness` 连续衰减，在阈值处投影为 `is_spoiled`，周期结束投影为 `is_rotten`。

水槽到容器或湿润工具的交互通过 `water_reservoir`、`water_container`、`wettable` 能力转移水量，并记录 `water_transferred` 事件；容器获得水或工具变湿时，源水量同步扣减。

新增设备只需声明 capabilities、slot topology、state effects 和 duration；不得在 `timed_transitions.py`、前端点击处理或单个动作分支中增加该设备名称判断。

编辑器预览没有运行实例时，前端使用同构的本地 `resolveLocalInteraction` 解析 canonical action；正式仿真 run 通过后端 `/runs/{run_id}/interactions`。Pointer Lock 期间视角切换可使用 `V` 键，退出锁定后也可点击视角按钮。

批量场景生成使用：

```text
POST /scene-versions/{scene_version_id}/layout/generate
```

接口依次从对象模板补全 composition、实例化门/抽屉/slot、按拓扑生成确定性布局并执行完整校验。返回值包含生成后的 source JSON、房间/物体数量、materialized component 数量和校验问题；生成结果只有显式 publish 后才形成新场景版本。
