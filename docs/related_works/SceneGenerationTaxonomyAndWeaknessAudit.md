# GraphWorld 场景生成体系与弱点审计

## 0. 结论先行

你说得对：当前 GraphWorld 的图生成/场景构建还不够像一套有外部依据的体系，更像是我们为了让 benchmark 跑起来先做出来的一组 hand-crafted scenes。它现在已经能支撑实验，但如果写成论文，需要补上“场景、房间、物体、状态、活动为什么这样选”的依据，否则容易被质疑为 toy world 或作者主观设计。

补充口径：这份文档保留“GraphWorld 当前哪里弱、体系应该怎么补”的审计；真正作为新文献和代码依据的主线，应转到 [近年场景生成代码审计：哪些能为 GraphWorld 所用](./RecentSceneGenerationCodeAudit.md)。ScanNet、Matterport3D、NYUv2 这类 2017 前后的数据集只适合放在 label/taxonomy background，不应该作为图生成方法的核心依据。

最合理的补强方向不是简单再加几个场景，而是建立一套 **evidence-backed scene graph construction protocol**：

```text
场景域选择
-> 房间类型 taxonomy
-> 对象类型 taxonomy
-> object-room compatibility
-> affordance / state schema
-> human activity / event schema
-> graph profile perturbation
-> automatic validation and coverage report
```

这套方法可以从现有室内场景数据集、程序化环境生成、家具/物体资产库、活动 benchmark 和具身任务 benchmark 里取依据。

## 1. 当前 GraphWorld 的实际情况

### 1.1 当前已有的强点

GraphWorld 已经不是空想图。当前代码已经有：

- 统一 object capability 模板：见 `backend/core/assets/object_library.py`。
- home 房间模板：见 `backend/core/assets/room_library.py`。
- 5 个 base scene：home、hospital、supermarket、office、factory。
- 3 个 graph profile：`compact_cleaning`、`normal_logistics`、`spread_device`。
- 可执行状态和动作系统：状态、候选动作、validator、transition rules 和 scoring 都已经接到 runtime。

抽样统计当前落盘场景：

```text
20 scene json files
5 base domains x (base + 3 variants)
29 unique room ids
78 unique object semantic types in scene jsons
72 object templates in OBJECT_LIBRARY
6 registered home room types
1 registered floorplan template
```

这些数字说明现在的系统已经能跑，但也暴露了核心问题：生成体系、taxonomy 和落盘场景之间还没有完全闭合。

### 1.2 当前最薄弱的地方

第一，房间 taxonomy 不完整。

`room_library.py` 目前只注册了 home 相关的 6 类房间：

```text
entrance, living_room, bedroom, bathroom, kitchen, balcony
```

但实际 20 个 scene json 里出现了 29 个 room id，例如：

```text
assembly_line, warehouse, control_room, break_room,
lobby, registration, waiting_area, outpatient_clinic_1,
pharmacy, open_office, meeting_room, pantry,
produce_area, shelf_area, checkout_area, cold_storage
```

这些 hospital / office / factory / supermarket 房间大多没有进入统一 `RoomTypeSpec`，所以论文里很难说“我们有一套系统房间类型体系”。

第二，物体 taxonomy 与场景实例不完全一致。

`OBJECT_LIBRARY` 里有 72 个模板，但 scene json 中出现了 78 个 object semantic types。也就是说，有些落盘语义类型是场景里出现了，但没有成为统一对象模板/能力定义的一部分。这会削弱 schema consistency。

第三，场景域选择缺少外部依据。

现在的 5 个域是合理的：home、hospital、supermarket、office、factory 都是长期服务机器人可能进入的空间。但论文需要解释为什么是这 5 类，而不是任意挑选。否则审稿人会认为是作者主观挑的 demo environments。

第四，graph profile 仍是人工命名和人工扰动。

`compact_cleaning`、`normal_logistics`、`spread_device` 很有实验意义，但目前更像研究者设计的三种压力条件。它们缺少参数化定义，例如：

