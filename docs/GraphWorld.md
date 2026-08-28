# GraphWorld：面向长时程具身任务规划的持续运行符号图仿真框架

## 1. 引言

服务机器人真正落地时，面对的并不是一个静态、一次性求解的任务环境，而是一个持续运行、不断变化、任务与事件反复出现的开放世界。在这样的场景中，机器人不仅要完成“把杯子放到桌上”这类单次指令，还要长期面对房间状态变化、物体位置迁移、人的活动干扰、周期性任务到达以及突发事件插入等复杂因素。更关键的是，真实服务机器人不应只是一个“接到命令再执行”的被动执行器，而应具备持续在线的自主决策能力，能够结合环境状态、潜在需求与长期目标，自驱动地判断下一步动作。因此，具身智能的核心挑战不再只是“给定任务如何规划”，而是“机器人如何在一个持续演化的世界中长期维持可用的世界认知、任务判断与行为决策能力”。

现有大量具身规划、语义地图和场景图工作已经证明，结构化表示对于机器人任务推理具有重要价值。但从机器人长期自主运行的角度看，现有方法仍存在几个根本不足：第一，许多工作仍以静态环境或短时 episode 为基本假设，缺少对全局时间推进和长期状态演化的统一建模；第二，现有 scene graph 往往更多承担“场景表达”或“任务 grounding 中间层”的职责，而尚未真正成为能够驱动任务流、规则约束和状态转移的仿真基础设施；第三，多数 Agent 规划框架仍围绕“给定目标-规划执行-任务结束”的有限闭环展开，对长期在线服务场景中的持续任务决策、事件响应与自我调整关注不足。

基于上述问题，我们提出 GraphWorld：一个面向长时程具身任务规划的持续运行符号仿真框架。GraphWorld 的核心思想是，不应把图仅仅视为环境的静态表示，而应将其提升为驱动仿真、任务生成、状态推进与行为评估的统一符号基座。该图不仅包含房间、物体、设备、人物、机器人等实体及其关系，还显式编码时间推进、外生事件、任务生成、规则约束、局部状态演化与动作引起的状态更新。换言之，我们研究的不是“静态场景图上的一次任务规划”，而是“在持续运行的符号仿真环境中研究长期任务决策与执行”。

从当前项目的设计逻辑来看，我们真正关心的并不是一个单次任务是否被完成，而是机器人在持续运行过程中，是否能够长期把整个环境维持好，并把与人相关的服务做好。因此，GraphWorld 更适合被定义为一个用于研究长期服务机器人综合表现评分的持续运行符号仿真框架。目前最关键的两类分数包括：

- 世界分：衡量机器人是否把环境维持在一个健康、稳定、低风险、可持续服务的状态，例如清洁程度、物品归位情况、资源状态、安全风险、异常积压和环境秩序等。
- 人类分：衡量机器人是否真正服务好了人，包括任务响应质量、时效性、舒适性、合理性、规则遵守情况，以及是否避免给人带来额外打扰、风险和负担。

因此，GraphWorld 要回答的核心问题可以概括为：如何构建一个持续运行的符号仿真引擎，使机器人能够在长期任务流、外生事件和环境变化下，通过自主决策不断提升世界分和人类分，而不是只在单次指令下被动完成局部任务。

本文的主要贡献可概括为三点：

1. 提出持续运行的符号图仿真框架，将时间推进、外生事件、任务流、规则约束和状态演化统一纳入图结构驱动的长期仿真过程。
2. 提出面向长期自主决策的记忆-规划-执行-反思 Agent 闭环，使机器人能够在持续运行环境中基于图状态主动判断、主动行动并动态调整策略。
3. 提出面向多场景扩展的统一仿真与长期评测接口，通过世界分、人类分及回放分析机制，对机器人在长时序运行中的环境维护能力与人机服务质量进行系统评估。

## 2. 参考文献

