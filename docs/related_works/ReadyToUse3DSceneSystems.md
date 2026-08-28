# 可直接接入的 3D 场景系统调研

## 0. 结论

如果目标是把 GraphWorld 扩展成可运行的 3D 系统，而不是只写 related work，当前最实际的路线是：

```text
GraphWorld SceneGraph
-> 中间层 house/layout JSON
-> ProcTHOR / AI2-THOR 风格 3D scene
-> 前端可视化、replay 或 embodied simulator
```

没有现成系统能直接读取 GraphWorld 的动态图 schema，并完整保留 `human events`、`robot actions`、`object states`、`device cycles` 和长期评分。但是有五类系统可以直接复用或改造：

1. **ProcTHOR + AI2-THOR**：最适合作为第一版工程底座。
2. **Holodeck**：最接近“LLM 生成 3D embodied environment”的可用系统。
3. **CommonScenes / Graph-to-3D**：最接近 graph-to-3D 的研究路线，但工程接入成本更高。
4. **ATISS / InstructScene / SceneFormer**：适合作为房间内家具摆放模块，不适合作为完整 runtime。
5. **3D-FRONT / 3D-FUTURE / HSSD / Objaverse**：适合作为数据、资产和评估来源。

推荐优先级：

```text
第一阶段：GraphWorld -> ProcTHOR/AI2-THOR house JSON
第二阶段：引入 Holodeck 式 LLM constraints 和 object placement
第三阶段：参考 CommonScenes / InstructScene 做 learned layout 或 graph-to-3D projection
```

## 1. 快速选择表

| 系统 | 是否能直接跑 | 输入 | 输出 | 适合 GraphWorld 的位置 | 推荐程度 |
| ---- | ---- | ---- | ---- | ---- | ---- |
| ProcTHOR | 是 | procedural house spec / sampler | AI2-THOR house JSON | 3D house schema、房间/门/墙/物体生成、交互仿真底座 | 最高 |
| AI2-THOR | 是 | scene name 或 house JSON | 可交互 Unity 3D 环境 | navigation、pickup、open/close、物体状态和相机观测 | 最高 |
| Holodeck | 是，但依赖 OpenAI API、AI2-THOR、Objathor | language query | AI2-THOR-compatible scene | LLM scene planning、object selection、spatial constraints | 高 |
| CommonScenes | 有官方代码，但数据/权重依赖重 | scene graph triplets | 3D indoor scene layout/shape | graph-to-3D 方法参考、未来 learned projection | 中 |
| Graph-to-3D | 有代码线索，偏研究 | scene graph | object layout + shape | graph editing / static 3D generation 参考 | 中 |
| Planner3D | 有论文/方法线索 | graph prior + LLM-enhanced constraints | 3D indoor scene | LLM 增强拓扑和减少碰撞的参考 | 中 |
| GraphDreamer | 有项目页，偏生成模型 | scene graph | compositional 3D scene | 关系约束到生成式 3D 的参考 | 中低 |
| ATISS | 是，依赖 3D-FRONT/3D-FUTURE | room layout / floor plan | furniture layout | 单房间家具摆放 baseline | 中 |
| SceneFormer | 是，偏研究代码 | room layout | object categories, boxes, poses | layout-conditioned object placement 参考 | 中 |
| InstructScene | 有代码/项目 | language instruction | indoor 3D scene | text/layout/semantic graph prior 参考 | 中 |
| DirectLayout | 有项目页，偏研究 | text | numerical 3D layout | text-to-layout baseline | 中低 |
| Habitat 3.0 | 是 | Habitat scene/task config | embodied simulation | 人机共处、导航、avatar 协作评测参考 | 中 |
| VirtualHome | 是 | activity program | household activity simulation | NPC activity / household program 参考 | 中 |
| 3D-FRONT / 3D-FUTURE | 数据/资产可申请使用 | indoor scenes / furniture assets | room layouts, CAD furniture | layout 和 furniture placement 的训练/评估数据 | 高 |
| HSSD-200 | 是 | curated synthetic scenes | high-quality Habitat scenes | realist scene benchmark 和资产质量参考 | 中 |
| Objaverse | 是，规模大 | 3D asset collection | object meshes | proxy asset 升级到真实 mesh 的资产来源 | 中 |

