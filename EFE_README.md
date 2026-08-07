# GraphWorld EFE Agent — Engineering Review Guide

本文档用于把当前 GraphWorld 的 EFE（Expected Free Energy）高层 goal 选择工程交给其他开发者共同分析。文档对应代码状态日期：**2026-08-05**。

> 当前主线 `goal_conditioned_b` 的完整参数矩阵、分层 Dirichlet 更新和数学公式，见
> [`docs/efe_complete_design_current.md`](docs/efe_complete_design_current.md)。

> 当前结论：实验底座和 explore 导航已经基本可用；旧 generative EFE 的主要瓶颈是把所有具体任务压缩成同一个 `act`，并且候选池在无任务时会迫使策略持续 explore。`goal_conditioned` v1 已解决大部分同分和被迫探索问题，但仍属于实验模式，尚未替换默认 `generative`。

## 1. 系统目标

机器人每个 step 会看到局部 observation、合法低层 actions 和当前环境 deviations。EFE agent 负责：

1. 从 pipeline、skill detector、LLM（可选）和 explore/maintain 中收集高层 goal；
2. 消除同一物体的冲突 goal；
3. 使用 EFE 或对照 selector 选择一个 goal；
4. 持有该 goal，直到完成或 stuck；
5. 把完成/失败结果反馈给 belief/model；
6. 让 LLM、规则 ranker 或导航器选择一个合法低层 action。

整体数据流：

```text
world scene / observation / deviations
                  │
                  ▼
      pipeline + skill goal builders
                  │
                  ├── structured task candidates
                  ├── explore candidates
                  └── maintain candidate (goal_conditioned only)
                  │
                  ▼
      deduplication + object ownership
                  │
                  ▼
         EFE / rule / random selector
                  │
                  ▼
          committed goal lifecycle
                  │
                  ▼
 LLM action / engine fallback / deterministic navigation
                  │
                  ▼
      completion or stuck outcome learning
```

## 2. Pipeline 是否还决定 goal

### 当前推荐架构

Pipeline 必须保留，但只负责：

- 检测环境任务；
- 生成带有 `object / target / room / phase / skill` 的可执行候选；
- 刷新 goal phase；
- 判断完成；
- 约束合法目标和执行顺序；
- 处理同一物体的 workflow ownership。

Pipeline 不应决定普通 goal 的优先级。

### 实际代码行为

| 模式 | Pipeline 行为 |
|---|---|
| `generative + current` | pipeline 第一个 fresh goal 可以直接 commit；作为旧行为基线保留 |
| `generative + efe_all` | pipeline goal 进入统一候选池，由 EFE 选择 |
| `goal_conditioned + current` | direct commit 被禁用，pipeline goal 进入统一候选池 |
| `goal_conditioned + efe_all` | 推荐配置；所有普通 goal 由 EFE 选择 |
| `rule_all` | 相同候选生成逻辑，固定 source priority 选择 |
| `random_all` | 相同候选生成逻辑，seeded random 选择 |

目前没有单独实现 `safety_override` 通道。高 urgency deviation 会提高 task need，但真正不可延迟的安全事件后续应实现为独立、可审计的硬约束，而不是重新让 pipeline 普通优先级接管选择。

## 3. 四套评分模式

评分入口位于 `backend/runtime/agent/efe_agent/efe_scorer.py`。

### 3.1 `phase1`：旧混合基线

```text
G(g) = -(P(g) + E(g) + beta * N(g))
```

- `P`：goal 覆盖 deviation 的 preference-weighted urgency；
- `E`：目标房间的 Beta posterior uncertainty；
- `N`：未知房间 novelty；
- `beta`：novelty 系数。

此模式只用于论文/历史对照，不是当前默认。

### 3.2 `generative`：原始默认 EFE

隐状态：

```text
I = needs_attention
S = normal
```

观测：

```text
low / medium / high urgency
```

动作：

```text
wait / explore / act
```

核心公式：

```text
Q(s' | a) = B[:, :, a] @ Q(s)
Q(o | a)  = A @ Q(s' | a)

risk      = KL(Q(o | a) || softmax(C))
ambiguity = E_Q(s'|a)[H(A[:, s'])]
G(a)      = risk + ambiguity
```

选择 `argmin G`。A/B 使用 Dirichlet pseudo-count 在线更新。

主要缺陷：`restore`、医院补给、清洁、垃圾处理等所有任务都映射为同一个 `act`。同房间的具体 goal 因此经常得到相同分数，无法真正学习“哪一种任务更有效”。

### 3.3 `goal_conditioned`：实验策略 v1

Goal 被映射为：