- room graph diameter 增加多少算 spread？
- key object entropy 或平均路径长度如何变化？
- cleaning / logistics / device pressure 如何从对象和事件分布中计算？

第五，缺少 object-room compatibility 的数据来源。

例如 `medicine_fridge` 应该在 pharmacy/staff room，`printer` 应该在 office，`cold_storage` 应有 `shelf/drink/box` 等。这些都符合常识，但需要来自数据集统计、benchmark ontology 或显式规则表，而不能只靠作者判断。

第六，human event / NPC schedule 缺少活动语料依据。

当前 NPC 日程能制造扰动，但活动类型、前置条件和效果主要是我们设计的。论文中需要借 VirtualHome、BEHAVIOR-1K、ALFRED 这类活动/任务 benchmark 来支撑“人类活动如何生成任务压力”。

第七，缺少生成质量验证。

现在主要验证是实验能跑、指标能出。但场景生成本身还缺少 validation report，例如：

- 每个房间是否满足 required objects？
- 每个 object 是否有合法 parent？
- 每个 interactive object 是否至少有一个可触发状态/动作？
- 每个 NPC event 的 precondition 是否对应真实图节点？
- 每个 scene profile 是否真的改变了 topology / object pressure？

第八，只有 5 个 base scenes，容易被质疑覆盖不足。

虽然 profile 和 schedule 扩展了实验矩阵，但 base domains 仍少。需要明确论文定位：GraphWorld 当前是 benchmark runtime / methodology prototype，而不是大规模场景库。或者补充程序化生成以产生更多 instances。

## 2. 可以支撑 taxonomy 的文献与数据来源

本节不要在论文里写成“主要方法依据”。更稳的写法是：

- 2023-2026 的 Holodeck、CommonScenes、DiffuScene、Infinigen Indoors 等工作支撑当前 scene generation / procedural generation 主线。
- 3D-FRONT、3D-FUTURE、AI2-THOR、ProcTHOR 等支撑 room/object/asset/action schema。
- ScanNet、Matterport3D、NYUv2 只作为真实室内语义标签背景，避免让读者觉得我们在用旧数据集包装新方法。

### 2.1 房间、布局和家具类别

#### 3D-FRONT

- 论文：3D-FRONT: 3D Furnished Rooms with layOuts and semaNTics
- 发表：ICCV 2021
- arXiv：https://arxiv.org/abs/2011.09127
- DOI：https://doi.org/10.1109/ICCV48922.2021.01075

3D-FRONT 是室内场景和房间布局的重要依据。它包含大规模 synthetic indoor scenes，强调 professionally designed layouts、room semantics 和 high-quality textured 3D models。论文摘要中提到包含 18,968 个 furnished rooms 和 13,151 个 furniture objects。

对 GraphWorld 的用法：

- 用 3D-FRONT 的 room/furniture semantics 作为 home/office-like indoor room-object compatibility 的依据。
- 从其 room layout + furniture arrangement 思路中抽出 “room type -> default furniture set”。
- 支撑论文中“房间和对象不是任意捏造，而是参照室内场景数据集构建”的表述。

#### 3D-FUTURE

- 论文：3D-FUTURE: 3D Furniture shape with TextURE
- 发表：IJCV 2021
- arXiv：https://arxiv.org/abs/2009.09633
- DOI：https://doi.org/10.1007/s11263-021-01534-z

3D-FUTURE 是家具资产和家具类别的重要来源。它包含 household scenario 中的 3D furniture shapes，并带有高质量纹理。

对 GraphWorld 的用法：

- 用来支撑家具类 object taxonomy，例如 bed、chair、table、cabinet、sofa、shelf、desk 等。
- 如果以后接 3D asset，可以作为 object semantic type 到 asset category 的映射参考。

#### Graph2Plan / House-GAN

