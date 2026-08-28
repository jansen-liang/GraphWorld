# 从 Graph 生成 3D 场景的相关工作调研

## 0. 简短结论

有。现有研究中已经存在比较明确的 `graph -> 3D scene` 路线，尤其是 **scene graph conditioned 3D indoor scene synthesis**。代表工作包括：

- `CommonScenes`：从 scene graph 生成可控 3D 室内场景，是当前最直接的近邻之一。
- `Scene Graph Masked VAE`：用 masked variational autoencoder 做 scene graph 条件下的 3D scene generation。
- `Graph2Scene`：用 interaction-aware scene graph 做 3D indoor scene generation。
- `GraphCanvas3D`：用层次化 graph-driven scene description 做可控 3D/4D 场景生成。

此外还有一条相邻路线是 `layout graph / adjacency graph -> floorplan / house layout`，代表工作包括 `Graph2Plan`、`House-GAN`、`House-GAN++` 和 `Graph Transformer GANs`。这类工作更多生成房间级布局或 2D/2.5D floorplan，不一定直接生成对象级 3D mesh，但对 GraphWorld 的“先房间拓扑、后对象填充”路线有参考价值。

和 GraphWorld 的关键区别是：这些工作大多把 graph 当作**静态几何生成条件**，目标是生成合理的 3D 场景、房间布局或对象摆放；GraphWorld 把 graph 当作**持续运行的世界状态底座**，目标是支持事件推进、动作合法性、状态转移、任务生成和长期评测。换句话说，相关工作回答“如何从图生成一个可看的/可用的 3D 场景”，GraphWorld 回答“如何让图本身成为一个会随时间演化、能评测 agent 的世界”。

## 1. 这个方向可以分成三类

### 1.1 Scene graph -> 3D indoor scene

这是最直接的“从 graph 生成 3D”路线。输入通常是对象节点、对象类别、空间关系、支撑关系或交互关系，输出是对象布局、3D bounding boxes、CAD/mesh 选择或生成后的完整室内场景。

典型目标：

- 保持输入 graph 中的语义关系和空间关系。
- 生成合理的对象尺寸、位置、朝向和相互关系。
- 允许通过编辑 graph 来控制生成结果。

对 GraphWorld 的意义：

- 证明 scene graph 可以作为 3D 场景生成接口。
- 如果以后要把 GraphWorld 的符号图投影成可视 3D 场景，这条路线最直接。
- 但这些工作通常不处理长期事件、NPC 日程、机器人动作、设备周期和评分闭环。

### 1.2 Layout graph -> floorplan / house layout

这类工作输入是房间类型、房间数量、房间邻接、建筑边界等高层约束，输出 floorplan、房间 bounding boxes 或 house layout。它们不一定生成对象级 3D 场景，但解决的是“图约束如何变成空间结构”。

典型目标：

- 从房间邻接图生成平面布局。
- 让布局满足建筑边界和房间连接约束。
- 生成真实、多样、与输入图兼容的 house layout。

对 GraphWorld 的意义：

- 支撑“先生成房间拓扑，再填充对象”的场景构建路线。
- 可以作为 GraphWorld base scene / graph profile 自动生成的上游模块。
- 但它们通常不关注对象状态、交互动作和长期维护任务。

### 1.3 3D scene graph construction / graph-grounded planning

这类工作不是从 graph 生成 3D，而是从 3D 感知构建 scene graph，或把已有 3D scene graph 用于机器人规划。代表方向包括 Hydra、ConceptGraphs、HOV-SG、SayPlan、Taskography 等。

对 GraphWorld 的意义：

- 它们说明 3D scene graph 是机器人理解和规划的有效中间层。
- 但多数工作将 graph 作为感知表示或规划 grounding，而不是一个持续更新的仿真运行时。

## 2. 代表工作

### 2.1 CommonScenes

- 论文：CommonScenes: Generating Commonsense 3D Indoor Scenes with Scene Graph Diffusion
- 作者：Guangyao Zhai, Evin Pinar Ornek, Shun-Cheng Wu, Yan Di, Federico Tombari, Nassir Navab, Benjamin Busam
- 发表：NeurIPS 2023
- arXiv：https://arxiv.org/abs/2305.16283
- NeurIPS：https://papers.nips.cc/paper_files/paper/2023/hash/5fba70900a84a8fb755c48ba99420c95-Abstract-Conference.html

