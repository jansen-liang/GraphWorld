# Task Planning Task Taxonomy Review

## 1. Report Metadata

- Review date: 2026-08-30
- Target venue/year/track: 未指定；按计算机科学研究设计文档与潜在论文方法/相关工作材料评审
- Paper title: `GraphWorld 文档`
- Input materials reviewed: `docs/related_works/task_planning_task_taxonomy.md`、其引用的核心代码与统计文件
- Search basis: 本地文档与代码事实核查；未执行外部文献检索
- Report file: `docs/related_works/ccfa-review-reports/task-planning-task-taxonomy-generic-review.md`
- Reviewer mode: full, assessment-only
- Manuscript version / comparison range: 2026-08-30 工作区版本；非版本比较

## 2. Desk Rejection Assessment

- Paper length: **不适用/不确定**。当前是 506 行内部 Markdown，不是完整论文。
- Topic compatibility: **通过**。任务本体、动态图、任务生成与符号规划具有明确研究价值。
- Minimum quality: **若按内部设计稿，勉强通过；若按论文 taxonomy/related work，未通过**。
- Policy/anonymity/compliance: **不适用**。未指定投稿目标。
- Prompt injection and hidden manipulation detection: **通过**。未发现隐藏指令或评审操纵文本。
- Ethics and reviewability: **部分通过**。无明显伦理风险，但事实、规范和设想混写，降低可审查性。

## 3. Paper Summary And Contribution Map

文档试图统一 GraphWorld 的场景域、对象、状态、关系、动作、过程和任务，并提出一个由最小目标文字扩展到组合任务的自动化链路：任务 schema 声明绑定条件与目标，grounding 在具体场景图中选择对象，PDDL 编译器生成问题，Fast Downward 验证可解性。其最有价值的设计判断是：任务由目标图差异定义，原子动作保持固定，新增产品主要增加声明式配方，而不是增加 `make_hamburger` 一类专用动作。

- Claimed problem: 如何定义最小任务，并从有限规则自动生成大量可解组合任务。
- Claimed gap: 当前对象、状态、动作和任务统计尚未形成统一的自动 PDDL 验证闭环。
- Method/contribution map:
  - state / relation / existence 三类目标文字；
  - 六个一级任务标签；
  - schema / grounding / PDDL 三层；
  - 配方与定时过程不扩张原子动作集合；
  - 仅将有成功计划的实例计入已验证任务。
- Evidence package: 当前代码结构、对象目录报告、task library、一个洗衣 PDDL 脚本与 coverage JSON。
- Stated limitations: 信息任务、持续约束、多主体、代价优化和全任务 PDDL 覆盖尚未完成。

## 4. Search And Related-Work Basis

- Queries used: 无外部查询。
- Sources searched: 当前仓库的 Markdown、Python、JSON 统计与验证脚本。
- Closest works found: 未在本次评审中外部检索。
- Unverified related-work risks: 文档位于 `related_works`，但正文没有论文引用，也没有说明六类来自哪些 benchmark 或文献。
- Source-quality screening status: 代码事实已局部核验；文献依据缺失。

## 5. Expected Review Outcome

- Expected outcome: **Weak reject（作为论文或正式 taxonomy）；可保留为内部架构草案**。
- Main accept signal: schema–grounding–PDDL 分层和“固定动作集 + 声明式配方”具有良好工程可扩展性。
- Main reject signal: taxonomy 不可判定、核心定义矛盾、文献证据缺失且当前/规划状态混写。
- Confidence: 4/5。全文和核心代码可读，但没有目标 venue、外部文献检索或完整 PDDL 编译器。

## 6. Strengths And Weaknesses

### Strengths

- 第 304–315 行把任务表述为目标约束，并区分 state、relation、existence，方向基本正确。
- 第 356–380 行明确新增产品不应扩张机器人动作集合；配方与过程负责生成产物，避免 `make_*` 动作爆炸。
- 第 382–425 行将 schema、grounding 和规划验证分离，能够支撑程序化任务生成。
- 第 427–437 行没有把候选任务误报成 PDDL 已验证任务，统计口径相对克制。
- 第 453–464 行主动列出时间、信息、持续约束、多主体和代价优化等边界，说明作者已经意识到经典终态规划的适用范围。

### Major Weaknesses