## 2. 首选：ProcTHOR + AI2-THOR

### 2.1 为什么最适合直接接

ProcTHOR 和 AI2-THOR 的优势不是“生成结果最漂亮”，而是工程闭环完整：

- 有房间、墙、门、物体、receptacle、可交互状态。
- 输出是 AI2-THOR house JSON，能进入 Unity simulator。
- 支持 embodied agent 的导航、拾取、放置、开关、相机观测。
- schema 和 GraphWorld 的 node/edge/state/action 很容易建立映射。

GraphWorld 可以先把自己的图转换成 ProcTHOR/AI2-THOR 风格 JSON：

```text
floor / room nodes
-> rooms, walls, doors

fixed_object nodes
-> floor objects / wall objects / receptacles

movable_object nodes
-> small objects on receptacles or inside containers

control_object nodes
-> doors, switches, buttons, devices

robot / human nodes
-> agent spawn points / avatars
```

### 2.2 建议接入方式

不要第一步就改 GraphWorld runtime。建议新建 adapter：

```text
backend/core/geometry/
  layout_schema.py
  graph_to_layout.py
  layout_to_ai2thor.py
  asset_mapping.py
```

核心中间表示：

```text
GraphWorld SceneGraph
-> LayoutSpec
-> AI2THORHouseSpec
```

这样 GraphWorld 的评测核心仍然由图和规则驱动，3D 是可选 projection：

```text
GraphWorld runtime 是真相源。
AI2-THOR scene 是可视化/仿真 grounding。
```

### 2.3 风险

- AI2-THOR 资产库主要偏 household，对 hospital/supermarket/factory 需要额外映射或 proxy asset。
- GraphWorld 的某些状态，例如 `is_dirty`、`is_rotten`、`is_wet`，不一定有 AI2-THOR 原生状态，需要自定义 metadata。
- AI2-THOR 的物理和交互规则可能与 GraphWorld validator 不完全一致，短期应避免让 3D simulator 反过来决定评测结果。

## 3. 最像 LLM 生成场景：Holodeck

Holodeck 的流程很接近我们讨论的路线：

```text
language query
-> LLM 生成房间、物体和空间约束
-> 生成墙、门、窗
-> 选择大物体、小物体、灯光
-> 输出 AI2-THOR-compatible scene
```

对 GraphWorld 最有价值的是它的分层生成思想：

```text
scene program
-> room generation
-> wall / door / window
-> floor objects
-> wall objects
-> small objects on receptacles
-> lighting / materials
```

GraphWorld 可以借鉴它，但不建议让 Holodeck 直接替代 GraphWorld 的场景生成。更合适的方式是：

```text
GraphWorld graph/profile
-> 转成 Holodeck-style textual constraints
-> 用 LLM 补充 object selection 或 placement hints
-> 程序验证后落到 LayoutSpec
```

风险：

- LLM 输出不天然可审计。
- 对 API、资产库、AI2-THOR 依赖较强。
- 它生成的是 embodied environment，不是长期动态图 benchmark runtime。

## 4. 最接近 Graph -> 3D：Graph-to-3D / CommonScenes / Planner3D / GraphDreamer

这类工作回答的是：

```text
给定 object-level scene graph，能否生成静态 3D indoor scene？
```

这和 GraphWorld 的“图恢复 3D 模型”方向最接近。但它们通常有几个限制：

- 数据格式绑定 3D-FRONT / SG-FRONT / 3D-FUTURE。
- 主要面向家具室内场景，跨到医院、超市、工厂要重新定义 taxonomy 和资产。
- 输出更像静态布局/mesh，不是带人类事件、设备周期、机器人动作的 runtime。

推荐用途：

