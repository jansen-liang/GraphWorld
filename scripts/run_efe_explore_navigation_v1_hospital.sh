#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-python3}"
STEPS="${STEPS:-300}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
SEEDS_CSV="${SEEDS_CSV:-0 1 2}"
CONDITIONS_CSV="${CONDITIONS_CSV:-current efe_all rule_all random_all}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_explore_navigation_v1_hospital}"
NO_LLM="${NO_LLM:-0}"

read -r -a SEEDS <<< "$SEEDS_CSV"
read -r -a CONDITIONS <<< "$CONDITIONS_CSV"
TOTAL_GROUPS=$((${#SEEDS[@]} * ${#CONDITIONS[@]}))
GROUP_INDEX=0

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

echo "EFE deterministic exploration-navigation v1"
echo "  total groups: $TOTAL_GROUPS (${#SEEDS[@]} seeds x ${#CONDITIONS[@]} conditions)"
echo "  scene:        simple_hospital_1f"
echo "  steps/group:  $STEPS"
echo "  seeds:        ${SEEDS[*]}"
echo "  conditions:   ${CONDITIONS[*]}"
echo "  output:       $OUTPUT_ROOT"
echo "  no_llm:       $NO_LLM"

for seed in "${SEEDS[@]}"; do
  for condition in "${CONDITIONS[@]}"; do
    GROUP_INDEX=$((GROUP_INDEX + 1))
    condition_root="$OUTPUT_ROOT/$condition/seed_$seed"
    log_path="$OUTPUT_ROOT/logs/simple_hospital_1f__${condition}__seed_${seed}.log"
    echo "===== group $GROUP_INDEX/$TOTAL_GROUPS | condition=$condition | seed=$seed ====="
    "$PYTHON_BIN" backend/run_efe_explore_navigation_v1.py \
      --scene simple_hospital_1f \
      --steps "$STEPS" \
      --only with_robot \
      --robots 1 \
      --humans 3 \
      --agent-model "$AGENT_MODEL" \
      --agent-mode efe \
      --efe-goal-authority "$condition" \
      --efe-candidate-source skill_only \
      --schedule-mode stochastic \
      --schedule-seed "$seed" \
      --output-root "$condition_root" \
      "${EXTRA_AGENT_ARGS[@]}" \
      --no-clean \
      --replay-scene-interval 20 \
      --metric-log-interval 10 \
      2>&1 | tee "$log_path"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_explore_navigation_v1.py "$OUTPUT_ROOT"

echo "===== all $TOTAL_GROUPS/$TOTAL_GROUPS groups finished ====="
echo "Raw runs:  $OUTPUT_ROOT/<condition>/seed_<seed>/simple_hospital_1f/..."
echo "Run logs:  $OUTPUT_ROOT/logs/"
echo "Per-run:   $OUTPUT_ROOT/navigation_runs.csv"
echo "Aggregate: $OUTPUT_ROOT/navigation_aggregate_summary.csv"