- Graph2Plan: Learning Floorplan Generation from Layout Graphs, TOG 2020, https://arxiv.org/abs/2004.13204
- House-GAN: Relational Generative Adversarial Networks for Graph-constrained House Layout Generation, ECCV 2020, https://arxiv.org/abs/2003.06988

这两类工作证明 “room adjacency graph -> floorplan/layout” 是成熟路线。

对 GraphWorld 的用法：

- 支撑 `room graph` 作为场景生成第一层。
- 支撑 profile 中 topology perturbation 的形式化定义，例如 graph diameter、centrality、room adjacency constraints。
- 但它们不应作为本文新方法主依据，只能作为旧 floorplan/layout baseline。

### 2.2 真实室内语义标签

#### ScanNet

- 论文：ScanNet: Richly-Annotated 3D Reconstructions of Indoor Scenes
- 发表：CVPR 2017
- DOI：https://doi.org/10.1109/CVPR.2017.261

ScanNet 提供真实室内 3D reconstruction 和 semantic annotation。它适合支撑真实室内对象类别，而不是只依赖 synthetic furniture datasets。

对 GraphWorld 的用法：

- 用 ScanNet label taxonomy 校验常见 indoor object categories。
- 支撑 “objects in rooms” 的真实世界分布。
- 注意：只作为历史标签背景，不作为 GraphWorld 图生成方法的主依据。

#### Matterport3D

- 论文：Matterport3D: Learning from RGB-D Data in Indoor Environments
- 发表：3DV 2017
- DOI：https://doi.org/10.1109/3DV.2017.00081

Matterport3D 是真实大规模室内空间数据集，适合支撑 room-scale、building-scale indoor environments。

对 GraphWorld 的用法：

- 用于支撑多房间/大空间室内环境，而不是单房间 toy scene。
- 可作为 room connectivity 和 object semantic coverage 的参考。
- 注意：只作为真实数据背景，不作为新方法主线。

#### NYU Depth v2

- 论文：Indoor Segmentation and Support Inference from RGBD Images
- 发表：ECCV 2012
- DOI：https://doi.org/10.1007/978-3-642-33715-4_54

NYUv2 常用于室内语义分割和支持关系推理。它虽然不是 GraphWorld 的直接近邻，但可支撑 “support relation / containment / room-object relation” 的语义基础。

注意：NYUv2 更老，只能做背景，不建议在 GraphWorld 方法段重点引用。

### 2.3 程序化和生成式 embodied environments

#### ProcTHOR

- 论文：ProcTHOR: Large-Scale Embodied AI Using Procedural Generation
- arXiv：https://arxiv.org/abs/2206.06994
- 项目：https://procthor.allenai.org

ProcTHOR 是最应该引用的程序化环境生成工作之一。论文明确说它是 procedural generation of Embodied AI environments，可以生成 diverse、interactive、customizable、performant virtual environments，并展示了 10,000 generated houses。

对 GraphWorld 的用法：

- 支撑“benchmark 不应只靠少数手工场景，而应支持程序化生成和大规模实例化”。
- 作为我们后续把 5 个 base scenes 扩展为 N 个 scene instances 的方法依据。
- 其不足是偏 3D embodied simulation，而 GraphWorld 当前偏 graph-native symbolic runtime。

#### Holodeck

- 论文：Holodeck: Language Guided Generation of 3D Embodied AI Environments
- 发表：CVPR 2024
- DOI：https://doi.org/10.1109/CVPR52733.2024.01536

Holodeck 从语言生成 3D embodied AI environments。它适合支撑高层场景描述到 3D 环境生成的路线。

对 GraphWorld 的用法：

- 可以作为 “scene type / room program / object list 可以由高层 specification 驱动生成” 的依据。
- 但语言生成可能不够可控，GraphWorld 更需要可审计的 graph schema 和规则验证。

#### Infinigen Indoors

- 论文：Infinigen Indoors: Photorealistic Indoor Scenes using Procedural Generation
- 发表：CVPR 2024
- DOI：https://doi.org/10.1109/CVPR52733.2024.02058