这篇是最直接的 graph-to-3D 相关工作之一。论文明确提出，scene graph 是 controllable scene synthesis 的合适接口，并提出一个 fully generative model，将 scene graph 转换成语义合理、符合 commonsense 的可控 3D 室内场景。

方法上，它把生成拆成两条分支：

- 用 VAE 预测整体 scene layout。
- 用 latent diffusion 生成兼容的 object shapes。

它还构建了 `SG-FRONT`，在 3D-FRONT 上补充 object-level mesh 和关系标签，用来训练和评测 scene graph conditioned 3D scene generation。

对 GraphWorld 的参考价值：

- 证明“图作为 3D 场景生成控制接口”是成熟方向。
- 可作为 GraphWorld 从符号 scene graph 导出 3D 可视场景的技术参考。
- 其输入 graph 主要是静态语义/空间关系，输出是静态 3D scene；GraphWorld 的 graph 还包含动态状态、事件、动作合法性和长期评分。

可用定位句：

> CommonScenes demonstrates that scene graphs can serve as a controllable interface for generating commonsense 3D indoor scenes. GraphWorld is complementary: instead of using graphs mainly as static generation conditions, it treats the graph as a dynamic runtime substrate for events, actions, state transitions, and long-horizon evaluation.

### 2.2 Scene Graph Masked Variational Autoencoders

- 论文：Scene Graph Masked Variational Autoencoders for 3D Scene Generation
- 作者：Rui Xu, Le Hui, Yuehui Han, Jianjun Qian, Jin Xie
- 发表：ACM Multimedia 2023
- DOI：https://doi.org/10.1145/3581783.3612262
- DBLP：https://dblp.org/rec/conf/mm/XuHHQX23

这篇工作同样属于 scene graph conditioned 3D scene generation。它用 masked variational autoencoder 建模 scene graph 到 3D scene 的生成过程，重点在于从图结构约束中学习对象布局和场景生成分布。

对 GraphWorld 的参考价值：

- 可作为 CommonScenes 之外的另一篇直接 graph-to-3D 论文。
- 说明该方向不只有 diffusion 路线，也有 VAE/MAE 风格的生成建模路线。
- 仍然主要面向静态场景合成，而不是动态图世界运行。

可用定位句：

> Scene Graph Masked VAE further confirms that scene graphs can condition generative models for 3D scene synthesis, but the generated scene is typically an endpoint artifact rather than a continuously simulated world state.

### 2.3 Graph2Scene

- 论文：Graph2Scene: Versatile 3D Indoor Scene Generation with Interaction-aware Scene Graph
- 作者：Minglin Chen, Rongkun Yang, Qibin Hu, Kaiwen Xue, 等
- 发表：IROS 2025
- DOI：https://doi.org/10.1109/IROS60139.2025.11246595

Graph2Scene 进一步强调 `interaction-aware scene graph`。从题目和出版信息看，它试图让 scene graph 不只是对象类别和空间关系，而是包含交互相关关系，用于更通用的 3D indoor scene generation。

对 GraphWorld 的参考价值：

- “interaction-aware graph” 和 GraphWorld 中的 `interactive_actions`、设备控制关系、对象功能关系有明显概念连接。
- 它说明 graph-to-3D 正在从纯空间关系走向功能/交互关系。
- 但其目标仍是 3D scene generation，而 GraphWorld 的目标是长期任务运行和评测。

可用定位句：

> Recent graph-conditioned scene synthesis has begun to include interaction-aware relations, suggesting that functional graph structure is useful for 3D scene generation. GraphWorld extends this idea from generation-time constraints to runtime constraints that determine legal actions and long-term consequences.

### 2.4 GraphCanvas3D

- 论文：Graph Canvas for Controllable 3D Scene Generation
- 作者：Libin Liu, Shen Chen, Sen Jia, Jingzhe Shi, Zhongyu Jiang, Can Jin, Wu Zongkai, Jenq-Neng Hwang, Lei Li
- arXiv：https://arxiv.org/abs/2412.00091
- 代码：https://github.com/ILGLJ/Graph-Canvas
- 发表：ACM Multimedia 2025
- DOI：https://doi.org/10.1145/3746027.3754554

