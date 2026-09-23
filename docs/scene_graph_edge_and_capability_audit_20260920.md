# SceneGraph Edge 与场景能力审计

## 1. 数据范围

统计 `backend/data/sg_output/simple_graph/simple_*_1f.json` 的五个基础场景，不包含带 `__profile` 的实验变体。

| 指标 | 数量 |
|---|---:|
| 场景 | 5 |
| Node | 252 |
| Edge | 302 |
| relation | 9 |
| category 字符串 | 6 |
| edge_type | 7 |
| semantic_type | 77 |

## 2. 当前 Edge 统计

### Relation

| relation | 数量 | 当前含义 |
|---|---:|---|
| `inside_room` | 132 | 物体进入房间的结构位置 |
| `contains` | 70 | floor/room/container 的反向或结构容纳 |
| `connected` | 34 | 房间连接 |
| `on` | 22 | 物体在表面上 |
| `controls` | 21 | 按钮/水龙头/旋钮控制设备 |
| `in` | 15 | 物体在容器/设备内 |
| `at` | 3 | 初始 agent/NPC 位置 |
| `near` | 3 | 初始邻近关系 |
| `part_of` | 2 | 组件属于设备 |

### 当前 category

| category | 数量 | 问题 |
|---|---:|---|
| `structural` | 206 | 同时承载楼层、房间、物体和组件结构 |
| `containment` | 35 | 与 `structural` 中的 `in/on` 重叠 |
| `physical` | 31 | 主要是 `contains`，但不是统一物理语义 |
| `control` | 21 | 最稳定的一类，对应 `controls` |
| `spatial` | 6 | `connected/near/contains` 混合 |
| `runtime_seed` | 3 | 不是世界关系，应是场景初始状态元数据 |

结论：当前不能直接用 `category` 做规划判断。`relation` 才是现阶段唯一可追溯的事实类型，但也需要 canonical 方向和端点约束。

## 3. 推荐的四层 Edge 规范

顶层只有一个 `Edge` 类，使用 `kind + relation + attributes`：

| kind | relation 示例 | 是否属于 SceneGraph |
|---|---|---|
| `spatial` | `at`、`inside`、`on`、`near`、`connected` | 是 |
| `logical` | `part_of`、`linked_to`、`requires` | 是 |
| `control` | `controls`、`powered_by` | 是 |
| `task` | `decomposes_to`、`achieves`、`requires` | 只属于 TaskGraph |

`consumes`、`produces`、`transforms` 是 `logical` kind 下的过程关系，不另设顶层 kind。

存储层只保留 canonical 方向：

```text
object --inside--> container
object --on--> surface
component --part_of--> device
control --controls--> device
door --connects--> room_a
door --connects--> room_b
```

`contains`、`holds`、`has_part` 等反向关系由查询层派生。`runtime_seed` 应迁移到 `SceneVersion.initial_state`。

## 4. 复合物体

洗衣机、洗碗机、咖啡机和组装台都使用同一表示：

```text
device Node
├── component Nodes
├── part_of Edges
├── controls Edges
├── state schema
└── ProcessSpec / CapabilitySpec
```

例如咖啡机过程至少声明：输入咖啡豆、水、杯子；设备；持续时间；消耗效果；输出咖啡；输出状态。设备不能仅凭 `semantic_type=coffeemachine` 就被认为支持生产，必须存在完整 `ProcessSpec` 并通过可执行计划验证。

## 5. 场景是否合理

发布前按四层检查：

1. 几何：房间共墙、门合法、footprint 在父空间内、不重叠。
2. 图结构：Edge 端点类型、canonical 方向、父子无环、组件角色唯一。
3. 能力：动作的 actor/target 能力、访问条件、容量和设备门状态可满足。
4. 过程：输入存在、输出可生成、状态字段有 schema、至少存在一条可执行 action chain。

最终场景元数据需要明确列出：

```text
supported_task_types
unsupported_task_types
process_catalog
validation_issues
verified_plans
```

没有验证计划的任务只能是 candidate，不能声称场景支持。

## 6. 当前 2D footprint 修正

当前编辑器的栅格为 `0.5m/cell`。房间现在按 RoomTypeSpec 的面积和比例离散化，不再全部使用 10×8：

```text
entrance 8×6       living_room 12×10
kitchen 8×6        bedroom 10×8
bathroom 6×5       balcony 8×4
```

控制小件 `button/knob/room_light/faucet` 默认 1×1；小型可移动物默认 1×1；微波炉/洗碗机/洗衣机约 2×1 或 2×2；床、桌、沙发等使用 3×2、4×2 等较大 footprint。它们是符号世界的占位和容量近似，不是 CAD 尺寸。