Infinigen Indoors 支撑高质量程序化室内视觉场景。它对 GraphWorld 的价值主要是说明“程序化室内场景生成”是活跃方向。

对 GraphWorld 的用法：

- 作为未来 3D rendering / visual projection 的参考。
- 不是 GraphWorld 当前必须实现的部分，因为我们核心是动态符号状态和长期评测。

#### DiffuScene

- DiffuScene: Denoising Diffusion Models for Generative Indoor Scene Synthesis, CVPR 2024, DOI：https://doi.org/10.1109/CVPR52733.2024.01938

DiffuScene 从 room type、floor plan、已有对象上下文或 text condition 生成 indoor object layouts。

对 GraphWorld 的用法：

- 可以支撑 object placement 不是纯手工，而可由统计/生成模型决定。
- 但它们不直接解决 dynamic events 和 long-horizon agent evaluation。
- 代码细读见 `RecentSceneGenerationCodeAudit.md`。

### 2.4 人类活动、任务和可交互物体

#### VirtualHome

- 论文：VirtualHome: Simulating Household Activities Via Programs
- 发表：CVPR 2018
- DOI：https://doi.org/10.1109/CVPR.2018.00886

VirtualHome 把 household activities 表示成 programs，是 GraphWorld 的 human event / task generation 很好的依据。

对 GraphWorld 的用法：

- 参考其 household activity programs，把人类活动拆成对象前置条件和效果。
- 支撑 “任务来自人类活动造成的环境偏离”。

#### ALFRED

- 论文：ALFRED: A Benchmark for Interpreting Grounded Instructions for Everyday Tasks
- 发表：CVPR 2020
- DOI：https://doi.org/10.1109/CVPR42600.2020.01075

ALFRED 聚焦 everyday household tasks，基于 AI2-THOR，有明确的对象交互和任务类型。

对 GraphWorld 的用法：

- 用于支撑 pick/place/open/close/toggle/clean/heat/cool 等 household task primitives。
- GraphWorld 和 ALFRED 的差异是：ALFRED 是指令驱动 episode，GraphWorld 是持续人类扰动下的长期维护。

#### BEHAVIOR-1K / OmniGibson

- 论文：BEHAVIOR-1K: A Benchmark for Embodied AI with 1,000 Everyday Activities and Realistic Simulation
- 项目：https://behavior.stanford.edu/behavior-1k
- OmniGibson：https://behavior.stanford.edu/omnigibson

BEHAVIOR-1K 的价值在于任务规模和 everyday activities。它适合支撑 GraphWorld 的 activity/task coverage，而不是 scene layout。

对 GraphWorld 的用法：

- 从 everyday activities 中抽象出高频可维护任务：清洁、整理、补给、搬运、准备、恢复。
- 用它支撑 “human event failures” 和 “blocking recovery” 的任务设计。

#### AI2-THOR

- 论文：AI2-THOR: An Interactive 3D Environment for Visual AI
- arXiv：https://arxiv.org/abs/1712.05474
- 项目：https://ai2thor.allenai.org

AI2-THOR 提供交互式 3D household environments 和对象动作，是 ALFRED、ProcTHOR 等工作的生态基础。

对 GraphWorld 的用法：

- 支撑对象 affordance 和 interaction primitive。
- 可作为 object state/action schema 的参考，例如 openable、toggleable、pickupable、receptacle、dirty/clean 等。

## 3. 建议的新方法：四层 taxonomy + 两层扰动

### 3.1 场景域层

不要只说我们选了 5 个场景，而要定义场景域选择原则：

```text
选择原则：
1. 有明确人类活动流
2. 有可维护状态偏离
3. 有空间归位需求
4. 有对象/设备/补给闭环
5. 能覆盖 private / public / institutional / commercial / industrial spaces
```

于是当前 5 类可以被重新解释为：

