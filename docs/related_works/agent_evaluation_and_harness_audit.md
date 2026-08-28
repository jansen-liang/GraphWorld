# 具身智能体评价与 Agent Harness 审计

本文回答三个问题：

1. 现有具身/Agent benchmark 实际评价哪些能力，是否存在可辩护的能力层级；
2. 不同 benchmark 的任务数据、环境状态、执行轨迹和评测器如何组织，是否存在 GraphWorld 同类的动态图运行时；
3. “agent = LLM + harness”在实验系统中具体指什么，以及它对 GraphWorld 评价设计有什么影响。

本文与 `reference_table_graphworld_related_work.md` 的分工不同：总表记录文献索引，本文件记录评价对象、数据管道和系统边界，避免在每篇文献的简介里重复同一套“动态环境/长期任务”的表述。

## 1. 先给结论

现有具身智能评价并不是一个统一的能力体系，而是几条相互重叠的评价传统：

| 评价传统 | 主要测量对象 | 典型测量单位 | 代表工作 |
|---|---|---|---|
| 感知与空间理解 | 物体、房间、关系、可通行性、空间定位 | observation / frame / navigation episode | Habitat、ConceptGraphs、Hydra |
| 具身操作与 affordance | 移动、抓取、放置、开关、工具使用 | action / short task | AI2-THOR、SayCan、RLBench、LIBERO |
| 指令条件任务执行 | 语言 grounding、任务分解、动作链完成 | instruction episode | ALFRED、VirtualHome、BEHAVIOR-1K |
| 长程任务组织 | 子任务排序、记忆、状态跟踪、反馈闭环 | long-horizon episode | Inner Monologue、SayPlan、TEACh、BEHAVIOR-1K |
| 动态交互与社会协作 | 人类/用户意图、交互协议、角色规范 | interaction episode / conversation | Habitat 3.0、MIA、Social Intelligence、τ-bench |
| Agent 工具使用与持续状态 | API 调用、网页/桌面状态、恢复、工具约束 | task trace / environment run | AgentBench、WebArena、BrowserGym、OSWorld、AndroidWorld |
| 开放式自主与价值后果 | 自主任务产生、长期世界后果、价值权衡 | continuous world trajectory | TongTest（框架性）、GraphWorld（可执行实现方向） |

这里不存在一个得到学界普遍承认的“Level 1 到 Level 5”统一层级。TongTest 提出了面向 AGI 的能力/价值等级框架，但它是上位理论与平台蓝图；ALFRED、BEHAVIOR-1K、OSWorld 等 benchmark 各自定义任务和成功条件，不能直接拼接成一个共同量尺。

因此，GraphWorld 不应声称发现了现成的通用能力层级。更严谨的做法是提出一个**评价依赖层级**：低层能力是高层能力的必要支撑，但高层得分不能由低层分数线性推出。

```text
感知/空间 grounding
        ↓
可执行动作与 affordance 约束
        ↓
闭环任务执行与状态跟踪
        ↓
长程任务组织、记忆与阶段保持
        ↓
动态扰动下的恢复与多任务调度
        ↓
自主需求发现、长期后果权衡与持续世界维护
```

这是一条面向研究设计的依赖关系，不是对所有智能体的心理发展等级，也不是把一个 benchmark 的分数换算成另一个 benchmark 的等级。

## 2. 现有评价到底测什么

### 2.1 能力分类：按“决策闭环中的位置”而不是按论文名称分类

#### A. 世界建模能力

包括对象识别、空间关系、可见性、场景记忆和状态估计。Hydra、ConceptGraphs 等主要解决“从观测构造或维护场景图”；它们的主要输出是地图/图，而不是长期任务成功率。此类能力是 GraphWorld 的输入假设之一，目前 GraphWorld 的符号观察绕过了视觉建图，因此不能把 GraphWorld 的结果解释为视觉感知能力。

#### B. 可执行性与操作能力

包括动作是否符合 affordance、前置条件是否满足、动作是否产生预期状态变化。SayCan 将语言模型的候选技能与低层 affordance 分数结合；AI2-THOR、BEHAVIOR-1K 等由模拟器执行交互并返回状态。GraphWorld 的 validator 和 transition rules 属于这一层，但它们主要保证评价环境可审计，不等价于评价模型是否理解 affordance。

