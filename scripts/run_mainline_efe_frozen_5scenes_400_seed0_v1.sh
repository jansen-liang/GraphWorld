#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-python3}"
STEPS="${STEPS:-400}"
SEED="${SEED:-0}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/mainline_efe_vs_single_5scenes_400_seed0_v1}"
REPLAY_SCENE_INTERVAL="${REPLAY_SCENE_INTERVAL:-20}"
METRIC_LOG_INTERVAL="${METRIC_LOG_INTERVAL:-10}"

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

SCENES=(
  "simple_home_1f|1"
  "simple_hospital_1f|3"
  "simple_office_1f|3"
  "simple_factory_1f|3"
  "simple_supermarket_1f|2"
)
TOTAL_GROUPS="${#SCENES[@]}"
CONDITION_ROOT="$OUTPUT_ROOT/efe_frozen/seed_$SEED"

mkdir -p "$OUTPUT_ROOT/logs"

echo "Mainline Goal-B Frozen control: 5 scenes"
echo "  total groups:  $TOTAL_GROUPS"
echo "  steps/group:   $STEPS"
echo "  seed:          $SEED"
echo "  model:         $AGENT_MODEL ($VLLM_MODEL)"
echo "  vllm url:      $VLLM_BASE_URL"
echo "  output:        $OUTPUT_ROOT"

if ! "$PYTHON_BIN" -c \
  'from backend.run_experiment import check_llm_agent; import sys; ok, status = check_llm_agent(sys.argv[1], timeout=10.0); print("LLM preflight:", status); raise SystemExit(0 if ok else 2)' \
  "$AGENT_MODEL"; then
  echo "ERROR: vLLM is not reachable. Start the server or override VLLM_BASE_URL/VLLM_MODEL." >&2
  exit 2
fi

group=0
for scene_spec in "${SCENES[@]}"; do
  IFS='|' read -r scene humans <<< "$scene_spec"
  group=$((group + 1))
  log_path="$OUTPUT_ROOT/logs/${scene}__efe_frozen__seed_${SEED}.log"

  echo "===== group $group/$TOTAL_GROUPS | scene=$scene | mode=efe_frozen | humans=$humans ====="

  if compgen -G "$CONDITION_ROOT/$scene/*/*/summary.json" > /dev/null; then
    echo "SKIP: completed summary already exists for $scene / efe_frozen / seed $SEED"
    continue
  fi

  EFE_CANDIDATE_LOG=1 \
    "$PYTHON_BIN" backend/run_experiment.py \
      --scene "$scene" \
      --steps "$STEPS" \
      --only with_robot \
      --robots 1 \
      --humans "$humans" \
      --agent-model "$AGENT_MODEL" \
      --agent-mode efe \
      --efe-mode goal_conditioned_b \
      --efe-goal-b-learning off \
      --efe-goal-authority efe_all \
      --efe-candidate-source skill_only \
      --efe-explore-navigation v1 \
      --schedule-mode stochastic \
      --schedule-seed "$SEED" \
      --output-root "$CONDITION_ROOT" \
      --no-clean \
      --replay-scene-interval "$REPLAY_SCENE_INTERVAL" \
      --metric-log-interval "$METRIC_LOG_INTERVAL" \
      2>&1 | tee "$log_path"
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

echo "===== all $TOTAL_GROUPS/$TOTAL_GROUPS Frozen groups finished ====="
echo "Per-run:   $OUTPUT_ROOT/goal_policy_runs.csv"
echo "Aggregate: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "Report:    $OUTPUT_ROOT/goal_policy_report.md"