```text
explore
maintain
restore_object
clean_state
return_supply
dispose_waste
laundry
hospital_bed
deliver_to_human
generic_skill
other
```

每个 family 有独立的 Beta-Bernoulli completion posterior：

```text
p_success = success_alpha / (success_alpha + failure_beta)
```

同时在线记录该 family 的平均 duration。当前决策目标为：

```text
G(g) = failure_risk
     + distance_cost
     + duration_cost
     + revisit_cost
     + switch_cost
     - expected_value
     - information_gain
```

各项定义：

- `need`：候选匹配 deviation 后，由 `urgency / (urgency + 5)` 归一化；无显式 deviation 的结构化 task 默认 need 为 0.35；
- `expected_value = need * p_success`；
- `failure_risk = 0.35 * need * (1 - p_success)`；
- `distance_cost = 0.12 * min(shortest_path / 6, 1)`；
- `duration_cost = 0.10 * min(mean_duration / 30, 1)`；
- explore information gain：`0.12 * room_uncertainty / (1 + visit_count)`；
- task information gain：Beta-Bernoulli 下一次结果对成功率参数的 mutual information；
- explore revisit cost：`0.05 * min(visit_count, 3)`；
- `switch_cost` 已进入公式接口，当前候选默认值为 0。

重要说明：这是一套“EFE-inspired、可审计的高层决策目标”，不是只由同一 A/B/C 表推导出来的教科书纯 EFE。工程代价被明确拆开，没有伪装成 epistemic value。协作者应重点讨论这些项的理论解释、归一化和消融设计。

### 3.4 `goal_conditioned_b`：分层生成模型 EFE v1

这是当前用于验证 EFE 学习能力的新实验模式。A 和 C 固定，只在线学习
Goal-conditioned B，不学习标量 reward。Goal 使用结构化签名：

```text
family | target_class | workflow | domain
```

转移后验按以下层级回退：

```text
action kind -> family -> family×target -> complete signature
```

实际 Goal 结果通过联合状态后验更新 Dirichlet 转移计数：

```text
xi[i,j] ∝ A[o_next,i] * B^sigma[i,j] * Q_before[j]
N_level[i,j] <- N_level[i,j] + xi[i,j]
```

评分仍严格为：

```text
G(g) = KL(Q(o|g) || softmax(C)) + E_Q(s'|g)[H(A[:,s'])]
```

完整公式、诊断和运行方式见
`docs/efe_goal_conditioned_b_v1.md`。现有 `goal_conditioned` 保留为工程目标函数基线，不被替换。

## 4. Goal outcome learning

实现文件：`backend/runtime/agent/efe_agent/goal_outcome_model.py`。

每个 family 初始为：

```text
success_alpha = 1
failure_beta  = 1
duration prior = 8 steps, weight 1
```

Goal 完成：

```text
success_alpha += 1
```

Goal stuck/失败：

```text
failure_beta += 1
```

完成和失败都会更新 duration mean。`EFE_GOAL_OUTCOME_LEARNING=0` 可以冻结该 posterior，作为消融对照。

当前学习信号只有“完成/失败 + duration”，还没有使用执行前后环境 score delta。因此一个很容易完成但没有实际收益的 goal 可能被高估，这是下一阶段最重要的改进点之一。

## 5. World belief 与 A/B 学习

### `WorldBelief`

文件：`backend/runtime/agent/efe_agent/world_belief.py`。

每个房间维护：

```text
Beta(alpha, beta)
risk_confidence = alpha / (alpha + beta)
epistemic_norm  = posterior variance / (1/12)
```

Deviation 支持增加 alpha，正常观测增加 beta。重复 evidence key 会被跳过。

### `GenerativeModel`

文件：`backend/runtime/agent/efe_agent/efe_model.py`。

- `A[o,s] = P(o|s)`；
- `B[s',s,a] = P(s'|s,a)`；
- `C[o]` 是 observation log preference；
- passive observation 更新 A；
- goal outcome 更新被执行 action slice 对应的 B。

`goal_conditioned` 仍保留这套 room belief 更新，但 goal 排名主要使用 family outcome posterior 和 room uncertainty。

## 6. Candidate generation 与 lifecycle

### 候选来源

1. pipeline fresh proposals；
2. deterministic skill builders；
3. LLM proposals（仅 `candidate_source=hybrid`）；
4. explore；
5. maintain（仅 `goal_conditioned`）。

正式可复现实验通常使用 `skill_only`，避免 LLM 高层候选生成随机性；LLM 仍可负责选定 goal 下的合法低层 action。

### 冲突消解