1. **最小任务的定义自相矛盾。**
   - Evidence basis: 第 304–315 行将原子任务定义为一个 goal literal；第 316 行却写“最小任务是规划器实现目标时可以选择的操作”。
   - Reviewer deduction: 任务和动作是全文最核心的两个层级，此处混淆使后续分类失去稳定语义。
   - Required fix: 明确写成“最小任务不是操作；操作是实现目标的原子动作”，并给出形式化类型定义。

2. **goal literal 不是“变化”，缺少初始条件。**
   - Evidence basis: 第 308–314 行只定义 `plate.is_dirty=false`、`in(plate,cabinet)` 等终态文字。
   - Reviewer deduction: 若初始图已经满足目标，任务零步完成；因此“一个目标文字”不能独立表示 `G_0 -> G_g` 的变化。
   - Required fix: 将原子任务定义为 `initial condition + goal literal` 或显式 delta，例如 `(is_dirty, true, false)`，并增加 non-triviality 条件 `G_0 \not\models g`。

3. **六类标签不是互斥、完备、可执行的分类函数。**
   - Evidence basis: 第 343–352 行的 `operate` 包含“一般功能状态改变”，会覆盖 `clean`；物品交接同时属于 `interact` 和 `relocate`；复合结构形成同时是 `make` 和 edge 变化。
   - Reviewer deduction: 当前只能视为多标签语义标签，不能称为最小互斥任务集合，也不能稳定统计覆盖率。
   - Required fix: 二选一：明确声明 multi-label taxonomy；或按 predicate namespace 和主体类型给出有优先级的互斥判定函数，并用反例测试。

4. **当前事实与未来设想混写，多个“当前”陈述已失真。**
   - Evidence basis:
     - 第 59 行称对象模板 115 个，当前代码实测为 130 个；
     - 第 190–210 行仍把 `clothesdryer/coffeemachine/soapbottle/spraybottle` 标为候选或暂缓，但它们已在对象库注册；
     - 第 121、130、149、150、154 行漏掉打印机、牙膏、盐/胡椒瓶、纸巾盒现有资源状态；
     - 引用的 object catalog 生成于 2026-08-22，早于 2026-08-27 修改的对象库。
   - Reviewer deduction: 读者无法判断哪一条是实现事实、规范要求还是路线图。
   - Required fix: 每张表增加 `implemented/proposed/deferred` 状态列；数量由脚本生成，不手工维护；在文首声明 source of truth 和快照日期。

5. **“通用 PDDL 编译器”仍是设计愿景，不是现有证据。**
   - Evidence basis: 第 390、418 行描述通用编译器；当前 `try_laundry_fastdownward.py` 手写了 laundry 专用 domain，并把洗衣和晾干效果建模为瞬时 `press-washer`、`dry` 动作。
   - Reviewer deduction: 一个专用 17 步计划不能支持“动作、过程、配方和场景图均可通用编译”的主张，也没有验证时间语义。
   - Required fix: 将文字改为 proposed architecture；实现至少 clean、relocate、refill、recipe、timed-device 五类编译测试，再报告覆盖矩阵。

6. **任务 schema 示例与当前 runtime 不一致。**
   - Evidence basis: 第 394–406 行要求 `cleaning_tool` 和 `tool_cleans_target`；当前 `brush` 直接修改目标，未要求机器人持有工具；`vacuumcleaner` 只有 `PICKABLE`，`cleaningcloth` 的 `CLEANABLE` 表示自身可清洁，并不等于能清洁其他对象。
   - Reviewer deduction: 示例 schema 当前无法从真实 capability registry 稳定 grounding，也无法由现有动作语义证明。
   - Required fix: 引入明确的 `cleaning_tool` / `cleans(target_family)` 能力和 tool-bound action 参数，或删除工具绑定要求并承认当前是无工具清洁抽象。

7. **作为 related-work/taxonomy 文档，文献证据近乎为零。**
   - Evidence basis: 全文没有 BEHAVIOR-1K、ALFRED、SayCan、SayPlan、VirtualHome 等来源的引用或任务映射，也没有参考文献节。
   - Reviewer deduction: 无法判断六类是否由文献归纳、由 GraphWorld 工程需求提出，还是头脑风暴所得。
   - Required fix: 为每个一级类型建立 paper/dataset/task-instance 证据表，并区分“文献观察”与“本文设计决策”。

8. **文档职责过多，组织结构不稳定。**
   - Evidence basis: 自动场景生成和验证位于“一、对象”之前；标题仅为“GraphWorld 文档”；第八节突然转向自进化、SFT、在线强化学习和人员分工。
   - Reviewer deduction: 读者无法确定这是 related-work、ontology specification、implementation audit 还是 project roadmap。
   - Required fix: 至少拆为 taxonomy/spec、implementation coverage、roadmap 三个文档；本文件只保留问题定义、文献证据、形式化 taxonomy 和验证协议。