#### C. 有目标任务规划能力

包括从明确指令生成子任务、选择动作顺序、完成终止条件。ALFRED、VirtualHome、SayPlan 和大量 LLM planner 工作集中于此。任务目标通常由测试者给定，成功条件通常可以在 episode 末端检查，因此这类评价主要测“给定目标下的 planning/execution”。

#### D. 长程状态与任务组织能力

包括跨步骤记忆、阶段保持、子任务依赖、反馈闭环和延迟效果。BEHAVIOR-1K、TEACh、Inner Monologue 等比单步操作更接近此层，但通常仍以一个外部给定活动为 episode 边界。GraphWorld 的 `active_goal`、技能阶段和长期 replay 可用于把这一层拆成过程指标。

#### E. 动态恢复与社会交互能力

包括环境变化后的重新规划、人类协作者的意图理解、对话/工具协议、权限和规则遵守。Habitat 3.0 把人类/Avatar/机器人放入共居环境；Web/desktop agent benchmark 则通过用户模拟器、应用状态和工具 API 测试交互闭环。该层的关键不是任务链长度，而是外部状态改变后原计划是否仍然有效。

#### F. 开放式自主能力

包括任务是否由环境状态和角色职责产生、目标是否需要自主排序、行为是否考虑长期人类后果。TongTest 从 DEPSI、无限任务、自主任务生成和价值系统提出上位问题；主流具身 benchmark 很少将其作为主要可重复指标。GraphWorld 的四个过程维度——任务涌现、后果权衡、意图持续、闭环自修——位于这一层，但仍需通过受控 opportunity 和 episode 才能从“长期分数”变成可诊断能力。

### 2.2 这些能力能否称为“层级”

可以称为**功能依赖层级**，不能称为已被验证的“智能发展等级”。理由如下：

- 没有可靠的感知/状态估计，任务规划无法 grounding；
- 没有可执行动作和状态反馈，长程规划无法验证；
- 没有阶段记忆，动态恢复只能退化成重新规划；
- 没有后果模型，目标调度只能按距离或局部奖励排序；
- 但高层能力并非低层能力的简单叠加：一个操作很强的 agent 可能仍不会主动发现任务，也可能在多任务竞争中失败。

因此，GraphWorld 的四类能力最好被描述为**开放任务持续自主层的四个构念**，而不是四个从低到高的等级：

| 构念 | 需要的前置能力 | 关键可观测证据 |
|---|---|---|
| 任务涌现 | 状态理解、事件影响理解 | 问题出现后的响应、发现时延、影响事件识别 |
| 后果权衡 | 多目标状态、时间/依赖模型 | 优先级选择、deadline、切换收益 |
| 意图持续 | 阶段状态、记忆、恢复上下文 | 中断前后目标和 phase 的连续性 |
| 闭环自修 | 状态差分、错误归因、反馈利用 | 行为改变、恢复成功、副作用 |

## 3. 现有 benchmark 的数据与评价管道

比较 benchmark 时要拆开四层，不能只问“有没有动态图”：

```text
任务规范 task specification
→ 环境真值 state transition
→ agent observation/action trace
→ evaluator / success metric
```

### 3.1 主要数据管道对比

