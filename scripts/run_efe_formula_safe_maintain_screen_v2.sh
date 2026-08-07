#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-100}"
SEED="${SEED:-0}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_formula_safe_maintain_screen_v2}"
EXPECTED_SECONDS_PER_GROUP="${EXPECTED_SECONDS_PER_GROUP:-120}"
NO_LLM="${NO_LLM:-0}"

# Same four controls as v1; only the independent safe-maintain harness changes.
CONDITIONS=(
  "01_global_ab_generative|generative|efe_all|1"
  "02_goal_conditioned_learned|goal_conditioned|efe_all|1"
  "03_goal_conditioned_frozen|goal_conditioned|efe_all|0"
  "04_rule_reference|goal_conditioned|rule_all|0"
)

TOTAL_GROUPS=${#CONDITIONS[@]}
ALL_START=$SECONDS

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs"
EXTRA_AGENT_ARGS=()
if [[ "$NO_LLM" == "1" ]]; then
  EXTRA_AGENT_ARGS+=(--no-llm)
fi

echo "============================================================"
echo "EFE formula screen v2 — safe maintain validation"
echo "总实验组: $TOTAL_GROUPS | seed=$SEED | 每组=$STEPS steps"
echo "预计总时间: 约 $((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "关键约束: maintain 只能 move 到本房间固定锚点，禁止 pick/place"
echo "结果目录: $OUTPUT_ROOT"
echo "============================================================"

group=0
for spec in "${CONDITIONS[@]}"; do
  IFS='|' read -r label efe_mode authority learning <<< "$spec"
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
  echo "$label | formula=$efe_mode | selector=$authority | online_learning=$learning"
  echo "预计剩余: 约 $((REMAINING_SECONDS / 60)) 分钟"

  log_path="$OUTPUT_ROOT/logs/group_${group}_of_${TOTAL_GROUPS}__${label}__seed_${SEED}.log"
  EFE_MODE="$efe_mode" EFE_GOAL_OUTCOME_LEARNING="$learning" \
    "$PYTHON_BIN" backend/run_efe_goal_conditioned_safe_maintain_v1.py \
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
      --schedule-seed "$SEED" \
      --output-root "$OUTPUT_ROOT/$label/seed_$SEED" \
      "${EXTRA_AGENT_ARGS[@]}" \
      --no-clean \
      --replay-scene-interval 20 \
      --metric-log-interval 10 \
      2>&1 | tee "$log_path"

  GROUP_SECONDS=$((SECONDS - GROUP_START))
  AVG_SECONDS=$(((SECONDS - ALL_START) / group))
  REMAINING_SECONDS=$((AVG_SECONDS * (TOTAL_GROUPS - group)))
  echo "实验组 $group/$TOTAL_GROUPS 完成，用时 $((GROUP_SECONDS / 60)) 分 $((GROUP_SECONDS % 60)) 秒"
  echo "当前进度: $group/$TOTAL_GROUPS；预计剩余约 $((REMAINING_SECONDS / 60)) 分钟"
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "全部 $TOTAL_GROUPS/$TOTAL_GROUPS 组完成，总用时 $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组数据: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "汇总数据: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "日志: $OUTPUT_ROOT/logs/"
echo "============================================================"