9. **“不可再拆分”缺少相对于何种本体粒度的定义。**
   - Evidence basis: 第 308 行把单个 goal literal 直接称为不可再拆分；但 `exists(hamburger)=true` 可以隐藏原料消耗、熟化状态和组成关系等多个变化。
   - Reviewer deduction: 原子性不是任务的绝对属性，而是相对于给定 predicate vocabulary、状态抽象和编译边界的语法性质。若不固定这些边界，任意复杂任务都能被包装成一个新 predicate，从而使“最小任务”失去约束力。
   - Required fix: 将 atomic 明确定义为“相对于版本化 ontology 的单个规范化 goal literal”，同时规定允许的 predicate signatures、派生谓词展开规则，以及 existence 目标必须满足的组成/资源一致性约束。

## 7. Potentially Missing Related Work

- Work: BEHAVIOR-1K task/activity taxonomy
  - Status: user-provided context, not verified in this review
  - Why relevant: 支撑家庭任务、状态变化和长时任务类型。
  - Overlap: 文档声称六个一级任务类型，但没有给出数据集任务映射。
  - Needed comparison: 原始任务、目标 predicate、所需技能与 GraphWorld 标签的逐项映射。
- Work: ALFRED task types and action abstraction
  - Status: user-provided context, not verified in this review
  - Why relevant: 区分任务目标、导航支撑动作和物体交互步骤。
  - Overlap: 与 schema/grounding 和组合任务直接相关。
  - Needed comparison: ALFRED 七类任务与 state/edge/existence 原子目标的映射及无法覆盖项。
- Work: VirtualHome / SayCan / SayPlan
  - Status: user-provided context, not verified in this review
  - Why relevant: 程序动作、技能组合、可供性和长程计划。
  - Overlap: 支撑固定技能集合与组合任务生成的设计选择。
  - Needed comparison: 技能/API 粒度、环境状态、任务目标和规划验证方式。

## 8. Claim-Evidence Audit

| Claim | Where stated | Evidence provided | Strength | Reviewer deduction | Required fix |
|---|---|---|---|---|---|
| 场景生成后可自动编译每个候选任务并求解 | 42–51 | 无通用 pipeline；仅 laundry 工具 | Weak | 设计与实现混写 | 标为 proposal，并提供端到端覆盖报告 |
| OBJECT_LIBRARY 有 115 个模板 | 59 | 旧 catalog 报告 | Contradicted | 当前代码为 130 | 改为自动生成数字与快照 |
| 六类可描述任务 | 343–354 | 示例，无分类证明 | Weak | 不互斥且完备性未验证 | 定义多标签或判定函数，跑语料覆盖统计 |
| 新产品只需增加 recipe | 356–380 | 咖啡最小实现 | Partial | 当前 recipe engine 仍硬编码语义分支 | 建立声明式 registry 与多配方测试 |
| 通用编译器读取动作、过程、配方和场景图 | 386–420 | 无对应通用模块 | Absent | 属于未来架构 | 降级为 proposed，或实现并给出 artifact |
| laundry 是已验证 PDDL 任务族 | 431–437 | coverage JSON + 专用脚本 | Adequate but narrow | 只证明专用子问题可解 | 保存具体 problem/plan/result 和 runtime 对齐证据 |

## 9. Experiment / Benchmark / Reproducibility Audit

- Baselines: 无 taxonomy baseline 或其他任务本体比较。
- Ablations: 无。尚未比较 state-only、state+edge、state+edge+existence 的覆盖差异。
- Datasets/benchmarks: 文中没有实际文献任务语料统计。
- Metrics: 尚未定义 taxonomy coverage、mutual-exclusion violation、grounding yield、solve rate、plan validity、runtime replay consistency。
- Statistical rigor: 无任务实例规模、随机种子、置信区间或失败分布。
- Robustness/failure cases: 边界表较好，但未转换成自动反例测试。
- Implementation details: 部分代码路径可追踪，但文档快照已经落后于实现。
- Artifacts and reproducibility: laundry PDDL 有脚本；通用 task compiler、grounder 和批量 coverage runner 不存在或未在文中提供证据。
- Limitations: 有边界情况，但没有把“经典 PDDL 不支持动态对象创建和自然时间”提升为正式建模假设。

