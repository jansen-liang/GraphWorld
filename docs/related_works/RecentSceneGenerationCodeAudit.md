# 近年场景生成代码审计：哪些能为 GraphWorld 所用

## 0. 先说结论

你说得对，GraphWorld 的场景生成依据不能主要靠 2017 年前后的数据集来撑。那些数据集最多用来说明 indoor label taxonomy 的历史来源，不能作为我们“图生成方法”的核心依据。

这份笔记只把 2023-2026 附近、且有代码或明确工程路径的方法放在主线上看。结论是：

1. **没有一个现有方法可以直接替代 GraphWorld。** 近年的方法大多生成静态 3D 室内场景、家具布局、视觉标注或 AI2-THOR house JSON；GraphWorld 需要的是跨场景域的动态图 runtime、状态转移、人类事件和长期评测。
2. **最值得借的是 Holodeck / ProcTHOR 的 schema 和 object placement 经验。** 它们能支撑 room-object compatibility、receptacle、asset metadata、AI2-THOR 兼容 house JSON。
3. **CommonScenes / DiffuScene 更适合作为 graph/profile 到 3D visual projection 的未来层。** 它们对“物体如何摆放、布局是否真实”有价值，但不解决动态事件和长期任务。
4. **Infinigen Indoors 适合作为高质量视觉/仿真资产生成参考。** 它的强项是 photorealistic procedural scene、dense annotations、Blender pipeline；不是 GraphWorld 的 symbolic graph 生成方法。
5. **GraphWorld 现在最该补的不是直接接一个 3D 生成模型，而是把自己的 graph construction protocol 写清楚：domain -> room -> object -> affordance/state -> event -> profile -> validation。**

## 1. 快速对比表

| 方法 | 年份 | 代码状态 | 输入 | 输出 | 主要效果 | 对 GraphWorld 的适配 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| Holodeck | CVPR 2024 | 官方代码可读，依赖 OpenAI API、AI2-THOR、Objathor | language query / high-level scene request | AI2-THOR-compatible procedural scene JSON、top-down image/video | 能从语言生成多房间 embodied AI environment，含 rooms/walls/doors/windows/objects/lights | **最接近可借用的工程路线**：借 scene JSON schema、object selection、placement constraints；不适合作为可审计 taxonomy 的唯一来源 |
| CommonScenes | NeurIPS 2023 | 官方代码可读，依赖 3D-FRONT/SG-FRONT/3D-FUTURE-SDF/PyTorch3D | scene graph triplets + object classes + boxes/SDF | 3D indoor scene layout/geometry | graph-conditioned 3D scene generation，能从关系图生成家具布局和形状 | 适合未来做 GraphWorld graph 到 3D visualization；不覆盖动态 state/event/NPC |
| DiffuScene | CVPR 2024 | 官方代码可读，依赖 3D-FRONT/3D-FUTURE/pretrained weights | room floor plan、room mask、可选 text/partial scene/given objects | bbox layout、retrieved textured objects、rendered image/mesh | diffusion-based indoor scene synthesis，支持 unconditional、text-conditioned、completion、rearrangement | 适合生成 object layout/profile variants；不提供 graph runtime，也不覆盖非家庭/非家具域 |
| Infinigen Indoors | CVPR 2024，另有 Articulated 2025 | 官方仓库可访问，完整 clone 较重；README/docs 可读 | procedural configs/seeds | Blender scene、photorealistic render、depth/flow/segmentation/3D boxes 等标注 | 高质量程序化室内视觉场景和 dense annotations | 适合未来视觉层和仿真资产层；不适合作为 GraphWorld room/object/event taxonomy 的核心依据 |
| ProcTHOR | NeurIPS 2022 | 官方代码可读，虽不够新但工程上仍重要 | procedural sampler、room specs、asset/receptacle databases | AI2-THOR house JSON | 大规模程序化 household scenes，有 placement annotations、receptacles、object states | 可借 object-room compatibility、receptacle rules、schema validation；但主文献地位应低于 2024 方法 |
| ATISS | NeurIPS 2021 | 官方代码可读，较旧 | room/floor plan/object sequence | room object layout/mesh | autoregressive indoor furniture placement | 只作为旧 baseline，不作为新方法依据 |
| Graph2Plan / House-GAN | 2020 | 代码可读，较旧 | room adjacency graph | floorplan/room boxes | graph-constrained floorplan generation | 只说明“room graph -> floorplan”是可行路线，不支撑 GraphWorld 的动态图评测 |
| GraphCanvas3D / Graph-Canvas | 近期论文线索 | 论文页指向 GitHub，但当前未核验到可 clone heads | scene graph / canvas-like constraints | 3D scene | 暂不可工程判断 | 暂不作为可依赖代码依据 |