| 系统 | 任务如何定义 | 环境状态/转移 | Agent 输入输出 | 评价方式 | 是否是 GraphWorld 式持续动态图引擎 |
|---|---|---|---|---|---|
| VirtualHome | 程序化家庭活动/动作脚本 | 程序执行更新场景图和对象状态 | 活动程序或语言到动作 | 程序执行/目标状态 | 部分相似；有可执行图状态，但主要是脚本活动，不是持续维护世界 |
| ALFRED | 语言指令 + 初始/目标活动 | AI2-THOR 交互环境 | 视觉观测 + 动作 | 任务目标、子任务/轨迹指标 | 否；episode 任务驱动 |
| BEHAVIOR-1K | BDDL 活动定义、初始条件和目标谓词 | OmniGibson/物理模拟器推进对象状态 | 视觉/机器人动作 | 活动成功、完成度、时间/操作代价 | 部分相似；状态谓词和活动复杂，但主单位仍是活动 episode |
| Habitat 3.0 | Habitat task config + 人类/Avatar 场景 | 3D simulator + avatar/human behavior | 传感器观测、动作、协作交互 | task measures、协作/导航结果 | 有动态共居，但不是 GraphWorld 的统一事件—长期维护评分 |
| SayPlan / Taskography | 外部给定语言任务和场景图 | 主要依赖规划器/模拟器执行 | 场景图 + 语言 → plan/action | 计划成功、规划效率/可行性 | 否；图主要是规划输入 |
| AndroidWorld | 任务模板、Android 初始状态、成功检查器 | Android emulator / app state | UI observation + tool/action calls | state-based task verifier | 有动态应用状态，但不是物理/社会世界 |
| OSWorld | 任务描述、VM 镜像、应用文件和 evaluator | 真实桌面应用/VM 状态 | screenshot/accessibility + mouse/keyboard | 文件/应用最终状态、任务 evaluator | 有状态转移，但世界范围是 desktop workflow |
| WebArena / BrowserGym | 网站实例、用户任务、浏览器状态 | 浏览器、网站后端和数据库 | DOM/screenshot + browser actions | URL/DB/页面状态检查 | 有可执行 web state，但不是具身空间图 |
| AgentBench | 多环境任务接口和环境特定任务 | 各子环境自行维护 state | LLM 输出动作/API 调用 | 环境特定 reward/success | 否；是多环境统一接口，不是统一世界本体 |
| τ-bench | policy API、工具集合、数据库、用户模拟器 | 工具调用改变业务数据库 | 对话 + tool calls | 任务成功、规则遵守、用户满意/一致性 | 有工具状态和用户交互，但不是连续物理世界 |
| TongTest | DEPSI 场景、能力/价值任务设想 | 物理/社会模拟平台 | 多模态交互 | U/V 能力价值评级 | 理论上要求开放动态环境；公开材料不足以证明已有统一可复现实运行时 |
| GraphWorld | NPC 日程、状态偏离、人类事件、可恢复问题 | 同一时序图驱动事件、动作、环境推进和评分 | 局部图观察 + 合法动作/目标选择 | 长期 state/spatial/human 结果 + capability episode | 是；当前更接近符号时序运行时，非高保真视觉物理引擎 |

### 3.2 现有系统是否有“动态图数据引擎”

答案不是简单的“有/没有”，而是三种不同含义：

1. **模拟器内部有动态状态**：AI2-THOR、OmniGibson、Habitat、Android emulator 都会更新状态；这解决“动作能否改变环境”。
2. **任务定义中有状态谓词和目标**：VirtualHome、BEHAVIOR-1K、OSWorld 等会定义初始条件、目标或检查器；这解决“本任务是否完成”。
3. **世界本体同时驱动外生事件、任务涌现、动作验证和长期评价**：这一点在主流 benchmark 中并不常见。GraphWorld 的差异在第三种统一性，而不只是“也有动态状态”。

因此，不能声称 GraphWorld 是第一个有动态环境的系统；更准确的创新边界是：

> GraphWorld 将外生人类事件、任务需求生成、机器人动作执行、状态转移、阻塞恢复和长期维护评价置于同一可审计的时序图运行时中。

### 3.3 数据集与运行日志的区别

多数 benchmark 的“数据集”并不是离线监督数据集，而是三类资源的组合：

- **scene/task specification**：场景、任务、初始条件、目标或规则；
- **runtime environment**：模拟器、VM、浏览器或 API 后端；
- **evaluator**：终止条件、状态谓词、测试脚本或人工/模型评审器。

轨迹通常是运行时生成的，不是预先存储的训练样本。由此，GraphWorld 不必把自己包装成大规模静态 dataset；更准确的产品形态是：

```text
可参数化场景/事件规范
+ 可执行时序运行时
+ agent interface
+ replay/episode schema
+ deterministic evaluator
```