- 同一个 goal key 去重；
- 同一 object 只能保留一个 destination/owner；
- specialized skill 优先于 generic restore；
- 医院 lifecycle object 不允许 generic baseline restore 把它送回冲突位置。

### Goal 生命周期

- commit 后持续持有，不每 step 重选；
- 每 step 根据完整 current scene 刷新 phase；
- `phase=done` 立即完成；
- emergency 期间仍执行 completion check；
- 30 steps 未完成判定 stuck；
- failed target cooldown 40 steps；
- explore 必须机器人实际进入目标房间，不能因“看见相邻房间”完成；
- maintain 在下一 step 自动完成。

## 7. Explore navigation variants

### Navigation v1

Navigation v1 已并入主 `EfeLoop`，由
`backend/runtime/agent/decision.py` 提供 BFS 动作选择，
`backend/runtime/agent/efe_agent/efe_core.py` 在 explore Goal 执行阶段调用。

- 只接管 `explore/patrol` 的低层 action；
- 基于 baseline room graph 执行 deterministic BFS shortest path；
- 优先 `move next_room`；
- 如果门阻挡，尝试 `open/move connecting door`；
- 找不到合法动作才 fallback 到原 EFE/LLM action；
- goal selection 和 skill execution 不变。

`backend/run_experiment.py` 默认启用 `--efe-explore-navigation v1`；使用
`--efe-explore-navigation llm` 可恢复原始 LLM explore 动作，便于正交消融。
旧文件 `backend/runtime/agent/efe_explore_navigation_v1.py` 和旧 wrapper 仅作为
兼容入口保留，不再包含另一套独立执行逻辑。

### Navigation v2 budgeted

文件：`backend/runtime/agent/efe_explore_navigation_v2_budgeted.py`。

- 在 v1 基础上加入 30-step patrol cooldown；
- 存在 concrete pipeline goal 时抑制 explore；
- 未探索房间优先；全部访问后只低频 patrol；
- 没有 goal 时选择 local idle anchor action。

v2 是独立实验变体，不应与 `goal_conditioned` 的 endogenous information gain/revisit cost 混为同一个变量。若比较两者，应做正交消融：公式固定，只切导航 budget；导航固定，只切公式。

## 8. LLM 的实际职责

`skill_only` 实验中：

- LLM 不生成高层 goal；
- EFE/rule/random 选择高层 goal；
- LLM 根据 active goal 从 legal candidate actions 中选择 action；
- navigation v1/v2 会在 explore 时覆盖 LLM 的导航动作。

无 LLM 模式会使用 engine ranker/fallback，适合结构 smoke test，不适合作为最终性能结论。

## 9. 关键源码索引

| 文件 | 职责 |
|---|---|
| `backend/runtime/agent/efe_agent/efe_core.py` | 候选合并、selector、goal lifecycle、学习接线、诊断 |
| `backend/runtime/agent/efe_agent/efe_scorer.py` | phase1/generative/goal-conditioned 评分 |
| `backend/runtime/agent/efe_agent/efe_model.py` | A/B/C generative model、EFE、Bayes、Dirichlet 更新 |
| `backend/runtime/agent/efe_agent/goal_outcome_model.py` | goal-family posterior、duration、mutual information |
| `backend/runtime/agent/efe_agent/world_belief.py` | room/node Beta belief |
| `backend/runtime/agent/efe_agent/thinker_post.py` | deviation 和 goal outcome 到 belief evidence 的映射 |
| `backend/runtime/agent/efe_agent/efe_goal_builder.py` | task candidate、phase、完成判定、医院 workflow |
| `backend/runtime/agent/efe_agent/test_efe_numerical.py` | 数值、学习、lifecycle、authority 测试 |
| `backend/run_experiment.py` | GraphWorld 主实验入口和 EFE 集成 |
| `backend/runtime/agent/efe_explore_navigation_v1.py` | deterministic shortest-path explore executor |
| `backend/runtime/agent/efe_explore_navigation_v2_budgeted.py` | budgeted navigation 实验变体 |

## 10. 测试

```bash
cd /home/autumn/GraphWorld

python backend/runtime/agent/efe_agent/test_efe_numerical.py

/home/autumn/miniconda3/envs/py311/bin/python3.11 \
  -m pytest backend/runtime/agent/test_efe_explore_navigation_v1.py -q
```

当前验证状态：

```text
EFE numerical/lifecycle/policy: 34/34 passed
navigation v1:                  4/4 passed
Python compile:                 passed
shell syntax:                   passed
```

## 11. 推荐复现实验

### 11.1 Goal authority 底座

```bash
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_goal_authority_ablation.sh
```

默认：2 scenes × 3 seeds × 4 selectors × 300 steps。