## 2. 本次代码核验证据

本次不是只看论文摘要，而是把能找到的官方代码拉到本地读了关键入口。核验状态如下：

| 方法 | Repo | 本地核验 commit | 关键代码/文档 | 证据结论 |
| ---- | ---- | ---- | ---- | ---- |
| Holodeck | `https://github.com/allenai/Holodeck` | `362b8ed` | `ai2holodeck/generation/holodeck.py`, `rooms.py`, `small_objects.py`, `prompts.py`, `README.md` | `generate_scene` 明确输出 AI2-THOR house JSON、top-down image/video；依赖 OpenAI API、AI2-THOR、Objathor assets |
| CommonScenes | `https://github.com/ymxlzgy/commonscenes` | `ec24cc2` | `README.md`, `SG-FRONT.md`, `dataset/threedfront_dataset.py`, `scripts/eval_3dfront.py` | 官方 graph-to-3D scene code；输入是 SG-FRONT scene graph triplets + boxes/SDF，评估含 FID/KID、MMD/COV/1-NN、关系约束准确率 |
| DiffuScene | `https://github.com/tangjiapeng/DiffuScene` | `d78a289` | `README.md`, `scripts/generate_diffusion.py`, `scripts/utils.py`, `compute_fid_scores.py`, `improved_precision_recall.py` | 官方 diffusion indoor layout code；生成 bbox params 后检索 3D-FUTURE 物体，可渲染 top-down image 或导出 mesh |
| Infinigen | `https://github.com/princeton-vl/infinigen` | `05a0975` | `README.md`, `docs/HelloRoom.md`, `docs/GroundTruthAnnotations.md`, `docs/ExportingToSimulators.md` | 仓库很重，完整 checkout 未完成，但 README/docs 可读；强项是 Blender procedural scene、photorealistic render 和 dense annotations |
| ProcTHOR | `https://github.com/allenai/procthor` | `53d5bd4` | `scripts/example.py`, `procthor/generation/house.py`, `room_specs.py`, `objects.py`, `small_objects.py`, `databases/*.json` | 可生成/验证/导出 AI2-THOR house JSON；数据库里有 room placement、receptacle、object groups 和 states |
| ATISS | `https://github.com/nv-tlabs/ATISS` | `0909ce0` | `README.md`, scene synthesis scripts | 旧但完整的 indoor furniture layout baseline；仅作上游背景 |
| Graph2Plan | `https://github.com/HanHan55/Graph2Plan` | `3e53c47` | `README.md` | 旧 floorplan/layout graph baseline；不处理 object state/event |
| HouseGAN | `https://github.com/ennauata/housegan` | `1afeabd` | `README.md` | 旧 graph-constrained floorplan baseline；只保留为历史参照 |

没有实际跑训练/推理的原因也要写清楚：这些方法普遍依赖大规模外部数据和 pretrained weights，例如 3D-FRONT、3D-FUTURE、SG-FRONT、Objathor assets、AI2-THOR、Blender pipeline 或 OpenAI API。对我们当前目标来说，读代码确认输入输出、生成层级、评估指标和工程依赖，比临时跑一个不完整 demo 更有判断价值。

## 3. 代码细读

### 3.1 Holodeck

代码入口：`ai2holodeck/generation/holodeck.py`。

它的 `generate_scene` 流程非常清晰：

```text
empty house
-> generate_rooms
-> generate_walls
-> generate_doors
-> generate_windows
-> select_objects
-> generate floor objects
-> generate wall objects
-> generate small objects on receptacles
-> optional ceiling objects
-> generate lights
-> assign layers
-> skybox/materials
-> save scene JSON + top-down image/video
```

输出是 AI2-THOR 风格的 procedural scene JSON，核心字段包括：

```text
rooms
walls
doors
windows
objects
floor_objects
wall_objects
small_objects
proceduralParameters.lights
```

对 GraphWorld 的价值：

- 可以借它的生成流水线分层：room program、建筑结构、object selection、large object placement、small object placement、render/export。
- 可以借它的 AI2-THOR/Objathor asset retrieval 思路，把 object semantic type 映射到可视化资产。
- 可以参考它把 small objects 放在 receptacle 上的方式，给 GraphWorld 建 `parent/receptacle/support` 约束。