GraphWorld 当前最值得补的不是“再增加若干 JSON 场景”，而是把上述五类资源明确分层，并发布固定 schema：`scene_spec`、`event_spec`、`opportunity_spec`、`trajectory`、`episode_outcome`、`capability_metrics`。

## 4. “Agent = LLM + Harness”究竟是什么意思

### 4.1 LLM 不是完整 Agent

LLM 本身通常只是一个条件生成器：给定上下文，输出文本、结构化动作或工具调用。它不天然拥有：

- 环境状态的持久保存；
- 工具执行和结果回读；
- 任务终止判断；
- 非法动作拦截；
- 重试和恢复策略；
- 评价器；
- 多轮记忆和任务队列。

所谓 **harness**，就是包在模型外面的运行控制系统。一个可操作的分解是：

```text
Agent
= model
+ observation/state adapter
+ prompt/context builder
+ memory
+ planner/controller
+ tool/action interface
+ parser/validator
+ execution loop
+ retry/recovery policy
+ evaluator/termination logic
```

“LLM + harness”不是某一个固定算法名称，而是一种实验事实：同一个 LLM 接入不同的观察摘要、候选动作过滤、记忆、规划循环和验证器，表现会显著不同。

### 4.2 Harness 在具身系统中具体做什么

| Harness 部件 | 作用 | GraphWorld 对应物 |
|---|---|---|
| observation adapter | 把环境真值/传感器变成模型可读上下文 | `Perception.robot_view` |
| state memory | 保存不可见或历史状态 | `memory.py`、recent history |
| goal manager | 创建、保持、切换、完成目标 | `active_goals`、goal lifecycle |
| skill/controller | 把高层目标映射为低层动作 | task library、decision logic |
| action space | 提供工具/技能候选 | `candidate_actions` |
| validator | 拦截非法操作 | action schema / validator |
| executor | 修改环境并返回反馈 | `RobotActionSystem` / runtime |
| reflection/recovery | 根据失败改变策略 | 当前是有限的 reflection + goal update，仍待加强 |
| evaluator | 计算任务/长期结果 | matrix evaluator、blocking metrics |

因此，GraphWorld 当前比较的不是“裸 LLM”，而是不同 harness：`reactive`、`single_round`、`goal_review` 和 rule-based scheduler。论文中应把方法名写成完整配置，例如：

```text
Qwen + reactive harness
Qwen + single-round goal/action harness
Qwen + goal-review + skill-library harness
rule scheduler + GraphWorld action harness
```

否则读者会误以为差异全部来自 backbone。

### 4.3 Harness 与训练方法不能混为一谈

需要区分三种改进：

1. **模型改进**：更新 LLM/VLM 参数、训练 adapter 或 policy；
2. **harness 改进**：增加记忆、规划、验证、反思、候选动作筛选或工具路由，不更新模型参数；
3. **环境/评价改进**：改变观察、任务生成、状态转移或 evaluator。

如果不拆开，所谓“agent 能力提升”可能只是：

- 给了更完整的状态；
- 缩小了动作空间；
- 加了规则优先级；
- 用 verifier 拦截了错误；
- 让 harness 替模型完成了规划。

这不意味着 harness 不重要。真实部署的 agent 本来就是系统级对象；但实验必须报告模型和 harness 的边界，才能判断提升来自哪里。

## 5. 对 GraphWorld 评价设计的直接影响

### 5.1 评价对象应定义为 Agent System，而不是 LLM

GraphWorld 的主评价对象应是：

```text
Agent system = backbone + observation + memory + goal manager
             + action interface + executor + recovery harness
```

同时做 harness ablation：

| 对照 | 固定 backbone | 改变 harness | 目的 |
|---|---:|---:|---|
| reactive → goal-review | 是 | 是 | 测目标管理/审查机制 |
| no-memory → structured memory | 是 | 是 | 测历史状态和阶段保持 |
| no-verifier → verifier | 是 | 是 | 测动作约束与安全过滤 |
| no-reflection → reflection | 是 | 是 | 测失败反馈利用 |
| same harness, different backbone | 否 | 否 | 测模型本身差异 |