```text
论文 related work：证明 graph-conditioned 3D scene generation 是已有方向。
未来研究模块：GraphWorld graph -> learned 3D layout / object placement。
不要作为第一版工程底座。
```

具体条目：

- **Graph-to-3D, ICCV 2021**：很直接的 scene graph to 3D scene 工作。输入对象节点和关系边，输出对象布局和形状，适合作为 GraphWorld graph 恢复 3D 的早期参考。
- **CommonScenes, NeurIPS 2023**：scene graph conditioned 3D scene generation，把 scene graph 转成布局和 3D shape，强调 commonsense、一致性和可编辑性，并构建了基于 3D-FRONT 的 SG-FRONT。
- **Planner3D, 2024**：用 LLM 增强 graph prior，再做 3D indoor scene generation，目标是减少布局碰撞、提高关系合理性。它和“LLM 先生成/增强拓扑，再做 layout”的路线很近。
- **GraphDreamer**：更偏生成式 3D / diffusion，从 scene graph 生成 compositional 3D scene。适合参考“关系约束如何进入生成模型”，但离可执行 household simulator 稍远。

## 5. 房间 Layout / 家具摆放生成：ATISS / SceneFormer / InstructScene / DirectLayout

这类方法适合解决局部问题：

```text
已知房间轮廓和房间类型，如何摆家具？
```

GraphWorld 可以这样用：

```text
room node + room geometry
-> furniture placement model
-> fixed_object geometry
-> movable object placement rules
```

但它们不负责：

- 多房间 house topology。
- 可交互状态。
- NPC 日程和事件。
- robot action validator。
- 长期评分。

因此它们适合成为 `ObjectPlacement` 的一个可选后端，而不是主系统。

具体条目：

- **ATISS, NeurIPS 2021**：输入 room type 和 floor plan，生成合理家具布局。它把室内场景看作 unordered object set，对 GraphWorld 的“撒物体”模块很有启发。
- **SceneFormer**：给定 room layout，预测对象类别、位置、朝向和尺寸，可作为 layout-conditioned object placement 参考。
- **InstructScene, ICLR 2024**：从自然语言 instruction 生成 3D indoor scene，中间引入 semantic graph prior 和 layout decoder，和“LLM 生成语义/拓扑，再 layout”的路线接近。
- **DirectLayout**：从文本直接生成数值化 3D layout，流程可概括为 BEV layout -> lift to 3D -> refine placement，可作为 text-to-layout baseline。

## 6. 语言驱动 3D 环境生成：Holodeck / ProcTHOR

这一组更接近可落地的系统工程，而不是单纯生成模型。

- **Holodeck, CVPR 2024**：用 GPT-4 做 commonsense scene planning，用 Objaverse 资产填充场景，再优化空间关系约束。对 GraphWorld 最有价值的是“LLM 生成空间关系约束，程序优化 layout”的路线。
- **ProcTHOR, NeurIPS 2022**：程序化生成大量可交互房屋，用于 Embodied AI。它不是从 graph 生成，但非常适合作为 GraphWorld-3D 的工程参照：房间、物体、交互状态、物理引擎和 AI2-THOR 兼容 house JSON。

## 7. 可交互 3D 仿真平台：AI2-THOR / Habitat 3.0 / VirtualHome

这一组不是 graph-to-3D 生成器，但决定 GraphWorld-3D 最后能不能运行起来。

- **AI2-THOR**：Unity 3D，可导航、可交互，物体有 open/close、on/off、hot/cold 等状态。GraphWorld 的状态系统和它较容易对齐。
- **Habitat 3.0**：偏高性能 embodied simulation 和 human-robot collaboration，有 humanoid avatar、人机协作任务。适合对照 GraphWorld 的“长期人类扰动下世界维护”设定。
- **VirtualHome**：household activity + program representation。它把家庭活动表示成可执行程序，和 GraphWorld 的 NPC schedule / human event 很接近。

## 8. 数据集 / 资产库：3D-FRONT / 3D-FUTURE / HSSD-200 / Objaverse

这一组适合提供训练、评估和资产来源，而不是直接替代 GraphWorld runtime。

