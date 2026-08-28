# Related Works 精读笔记

这组笔记服务于 GraphWorld 的论文写作与 related works 梳理，重点不是做“百科式摘要”，而是紧扣我们自己的研究问题来读：

- 如何支持持续演化的开放环境
- 如何支持图结构世界底座
- 如何支持长期、非单轮的任务评测
- 如何支持人类活动、社会交互与外生事件
- 如何支持 state-aware / closed-loop / graph-grounded 的 agent 决策

当前先按“文章名”组织，而不是按大类组织：

1. [TongTest](./TongTest.md)
2. [从 Graph 生成 3D 场景的相关工作调研](./GraphTo3DGeneration.md)
3. [GraphWorld 场景生成体系与弱点审计](./SceneGenerationTaxonomyAndWeaknessAudit.md)
4. [近年场景生成代码审计：哪些能为 GraphWorld 所用](./RecentSceneGenerationCodeAudit.md)
5. [可直接接入的 3D 场景系统调研](./ReadyToUse3DSceneSystems.md)
6. [具身智能体评价与 Agent Harness 审计](./agent_evaluation_and_harness_audit.md)
7. [三类文献总表：场景数据集、Benchmark、方法](./three_domain_literature_tables.md)
8. [典型任务规划论文的任务分类、技能与动作](./task_planning_task_taxonomy.md)

配套表格：

- [参考文献表（Markdown）](../reference_table_graphworld_related_work.md)
- [参考文献表（Excel）](../reference_table_graphworld_related_work.xlsx)

建议写 related works 时的使用方式：

- 如果要强调“GraphWorld 不只是单轮 episode benchmark”，优先从 TongTest 开始。
- 如果要回答“有没有 graph 生成 3D / graph-conditioned scene generation”，看 `GraphTo3DGeneration.md`。
- 如果要回答“有没有能直接用的 3D 系统、应该先接谁”，看 `ReadyToUse3DSceneSystems.md`。
- 如果要补强“房间类、物体类、场景类从哪里来”以及当前方法哪里弱，看 `SceneGenerationTaxonomyAndWeaknessAudit.md`。
- 如果要回应“要看新文献和代码，别拿 2017 的旧数据集当主依据”，看 `RecentSceneGenerationCodeAudit.md`。
- 如果后续继续补文献，再按文章单独建文件，不再按大类堆到一起。
- 如果要比较能力分类、评价管道、动态状态引擎或 LLM+harness，先看 `agent_evaluation_and_harness_audit.md`，不要把这些系统问题重复写回每篇论文摘要。
- 如果要按清洁、制作、运输、收纳等任务类别比较 ALFRED、BEHAVIOR-1K、SayCan、SayPlan 和 GridWorld，查看 `task_planning_task_taxonomy.md`；其 CSV 版本可直接导入 Excel。
- 原子动作的逐行映射见 `task_atomic_action_mapping.csv`，包含动作角色、参数、前置条件和效果。

当前笔记的统一字段：

- 研究问题
- 核心方法 / 系统设计
- 任务与评测设定
- 对我们最有价值的参考点
- 与 GraphWorld 的关键差异
- 写作时可直接使用的定位句
