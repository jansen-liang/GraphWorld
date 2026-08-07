#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCENE="${SCENE:-simple_home_1f}"
STEPS="${STEPS:-100}"
SEED="${SEED:-0}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_goal_b_v1_${SCENE}}"
NO_LLM="${NO_LLM:-0}"

case "$SCENE" in
  simple_home_1f) HUMANS="${HUMANS:-1}" ;;
  *) HUMANS="${HUMANS:-3}" ;;
esac

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

# label|EFE_MODE|authority|B-learning
CONDITIONS=(
  "shared_b_generative|generative|efe_all|0"
  "goal_b_frozen|goal_conditioned_b|efe_all|0"
  "goal_b_learned|goal_conditioned_b|efe_all|1"
  "rule_all|goal_conditioned_b|rule_all|0"
)

echo "Goal-conditioned B v1 quick experiment"
echo "  total groups: 4"
echo "  scene:        $SCENE"
echo "  humans:       $HUMANS"
echo "  seed:         $SEED"
echo "  steps/group:  $STEPS"
echo "  output:       $OUTPUT_ROOT"
echo "  no_llm:       $NO_LLM"

group=0
for spec in "${CONDITIONS[@]}"; do
  IFS='|' read -r label efe_mode authority learning <<< "$spec"
  group=$((group + 1))
  log_path="$OUTPUT_ROOT/logs/${label}__seed_${SEED}.log"
  echo "===== group $group/4 | $label | mode=$efe_mode | B-learning=$learning ====="
  EFE_MODE="$efe_mode" EFE_GOAL_B_LEARNING="$learning" \
    "$PYTHON_BIN" backend/run_efe_explore_navigation_v1.py \
      --scene "$SCENE" \
      --steps "$STEPS" \
      --only with_robot \
      --robots 1 \
      --humans "$HUMANS" \
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
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

echo "===== all 4/4 groups finished ====="
echo "Per-run:   $OUTPUT_ROOT/goal_policy_runs.csv"
echo "Aggregate: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "Report:    $OUTPUT_ROOT/goal_policy_report.md"
