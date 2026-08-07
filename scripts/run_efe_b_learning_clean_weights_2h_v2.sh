#!/usr/bin/env bash
set -euo pipefail

# Pure Goal-conditioned-B experiment. Existing v1 code/results are untouched.
# Stage 1: one short run must prove B updates are non-zero.
# Stage 2: 6 conditions x 3 paired schedule seeds = 18 formal groups.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-400}"
SMOKE_STEPS="${SMOKE_STEPS:-100}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_learning_clean_weights_2h_v2}"
SMOKE_ROOT="${SMOKE_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_learning_smoke_v2}"
EXPECTED_SECONDS_PER_GROUP="${EXPECTED_SECONDS_PER_GROUP:-400}"

# label | clean evidence | B online learning
CONDITIONS=(
  "01_b_frozen_clean_none|none|0"
  "02_b_online_clean_none|none|1"
  "03_b_online_clean_w050|clean_w050|1"
  "04_b_online_clean_w075|clean_w075|1"
  "05_b_online_clean_w100|clean_w100|1"
  "06_b_online_clean_w125|clean_w125|1"
)
SEEDS=(0 1 2)
TOTAL_GROUPS=18

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs" "$SMOKE_ROOT/logs"

echo "============================================================"
echo "EFE Goal-conditioned-B + clean evidence experiment v2"
echo "预检: 1组 × $SMOKE_STEPS steps（必须观测到 B updates > 0）"
echo "正式实验: 18组（6条件 × 3 seeds）"
echo "每组: $STEPS steps"
echo "组号: 1-6=seed0，7-12=seed1，13-18=seed2"
echo "预计正式实验: 约 $((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "正式结果: $OUTPUT_ROOT"
echo "============================================================"

smoke_summary="$(find "$SMOKE_ROOT" -name summary.json -print -quit 2>/dev/null || true)"
if [[ -z "$smoke_summary" ]]; then
  echo
  echo "########## B更新预检（不计入正式18组） ##########"
  EFE_FORMULA_VARIANT="goal_conditioned_current" \
    EFE_CLEAN_EVIDENCE_VARIANT="none" \
    EFE_MODE="goal_conditioned_b" \
    EFE_GOAL_OUTCOME_LEARNING="1" \
    "$PYTHON_BIN" backend/run_efe_clean_entry_b_learning_v2.py \
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
      --schedule-seed 99 \
      --output-root "$SMOKE_ROOT" \
      --no-clean \
      --replay-scene-interval 20 \
      --metric-log-interval 10 \
      2>&1 | tee "$SMOKE_ROOT/logs/b_update_smoke.log"
else
  echo
  echo "B更新预检已有完整结果，直接复核：$smoke_summary"
fi

"$PYTHON_BIN" scripts/check_efe_b_updates_v2.py "$SMOKE_ROOT"

ALL_START=$SECONDS
group=0
for seed in "${SEEDS[@]}"; do
  for spec in "${CONDITIONS[@]}"; do
    IFS='|' read -r label clean_variant learning <<< "$spec"
    group=$((group + 1))
    result_root="$OUTPUT_ROOT/$label/seed_$seed"

    if find "$result_root" -name summary.json -print -quit 2>/dev/null | grep -q .; then
      echo
      echo "########## 实验组 $group/$TOTAL_GROUPS：已有完整结果，跳过 ##########"
      continue
    fi

    elapsed=$((SECONDS - ALL_START))
    if (( group == 1 )); then
      remaining=$((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP))
    else
      remaining=$(((elapsed / (group - 1)) * (TOTAL_GROUPS - group + 1)))
    fi

    echo
    echo "########## 实验组 $group/$TOTAL_GROUPS ##########"
    echo "条件=$label | B学习=$([[ "$learning" == "1" ]] && echo 在线 || echo 冻结)"
    echo "clean evidence=$clean_variant | seed=$seed | steps=$STEPS"
    echo "开始前预计剩余: $((remaining / 60)) 分钟"

    log_path="$OUTPUT_ROOT/logs/group_${group}_of_${TOTAL_GROUPS}__${label}__seed_${seed}.log"
    EFE_FORMULA_VARIANT="goal_conditioned_current" \
      EFE_CLEAN_EVIDENCE_VARIANT="$clean_variant" \
      EFE_MODE="goal_conditioned_b" \
      EFE_GOAL_OUTCOME_LEARNING="$learning" \
      "$PYTHON_BIN" backend/run_efe_clean_entry_b_learning_v2.py \
        --scene simple_hospital_1f \
        --steps "$STEPS" \
        --only with_robot \
        --robots 1 \
        --humans 3 \
        --agent-model "$AGENT_MODEL" \
        --agent-mode efe \
        --efe-goal-authority efe_all \
        --efe-candidate-source skill_only \
        --schedule-mode stochastic \
        --schedule-seed "$seed" \
        --output-root "$result_root" \
        --no-clean \
        --replay-scene-interval 20 \
        --metric-log-interval 10 \
        2>&1 | tee "$log_path"

    if [[ "$learning" == "1" ]]; then
      "$PYTHON_BIN" scripts/check_efe_b_updates_v2.py "$result_root"
    fi
    group_seconds=$((SECONDS - ALL_START - elapsed))
    echo "实验组 $group/$TOTAL_GROUPS 完成，用时 $((group_seconds / 60)) 分 $((group_seconds % 60)) 秒"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "正式实验完成: 18/18组"
echo "总用时: $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组结果: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "聚合结果: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "日志: $OUTPUT_ROOT/logs/"
echo "============================================================"
