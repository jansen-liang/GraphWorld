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
SCHEDULE_MODE="${SCHEDULE_MODE:-stochastic}"
SCENES_CSV="${SCENES_CSV:-simple_home_1f simple_hospital_1f}"
SEEDS_CSV="${SEEDS_CSV:-0 1 2}"
CONDITIONS_CSV="${CONDITIONS_CSV:-current efe_all rule_all random_all}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_goal_authority_v3_goal_lifecycle_fix}"
NO_LLM="${NO_LLM:-0}"

read -r -a SCENES <<< "$SCENES_CSV"
read -r -a SEEDS <<< "$SEEDS_CSV"
read -r -a CONDITIONS <<< "$CONDITIONS_CSV"

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

humans_for_scene() {
  case "$1" in
    simple_home_1f) echo 1 ;;
    simple_hospital_1f) echo 3 ;;
    *) echo 3 ;;
  esac
}

echo "EFE goal-authority ablation"
echo "  output:     $OUTPUT_ROOT"
echo "  steps:      $STEPS"
echo "  scenes:     ${SCENES[*]}"
echo "  seeds:      ${SEEDS[*]}"
echo "  conditions: ${CONDITIONS[*]}"
echo "  schedule:   $SCHEDULE_MODE"
echo "  candidates: skill_only"
echo "  no_llm:     $NO_LLM"

for seed in "${SEEDS[@]}"; do
  for scene in "${SCENES[@]}"; do
    humans="$(humans_for_scene "$scene")"
    for condition in "${CONDITIONS[@]}"; do
      condition_root="$OUTPUT_ROOT/$condition/seed_$seed"
      log_path="$OUTPUT_ROOT/logs/${scene}__${condition}__seed_${seed}.log"
      echo "===== $(date -Is) scene=$scene condition=$condition seed=$seed ====="
      "$PYTHON_BIN" backend/run_experiment.py \
        --scene "$scene" \
        --steps "$STEPS" \
        --only with_robot \
        --robots 1 \
        --humans "$humans" \
        --agent-model "$AGENT_MODEL" \
        --agent-mode efe \
        --efe-goal-authority "$condition" \
        --efe-candidate-source skill_only \
        --schedule-mode "$SCHEDULE_MODE" \
        --schedule-seed "$seed" \
        --output-root "$condition_root" \
        "${EXTRA_AGENT_ARGS[@]}" \
        --no-clean \
        --replay-scene-interval 20 \
        --metric-log-interval 10 \
        2>&1 | tee "$log_path"
    done
  done
done

"$PYTHON_BIN" scripts/summarize_efe_goal_authority.py "$OUTPUT_ROOT"

echo "===== finished $(date -Is) ====="
echo "Raw runs:  $OUTPUT_ROOT/<condition>/seed_<seed>/<scene>/..."
echo "Run logs:  $OUTPUT_ROOT/logs/"
echo "Aggregate: $OUTPUT_ROOT/aggregate_summary.csv"
echo "Report:    $OUTPUT_ROOT/aggregate_report.md"
