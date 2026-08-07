#!/usr/bin/env bash
set -euo pipefail

# Large V3 experiment: 8 conditions x 4 paired seeds = 32 formal groups.
# This script is intentionally independent of all V1/V2 runners and outputs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-400}"
SMOKE_STEPS="${SMOKE_STEPS:-140}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_connected_large_v3}"
SMOKE_ROOT="${SMOKE_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_connected_smoke_v3}"
EXPECTED_SECONDS_PER_GROUP="${EXPECTED_SECONDS_PER_GROUP:-400}"

# label | authority | B update | learn maintain | clean evidence
CONDITIONS=(
  "01_b_frozen_all_clean_none|efe_all|0|1|none"
  "02_b_online_all_clean_none|efe_all|1|1|none"
  "03_b_online_taskonly_clean_none|efe_all|1|0|none"
  "04_b_online_taskonly_clean_w050|efe_all|1|0|clean_w050"
  "05_b_online_taskonly_clean_w075|efe_all|1|0|clean_w075"
  "06_b_online_taskonly_clean_w100|efe_all|1|0|clean_w100"
  "07_b_online_taskonly_clean_w125|efe_all|1|0|clean_w125"
  "08_rule_reference|rule_all|0|0|none"
)
SEEDS=(0 1 2 3)
TOTAL_GROUPS=$((${#CONDITIONS[@]} * ${#SEEDS[@]}))

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs" "$SMOKE_ROOT/logs"

echo "============================================================"
echo "EFE connected-B large experiment v3"
echo "运行者: 用户（本脚本不会由Codex自动启动）"
echo "预检: 1组 × $SMOKE_STEPS steps"
echo "正式实验: $TOTAL_GROUPS组（${#CONDITIONS[@]}条件 × ${#SEEDS[@]} seeds）"
echo "每组: $STEPS steps"
echo "组号: 1-8=seed0，9-16=seed1，17-24=seed2，25-32=seed3"
echo "预计正式时长: 约 $((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "正式结果: $OUTPUT_ROOT"
echo "============================================================"

# A completed smoke run is reused, making script restarts safe.
smoke_summary="$(find "$SMOKE_ROOT" -name summary.json -print -quit 2>/dev/null || true)"
if [[ -z "$smoke_summary" ]]; then
  echo
  echo "########## V3接线预检（不计入正式32组） ##########"
  echo "检查项: B有更新、maintain被去相关、评分读到leaf_samples>0"
  EFE_FORMULA_VARIANT="goal_conditioned_current" \
    EFE_CLEAN_EVIDENCE_VARIANT="clean_w100" \
    EFE_MODE="goal_conditioned_b" \
    EFE_GOAL_OUTCOME_LEARNING="1" \
    EFE_B_LEARN_MAINTAIN="0" \
    EFE_CANDIDATE_LOG="1" \
    "$PYTHON_BIN" backend/run_efe_b_connected_task_learning_v3.py \
      --scene simple_hospital_1f \
      --steps "$SMOKE_STEPS" \
      --only with_robot \
      --robots 1 \
      --humans 3 \
      --agent-model "$AGENT_MODEL" \
      --agent-mode efe \
      --efe-goal-authority efe_all \
      --efe-candidate-source skill_only \
      --schedule-mode stochastic \
      --schedule-seed 97 \
      --output-root "$SMOKE_ROOT" \
      --no-clean \
      --replay-scene-interval 20 \
      --metric-log-interval 5 \
      2>&1 | tee "$SMOKE_ROOT/logs/v3_connection_smoke.log"
else
  echo
  echo "V3预检已有完整结果，直接复核: $smoke_summary"
fi

"$PYTHON_BIN" scripts/check_efe_b_connected_v3_smoke.py "$SMOKE_ROOT"

ALL_START=$SECONDS
completed_this_run=0
group=0
for seed in "${SEEDS[@]}"; do
  for spec in "${CONDITIONS[@]}"; do
    IFS='|' read -r label authority learning learn_maintain clean_variant <<< "$spec"
    group=$((group + 1))
    result_root="$OUTPUT_ROOT/$label/seed_$seed"

    if find "$result_root" -name summary.json -print -quit 2>/dev/null | grep -q .; then
      echo
      echo "########## 实验组 $group/$TOTAL_GROUPS：已有完整结果，跳过 ##########"
      continue
    fi

    echo
    echo "########## 实验组 $group/$TOTAL_GROUPS ##########"
    echo "条件=$label | seed=$seed | steps=$STEPS"
    echo "选择器=$authority | B更新=$learning | maintain学习=$learn_maintain"
    echo "clean evidence=$clean_variant"
    remaining_groups=$((TOTAL_GROUPS - group + 1))
    echo "按初始估计剩余: $((remaining_groups * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"

    group_start=$SECONDS
    log_path="$OUTPUT_ROOT/logs/group_${group}_of_${TOTAL_GROUPS}__${label}__seed_${seed}.log"
    EFE_FORMULA_VARIANT="goal_conditioned_current" \
      EFE_CLEAN_EVIDENCE_VARIANT="$clean_variant" \
      EFE_MODE="goal_conditioned_b" \
      EFE_GOAL_OUTCOME_LEARNING="$learning" \
      EFE_B_LEARN_MAINTAIN="$learn_maintain" \
      EFE_CANDIDATE_LOG="1" \
      "$PYTHON_BIN" backend/run_efe_b_connected_task_learning_v3.py \
        --scene simple_hospital_1f \
        --steps "$STEPS" \
        --only with_robot \
        --robots 1 \
        --humans 3 \
        --agent-model "$AGENT_MODEL" \
        --agent-mode efe \
        --efe-goal-authority "$authority" \
        --efe-candidate-source skill_only \
        --schedule-mode stochastic \
        --schedule-seed "$seed" \
        --output-root "$result_root" \
        --no-clean \
        --replay-scene-interval 20 \
        --metric-log-interval 10 \
        2>&1 | tee "$log_path"

    completed_this_run=$((completed_this_run + 1))
    group_seconds=$((SECONDS - group_start))
    elapsed=$((SECONDS - ALL_START))
    echo "实验组 $group/$TOTAL_GROUPS 完成，用时 $((group_seconds / 60)) 分 $((group_seconds % 60)) 秒"
    echo "本次累计用时: $((elapsed / 60)) 分钟"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

summary_count="$(find "$OUTPUT_ROOT" -name summary.json | wc -l)"
TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "正式实验完整结果: $summary_count/$TOTAL_GROUPS组"
echo "本次实际运行: $completed_this_run组"
echo "本次用时: $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组结果: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "聚合结果: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "候选评分审计: 各组metrics.csv中的candidate_table"
echo "日志: $OUTPUT_ROOT/logs/"
echo "============================================================"