建议的最小证据矩阵：

| 轴 | 必测项 |
|---|---|
| 原子目标类型 | state / relation / existence |
| 一级标签 | clean / make / relocate / operate / interact / navigate |
| 组合深度 | 1 / 2 / 3+ goals |
| 过程 | instantaneous / triggered timed / natural decay |
| 结果 | grounded / rejected / solved / timeout / runtime-replay-pass |

## 10. Multi-Reviewer Panel

### Reviewer: Method / Soundness

- Expertise: symbolic planning and formal task modeling
- Likely score: 4/10
- Confidence: 4/5
- Main positive signal: 正确区分任务目标、动作和环境过程的意图。
- Main negative signal: 原子任务定义在第 316 行自我推翻，六类没有判定函数。
- Evidence basis: 304–354。
- Score-change condition: 给出 typed goal grammar、non-trivial initial condition 和可执行分类规则，可升至 6/10。

### Reviewer: Evidence / Experiment

- Expertise: benchmark and empirical validation
- Likely score: 3/10
- Confidence: 4/5
- Main positive signal: 坦诚指出 PDDL 仅验证一个任务族。
- Main negative signal: 无语料覆盖统计，专用 laundry solver 被用于支撑更广架构。
- Evidence basis: 427–437 与 `try_laundry_fastdownward.py`。
- Score-change condition: 五类以上 task compiler 测试与批量失败报告，可升至 5–6/10。

### Reviewer: Novelty / Positioning

- Expertise: embodied task planning and related work
- Likely score: 3/10
- Confidence: 2/5
- Main positive signal: 将动态图目标、过程与程序化任务生成放进同一框架，有潜在系统价值。
- Main negative signal: 没有外部文献引用，无法判断 taxonomy 的来源和差异。
- Evidence basis: 全文无引用节。
- Score-change condition: 完成 benchmark-to-predicate 映射和最近工作对比后才能可靠评分。

### Reviewer: Writing / Clarity

- Expertise: technical communication
- Likely score: 4/10
- Confidence: 5/5
- Main positive signal: 表格和具体例子使局部设计容易理解。
- Main negative signal: 文档类型、事实状态和章节主线不清；存在 TODO、陈旧数字和直接矛盾。
- Evidence basis: 1、42–59、179–218、302–425、467–506。
- Score-change condition: 拆分文档职责并统一 implemented/proposed 标记，可升至 6/10。

### Reviewer: Ethics / Reproducibility

- Expertise: artifact audit
- Likely score: 5/10
- Confidence: 4/5
- Main positive signal: 提供多数代码路径和 coverage JSON。
- Main negative signal: 手写表格随代码漂移，没有生成时间和 commit/version 绑定。
- Evidence basis: 59、181、254、431–437。
- Score-change condition: 自动生成 catalog/state/action/coverage 表并保存 planner artifacts，可升至 7/10。

### Reviewer: AC / Domain Application

- Expertise: systems and embodied AI
- Likely score: 4/10
- Confidence: 4/5
- Main positive signal: 问题重要，架构方向实用。
- Main negative signal: 当前材料无法证明 taxonomy 的科学依据或通用编译能力。
- Evidence basis: 全文及代码核验。
- Score-change condition: 先把它变成自洽规范，再用文献语料和多任务 PDDL 覆盖证明。

Panel synthesis:

- Agreement: 架构方向值得继续，但当前不能作为正式 taxonomy 结论。
- Disagreement: 工程可用性评价高于论文证据评价。
- Decisive positive axis: 固定动作集、声明式过程/配方、自动 grounding 的组合思路。
- Decisive negative axis: 分类不可判定、证据不足、实现状态漂移。
- Unresolved evidence: 外部文献覆盖、通用 compiler、interaction/navigate/make 的 PDDL 实例。
- AC stance: weak reject as paper; continue as internal design specification.

## 11. Concerns Table