不能直接满足 GraphWorld 的地方：

- 它主要依赖 LLM prompt 和 asset retrieval，生成结果不天然可审计。
- 它不是 graph-native runtime，没有 GraphWorld 里的 state transition、human event、task pressure、long-horizon scoring。
- 它更适合生成 embodied AI 3D environment，不适合解释我们 hospital/supermarket/factory 的动态图规则为什么这样设计。

推荐用法：

```text
不要替换 GraphWorld。
把 Holodeck 当作 3D/AI2-THOR export 的参考 schema，以及 scene construction pipeline 的近年依据。
```

效果判断：

```text
能满足：从高层 query 生成可视化 embodied environment，适合做 3D export/schema inspiration。
不能满足：不能作为 GraphWorld 的动态图 runtime；LLM 生成也不够可审计。
```

### 3.2 CommonScenes

代码入口包括：

```text
dataset/threedfront_dataset.py
scripts/train_Graph-to-Box.sh
scripts/train_Graph-to-3D.sh
scripts/train_CommonScenes.sh
helpers/visualize_graph.py
helpers/visualize_scene.py
```

它的数据格式很适合我们理解 graph-conditioned scene generation：

```text
classes_{room_type}.txt
relationships.txt
relationships_{room_type}_{split}.json
obj_boxes_{room_type}_{split}.json
```

`relationships_*.json` 里是 object ids 和 triplets：

```text
[subject_id, object_id, relationship_id, relationship_text]
```

`obj_boxes_*.json` 里有：

```text
param7
scale
model_path
scene_center
```

它的关系类型包括 spatial 和 semantic relations，例如：

```text
left / right / front / behind
bigger than / smaller than
same material as / same style as
standing on / above
```

对 GraphWorld 的价值：

- 支撑“从 scene graph 到 3D 室内场景”这一层，不是空想。
- 可以把 GraphWorld 的 room-object graph 映射成 CommonScenes 风格的 triplets，用作未来 3D projection。
- 它的关系标签能启发 GraphWorld 补充 `support/containment/spatial` edge taxonomy。

不能直接满足 GraphWorld 的地方：

- 数据和模型强绑定 3D-FRONT / SG-FRONT / 3D-FUTURE-SDF。
- 主要是 bedroom/livingroom/dining/library 等室内家具域，不覆盖 hospital/supermarket/factory。
- 它生成静态布局和几何，不处理 object state、human events、任务恢复和长期评分。

推荐用法：

```text
作为 graph-to-3D related work 和未来可视化层。
不作为 GraphWorld 当前动态图生成体系的替代。
```

效果判断：

```text
能满足：GraphWorld scene graph 如果未来要投影到 3D furniture scene，CommonScenes 是最贴近的 graph-conditioned 证据。
不能满足：只解决静态布局/几何，不解决多域服务场景、状态演化和事件恢复。
```

### 3.3 DiffuScene

代码入口：`scripts/generate_diffusion.py`。

核心生成流程是：

```text
load dataset and 3D-FUTURE assets
-> choose/test room floor plan
-> floor_plan_from_scene(...)
-> network.generate_layout(room_mask, optional text, seeds)
-> dataset.post_process(bbox_params)
-> class_labels + translations + sizes + angles
-> retrieve textured objects
-> render top-down image or export mesh
```

代码里实际生成的布局张量会被拼成：

```text
class_labels
translations
sizes
angles
```

然后通过 3D-FUTURE object retrieval 转成可渲染物体。

对 GraphWorld 的价值：

- 适合补“object placement/layout generation”依据。
- 可以用来做某些 home/office-like room 的布局变体。
- 它的评估思路有参考价值：FID/KID、precision/recall、bbox IoU、intersection、symmetry 等。

不能直接满足 GraphWorld 的地方：

- 它主要关注静态室内家具布局。
- text-conditioned 模式仍围绕 partial-scene/room description，不是完整 graph runtime。
- 不解决可交互对象状态、human event schedule、domain-specific service workflow。

推荐用法：

```text
借它做 object layout/profile diversification 的依据。
GraphWorld 的核心 runtime 仍然需要自己保持 graph-native。
```

效果判断：

```text
能满足：给定 room/floor plan 生成更真实的 furniture bbox/layout，并可渲染/导出 mesh。
不能满足：不能输入 GraphWorld 的完整动态图，也不覆盖 hospital/supermarket/factory workflow。
```

