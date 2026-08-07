#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCENE="${SCENE:-simple_home_1f}"
STEPS="${STEPS:-50}"
SEED="${SEED:-0}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_goal_b_vs_single_round_llm_smoke_v1}"

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

# label|agent-mode|EFE-mode|authority|B-learning
CONDITIONS=(
  "single_round|single_round|goal_conditioned_b|current|0"
  "goal_b_frozen|efe|goal_conditioned_b|efe_all|0"
  "goal_b_learned|efe|goal_conditioned_b|efe_all|1"
)

echo "Goal-B versus single_round LLM smoke v1"
echo "  total groups: 3"
echo "  scene:        $SCENE"
echo "  steps/group:  $STEPS"
echo "  seed:         $SEED"
echo "  model:        $AGENT_MODEL"
echo "  vllm url:     $VLLM_BASE_URL"
echo "  served model: $VLLM_MODEL"
echo "  output:       $OUTPUT_ROOT"

if ! "$PYTHON_BIN" -c \
  'from backend.run_experiment import check_llm_agent; import sys; ok, status = check_llm_agent(sys.argv[1], timeout=10.0); print("LLM preflight:", status); raise SystemExit(0 if ok else 2)' \
  "$AGENT_MODEL"; then
  echo "ERROR: vLLM is not reachable. Start the server or override VLLM_BASE_URL/VLLM_MODEL." >&2
  exit 2
fi

group=0
for spec in "${CONDITIONS[@]}"; do
  IFS='|' read -r label agent_mode efe_mode authority learning <<< "$spec"
  group=$((group + 1))
  log_path="$OUTPUT_ROOT/logs/${label}__seed_${SEED}.log"
  echo "===== group $group/3 | $label | mode=$agent_mode | B-learning=$learning ====="
  EFE_MODE="$efe_mode" EFE_GOAL_B_LEARNING="$learning" \
    "$PYTHON_BIN" backend/run_efe_explore_navigation_v1.py \
      --scene "$SCENE" --steps "$STEPS" --only with_robot \
      --robots 1 --humans "$HUMANS" --agent-model "$AGENT_MODEL" \
      --agent-mode "$agent_mode" --efe-goal-authority "$authority" \
      --efe-candidate-source skill_only --schedule-mode stochastic \
      --schedule-seed "$SEED" --output-root "$OUTPUT_ROOT/$label/seed_$SEED" \
      --no-clean --replay-scene-interval 20 --metric-log-interval 10 \
      2>&1 | tee "$log_path"
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

echo "===== all 3/3 groups finished ====="
echo "Per-run:   $OUTPUT_ROOT/goal_policy_runs.csv"
echo "Aggregate: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "Report:    $OUTPUT_ROOT/goal_policy_report.md"