### 5.2 Benchmark 需要单独标注“模型能看见什么”和“harness 替它做了什么”

建议每个测试实例固定记录：

- observation scope：全图、局部图、历史摘要或原始传感器；
- action scope：原子动作、技能、候选动作集合；
- external help：规则优先级、oracle issue、目标生成器是否暴露；
- memory scope：是否提供历史状态、目标阶段和失败记录；
- evaluator scope：是否在执行中拦截非法动作；
- adaptation budget：是否允许跨 episode 更新记忆或参数。

否则“任务涌现”可能被外部 goal generator 代替，“失败反思”可能被 harness 的自动重试代替。

### 5.3 GraphWorld 目前的真实贡献边界

基于现有代码和数据，GraphWorld 可以有力地声称：

- 以统一时序图驱动人类事件、机器人动作、环境推进和长期评价；
- 将人类活动阻塞作为可恢复、可归因的过程事件；
- 在同一世界中比较不同 agent harness 的长期维护行为；
- 用 state/spatial/human 结果和过程日志诊断长期调度缺陷。

目前不应直接声称：

- 已经评估视觉感知能力；观察是结构化图而不是原始视觉输入；
- 已经证明 agent 具备因果理解；环境有因果规则不等于模型学到了因果模型；
- 已经实现通用无限任务；当前任务生成空间仍由有限场景、事件库和技能库定义；
- 已经测量模型内部反思；现有 reflection 更接近外部 harness 的行为更新。

## 6. 推荐补入现有总表的字段

现有表格的“是否单轮任务/是否显式语言指令”不足以支持上述比较。建议新增一个单独的评价审计表，而不是继续扩张原来的核心参考点列。最少增加：

| 字段 | 规范化取值 |
|---|---|
| primary capability | grounding / manipulation / planning / memory / recovery / social / proactive autonomy |
| evaluation unit | frame / action / instruction episode / long-horizon episode / continuous run |
| task source | external instruction / script / sampled task / emergent event / user interaction |
| state authority | simulator state / app-VM state / backend DB / symbolic graph / human judgment |
| transition owner | robot action only / simulator + exogenous events / external backend / mixed |
| evaluator type | terminal predicate / trajectory measure / rule checker / unit tests / human or LLM judge |
| data artifact | specification / demonstration / online trajectory / replay / generated episode |
| harness components | memory / planner / tool use / validator / retry / verifier |
| persistent world | no reset within task / reset per episode / shared continuous world |
| GraphWorld relation | supports / partially overlaps / orthogonal / missing capability |

推荐把现有总表定位为“文献导航表”，新增审计表定位为“评价系统比较表”。这样不会把同一句 related-work 结论重复写进每一行。

## 7. 当前综述的真正缺口

现有 docs 已经覆盖了 TongTest、VirtualHome、ALFRED、Habitat 3.0、BEHAVIOR-1K、SayCan、SayPlan、ConceptGraphs 和场景生成路线，但还缺少三条对 GraphWorld 评价最关键的文献线：

1. **Agent benchmark / harness 线**：AgentBench、WebArena、BrowserGym、OSWorld、AndroidWorld、τ-bench、SWE-bench。它们能帮助我们把 harness、tool loop、state checker 和 evaluator 写清楚；
2. **长程具身任务与恢复线**：TEACh、BEHAVIOR-1K 的 activity/state formalism、Habitat 3.0 的 human-in-the-loop protocol。它们能帮助我们避免把“长程”仅写成动作步数；
3. **评测方法学线**：构念有效性、机会集、反事实干预、跨场景泛化和 harness ablation。它们决定四类过程能力是不是可证伪的评价构念，而不是事后给轨迹贴标签。

GraphWorld 下一版综述的重点不应是再证明“别人也有动态环境”，而应回答一个更窄的问题：

> 现有系统把动态性放在环境内部，但是否把外生事件、任务产生、策略状态、恢复过程和长期后果统一成同一个可审计评价对象？

目前的答案是：各家分别覆盖其中一部分，GraphWorld 的潜在差异在于把它们统一到长期维护 episode；但这个差异需要用统一字段、对照实验和 harness ablation 证明，而不能只用文字宣称。
