#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-300}"
SEEDS_CSV="${SEEDS_CSV:-0 1 2}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_formula_multi_direction_90min_v1}"
EXPECTED_SECONDS_PER_GROUP="${EXPECTED_SECONDS_PER_GROUP:-300}"

# label | formula variant | EFE mode | authority | outcome learning
CONDITIONS=(
  "01_global_ab|global_ab|generative|efe_all|1"
  "02_rule_reference|global_ab|generative|rule_all|0"
  "03_goal_conditioned_current|goal_conditioned_current|goal_conditioned|efe_all|1"
  "04_null_fixed|null_fixed|goal_conditioned|efe_all|1"
  "05_stale_slow_h005|stale_h005|goal_conditioned|efe_all|1"
  "06_stale_medium_h020|stale_h020|goal_conditioned|efe_all|1"
)

read -r -a SEEDS <<< "$SEEDS_CSV"
TOTAL_GROUPS=$((${#CONDITIONS[@]} * ${#SEEDS[@]}))
ALL_START=$SECONDS

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs"

echo "============================================================"
echo "EFE multi-direction formula experiment v1"
echo "总实验组: $TOTAL_GROUPS（${#CONDITIONS[@]} 方向 × ${#SEEDS[@]} seeds）"
echo "每组: $STEPS steps | 预计每组: $((EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "预计总时长: $((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "组号: 1-6=seed0，7-12=seed1，13-18=seed2"
echo "结果目录: $OUTPUT_ROOT"
echo "============================================================"

group=0
for seed in "${SEEDS[@]}"; do
  for spec in "${CONDITIONS[@]}"; do
    IFS='|' read -r label variant efe_mode authority learning <<< "$spec"
    group=$((group + 1))
    GROUP_START=$SECONDS
    if (( group == 1 )); then
      REMAINING_SECONDS=$((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP))
    else
      AVG_SECONDS=$(((SECONDS - ALL_START) / (group - 1)))
      REMAINING_SECONDS=$((AVG_SECONDS * (TOTAL_GROUPS - group + 1)))
    fi

    echo
    echo "########## 实验组 $group/$TOTAL_GROUPS ##########"
    echo "方向=$label | variant=$variant | seed=$seed | steps=$STEPS"
    echo "开始前预计剩余: $((REMAINING_SECONDS / 60)) 分钟"

    log_path="$OUTPUT_ROOT/logs/group_${group}_of_${TOTAL_GROUPS}__${label}__seed_${seed}.log"
    EFE_FORMULA_VARIANT="$variant" EFE_MODE="$efe_mode" \
      EFE_GOAL_OUTCOME_LEARNING="$learning" \
      "$PYTHON_BIN" backend/run_efe_formula_staleness_v1.py \
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
        --output-root "$OUTPUT_ROOT/$label/seed_$seed" \
        --no-clean \
        --replay-scene-interval 20 \
        --metric-log-interval 10 \
        2>&1 | tee "$log_path"

    GROUP_SECONDS=$((SECONDS - GROUP_START))
    AVG_SECONDS=$(((SECONDS - ALL_START) / group))
    REMAINING_SECONDS=$((AVG_SECONDS * (TOTAL_GROUPS - group)))
    echo "实验组 $group/$TOTAL_GROUPS 完成，用时 $((GROUP_SECONDS / 60)) 分 $((GROUP_SECONDS % 60)) 秒"
    echo "总进度: $group/$TOTAL_GROUPS；预计剩余 $((REMAINING_SECONDS / 60)) 分钟"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "全部 $TOTAL_GROUPS/$TOTAL_GROUPS 组完成，总用时 $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组结果: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "聚合结果: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "日志目录: $OUTPUT_ROOT/logs/"
echo "============================================================"