下面只保留与 GraphWorld 主线最强相关的文献，避免被“如何构建一个图”这类支线带偏。

### 2.1 开放任务规划仿真引擎与动态 benchmark

1. BEHAVIOR-1K: A Human-Centered, Embodied AI Benchmark with 1,000 Everyday Activities and Realistic Simulation. 2024. https://arxiv.org/abs/2403.09227

   该工作与 GraphWorld 最接近的点在于，它同样关注长时程日常任务、复杂环境状态和长期 embodied evaluation。区别在于，BEHAVIOR-1K 更偏高保真物理仿真，而 GraphWorld 更强调 graph-native 的符号状态、显式状态转移以及长期评分闭环。

2. AndroidWorld: A Dynamic Benchmarking Environment for Autonomous Agents. 2024. https://arxiv.org/abs/2405.14573

   该工作的重要相关性不在于机器人场景本身，而在于它强调动态环境、持续交互和长期 agent benchmarking。GraphWorld 与其共同点是都把评估对象从单步任务成功率推进到开放环境中的持续自主能力。

3. VirtualHome: Simulating Household Activities via Programs. CVPR 2018. https://arxiv.org/abs/1806.07011

   VirtualHome 是家庭活动可程序化仿真的重要近邻。它的价值在于说明“可执行环境程序”可以作为具身任务研究基础；GraphWorld 则进一步把该思路扩展为持续运行的动态图世界与 agent 闭环。

### 2.2 机器人 Agent 相关工作

1. Do As I Can, Not As I Say: Grounding Language in Robotic Affordances. 2022. https://arxiv.org/abs/2204.01691

   SayCan 的关键贡献是把高层语言规划和低层可执行 affordance 对齐。GraphWorld 当前的 `legal_action_space`、前置条件验证与动作原语设计，与该思路高度一致，但进一步放到了持续演化的图世界中。

2. Inner Monologue: Embodied Reasoning through Planning with Language Models. 2022. https://arxiv.org/abs/2207.05608

   该工作最相关的点在于引入环境反馈驱动的循环式规划。GraphWorld 当前的观察-规划-执行-反思闭环与其高度相似，但反馈被显式结构化为图状态变化、分数变化和经验摘要。

3. Open-Ended Instructable Embodied Agents with Memory-Augmented Large Language Models. 2023. https://arxiv.org/abs/2310.15127

   该工作与 GraphWorld 的 memory 设计最相关。它说明长程 embodied agent 需要外部记忆支持；GraphWorld 进一步把这一记忆实现为 layered graph memory，而不是仅依赖自然语言文本缓存。

## 3. 方法

GraphWorld 的方法部分可分为两个层面：其一是持续运行的场景图架构，其二是运行在该图世界之上的 Agent 系统。前者定义“世界如何被表示与演化”，后者定义“机器人如何在该世界中持续决策”。

### 3.1 场景图架构

#### 3.1.1 节点类型

从实现上看，GraphWorld 目前同时保留底层核心图元与运行时规范化 schema 两套表示。

在底层核心抽象中，`backend/core/nodes.py` 定义了五类基本节点：

- `Floor`
- `Room`
- `Object`
- `MobileTool`
- `Agent`

在实际仿真与 agent 运行时，系统以 `backend/runtime/schema/home_schema.py` 中的规范化结果为准。当前节点首先按 `node_type` 划分为：

- `room`
- `fixed_object`
- `movable_object`
- `agent`

进一步地，每个节点还带有 `semantic_type` 与 `semantic_class`。这使图不是一个同质图，而是一个带有对象语义、可交互属性和状态变量的层级异质图。当前代码中已支持的典型语义类型包括：

