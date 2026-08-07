#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-300}"
SEEDS_CSV="${SEEDS_CSV:-0 1 2}"
CONDITIONS_CSV="${CONDITIONS_CSV:-efe_all rule_all}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_explore_navigation_v2_budgeted_hospital}"
EXPECTED_SECONDS_PER_GROUP="${EXPECTED_SECONDS_PER_GROUP:-360}"

read -r -a SEEDS <<< "$SEEDS_CSV"
read -r -a CONDITIONS <<< "$CONDITIONS_CSV"
TOTAL_GROUPS=$((${#SEEDS[@]} * ${#CONDITIONS[@]}))
GROUP_INDEX=0
ALL_START=$SECONDS

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs"

echo "============================================================"
echo "EFE exploration navigation v2 — budgeted hospital experiment"
echo "总实验组: $TOTAL_GROUPS 组（${#CONDITIONS[@]} 算法 × ${#SEEDS[@]} seeds）"
echo "每组步数: $STEPS"
echo "预计每组: 约 $((EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "预计总计: 约 $((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "结果目录: $OUTPUT_ROOT"
echo "组号顺序: seed 0 的 EFE/Rule，然后 seed 1，最后 seed 2"
echo "============================================================"

for seed in "${SEEDS[@]}"; do
  for condition in "${CONDITIONS[@]}"; do
    GROUP_INDEX=$((GROUP_INDEX + 1))
    GROUP_START=$SECONDS
    if (( GROUP_INDEX == 1 )); then
      ETA_SECONDS=$((TOTAL_GROUPS * EXPECTED_SECONDS_PER_GROUP))
    else
      AVG_SECONDS=$(((SECONDS - ALL_START) / (GROUP_INDEX - 1)))
      ETA_SECONDS=$((AVG_SECONDS * (TOTAL_GROUPS - GROUP_INDEX + 1)))
    fi
    echo
    echo "########## 实验组 $GROUP_INDEX/$TOTAL_GROUPS ##########"
    echo "算法=$condition | seed=$seed | steps=$STEPS"
    echo "当前预计剩余时间: 约 $((ETA_SECONDS / 60)) 分钟"

    condition_root="$OUTPUT_ROOT/$condition/seed_$seed"
    log_path="$OUTPUT_ROOT/logs/group_${GROUP_INDEX}_of_${TOTAL_GROUPS}__${condition}__seed_${seed}.log"
    "$PYTHON_BIN" backend/run_efe_explore_navigation_v2_budgeted.py \
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
      --no-clean \
      --replay-scene-interval 20 \
      --metric-log-interval 10 \
      2>&1 | tee "$log_path"

    GROUP_SECONDS=$((SECONDS - GROUP_START))
    FINISHED_SECONDS=$((SECONDS - ALL_START))
    AVG_SECONDS=$((FINISHED_SECONDS / GROUP_INDEX))
    REMAINING_SECONDS=$((AVG_SECONDS * (TOTAL_GROUPS - GROUP_INDEX)))
    echo "实验组 $GROUP_INDEX/$TOTAL_GROUPS 完成，用时 $((GROUP_SECONDS / 60)) 分 $((GROUP_SECONDS % 60)) 秒"
    echo "全部进度: $GROUP_INDEX/$TOTAL_GROUPS；预计剩余 $((REMAINING_SECONDS / 60)) 分钟"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_explore_navigation_v1.py "$OUTPUT_ROOT"

TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "全部 $TOTAL_GROUPS/$TOTAL_GROUPS 组完成，总用时 $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "逐组日志: $OUTPUT_ROOT/logs/"
echo "逐组结果: $OUTPUT_ROOT/navigation_runs.csv"
echo "汇总结果: $OUTPUT_ROOT/navigation_aggregate_summary.csv"
echo "============================================================"
