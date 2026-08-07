# EFE Goal Policy v1

这一版优化高层 goal 选择策略，不改变 skill executor。Pipeline 继续生成结构化候选、刷新 phase、判断完成和执行动作，但在 `goal_conditioned` 模式下不再直接提交普通目标；pipeline、skill 和 explore 候选统一由 EFE 评分。

## Goal families

原 generative scorer 只区分 `wait / explore / act`。v1 将可执行 goal 映射为：

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
```

每个 family 使用 Beta-Bernoulli posterior 学习完成概率，并在线记录平均完成/失败耗时。完成和 stuck 才更新 outcome model；普通房间观测仍由原 room belief 和 A/B 模型处理。

## Selection objective

```text
G = failure_risk + distance_cost + duration_cost + switch_cost
    - expected_value - information_gain
```

- `expected_value`：候选覆盖的 deviation urgency 与该 family 完成概率；
- `information_gain`：explore 的房间不确定性/访问衰减，或 task family 下一次结果的 Beta-Bernoulli mutual information；
- `revisit_cost`：重复访问同一房间的显式代价；首次探索不受惩罚；
- `distance_cost`：baseline room graph 最短路；
- `duration_cost`：该 family 在线学习的平均耗时；
- `failure_risk`：任务价值乘以预测失败概率。

各分量会写入 `authority_step.score_breakdown`。累计诊断包含 `selected_goal_family_counts`、`goal_family_beliefs`、`pipeline_candidates_scored` 和 `goal_outcome_learning`。

`goal_conditioned` 会始终提供一个单步 `maintain_order` 候选。它解决了“没有 repair 时只能被迫 explore”的候选集缺陷；maintain 在下一 step 自动完成，不会触发 stuck。

## 快速实验

```bash
cd /home/autumn/GraphWorld
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_goal_policy_v1_quick.sh
```

默认共 4 组，每组 100 steps、医院场景、seed 0：

```text
generative_efe
goal_conditioned_learned
goal_conditioned_frozen
rule_all
```

结果写入：

```text
backend/data/experiments/efe_goal_policy_v1_quick/
```

优先查看 `goal_policy_report.md` 和 `goal_policy_runs.csv`。这个 quick experiment 只用于筛查方向；出现优势后再补 seed 1、2。
