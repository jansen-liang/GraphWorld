#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCENE="${SCENE:-simple_home_1f}"
STEPS="${STEPS:-100}"
SEEDS="${SEEDS:-0 1 2}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_goal_b_v2_validation_${SCENE}_${STEPS}}"
NO_LLM="${NO_LLM:-1}"

case "$SCENE" in
  simple_home_1f) HUMANS="${HUMANS:-1}" ;;
  *) HUMANS="${HUMANS:-3}" ;;
esac

read -r -a SEED_LIST <<< "$SEEDS"
CONDITIONS=(
  "shared_b_generative|generative|efe_all|0"
  "goal_b_frozen|goal_conditioned_b|efe_all|0"
  "goal_b_learned|goal_conditioned_b|efe_all|1"
  "rule_all|goal_conditioned_b|rule_all|0"
)
TOTAL_GROUPS=$((${#SEED_LIST[@]} * ${#CONDITIONS[@]}))

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
mkdir -p "$OUTPUT_ROOT/logs"
EXTRA_AGENT_ARGS=()
if [[ "$NO_LLM" == "1" ]]; then
  EXTRA_AGENT_ARGS+=(--no-llm)
fi

echo "Goal-conditioned B v2 validation"
echo "  total groups: $TOTAL_GROUPS (${#CONDITIONS[@]} conditions x ${#SEED_LIST[@]} seeds)"
echo "  scene:        $SCENE"
echo "  steps/group:  $STEPS"
echo "  seeds:        ${SEED_LIST[*]}"
echo "  output:       $OUTPUT_ROOT"

group=0
for seed in "${SEED_LIST[@]}"; do
  for spec in "${CONDITIONS[@]}"; do
    IFS='|' read -r label efe_mode authority learning <<< "$spec"
    group=$((group + 1))
    log_path="$OUTPUT_ROOT/logs/${label}__seed_${seed}.log"
    echo "===== group $group/$TOTAL_GROUPS | $label | seed=$seed | B-learning=$learning ====="
    EFE_MODE="$efe_mode" EFE_GOAL_B_LEARNING="$learning" \
      "$PYTHON_BIN" backend/run_efe_explore_navigation_v1.py \
        --scene "$SCENE" --steps "$STEPS" --only with_robot \
        --robots 1 --humans "$HUMANS" --agent-model "$AGENT_MODEL" \
        --agent-mode efe --efe-goal-authority "$authority" \
        --efe-candidate-source skill_only --schedule-mode stochastic \
        --schedule-seed "$seed" \
        --output-root "$OUTPUT_ROOT/$label/seed_$seed" \
        "${EXTRA_AGENT_ARGS[@]}" --no-clean \
        --replay-scene-interval 20 --metric-log-interval 10 \
        2>&1 | tee "$log_path"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

echo "===== all $TOTAL_GROUPS/$TOTAL_GROUPS groups finished ====="
echo "Report: $OUTPUT_ROOT/goal_policy_report.md"