| GraphWorld 场景 | 覆盖空间类型 | 主要长期压力 |
| ---- | ---- | ---- |
| home | private domestic | 清洁、洗衣、食物、归位 |
| hospital | institutional care | 医疗补给、床单、药品、等待区 |
| supermarket | commercial service | 商品补货、冷藏、购物车、结账 |
| office | workplace | 文件、会议室、杯子、工位 |
| factory | industrial workspace | 零件、工具、安全装备、质检 |

这样写比“我们想了五个场景”更稳。

### 3.2 房间层

为每个 scene domain 建立 `RoomTypeSpec`，而不是只有 home 有注册表。

每个 room type 至少有：

```text
room_type
domain
function_role
privacy_level
allowed_neighbors
required_neighbors
default_fixture_templates
default_movable_templates
default_activity_tags
required_objects
optional_objects
forbidden_objects
```

房间来源：

- room program / layout pipeline：优先参考 Holodeck、CommonScenes、DiffuScene。
- household rooms：参考 AI2-THOR、ProcTHOR；3D-FRONT / 3D-FUTURE 作资产和家具背景。
- activity rooms：参考 VirtualHome / BEHAVIOR activity locations。
- hospital / supermarket / factory：可以先采用 domain program + object-function rules，但需要在文档中承认这部分更偏 task-driven construction。
- 真实室内标签：ScanNet / Matterport3D 只做辅助 label coverage check。

### 3.3 物体层

对象不要只按名字列，而应拆成三套标签：

```text
semantic_type: cup, medicine_box, washer
functional_class: container, tool, consumable, device, surface, supply, waste
capability_set: pickable, openable, cleanable, fillable, switchable, perishable
```

这样做的好处是：即使 object semantic types 不同，也能共享动作和状态逻辑。

建议依据：

- furniture / layout object：CommonScenes、DiffuScene、3D-FRONT、3D-FUTURE。
- procedural asset / visual projection：Holodeck、Infinigen Indoors。
- household interactable object：AI2-THOR、ProcTHOR、ALFRED。
- everyday activity object：VirtualHome, BEHAVIOR-1K。
- real indoor labels：ScanNet、Matterport3D、NYUv2 只做背景校验。

### 3.4 活动/事件层

当前 NPC schedule 应改写成 activity schema：

```text
activity_type
actor_role
location_type
required_objects
preconditions
effects
failure_mode
recovery_goal
source_basis
```

其中 `source_basis` 可以标注来自：

- VirtualHome household program
- BEHAVIOR-1K everyday activity
- ALFRED task primitive
- domain-specific hand-authored rule

这会让“人类事件”从想象规则变成可审计规则。

### 3.5 Profile 扰动层

把现在的 `compact_cleaning / normal_logistics / spread_device` 改写成可量化扰动：

```text
topology_pressure:
  room_graph_diameter
  average_shortest_path(robot_start, key_objects)
  cross_room_dependency_count

object_pressure:
  movable_object_count
  misplaced_object_count
  dirty_object_count
  supply_object_count
  device_chain_count

event_pressure:
  human_event_rate
  blocking_precondition_count
  deadline_window_length
```

这样 profile 不再只是名字，而是可以报告的生成参数。

## 4. 当前工作最需要补的实验/文档

### 4.1 Coverage report

建议新增一个表，列出每个场景：

```text
rooms
objects
semantic types
interactive objects
human roles
activity types
event preconditions
state variables touched
action types required for recovery
```

这能直接回应“不是 toy scene”的质疑。

### 4.2 Schema consistency check

建议加脚本检查：

```text
所有 semantic_type 是否在 object taxonomy 中注册
所有 room id/type 是否在 room taxonomy 中注册
所有 interactive_actions 是否被 validator 支持
所有 event precondition/effect 引用的 node/state 是否存在
所有 required_objects 是否在对应 room 或可达 room 中出现
```

### 4.3 Source mapping table

建议给每个类别加来源：

