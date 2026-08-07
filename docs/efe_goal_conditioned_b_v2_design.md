# Goal-conditioned B EFE v2：当前设计与验证结果

## 1. 目标

本设计验证 EFE 是否能学习“某类 Goal 会把世界带到什么状态”，并据此改进 Goal 选择。学习对象不是成功率奖励或累计回报，而是 Goal-conditioned 状态转移矩阵：

\[
B^\sigma_{ij}=P(s_{t+1}=i\mid s_t=j,\sigma)
\]

其中 \(\sigma\) 是结构化 Goal 类型。A（观测模型）和 C（偏好）在当前实验中固定，只更新 B，以便 Frozen/Learned 对照只检验转移学习。

## 2. Goal 选择与执行边界

当前 `goal_conditioned_b` 模式中：

1. pipeline、skill builder、explore builder 和 maintain builder 只产生候选 Goal；
2. EFE 对全部候选统一打分并选择；pipeline 不直接决定 Goal；
3. 选中的 Goal 持有到完成或连续无进展；
4. 底层动作由 Goal-aware 确定性排序器约束，LLM 只能在合法候选中提出动作；
5. Goal 结束后，实际后验观测用于更新该 Goal 类型的 B。

因此 pipeline 仍有必要，但角色是“提供可执行、带 phase/target 的候选”，不是最终决策者。

## 3. 生成模型

### 3.1 隐状态 S

隐状态是问题程度和认知状态的笛卡尔积，共 6 类：

\[
s=(c,k),\quad
c\in\{normal,mild,severe\},\quad
k\in\{unknown,known\}
\]

代码顺序为：`normal_unknown, mild_unknown, severe_unknown, normal_known, mild_known, severe_known`。

### 3.2 观测 O 与 A

观测共 4 类：`unobserved, low, medium, high`。固定矩阵

\[
A_{oi}=P(o_{t+1}=o\mid s_{t+1}=i)
\]

把 unknown 状态主要映射为 `unobserved`，把 known 状态按问题程度映射为 low/medium/high。

### 3.3 偏好 C

固定偏好分布为：

\[
P_C(o)=(0.08,0.72,0.15,0.05),\qquad C=\ln P_C
\]

这表示偏好可观测的低问题状态，同时避免把 `unobserved` 当成理想结果。

### 3.4 结构化 Goal 签名

\[
\sigma=(family,target\_class,workflow,domain)
\]

例如：

- `dispose_waste|food|dispose_food|home`
- `restore_object|bowl|direct_restore|home`
- `clean_state|cup|empty_cup|home`
- `explore|room|inspect_room|home`
- `maintain|room|wait|home`

签名不包含具体 object id，因此能在同类对象间迁移，又不会把 dispose、restore、clean 混成一个粗粒度动作。

## 4. 分层 Dirichlet B

为解决细分类别样本稀疏，B 使用四级回退：

\[
kind \rightarrow family \rightarrow family\times target \rightarrow \sigma
\]

根层以可解释的弱先验 \(B^0\) 初始化。每一级的有效参数为：

\[
\alpha^{(l)}=\lambda B^{(l-1)}+N^{(l)},\qquad
B^{(l)}_{ij}=\frac{\alpha^{(l)}_{ij}}
{\sum_r\alpha^{(l)}_{rj}}
\]

新签名依赖父类先验；样本增加后，叶子计数逐渐主导。这实现了“细致但不繁琐”的分类。

## 5. EFE 打分

候选 Goal 的当前状态先验为 \(q_t=Q(s_t\mid\text{scene},g)\)。预测为：

\[
q_{t+1}=B^\sigma q_t,\qquad
q(o_{t+1})=Aq_{t+1}
\]

当前使用标准 risk + ambiguity 分解：

\[
G(g)=D_{KL}[q(o_{t+1}\mid g)\Vert P_C(o)]
+\mathbb E_{q(s_{t+1}\mid g)}[H(A_{\cdot,s_{t+1}})]
\]

选择 \(G\) 最小的 Goal。没有额外成功奖励、距离奖励、maintain 惩罚或人工加权 bonus。

### 5.1 非修复 Goal 的全局状态

task Goal 表示对局部问题实施干预；explore/maintain 则是在“暂不修复”的前提下作用于全局。因此当结构化任务仍存在时：

- explore/maintain 的 \(Q(s_t)\) 至少为 mild，而不能因当前房间安静被标为 normal；
- 它们结束后的观测反映全局剩余问题，不能用一个安静目标房间冒充全局改善。

这是状态推断和观测归因修正，不是奖励塑形。

### 5.2 任务型 Goal 的目标级状态

task Goal 的因果作用范围是其问题对象，而不是对象所在的整个房间。因此从
当前实现开始，task Goal 的执行前先验和执行后观测使用同一目标粒度：

\[
c_t^g=\operatorname{condition}(x_g,t),\qquad
c_{t+1}^g=\operatorname{condition}(x_g,t+1)
\]

其中 \(x_g\) 优先取 Goal 的 `object`；只有无 object 的 Goal 才使用
`target`。同房间其他对象的偏差不再进入该 Goal 的 \(q_t\) 或
\(o_{t+1}\)。结构化 detector 在提交时记录 `target_issue_before`，在 Goal
结束时重新计算 `target_issue_after`：

- `True -> False`：目标问题被消除，观测为 `low`；
- `True -> True`：目标问题仍存在，按目标自身紧急度观测为 `medium/high`；
- detector 在部分可观测条件下返回 `None` 时，才回退到目标自身 deviation
  和 Goal lifecycle result。