| ID | Severity | Concern | Evidence basis | Affected criterion | Fix class | Required action | Owner skill | Score-change condition |
|---|---|---|---|---|---|---|---|---|
| C1 | Fatal for taxonomy claim | 原子任务与动作定义矛盾 | 304–323 | Soundness | method/soundness | 修正定义并增加 typed grammar | ccf-paper-writer after method decision | 核心定义唯一且反例通过 |
| C2 | Major | 六类不互斥、无判定函数 | 343–354 | Soundness | method/soundness | 明确 multi-label 或优先级分类器 | ccf-idea-optimizer / project owner | 语料上可计算一致性 |
| C3 | Major | 无文献依据 | 全文 | Positioning | related-work | 建立论文到目标谓词映射 | ccf-literature-searcher | 主要类别均有来源与反例 |
| C4 | Major | 当前/规划状态混写且数字过期 | 59、181–218、254 | Reproducibility | reproducibility | 自动生成状态表并标注快照 | project code owner | 文档与 CI 检查一致 |
| C5 | Major | 通用 PDDL 编译能力未实现 | 390、418 | Evidence | experiment | 实现并覆盖多任务族 | ccf-experiment-designer + code owner | 至少五类端到端通过 |
| C6 | Major | schema capability 与 runtime 不一致 | 394–406 | Soundness | method/soundness | 统一 tool capability/action binding | code owner | schema 可真实 grounding/replay |
| C7 | Moderate | 任务 goal 缺 initial delta/nontriviality | 306–314 | Soundness | method/soundness | 增加初始约束和零步过滤 | code owner | 无 trivial task 进入数据集 |
| C8 | Moderate | 文档职责和标题不清 | 1–53、467–506 | Clarity | writing | 拆分 spec/audit/roadmap | ccf-paper-writer | 单文档有单一论证主线 |
| C9 | Moderate | 时间与动态创建仅作口头编译 | 378–380、451–464 | Evidence | method/soundness | 明确 PDDL 版本或编译语义 | code owner | planner/runtime 语义对齐测试通过 |
| C10 | Minor | 格式和 TODO 残留 | 49、250、498–501 | Clarity | writing | 清理 TODO、列表格式和尾随空格 | ccf-paper-writer | 文档质量检查无警告 |
| C11 | Major | 原子性未绑定 ontology 粒度 | 308–314 | Soundness | method/soundness | 固定 predicate vocabulary 与派生谓词展开规则 | project owner | 复杂目标不能靠新增 predicate 伪装成原子目标 |

## 12. AC / Meta-Review

评审意见高度一致：该文档包含一个合理且可发展的系统架构，但它把“设计提案”“当前实现”“文献结论”和“项目待办”放在同一证据层级。最决定性的正面因素是任务目标与动作/过程分离的方向；最决定性的负面因素是 taxonomy 本身尚未成为一个可计算、可复现、被文献支持的分类体系。

AC stance: 当前不宜将六类写成经文献验证的“最小互斥任务集合”。建议先将文档定位为 GraphWorld Task Ontology Design Draft，完成形式化和代码对齐后，再升级为论文 taxonomy。

## 13. Quantitative Scores

### Scorecard

| Dimension | Score (1-5) | Confidence (1-5) | Evidence basis | Deduction / score-change condition |
|:---|:---:|:---:|:---|:---|
| Novelty | 3 | 2 | 302–425 | 有系统整合价值，但无外部对比；完成文献映射后重评 |
| Soundness | 2 | 5 | 304–354、378–425 | 核心定义矛盾且分类不可判定；形式化并通过反例测试可升至 4 |
| Evidence | 2 | 5 | 427–437 与 laundry 脚本 | 仅一个专用任务族；多族 compiler/replay 证据可升至 4 |
| Significance | 4 | 4 | 3–51、382–425 | 自动任务生成与验证问题重要；保持此定位 |
| Clarity | 3 | 5 | 全文结构 | 局部清楚但整体职责混杂；拆分并统一术语可升至 4 |
| Reproducibility | 3 | 5 | 59、181、431–437 | 路径可追踪但统计漂移；自动生成表和 artifact manifest 可升至 4–5 |
| Ethics / Limitations | 3 | 4 | 453–464 | 边界列得较全，但动态规划假设未正式化；补充明确假设可升至 4 |

**Overall:** 4/10 | **Scholarly Confidence:** 4/5

**Recommendation:** weak-reject（作为正式研究/taxonomy 文档）

**Verdict:** 修正任务形式定义、明确六类为 multi-label 或给出互斥分类器，并补齐文献与多任务 PDDL 证据，可提高约 2 个总体分；若通用 compiler 与 runtime 继续不一致，分数可能降至 3。

Compact summary:

- Quality: 2/5
- Clarity: 3/5
- Significance: 4/5
- Originality: 3/5
- Soundness: 2/5
- Evidence: 2/5
- Reproducibility: 3/5
- Ethics / Limitations: 3/5
- Overall: 4/10
- Confidence: 4/5

## 14. Questions For Authors

