#!/usr/bin/env bash
set -euo pipefail

# Scientifically clean restart for interrupted V3 group 9, then groups 10-32.
# Groups 1-8 and any later completed summaries are detected and skipped.
# The partial group-9 checkpoint/log are retained but not mixed into results.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-400}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_connected_large_v3}"
SMOKE_ROOT="${SMOKE_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_connected_smoke_v3}"
EXPECTED_SECONDS_PER_GROUP="${EXPECTED_SECONDS_PER_GROUP:-700}"
RUN_TAG="${RUN_TAG:-restart}"

# Prevent two V3 launchers from writing the same condition/seed concurrently.
LOCK_FILE="${LOCK_FILE:-/tmp/graphworld_efe_b_connected_large_v3.lock}"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "错误：另一个EFE V3实验脚本仍在运行；本次续跑未启动。" >&2
  exit 1
fi

# label | authority | B update | learn maintain | clean evidence
CONDITIONS=(
  "01_b_frozen_all_clean_none|efe_all|0|1|none"
  "02_b_online_all_clean_none|efe_all|1|1|none"
  "03_b_online_taskonly_clean_none|efe_all|1|0|none"
  "04_b_online_taskonly_clean_w050|efe_all|1|0|clean_w050"
  "05_b_online_taskonly_clean_w075|efe_all|1|0|clean_w075"
  "06_b_online_taskonly_clean_w100|efe_all|1|0|clean_w100"
  "07_b_online_taskonly_clean_w125|efe_all|1|0|clean_w125"
  "08_rule_reference|rule_all|0|0|none"
)
SEEDS=(1 2 3)
TOTAL_GROUPS=32

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs"

echo "============================================================"
echo "EFE connected-B large experiment v3（第9组起干净重跑）"
echo "原实验总组数: 32"
echo "已完整完成: 第1-8组"
echo "本脚本处理: 第9-32组，共24组"
echo "第9组策略: 从0/400重新运行，避免缺失EFE内部状态"
echo "原第9组中断记录: 保留，不覆盖"
echo "预计剩余时长: 约 $((24 * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"
echo "结果目录: $OUTPUT_ROOT"
echo "============================================================"

# Reuse the already completed V3 smoke test; this performs no experiment run.
"$PYTHON_BIN" scripts/check_efe_b_connected_v3_smoke.py "$SMOKE_ROOT"

ALL_START=$SECONDS
completed_this_run=0
group=8

for seed in "${SEEDS[@]}"; do
  for spec in "${CONDITIONS[@]}"; do
    IFS='|' read -r label authority learning learn_maintain clean_variant <<< "$spec"
    group=$((group + 1))
    result_root="$OUTPUT_ROOT/$label/seed_$seed"

    if find "$result_root" -name summary.json -print -quit 2>/dev/null | grep -q .; then
      echo
      echo "########## 实验组 $group/$TOTAL_GROUPS：已有完整结果，跳过 ##########"
      continue
    fi

    remaining_groups=$((TOTAL_GROUPS - group + 1))
    echo
    echo "########## 实验组 $group/$TOTAL_GROUPS ##########"
    echo "条件=$label | seed=$seed | steps=$STEPS"
    echo "选择器=$authority | B更新=$learning | maintain学习=$learn_maintain"
    echo "clean evidence=$clean_variant"
    if [[ "$group" == "9" ]]; then
      echo "说明=原第9组中断，本次从0/400干净重跑"
    fi
    echo "按真实速度预计剩余: $((remaining_groups * EXPECTED_SECONDS_PER_GROUP / 60)) 分钟"

    group_start=$SECONDS
    log_path="$OUTPUT_ROOT/logs/group_${group}_of_${TOTAL_GROUPS}__${label}__seed_${seed}__${RUN_TAG}.log"
    EFE_FORMULA_VARIANT="goal_conditioned_current" \
      EFE_CLEAN_EVIDENCE_VARIANT="$clean_variant" \
      EFE_MODE="goal_conditioned_b" \
      EFE_GOAL_OUTCOME_LEARNING="$learning" \
      EFE_B_LEARN_MAINTAIN="$learn_maintain" \
      EFE_CANDIDATE_LOG="1" \
      "$PYTHON_BIN" backend/run_efe_b_connected_task_learning_v3.py \
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
        --output-root "$result_root" \
        --no-clean \
        --replay-scene-interval 20 \
        --metric-log-interval 10 \
        2>&1 | tee "$log_path"

    completed_this_run=$((completed_this_run + 1))
    group_seconds=$((SECONDS - group_start))
    elapsed=$((SECONDS - ALL_START))
    echo "实验组 $group/$TOTAL_GROUPS 完成，用时 $((group_seconds / 60)) 分 $((group_seconds % 60)) 秒"
    echo "本次续跑累计用时: $((elapsed / 60)) 分钟"
  done
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_canonical_v3.py "$OUTPUT_ROOT"

summary_count="$(( $(wc -l < "$OUTPUT_ROOT/goal_policy_runs.csv") - 1 ))"
TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "正式实验完整结果: $summary_count/$TOTAL_GROUPS组"
echo "本次实际运行: $completed_this_run组"
echo "本次续跑用时: $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组结果: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "聚合结果: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "续跑日志标记: __${RUN_TAG}.log"
echo "============================================================"