```text
semantic_type, functional_class, supported_by, used_in_scenes, used_by_events
cup, consumable/container, AI2-THOR/ALFRED/VirtualHome, home/office, return_cups
medicine_box, supply, BEHAVIOR/domain rule, hospital, replenish_medicine_box
toolkit, tool, domain rule, factory, return_toolkit
```

其中 `domain rule` 不可避免，但要标出来，不要伪装成完全来自数据集。

### 4.4 Procedural split

如果论文要更强，最好不要只说 5 个 base scenes。可以说：

- 当前论文主实验使用 5 个 canonical domains。
- 每个 domain 支持 profile perturbation。
- 下一版或补充实验可从 taxonomy 生成多个 instances。

更强版本是补一个小实验：

```text
5 domains x 3 generated instances x 3 profiles
```

即使不跑所有模型，只跑 no_robot + best agent，也能证明场景生成不是单点手工样例。

## 5. 可以写进论文的定位段

中文草稿：

> 为避免场景构建退化为少量手工样例，GraphWorld 将场景图构建拆分为场景域、房间类型、物体类型、功能能力、人类活动和扰动 profile 六个层次。近年的 Holodeck、CommonScenes、DiffuScene 与 Infinigen Indoors 说明，室内场景可以通过语言、场景图、扩散模型或程序化规则生成，并能进一步连接 3D asset、layout 和视觉标注；GraphWorld 借鉴这些工作对 layout、asset selection、placement constraint 和 procedural instantiation 的分层思想，但目标不是生成静态 3D 几何，而是构建一个可执行的动态图运行时，使对象状态、人类事件、机器人动作和长期评分在同一图结构中共同演化。3D-FRONT、3D-FUTURE、AI2-THOR、ProcTHOR 以及真实室内语义数据集仅作为 room/object/action schema 的辅助背景。

英文草稿：

> To avoid relying on a small set of ad hoc hand-crafted scenes, GraphWorld organizes scene construction into six layers: scene domains, room types, object types, functional capabilities, human activities, and graph perturbation profiles. Recent systems such as Holodeck, CommonScenes, DiffuScene, and Infinigen Indoors show that indoor environments can be instantiated from language, scene graphs, diffusion-based layout models, or procedural rules, often with links to 3D assets, layouts, and visual annotations. GraphWorld builds on this layered view of layout generation, asset selection, placement constraints, and procedural instantiation, but targets a different missing layer: an executable graph-native runtime in which persistent object states, exogenous human events, robot recovery actions, and long-horizon metrics co-evolve. Earlier indoor scene and asset datasets are used only as auxiliary background for room, object, and action schemas.

## 6. 最坦诚的 weakness statement

如果论文需要 limitations，可以写：

> The current version of GraphWorld uses a limited number of canonical domains and manually specified scene profiles. Although the runtime, action validation, state transitions, and long-horizon metrics are fully executable, the scene construction pipeline is not yet a large-scale data-driven generator. In particular, room-object compatibility, domain-specific object choices, and human event schedules are partly rule-authored. Future versions should derive room and object distributions from indoor scene datasets, expose profile perturbations as measurable graph parameters, and generate multiple instances per domain with automatic schema validation.

这段是诚实的，但不致命。它把弱点变成 future work，同时强调当前贡献在 runtime/evaluation，而不是 3D asset generation。

## 7. 优先级建议

最应该立刻补的不是 3D，而是三件事：

1. 补全 `RoomTypeSpec`
   给 hospital / supermarket / office / factory 建 room taxonomy。

2. 补 `taxonomy_source.md`
   给每个 room/object/activity 标来源：dataset / benchmark / domain rule。

3. 补 `validate_scene_schema.py`
   自动检查 semantic type、room type、actions、states、events、profile pressure。

这三件事完成后，GraphWorld 的场景生成就会从“我们 brainstorm 出来的”变成“有 taxonomy、有来源、有 validator、有 coverage report 的 benchmark construction protocol”。