- 空间类：`floor`, `room`
- 控制类：`door`, `window`, `button`, `knob`
- 设备类：`room_light`, `stove`, `faucet`, `washer`, `dishwasher`, `microwave`, `refrigerator`, `air_conditioner`
- 家具类：`sofa`, `bed`, `table`, `desk`, `counter`, `shelf`, `chair`
- 容器类：`cabinet`, `drawer`, `wardrobe`, `shoe_rack`, `rack`, `trash_bin`
- 工具类：`brush`, `cloth`, `broom`, `watering_can`, `cart`, `medical_cart`
- 消耗品类：`milk`, `juice`, `vegetable`, `fruit`, `bowl`, `cup`, `plate`
- 人与机器人：`human`, `robot`

因此，时刻 \(t\) 的世界图可表示为：

\[
\mathcal{G}_t=(\mathcal{V}_t,\mathcal{E}_t,\mathbf{X}_t,\mathbf{S}_t,\mathbf{W}_t)
\]

其中 \(\mathcal{V}_t\) 是节点集合，\(\mathbf{X}_t\) 是节点属性与语义标签，\(\mathbf{S}_t\) 是节点状态，\(\mathbf{W}_t\) 是世界级状态。

#### 3.1.2 边类型

GraphWorld 中的边不仅描述几何相邻关系，还承担世界结构、动态位置与功能控制三种不同作用。结合 `home_schema.py` 与 `engine.py`，当前边主要可分为：

1. 结构边 `structural_edges`
   包括 `adjacent_to`、`contains`、`inside_room`、`part_of`，用于定义房间拓扑、层级结构与静态包含关系。
2. 控制边 `control_edges`
   主要是 `controls`，用于表示按钮、旋钮、门控件与设备之间的功能耦合关系。
3. 动态边 `dynamic_edges`
   包括 `in`、`on`、`held_by`、`worn_by`、`at`、`near`，用于表示运行时的动态位置与持有关系。

因此，边集可以分解为：

\[
\mathcal{E}_t=\mathcal{E}^{\text{struct}} \cup \mathcal{E}^{\text{control}} \cup \mathcal{E}^{\text{dyn}}_t
\]

其中 \(\mathcal{E}^{\text{struct}}\) 和 \(\mathcal{E}^{\text{control}}\) 较稳定，\(\mathcal{E}^{\text{dyn}}_t\) 则会随动作执行、NPC 活动与环境规则不断变化。

#### 3.1.3 状态空间

与传统 scene graph 只关注实体和关系不同，GraphWorld 将“状态”作为图世界的一等公民。`home_schema.py` 中的 `canonical_states(...)` 会为不同语义类别的节点补齐默认状态，并过滤为统一状态空间。当前较关键的状态变量包括：

- 开关与控制状态：`is_on`, `is_open`, `is_pressed`, `mode`, `fan_level`
- 清洁与维护状态：`is_dirty`, `is_clean`, `cleanliness`, `brushed`, `scattered`
- 容量与资源状态：`fill_level`, `is_full`, `holding`, `handempty`
- 过程与生命周期状态：`is_wet`, `is_dry`, `dry_remaining`, `cycle_remaining`
- 食品状态：`freshness`, `temperature`, `is_cooked`, `is_rotten`
- 植物和环境状态：`vitality`, `is_wilted`, `temperature`
- 角色状态：`current_activity`, `mood`, `is_home`
- 历史痕迹状态：`scanned`, `pushed`, `pulled`, `misplaced_near`

如果记节点 \(v\) 的状态向量为 \(\mathbf{s}_v^{(t)}\)，则整个图的状态写为：

\[
\mathbf{S}_t=\{\mathbf{s}_v^{(t)} \mid v \in \mathcal{V}_t\}
\]

这种状态设计的关键价值在于：节点状态既可以被机器人动作改变，也可以被时间推进、规则系统与环境过程改变，从而使 GraphWorld 具备真正的长期演化能力。

#### 3.1.4 演化机制

GraphWorld 的运行并不是“给定一个静态图，然后只让机器人在上面动作”。相反，系统首先通过 `build_runtime_state(raw)` 将场景图转换为一个因子化的运行时状态，核心包括：