- **3D-FRONT / 3D-FUTURE**：室内家具场景和 CAD 家具资产，是很多 indoor scene synthesis 工作的基础。适合训练/评估 layout 和 object placement。
- **HSSD-200, CVPR 2024**：Habitat Synthetic Scene Dataset，包含高质量 3D 场景和大量真实物体模型。适合作为 realist scene benchmark 和资产质量参考。
- **Objaverse**：大规模 3D asset 来源，Holodeck 这类系统常用。GraphWorld 以后从 proxy box 升级到真实 mesh 时可以参考类似资产库。

## 9. GraphWorld 推荐工程路线

### 9.1 MVP

第一版只做 2.5D 到 3D proxy：

```text
room -> rectangle/polygon + wall height
door -> wall opening
fixed object -> box / cylinder proxy
movable object -> small proxy mesh
robot/human -> capsule
```

目标不是逼真，而是让图关系落到几何上：

```text
in(room)       -> object position inside room polygon
on(table)      -> object position on table top
inside(fridge) -> object hidden/contained in fridge volume
connected      -> rooms share door or passage
controls       -> switch/device metadata relation
```

### 9.2 中间层 schema

建议不要把几何字段散落到所有 node 里。可以让 node 保留少量 geometry id，详细几何由独立 layout 表维护：

```json
{
  "scene_name": "simple_home_1f",
  "layout": {
    "units": "meter",
    "rooms": {
      "living_room": {
        "floor_id": "F1",
        "polygon": [[0, 0], [5, 0], [5, 4], [0, 4]],
        "height": 2.8
      }
    },
    "objects": {
      "table_living_room": {
        "position": [2.0, 0.45, 1.5],
        "rotation_yaw": 90,
        "size": [1.2, 0.9, 0.75],
        "asset_id": "proxy/table"
      }
    }
  }
}
```

### 9.3 导出路径

短期：

```text
LayoutSpec -> Three.js visualization
```

中期：

```text
LayoutSpec -> AI2-THOR house JSON
```

长期：

```text
LayoutSpec -> glTF / USD / Blender / Habitat
```

## 10. 与现有工作的差异点

现有系统大多把 3D scene 当成生成结果。GraphWorld 更适合强调：

```text
3D scene is not the endpoint.
It is a geometric grounding of a dynamic graph runtime.
```

GraphWorld 的核心不是生成一个好看的房间，而是：

- 人会持续扰动环境。
- 物体状态会变化。
- 设备会周期运行。
- 机器人动作有合法性和长期后果。
- 评价关注 `state / spatial / human` 长期维护结果。

所以最合理的论文/系统表述是：

```text
Existing scene generation systems can provide geometry, assets, and interactive simulators.
GraphWorld contributes the dynamic graph-native runtime and long-horizon maintenance benchmark.
```

## 11. 参考链接

- ProcTHOR: https://github.com/allenai/procthor
- AI2-THOR: https://github.com/allenai/ai2thor
- Holodeck: https://github.com/allenai/Holodeck
- CommonScenes: https://github.com/ymxlzgy/commonscenes
- Graph-to-3D: https://github.com/he-dhamo/graphto3d
- Planner3D: https://arxiv.org/html/2403.12848v2
- GraphDreamer: https://graphdreamer.github.io/
- ATISS: https://github.com/nv-tlabs/ATISS
- InstructScene: https://chenguolin.github.io/projects/InstructScene/
- SceneFormer: https://github.com/cy94/sceneformer
- DirectLayout: https://directlayout.github.io/
- Habitat 3.0: https://aihabitat.org/habitat3/
- VirtualHome: https://virtual-home.org/
- 3D-FRONT: https://openaccess.thecvf.com/content/ICCV2021/papers/Fu_3D-FRONT_3D_Furnished_Rooms_With_layOuts_and_semaNTics_ICCV_2021_paper.pdf
- HSSD-200: https://3dlg-hcvc.github.io/hssd/
- Objaverse: https://objaverse.allenai.org/