explore/maintain 不代表对某个对象的修复，仍使用环境级状态。日志字段
`credit_assignment` 会明确标记 `target_condition` 或
`environment_condition`，使每次 B 更新可以审计。

## 6. B 的学习规则

Goal 完成后先得到观测 \(o_{t+1}\)，再计算联合转移后验：

\[
\xi_{ij}\propto A_{o_{t+1},i}B^\sigma_{ij}q_t(j),
\qquad \sum_{ij}\xi_{ij}=1
\]

然后在签名的四个层级更新 Dirichlet 计数：

\[
N^{(l)}_{ij}\leftarrow N^{(l)}_{ij}+\xi_{ij}
\]

Frozen 条件计算完全相同的预测和观测，但不更新计数。

预序列负对数似然用于衡量模型是否越来越准：

\[
NLL_t=-\log P(o_{t+1}\mid q_t,B^\sigma,A)
\]

应同时报告全程平均 NLL 与最近 20 次 NLL；只看最终 world score 无法判断 B 是否真的学会。

## 7. v2 生命周期修复

- maintain 是一个时间步的观测动作，下一步即闭合一次转移，不再要求离开当前房间；
- stuck 从“总时长 30 步”改成“连续 12 步无可观察进展”，并保留 160 步硬上限；
- phase、object parent 或沿规划路线缩短距离才算进展，来回移动不算；
- 临时放下错误手持物是单步执行约束，不替换原 Goal，不产生 `generic` B 样本；
- 修复 dispose 状态机：新食物问题出现而机器人仍拿着空垃圾桶时，先 `return_bin`，不能错误回到 `dump_bin`。

新增诊断：`goal_no_progress_failures`、`goal_hard_timeout_failures`、`goal_progress_events`、`transient_drop_constraints`。

## 8. 验证结果

命令：

```bash
cd /home/autumn/GraphWorld
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
SCENE=simple_home_1f STEPS=100 SEEDS='0 1 2' NO_LLM=1 \
bash scripts/run_efe_goal_b_v2_validation.sh
```

Home 100 步，3 seeds，共 12 组：

| 条件 | final | completions | stuck | B NLL | recent-20 NLL |
|---|---:|---:|---:|---:|---:|
| Goal-B Frozen | 0.8322 | 39.33 | 0.00 | 0.7368 | 0.6740 |
| Goal-B Learned | 0.8313 | 39.00 | 0.00 | 0.7014 | 0.6411 |
| Rule | 0.8218 | 26.00 | 0.00 | 1.0308 | 1.0033 |
| Shared-B Generative | 0.8250 | 25.33 | 0.00 | - | - |

Learned 相比 Frozen：

- 平均 NLL 降低约 4.8%；
- recent-20 NLL 降低约 4.9%；
- EFE 分数并列率从 0.171 降到 0.067；
- 完成数和最终分基本持平，没有 maintain/explore 策略塌缩；
- 当前不能宣称 world score 有显著提升。

结果目录：`backend/data/experiments/efe_goal_b_v2_validation_home_100/`，汇总报告为其中的 `goal_policy_report.md`。

## 9. 代码入口

- `backend/runtime/agent/efe_agent/goal_transition_model.py`：A/C、Goal 签名、分层 B、EFE 与学习；
- `backend/runtime/agent/efe_agent/efe_core.py`：候选池、Goal 生命周期、后验观测和模型接线；
- `backend/runtime/agent/efe_agent/efe_goal_builder.py`：可执行 workflow/phase；
- `backend/runtime/agent/decision.py`：Goal-aware 动作排序；
- `scripts/run_efe_goal_b_v2_validation.sh`：多 seed 验证；
- `scripts/summarize_efe_goal_policy_v1.py`：结果汇总；
- `backend/runtime/agent/efe_agent/test_efe_numerical.py`：矩阵和生命周期回归测试。

## 10. 当前结论与下一步

当前版本已证明：结构化 Goal 的实际后验可以稳定更新 Goal-conditioned B，预测校准会随样本改善，且不需要奖励函数。但 100 步 Home 仍不足以证明学习带来显著任务性能增益。

下一优先实验应是：

1. Home 400/800 步、至少 5 seeds，比较 Learned/Frozen 的 NLL 曲线和后半程 task choice；
2. Hospital 400 步，检验 `bed_linen/return_supply/clean_state` 的跨类别分化；
3. 按前 25% 与后 25% 分段报告 NLL、Goal family 选择和实际问题消除率；
4. 若长程仍只改善 NLL、不改变选择，再考虑多步 policy horizon，而不是添加奖励项。

## 11. 目标级信用分配快速验证（2026-08-06）

修复后运行 Home 50 步、seed 0、无 LLM 的 Frozen/Learned 冒烟对照：

- 10 次 EFE 选择、9 次 Goal 完成、0 次 stuck；
- 9 次 B 更新中，所有已完成 task Goal 都记录为目标级 `low`；
- `dispose_waste`、5 次 `restore_object` 和 `clean_state` 均未被同房间残余
  问题错误标记为 `medium`；
- explore/maintain 仍记录环境级 `medium`，符合其全局因果语义；
- Frozen/Learned 的平均 NLL 为 `0.8399/0.7600`，Learned 降低约 9.5%；
- 两者短程选择与最终分相同，但 EFE 分数并列次数由 `5` 降到 `3`；
- 相关回归测试共 58 项全部通过。

冒烟结果位于：
`backend/data/experiments/efe_goal_b_target_credit_smoke_v1/`。

这只验证信号归因和执行链正确，不用于宣称 Learned 已优于 Frozen。下一轮仍需
用相同轨迹/seed 做 Frozen-Learned 对照，检查新的 B 是否产生任务有利的严格
Goal 翻转。