### 11.2 Explore navigation v1

```bash
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_explore_navigation_v1_hospital.sh
```

默认：hospital × 3 seeds × 4 selectors × 300 steps。

### 11.3 Goal-conditioned formula quick screen

```bash
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_formula_goal_conditioned_screen_v1.sh
```

也可运行功能相同的简化入口：

```bash
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_goal_policy_v1_quick.sh
```

四组条件：

```text
generative_efe
goal_conditioned_learned
goal_conditioned_frozen
rule_all
```

### 11.4 Navigation v2 budgeted

```bash
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_explore_navigation_v2_budgeted_hospital.sh
```

## 12. 已有实验信号

### Navigation v1，hospital，3 seeds，300 steps

| selector | final mean | spatial mean | explore navigation decisions |
|---|---:|---:|---:|
| current | 0.6977 | 0.6861 | 221.3 |
| efe_all | 0.6978 | 0.6865 | 223.3 |
| rule_all | 0.6996 | 0.6922 | 224.3 |
| random_all | 0.6718 | 0.6259 | 247.7 |

解释：导航成功率已经很高，但旧 EFE 与 rule 基本持平，并且 explore 数量极高。问题主要转移到了高层价值估计和候选结构。

### Goal-conditioned 开发 smoke，hospital，seed 0，100 steps，无 LLM

| condition | final | spatial | score tie | explore rate | maintain rate |
|---|---:|---:|---:|---:|---:|
| generative_efe | 0.7479 | 0.6873 | 23.8% | 61.9% | 0% |
| goal_conditioned_frozen | 0.7387 | 0.6855 | 0% | 16.3% | 34.7% |
| goal_conditioned_learned | 0.7671 | 0.7437 | 2.0% | 16.3% | 34.7% |
| rule_all | 0.7479 | 0.6873 | 0% | 61.9% | 0% |

这是结构 smoke test，不是正式性能证据。它支持继续运行带 LLM、多个 seed 的小型筛查，但不能据此宣称算法显著优于 rule。

## 13. 关键诊断字段

建议优先检查：

```text
efe_coverage
selection_opportunities
mean_candidates_per_selection
single_candidate_rate
efe_score_tie_rate
pipeline_direct_commits
pipeline_candidates_scored
selected_source_counts
selected_goal_family_counts
goal_completions
goal_stuck_rate
mean_completed_goal_duration
goal_conflict_count
goal_reversal_count
phase_done_action_count
goal_family_beliefs
explore_navigation_override_rate
explore_navigation_fallback_rate
```

每次 EFE 选择的详细分解位于：

```text
authority_step.score_breakdown
```

## 14. 已知限制

1. `goal_conditioned` 权重目前是工程初值，尚未做系统消融；
2. family 粒度可能仍然太粗，同 family 的不同 object/room 共享 posterior；
3. outcome learning 只使用完成/失败，不使用实际 score improvement；
4. maintain 很容易完成，必须防止 posterior 因“低价值成功”被高估；
5. `switch_cost` 接口存在，但当前默认没有真正计算中断代价；
6. `current` 在旧 generative 模式仍允许 pipeline direct commit，仅应作为基线；
7. run checkpoint 当前没有完整恢复 EfeLoop 的在线 belief/outcome state；`to_dict/from_dict` 已存在，但主 runner 尚未接入 checkpoint；
8. 跨 run transfer 尚未作为正式实验流程启用；
9. navigation v2 的硬 exploration budget 与 goal-conditioned 内生探索不能同时变化后直接归因；
10. 当前正式证据不足以证明“随时间变强”，需要 learned vs frozen 的多 seed、时间窗口分析。

## 15. 建议协作者优先分析的问题

1. Goal-conditioned 目标是否能写成更严格的 expected free energy/policy EFE，而不是当前显式加权目标？
2. Task utility 应来自 urgency、human blocking recovery、score delta，还是学习的 reward model？
3. Outcome posterior 应按 family、family×room、family×object semantic 哪个粒度维护？
4. 如何防止 maintain/explore 的“容易完成”污染 success posterior？
5. 是否需要多步 policy rollout，而不是只评估单个高层 goal？
6. 如何实现安全 override，同时保持普通 goal 的 EFE authority？
7. 如何把 EfeLoop state 接入 checkpoint 和跨 run transfer？

## 16. 打包给协作者

运行：

```bash
bash scripts/package_efe_review_bundle.sh
```

脚本会在 `dist/` 生成带时间戳的 `.tar.gz`，包含本文档、EFE 源码、导航变体、实验脚本、测试和小体积聚合结果，不包含 raw replay、模型权重或大日志。
