# EFE Goal-Authority Ablation

这个实验验证 EFE 是否真正获得了高层目标决策权，以及统一候选池后，EFE 是否优于规则选择和随机选择。

## 四个条件

| 条件 | 含义 |
|---|---|
| `current` | fresh pipeline proposal 优先直接提交；目标生命周期统一由 EFE loop 管理 |
| `efe_all` | pipeline、skill 和 explore 目标进入统一候选池，由 EFE 选择 |
| `rule_all` | 使用同一候选生成逻辑，按 pipeline、skill、LLM、explore 的固定顺序选择 |
| `random_all` | 使用同一候选生成逻辑，由带 seed 的随机选择器选择 |

正式脚本默认使用 `skill_only`：高层候选只来自规则技能、pipeline 和固定数量的 explore 候选，避免 LLM 候选生成的随机性干扰 authority 对比。LLM 仍负责在选定目标下选择合法动作。

## v3 实验底座修复

- pipeline 只负责每步生成 fresh proposal；提交、完成、失败和 cooldown 只有 EFE loop 一个 owner；
- 医院物品由专用 workflow 独占，generic restore 不再把床单等物品送回冲突目标；
- 已提交目标会依据完整当前场景刷新 phase，紧急事件期间也照常判定完成；
- explore 以机器人真正进入房间为完成条件，不再把“看见相邻房间”误记为访问；
- repair 与 explore 同时进入候选池，并记录单候选率、冲突、反转、score tie、完成耗时和 stuck rate。

这些修改只修复候选生成和目标生命周期，不改变 EFE 的评分公式。v1/v2 结果不要与 v3 混在同一目录中。

## 运行

确保 vLLM 服务已经启动，然后执行：

```bash
cd /home/autumn/GraphWorld
PYTHON_BIN=/path/to/python \
VLLM_BASE_URL=http://127.0.0.1:8000/v1 \
VLLM_MODEL=qwen3.5-9b \
bash scripts/run_efe_goal_authority_ablation.sh
```

默认运行：

```text
2 scenes × 3 seeds × 4 conditions × 300 steps = 24 runs
```

快速试跑一个条件：

```bash
STEPS=20 \
SCENES_CSV="simple_home_1f" \
SEEDS_CSV="0" \
CONDITIONS_CSV="efe_all" \
bash scripts/run_efe_goal_authority_ablation.sh
```

## 输出

默认根目录：

```text
backend/data/experiments/efe_goal_authority_v3_goal_lifecycle_fix/
```

目录结构：

```text
efe_goal_authority_v3_goal_lifecycle_fix/
├── current/seed_0/<scene>/<group>/<run_id>/
├── efe_all/seed_0/<scene>/<group>/<run_id>/
├── rule_all/seed_0/<scene>/<group>/<run_id>/
├── random_all/seed_0/<scene>/<group>/<run_id>/
├── logs/
├── runs.csv
├── aggregate_summary.csv
├── aggregate_summary.json
└── aggregate_report.md
```

每个 raw run 内含：

- `summary.json`：最终分数和累计 authority diagnostics；
- `with_robot/metrics.csv`：逐 step 分数及 EFE diagnostics；
- `with_robot/replay.json`：完整回放；
- `with_robot/checkpoint.json`：中断恢复状态。

最先检查 `aggregate_report.md` 和以下字段：

- `efe_coverage`；
- `pipeline_direct_commits`；
- `goal_completions`；
- `goal_stuck_failures`；
- `goal_switches`；
- `same_target_reselections`；
- `goal_reversal_count`；
- `goal_conflict_count`；
- `single_candidate_rate`；
- `efe_score_tie_rate`；
- `goal_stuck_rate`；
- `mean_completed_goal_duration`；
- `phase_done_action_count`；
- 四个最终评分。