- `nodes`
- `parent_of`
- `room_of`
- `structural_edges`
- `control_edges`
- `world_state`
- `logs`

在此基础上，`simulate_scene_with_state(...)` 会按照离散时间步推进世界时钟，并在每个时间步依次调用：

- `apply_npc_routines(...)`
- `apply_runtime_rules(...)`
- `apply_environment_step(...)`

这说明 GraphWorld 的演化并非单源驱动，而是同时受到机器人动作、NPC 行为、环境规则和自然过程影响。因此，它更接近一个持续运行的开放世界动态图过程，而不是单 agent 的封闭 episode。

#### 3.1.5 演化方程

基于当前实现，GraphWorld 的状态转移可抽象写为：

\[
\mathcal{G}_{t+1}=\Phi\big(\mathcal{G}_t, a_t, \xi_t^{npc}, \xi_t^{rule}, \xi_t^{env}\big)
\]

其中：

- \(a_t\) 表示机器人在时刻 \(t\) 的动作；
- \(\xi_t^{npc}\) 表示 NPC 的外生行为；
- \(\xi_t^{rule}\) 表示规则系统引发的状态修正；
- \(\xi_t^{env}\) 表示环境系统引发的自然演化；
- \(\Phi\) 表示统一状态转移算子。

世界时钟本身也采用离散推进：

\[
\tau_{t+1}=\tau_t+\Delta,\qquad \Delta=\text{minutes\_per\_step}
\]

并在跨日时自动更新 `day`、`time_min`、`day_phase` 等世界变量。

#### 3.1.6 动态边重建

GraphWorld 中一个很关键的实现选择，是将运行时位置关系抽象为 `parent_of` 映射，而不是把所有动态边永久固化到图中。`engine.py` 中的 `_dynamic_edges(state)` 会根据 `parent_of` 和节点的 `runtime relation` 动态恢复：

\[
\mathcal{E}^{\text{dyn}}_t=\Psi(\texttt{parent\_of}_t,\texttt{runtime\_relation}_t)
\]

这种设计有三方面优点：

1. 将结构拓扑与动态位置解耦，保持底层场景骨架稳定。
2. 动作执行时只需修改父子映射和节点状态，不必全量维护位置边。
3. 在 replay 和后验分析阶段，可以同时恢复稳定图结构与时间变化轨迹。

从学术角度看，这使 GraphWorld 具备“稳定结构图 + 动态关系图”的双层表示特征。

### 3.2 Agent 系统

GraphWorld 的 Agent 系统运行在动态图世界之上，其目标不是完成一次性指令，而是在长期运行中持续提升世界分和人类分。当前权威入口是 `backend/runtime/agent/robot_agent_runtime.py` 中的 `step_robot_agent(...)`。整个 agent 闭环可以表示为：

\[
\text{Observation} \rightarrow \text{Memory} \rightarrow \text{Planning} \rightarrow \text{Execution} \rightarrow \text{Reflection} \rightarrow \text{Memory Update}
\]

#### 3.2.1 记忆

当前记忆模块由 `robot_memory.py` 实现，并不是简单的自然语言历史缓存，而是一个 layered graph memory。它主要包含三层：

- `stable_node`, `stable_edge`
  保存相对稳定的结构知识，例如房间邻接、控制关系、已知房间。
- `decaying_node`, `decaying_edge`
  保存最近观察到、但可能随时间失效的局部知识。
- `working_memory`
  保存当前任务上下文与短期经验，包括 `recent_observations`、`recent_actions`、`recent_reflections`、`experience_summaries`、`experience_library`、`active_goal` 和 `learned_rules`。

因此，时刻 \(t\) 的记忆可形式化为：

\[
\mathcal{M}_t=\{\mathcal{M}^{stable}_t,\mathcal{M}^{decay}_t,\mathcal{M}^{work}_t\}
\]

