#!/usr/bin/env bash
set -euo pipefail

# Continue the interrupted 18-group clean-evidence experiment.
# Group 10 resumes from its checkpoint; groups 11-18 start normally.
# Existing completed groups are detected and skipped.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-400}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_clean_evidence_long_v1}"
RESUME_RUN="${RESUME_RUN:-$OUTPUT_ROOT/04_stale_clean_w025/seed_1/simple_hospital_1f/steps_400__robots_1__humans_3__model_vllm_qwen3_5_9b_efe_authority_efe_all_candidates_skill_only__schedule_stochastic__seed_1/20260806T035344Z_4b8ab76c}"
EXPECTED_SECONDS_PER_FULL_GROUP="${EXPECTED_SECONDS_PER_FULL_GROUP:-400}"

# original group | label | formula | clean evidence | EFE mode | selector | learning | seed
RUN_SPECS=(
  "10|04_stale_clean_w025|stale_h005|clean_w025|goal_conditioned|efe_all|1|1"
  "11|05_stale_clean_w050|stale_h005|clean_w050|goal_conditioned|efe_all|1|1"
  "12|06_stale_clean_w100|stale_h005|clean_w100|goal_conditioned|efe_all|1|1"
  "13|01_global_ab|global_ab|none|generative|efe_all|1|2"
  "14|02_rule_reference|global_ab|none|generative|rule_all|0|2"
  "15|03_stale_no_clean|stale_h005|none|goal_conditioned|efe_all|1|2"
  "16|04_stale_clean_w025|stale_h005|clean_w025|goal_conditioned|efe_all|1|2"
  "17|05_stale_clean_w050|stale_h005|clean_w050|goal_conditioned|efe_all|1|2"
  "18|06_stale_clean_w100|stale_h005|clean_w100|goal_conditioned|efe_all|1|2"
)

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL

mkdir -p "$OUTPUT_ROOT/logs"

echo "============================================================"
echo "EFE clean-entry evidence long experiment v1（续跑）"
echo "原实验总组数: 18"
echo "已完成: 1-9组"
echo "本脚本处理: 10-18组，共9组"
echo "第10组: 从 checkpoint 的 next_step=276/400 继续"
echo "第11-18组: 每组 $STEPS steps"
echo "预计剩余: 约 $((8 * EXPECTED_SECONDS_PER_FULL_GROUP / 60 + 3)) 分钟"
echo "结果目录: $OUTPUT_ROOT"
echo "============================================================"

ALL_START=$SECONDS
processed=0

for spec in "${RUN_SPECS[@]}"; do
  IFS='|' read -r group label formula clean_variant efe_mode authority learning seed <<< "$spec"
  result_root="$OUTPUT_ROOT/$label/seed_$seed"

  if find "$result_root" -name summary.json -print -quit 2>/dev/null | grep -q .; then
    echo
    echo "########## 实验组 $group/18：已有完整结果，跳过 ##########"
    continue
  fi

  processed=$((processed + 1))
  echo
  echo "########## 实验组 $group/18 ##########"
  echo "方向=$label | formula=$formula | clean=$clean_variant | seed=$seed"

  if [[ "$group" == "10" ]]; then
    if [[ ! -f "$RESUME_RUN/with_robot/checkpoint.json" ]]; then
      echo "错误：找不到第10组 checkpoint：$RESUME_RUN/with_robot/checkpoint.json" >&2
      exit 1
    fi
    echo "模式=checkpoint续跑（不会重跑前272步）"
    log_path="$OUTPUT_ROOT/logs/group_10_of_18__04_stale_clean_w025__seed_1__resume.log"
    EFE_FORMULA_VARIANT="$formula" \
      EFE_CLEAN_EVIDENCE_VARIANT="$clean_variant" \
      EFE_MODE="$efe_mode" \
      EFE_GOAL_OUTCOME_LEARNING="$learning" \
      "$PYTHON_BIN" backend/run_efe_clean_entry_evidence_v1.py \
        --resume \
        --resume-run "$RESUME_RUN" \
        --only with_robot \
        --replay-scene-interval 20 \
        --metric-log-interval 10 \
        2>&1 | tee "$log_path"
  else
    echo "模式=新实验组，完整运行 $STEPS steps"
    log_path="$OUTPUT_ROOT/logs/group_${group}_of_18__${label}__seed_${seed}__resume.log"
    EFE_FORMULA_VARIANT="$formula" \
      EFE_CLEAN_EVIDENCE_VARIANT="$clean_variant" \
      EFE_MODE="$efe_mode" \
      EFE_GOAL_OUTCOME_LEARNING="$learning" \
      "$PYTHON_BIN" backend/run_efe_clean_entry_evidence_v1.py \
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
  fi

  elapsed=$((SECONDS - ALL_START))
  echo "实验组 $group/18 完成；本次续跑累计用时 $((elapsed / 60)) 分 $((elapsed % 60)) 秒"
done

"$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"

TOTAL_SECONDS=$((SECONDS - ALL_START))
echo
echo "============================================================"
echo "续跑完成：原实验18/18组应已齐全"
echo "本次实际执行组数: $processed"
echo "本次用时: $((TOTAL_SECONDS / 60)) 分 $((TOTAL_SECONDS % 60)) 秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组结果: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "聚合结果: $OUTPUT_ROOT/goal_policy_aggregate.csv"
echo "续跑日志: $OUTPUT_ROOT/logs/*__resume.log"
echo "============================================================"