1. 六类任务究竟要求互斥分类，还是允许多标签？这会直接决定统计口径和生成器设计。
2. 原子任务是单一终态 literal，还是带初始值的最小 delta？如何排除零步任务？
3. “不可再拆分”相对于哪一版 predicate vocabulary？`exists(hamburger)` 是否必须展开并校验组成、熟化和资源消耗约束？
4. `clean_surface` 是否必须使用工具？若是，当前 `brush(target)` 为什么没有 tool 参数和持有前置条件？
5. 计划采用经典 PDDL、PDDL2.1 durative actions，还是 tick compilation 表达设备和自然过程？
6. 自动生成的潜在输出对象数量如何界定，避免多配方、多实例造成对象池爆炸？
7. 哪些陈述是已实现规范，哪些是下一阶段 proposal？谁是每张统计表的 source of truth？

## 15. Score Revision Criteria

Raising the score would require:

- 给出严格的 Task/Goal/Action/Process 类型系统和 initial-to-goal delta；
- 明确六类标签的多标签或互斥语义，并在文献任务语料上统计覆盖；
- 实现至少五类 schema 的通用 grounding、PDDL、solver、runtime replay 闭环；
- 从代码自动生成对象、状态、动作和覆盖表。

Lowering the score would be triggered by:

- 发现六类无法覆盖主要 benchmark 任务且没有清晰扩展机制；
- PDDL 计划无法在 runtime 重放，或过程语义与规划语义系统性不一致；
- 继续用过期手工统计支持定量结论。

Concerns unlikely to change before submission:

- 真正的通用 PDDL 编译器与大规模任务覆盖需要新增实现和实验，不能只靠文字修改完成。

Score-change table:

| Change | Condition | Likely affected dimensions | Expected movement |
|---|---|---|---|
| Raise score | 形式定义、分类规则、文献映射和多族验证全部完成 | Soundness, Evidence, Positioning | +2 overall |
| Lower score | runtime/PDDL 对齐测试失败 | Soundness, Reproducibility | -1 overall |
| No quick change | 通用 compiler 和任务语料覆盖 | Evidence | 需要新实现与实验 |

## 16. Action Plan And CCFA Handoffs

1. Priority: P0
   - Action: 决定六类是 multi-label taxonomy 还是互斥 partition，并写出形式化分类规则。
   - Owner skill: ccf-idea-optimizer（研究定义）/ project owner（最终决策）
   - Input needed: 任务语料与期望统计口径
   - Expected output: typed goal grammar + classification policy
   - Handoff required: yes
2. Priority: P0
   - Action: 修复任务/动作矛盾，增加 initial delta 和 non-triviality。
   - Owner skill: ccf-paper-writer after method decision
   - Input needed: P0 分类决策
   - Expected output: 自洽的第六节
   - Handoff required: yes
3. Priority: P1
   - Action: 调研并构建 BEHAVIOR-1K、ALFRED、VirtualHome、SayCan、SayPlan 的任务到 predicate 映射。
   - Owner skill: ccf-literature-searcher
   - Input needed: 纳入范围与检索标准
   - Expected output: 文献证据表和未覆盖反例
   - Handoff required: yes
4. Priority: P1
   - Action: 设计通用 PDDL 编译与覆盖实验矩阵。
   - Owner skill: ccf-experiment-designer + project code owner
   - Input needed: 正式 goal grammar、action/process registry
   - Expected output: task matrix、指标、失败分类和结果表 schema
   - Handoff required: yes
5. Priority: P2
   - Action: 拆分 taxonomy/spec、implementation audit 和 roadmap，并从代码生成统计表。
   - Owner skill: ccf-paper-writer + project code owner
   - Input needed: P0/P1 产物
   - Expected output: 单一职责文档与自动快照
   - Handoff required: yes

Checks run:

- 全文三遍阅读与行号核查；
- 对象、动作、状态、task skill、coverage JSON 和 laundry PDDL 实现核验；
- prose quality 非修改扫描；
- Markdown diff whitespace 检查。

Checks skipped:

- 外部文献检索与 citation existence audit；
- 目标 venue 格式、页数和匿名性检查；
- 通用 PDDL 编译器测试，因为当前没有对应实现证据。

Unresolved risks:

- 六类 taxonomy 的文献来源和语料覆盖；
- temporal PDDL 与 runtime scheduler 的语义等价；
- existence-object pool 的有限化与多实例生成策略；
- 工具能力和动作参数的最终抽象。