### 3.4 Infinigen Indoors

代码与文档入口：

```text
README.md
docs/HelloRoom.md
docs/GroundTruthAnnotations.md
docs/ExportingToSimulators.md
infinigen/datagen/manage_jobs
```

它的强项不是 symbolic graph，而是：

```text
procedural generation
photorealistic Blender rendering
depth / surface normal / optical flow
panoptic segmentation
object metadata
3D bounding boxes
export to simulators
```

对 GraphWorld 的价值：

- 可以作为未来视觉化和仿真导出参考。
- 2025 的 articulated asset 方向也能启发 GraphWorld object capability 到 articulated simulation asset 的映射。
- 它的 dense annotations 可以支撑以后把 GraphWorld 的 graph state 映射到视觉观测。

不能直接满足 GraphWorld 的地方：

- 它没有提供我们需要的 multi-domain task graph、NPC event、长期维护评分。
- 配置/Blender pipeline 比较重，不适合作为当前 paper experiment 的直接依赖。
- 它解释不了 GraphWorld 的 hospital/supermarket/factory object/action taxonomy。

推荐用法：

```text
作为未来视觉层和模拟资产层，不放在当前动态图方法的中心。
```

效果判断：

```text
能满足：高质量视觉生成、dense visual annotations、未来可视化/仿真资产。
不能满足：不提供 GraphWorld 需要的 symbolic event/state/action benchmark schema。
```

### 3.5 ProcTHOR

虽然 ProcTHOR 是 2022，不符合“新文献主线”，但代码对我们很有用。它应该作为工程参考，不应该压过 2024 方法。

代码里值得借的部分：

```text
procthor/generation/room_specs.py
procthor/generation/objects.py
procthor/generation/object_states.py
procthor/databases/placement-annotations.json
procthor/databases/receptacles.json
procthor/databases/object-groups.json
procthor/databases/asset-database.json
```

对 GraphWorld 的价值：

- `placement-annotations.json` 可以启发 object-room compatibility。
- `receptacles.json` 可以启发 parent-child placement probabilities。
- `object_states.py` 可以启发 `isOn/isDirty/open` 等状态初始化。
- `HouseGenerator(...).sample().to_json(...)` 说明 procedural house JSON 是成熟工程路线。

限制：

- room 类型基本是 household：Bedroom、Bathroom、Kitchen、LivingRoom。
- 不覆盖 GraphWorld 当前的 hospital、supermarket、office、factory。
- 不是最新主线，不宜作为“我们方法依据”的主引用。

效果判断：

```text
能满足：object-room compatibility、receptacle relations、AI2-THOR house schema、object state initialization。
不能满足：场景域太窄，不能支撑 GraphWorld 的 hospital/supermarket/office/factory 全部 domain program。
```

## 4. 效果与 GraphWorld 适配性判定

### 4.1 能满足的部分

这些近年方法可以补 GraphWorld 的四类弱点：

| GraphWorld 当前弱点 | 可借方法 | 具体借法 |
| ---- | ---- | ---- |
| room/object taxonomy 显得手工 | Holodeck、ProcTHOR、CommonScenes | 把 room program、object selection、receptacle/placement 规则整理成 source mapping table |
| object placement 缺少依据 | DiffuScene、CommonScenes、ProcTHOR | 引入 object-room compatibility、support relation、bbox/layout validation |
| 缺少 3D/visual projection | CommonScenes、DiffuScene、Infinigen | 作为未来 graph-to-3D 或 visual observation 层 |
| 缺少生成质量验证 | DiffuScene、Infinigen、ProcTHOR | 引入 intersection、coverage、object metadata、schema validation |

### 4.2 不能满足的部分

它们普遍不能直接解决：

```text
multi-domain graph runtime
object state transition rules
human activity/event schedule
long-horizon maintenance pressure
robot action validation
blocking recovery
dynamic scoring
hospital/supermarket/factory-specific workflows
```

这正好说明 GraphWorld 的贡献不要写成“我们也生成 3D 场景”，而要写成：

```text
GraphWorld builds executable dynamic scene graphs for long-horizon service-robot evaluation.
Recent 3D scene generators provide useful priors for layout, assets, and visual projection,
but they do not model persistent graph state, exogenous human events, and recovery-oriented scoring.
```

### 4.3 最终判定