GraphCanvas3D 把场景描述成层次化 graph-driven scene descriptions，用 graph nodes 表示空间元素，并通过关系约束对象在 3D 环境中的一致性。它强调 programmable、extensible、controllable，并提到支持 4D scene generation，即引入 temporal dynamics 来描述随时间变化的场景。

对 GraphWorld 的参考价值：

- 它很接近“图作为可编辑场景描述语言”的方向。
- 其 4D scene generation 说法说明图生成领域已经开始关注时间维度。
- 但它的 temporal dynamics 更偏生成/展示层面的时序场景，GraphWorld 的时间维度则落实到 NPC 事件、设备周期、机器人动作和评分累积。

可用定位句：

> GraphCanvas3D uses hierarchical graph-driven descriptions for controllable 3D and even 4D scene generation. GraphWorld differs in that temporal change is not only a rendered sequence but a rule-governed runtime process tied to agent decisions and evaluation metrics.

## 3. 房间布局和楼层生成相关工作

### 3.1 Graph2Plan

- 论文：Graph2Plan: Learning Floorplan Generation from Layout Graphs
- 作者：Ruizhen Hu, Zeyu Huang, Yuhan Tang, Oliver van Kaick, Hao Zhang, Hui Huang
- 发表：ACM Transactions on Graphics, 2020
- arXiv：https://arxiv.org/abs/2004.13204
- DOI：https://doi.org/10.1145/3386569.3392391

Graph2Plan 从 `layout graph + building boundary` 生成 floorplan。layout graph 表示用户提供的稀疏设计约束，例如房间数量和布局关系。系统先生成 raster floorplan image，再生成 refined room boxes。

对 GraphWorld 的参考价值：

- 适合作为“房间拓扑图到楼层布局”的上游参考。
- GraphWorld 如果要自动生成更多 base scenes，可以先用类似方法生成房间级 topology/layout，再按房间功能填充对象。
- 但 Graph2Plan 不处理对象状态、可交互动作和事件流。

### 3.2 House-GAN 系列

- 论文：House-GAN: Relational Generative Adversarial Networks for Graph-constrained House Layout Generation
- 作者：Nelson Nauata, Kai-Hung Chang, Chin-Yi Cheng, Greg Mori, Yasutaka Furukawa
- 发表：ECCV 2020
- arXiv：https://arxiv.org/abs/2003.06988
- DOI：https://doi.org/10.1007/978-3-030-58452-8_10

House-GAN 把建筑约束表示为图，包括房间数量、房间类型和空间邻接，然后生成 axis-aligned room bounding boxes。论文评测 realism、diversity 和 compatibility with input graph constraint。

后续相关工作：

- House-GAN++: Generative Adversarial Layout Refinement Network towards Intelligent Computational Agent for Professional Architects, CVPR 2021, DOI：https://doi.org/10.1109/CVPR46437.2021.01342
- Graph Transformer GANs for Graph-Constrained House Generation, CVPR 2023, DOI：https://doi.org/10.1109/CVPR52729.2023.00216

对 GraphWorld 的参考价值：

- 这条线说明 graph-constrained generation 在建筑布局中已经很成熟。
- 适合支持“GraphWorld 场景图 profile 不是手写，而是可以生成”的论点。
- 但它们主要输出房间框和布局，不直接给出可执行的对象状态/动作系统。

## 4. 与 GraphWorld 的关系

### 4.1 可以借鉴的点

第一，graph 可以作为生成接口。CommonScenes、Scene Graph Masked VAE 和 GraphCanvas3D 都表明，graph 比纯文本或随机 latent code 更适合控制对象关系和空间结构。

第二，graph 可以分层。Graph2Plan 和 House-GAN 系列关注房间级图，CommonScenes 等关注对象级 scene graph。GraphWorld 也可以保持类似分层：房间拓扑图、对象包含关系图、设备控制图、状态图和事件图。

第三，graph 编辑可以带来可控变化。Graph-to-3D 工作通常支持通过编辑输入 graph 改变输出场景，这和 GraphWorld 的 graph profile / schedule profile 思路一致：改变图结构或事件结构，就能系统改变任务难度。

### 4.2 不能直接替代 GraphWorld 的地方

第一，它们大多是静态生成。即使生成了 3D 场景，也通常不会在 800 step 里持续执行 human events、robot actions 和 environment processes。

第二，它们主要关注几何和视觉合理性。GraphWorld 关心的是长期维护效果，包括 `state_score`、`spatial_score` 和 `human_score`。