并通过 `_sync_layered_graph(...)` 融合成统一 belief graph：

\[
\widehat{\mathcal{G}}_t=\Gamma(\mathcal{M}^{stable}_t,\mathcal{M}^{decay}_t,\mathcal{M}^{work}_t)
\]

这一设计的意义在于，Agent 面对的是部分可观测世界，因此需要通过图结构化记忆维持对环境的长期信念，而不是仅依赖当前一步观测。

#### 3.2.2 规划

当前规划模块不是单级动作选择，而是一个两阶段决策机制。

第一阶段是高层意图规划。系统先根据当前观测、记忆摘要和局部问题，决定当前应处于哪种 focus，例如：

- `explore`
- `intervene`
- `support`
- `recover`
- `verify`

第二阶段是低层动作选择。系统在经前置条件过滤后的 `legal_action_space` 中，选择一个可执行动作原语。当前动作空间包括：

- `move`
- `pick`
- `place`
- `press`
- `open`
- `close`
- `brush`
- `fold`
- `dump`

因此，可把规划过程抽象为：

\[
g_t=\pi_H(o_t,\mathcal{M}_t), \qquad
a_t=\pi_L(o_t,\mathcal{M}_t,g_t,\mathcal{A}^{legal}_t)
\]

其中 \(o_t\) 是当前观测，\(g_t\) 是高层目标，\(\mathcal{A}^{legal}_t\) 是满足前置条件的动作集合。与一次性长链规划不同，这种设计更适合长期运行中的滚动决策。

#### 3.2.3 执行

执行模块由 `robot_executor.py` 实现，其核心不是简单地“调用动作”，而是将动作编码为图状态变换算子。执行器会完成以下步骤：

1. 检查动作前置条件；
2. 更新 `parent_of`、`room_of` 与目标节点状态；
3. 记录 `state diff`；
4. 校验运行时不变量；
5. 将运行时状态重新投影回 scene graph。

因此，动作执行本质上是：

\[
a_t : (\mathcal{G}_t,\mathcal{M}_t)\mapsto \mathcal{G}'_t
\]

这里 \(\mathcal{G}'_t\) 是执行动作后的中间图状态。随后系统再调用 `advance_world_one_step(...)` 让世界继续推进，得到真正的下一时刻图状态 \(\mathcal{G}_{t+1}\)。

#### 3.2.4 反思

反思模块由 `robot_reflation.py` 实现。它的作用不是生成冗长文本，而是把动作后果压缩为结构化反馈，包括：

- `score_delta`
- `resolved_issues`
- `failed_preconds`
- `repeated_ineffective`
- `experience_summary`
- `experience_library`

记反思输出为 \(r_t\)，则可写为：

\[
r_t=\mathcal{R}(o_t,a_t,\mathcal{G}_t,\mathcal{G}_{t+1},J_t)
\]

其中 \(J_t\) 表示由评测器返回的世界分与人类分反馈。随后，记忆更新为：

\[
\mathcal{M}_{t+1}=\Lambda(\mathcal{M}_t,o_t,a_t,r_t)
\]

这样，GraphWorld 的 agent 就形成了一个真正的长期闭环：它不仅会执行动作，还会根据动作是否改善环境与服务质量来调整后续行为。

#### 3.2.5 系统特点

综上，GraphWorld 的 agent 系统具有以下几个特点：

1. 记忆是图结构化的，而不是纯文本缓存。
2. 规划是两阶段的，兼顾高层意图与低层动作 grounding。
3. 执行直接作用于图状态，而不是独立于环境状态的动作黑盒。
4. 反思直接连接评分信号，使 agent 的长期目标与 world score / human score 一致。

因此，GraphWorld 中的 agent 并不是传统意义上“收到任务后执行”的被动规划器，而是一个在持续演化图世界中不断记忆、规划、执行和反思的长期自主体。