| 需求 | 现有方法能否直接满足 | 最合适借鉴对象 | GraphWorld 仍需自己做的部分 |
| ---- | ---- | ---- | ---- |
| 多 domain room/object taxonomy | 部分满足 | Holodeck、ProcTHOR、CommonScenes | hospital/supermarket/factory 的 domain program 和 source mapping |
| 物体布局真实感 | 可以满足一部分 | DiffuScene、CommonScenes、ProcTHOR | 把布局约束投影到 GraphWorld graph schema |
| 3D 可视化/导出 | 可以满足一部分 | Holodeck、Infinigen、CommonScenes | 从 GraphWorld JSON 到这些格式的 adapter |
| 可交互对象状态 | 部分满足 | ProcTHOR、AI2-THOR 生态 | GraphWorld 的跨域状态变量和 transition rules |
| 人类活动/NPC event | 不能直接满足 | BEHAVIOR-1K、ALFRED、VirtualHome 作为任务语料 | GraphWorld event schema、precondition/effect、schedule |
| 长期维护评测 | 不能满足 | 无直接替代 | GraphWorld scoring、blocked recovery、long-horizon metrics |
| 可审计生成过程 | 不能完全满足 | ProcTHOR 的 validator 思路 | taxonomy source table、schema validator、coverage report |

一句话判断：

```text
这些代码足以支撑 GraphWorld 的 scene construction protocol，但不足以替代 GraphWorld。
GraphWorld 应该借它们的 layout/asset/placement/validation 层，把核心贡献放在 dynamic graph runtime 和 long-horizon evaluation。
```

## 5. 建议改 GraphWorld 方法体系

我建议把 GraphWorld 的图生成写成这套 protocol：

```text
Domain program
-> Room type schema
-> Object semantic schema
-> Functional capability schema
-> Placement and receptacle constraints
-> Human activity/event schema
-> Profile perturbation parameters
-> Automatic validation and coverage report
```

每层都标来源：

| 层 | 来源优先级 |
| ---- | ---- |
| room program | Holodeck / ProcTHOR / domain program rules |
| furniture/object layout | CommonScenes / DiffuScene / ProcTHOR |
| receptacle/support relations | ProcTHOR / AI2-THOR / CommonScenes |
| visual/asset projection | Holodeck / Infinigen / DiffuScene |
| activity/task events | BEHAVIOR-1K / ALFRED / VirtualHome / domain rules |
| long-horizon graph runtime | GraphWorld 自己的贡献 |

这里要诚实：hospital/supermarket/factory 很多规则很难从现成 residential datasets 里直接来。因此这部分应该明确叫 **domain program rules**，然后用 validator 和 coverage report 保证它可审计，而不是伪装成完全 data-driven。

## 6. 对论文写法的直接建议

不要这样写：

```text
We design five scenes based on common environments.
```

这样太像 brainstorm。

建议改成：

```text
We instantiate GraphWorld scenes through an evidence-backed graph construction protocol.
The protocol separates domain programs, room types, object semantics, functional capabilities,
placement constraints, human activity events, and profile perturbations. Recent 3D scene
generation systems such as Holodeck, CommonScenes, DiffuScene, and Infinigen motivate the
layout, asset, and procedural-instantiation layers, while GraphWorld contributes the missing
dynamic graph runtime for persistent object states, exogenous human events, recovery actions,
and long-horizon scoring.
```

中文定位：

```text
GraphWorld 不应该被定位为又一个 3D 场景生成器，而应该定位为一个动态图 benchmark runtime。
近年 3D scene generation 负责告诉我们“房间、物体、布局、资产可以怎么生成”，但它们没有解决
“物体状态如何持续演化、人类活动如何制造任务压力、机器人如何在长期图状态中恢复环境”。
这正是 GraphWorld 的核心贡献。
```

## 7. 下一步最该补的工程

优先级从高到低：

1. 补 `RoomTypeSpec`：hospital / supermarket / office / factory 都进统一 room schema。
2. 补 `taxonomy_source.md`：每个 room/object/activity 标 `Holodeck/CommonScenes/DiffuScene/ProcTHOR/domain_rule` 等来源。
3. 补 `validate_scene_schema.py`：检查 room type、semantic type、receptacle、action/state/event 引用是否闭合。
4. 补 `coverage_report.py`：输出每个 scene/profile 覆盖了多少 room/object/action/state/event。
5. 可选做 3D layer：优先尝试 Holodeck/AI2-THOR JSON export 或 CommonScenes-style scene graph projection，不要一开始就接重型训练 pipeline。