第三，它们不一定有动作合法性系统。GraphWorld 中 `open/close/pick/place/press/brush/fold/dump` 等动作会直接读写图状态，并被 validator 检查合法性。

第四，它们不以 benchmark runtime 为目标。GraphWorld 的核心贡献不是“生成一个场景”，而是“让场景在规则和人类扰动下持续演化，并评测 agent 能否维护它”。

## 5. 写论文 Related Work 时的建议

可以把这条线放在“graph-based scene generation / graph-conditioned environment construction”下面，和 3D scene graph construction / graph-grounded planning 分开写。

建议表述：

> A growing body of work studies graph-conditioned 3D scene synthesis, where scene graphs or layout graphs are used to generate indoor scenes, object arrangements, or floorplans. CommonScenes converts scene graphs into controllable 3D indoor scenes with scene graph diffusion, while Graph2Plan and House-GAN generate floorplans or house layouts from layout/adjacency graphs. These works show that graph structure is a powerful interface for controllable environment construction. GraphWorld is complementary: rather than using a graph only as a static generation condition, it turns the graph into a dynamic runtime substrate whose nodes, relations, states, human events, robot actions, and evaluation metrics co-evolve over time.

如果篇幅很短，可以只写一句：

> Graph-conditioned 3D scene synthesis methods such as CommonScenes demonstrate that scene graphs can generate controllable indoor scenes, but they primarily target static geometric synthesis; GraphWorld instead uses a graph-native world as an executable, continuously evolving benchmark runtime.

## 6. 对后续系统设计的启发

如果 GraphWorld 后续想接 3D，可考虑三层路线：

1. `GraphWorld scene graph -> room/floor layout`
   借鉴 Graph2Plan / House-GAN，从房间拓扑和边界生成 floorplan。

2. `room/object graph -> 3D object layout`
   借鉴 CommonScenes / Scene Graph Masked VAE / Graph2Scene，从对象关系生成 3D boxes、朝向和对象实例。

3. `dynamic graph state -> visual state renderer`
   GraphWorld 自己负责把 `is_dirty`、`is_open`、`is_wet`、`fill_level`、`held_by`、`worn_by` 等运行时状态映射到材质、动画、位置和可视效果。

这意味着未来的 3D 化不应该把 GraphWorld 改成一个普通 3D simulator，而应该让 3D 成为动态图世界的一个 projection layer：图仍然是状态真值和规则执行层，3D 负责可视化、交互和可能的感知输入。

## 7. 参考文献清单

| 类别 | 工作 | 年份/发表 | 链接 | 与 GraphWorld 的关系 |
| ---- | ---- | ---- | ---- | ---- |
| Scene graph -> 3D scene | CommonScenes | NeurIPS 2023 | https://arxiv.org/abs/2305.16283 | 最直接的 scene graph conditioned 3D indoor generation 近邻 |
| Scene graph -> 3D scene | Scene Graph Masked VAE | ACM MM 2023 | https://doi.org/10.1145/3581783.3612262 | 另一条 scene graph 到 3D scene 的生成建模路线 |
| Scene graph -> 3D scene | Graph2Scene | IROS 2025 | https://doi.org/10.1109/IROS60139.2025.11246595 | 强调 interaction-aware scene graph，和 GraphWorld 的交互/动作关系相关 |
| Graph-driven 3D/4D scene | GraphCanvas3D | arXiv 2024 / ACM MM 2025 | https://arxiv.org/abs/2412.00091 | 层次化 graph-driven scene description，可控生成和 4D 生成 |
| Layout graph -> floorplan | Graph2Plan | TOG 2020 | https://arxiv.org/abs/2004.13204 | 房间拓扑到 floorplan，上游布局生成参考 |
| Graph-constrained house layout | House-GAN | ECCV 2020 | https://arxiv.org/abs/2003.06988 | 房间邻接图到 house layout，支持 graph profile 自动生成思路 |
| Graph-constrained house layout | House-GAN++ | CVPR 2021 | https://doi.org/10.1109/CVPR46437.2021.01342 | House-GAN 后续布局 refinement |
| Graph-constrained house layout | Graph Transformer GANs | CVPR 2023 | https://doi.org/10.1109/CVPR52729.2023.00216 | Transformer/GAN 路线的 graph-constrained house generation |
