#!/usr/bin/env bash
set -euo pipefail

# Resume only formal groups 30-32 of efe_b_connected_large_v3.
#
# The original experiment ran from the pre-branch-switch stash snapshot.  The
# current collaborator branch no longer contains the EFE V3 runtime, so this
# script reconstructs that exact snapshot in an isolated temporary directory.
# It never checks out another branch and never modifies current tracked files.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-/home/autumn/miniconda3/envs/py311/bin/python3.11}"
STEPS="${STEPS:-400}"
AGENT_MODEL="${AGENT_MODEL:-vllm-qwen3.5-9b}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-qwen3.5-9b}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_connected_large_v3}"

# Exact snapshots made immediately before the collaborator branch switch:
# tracked worktree state + formerly untracked V3 experiment files.
TRACKED_SNAPSHOT="cc95452"
V3_FILES_SNAPSHOT="9b67673"

export PYTHONUNBUFFERED=1
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-graphworld}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export VLLM_BASE_URL VLLM_MODEL
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

mkdir -p "$OUTPUT_ROOT/logs"

LOCK_FILE="$OUTPUT_ROOT/.groups30_32_isolated.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: 另一份30-32组续跑脚本仍在运行，本次不重复启动。" >&2
  exit 1
fi

if ! git cat-file -e "$TRACKED_SNAPSHOT^{tree}" 2>/dev/null; then
  echo "ERROR: 找不到原实验tracked快照 $TRACKED_SNAPSHOT。" >&2
  exit 2
fi
if ! git cat-file -e "$V3_FILES_SNAPSHOT^{tree}" 2>/dev/null; then
  echo "ERROR: 找不到原实验V3文件快照 $V3_FILES_SNAPSHOT。" >&2
  exit 2
fi

RUNTIME_ROOT="$(mktemp -d /tmp/graphworld_efe_v3_groups30_32.XXXXXX)"
cleanup_runtime() {
  case "$RUNTIME_ROOT" in
    /tmp/graphworld_efe_v3_groups30_32.*) rm -rf -- "$RUNTIME_ROOT" ;;
    *) echo "WARNING: 临时目录路径异常，未自动清理: $RUNTIME_ROOT" >&2 ;;
  esac
}
trap cleanup_runtime EXIT INT TERM

echo "正在隔离目录恢复第1-29组使用的原始代码快照……"
git archive "$TRACKED_SNAPSHOT" | tar -x -C "$RUNTIME_ROOT"
git archive "$V3_FILES_SNAPSHOT" | tar -x -C "$RUNTIME_ROOT"

required_files=(
  "backend/run_efe_b_connected_task_learning_v3.py"
  "backend/runtime/agent/efe_b_connected_task_learning_v3.py"
  "backend/runtime/agent/efe_clean_entry_b_learning_v2.py"
  "backend/runtime/agent/efe_formula_staleness_v1.py"
  "backend/runtime/agent/efe_goal_conditioned_safe_maintain_v1.py"
  "scripts/summarize_efe_goal_policy_v1.py"
)
for relative_path in "${required_files[@]}"; do
  if [[ ! -f "$RUNTIME_ROOT/$relative_path" ]]; then
    echo "ERROR: 隔离快照缺少 $relative_path。" >&2
    exit 2
  fi
done

if ! "$PYTHON_BIN" -c \
  'from backend.run_experiment import check_llm_agent; import sys; ok, status = check_llm_agent(sys.argv[1], timeout=10.0); print("LLM预检:", status); raise SystemExit(0 if ok else 2)' \
  "$AGENT_MODEL"; then
  echo "ERROR: vLLM不可用，未启动任何实验组。" >&2
  exit 2
fi

# group | label | authority | B update | learn maintain | clean evidence
GROUPS=(
  "30|06_b_online_taskonly_clean_w100|efe_all|1|0|clean_w100"
  "31|07_b_online_taskonly_clean_w125|efe_all|1|0|clean_w125"
  "32|08_rule_reference|rule_all|0|0|none"
)

echo "============================================================"
echo "EFE connected-B large v3：隔离续跑"
echo "原实验总组数: 32"
echo "已完成: 1-29组"
echo "本脚本: 仅检查并补跑30-32组，共3组"
echo "每组: $STEPS steps"
echo "预计剩余: 约21分钟（按第29组约7分钟估计）"
echo "当前仓库分支: 不切换、不覆盖"
echo "结果目录: $OUTPUT_ROOT"
echo "============================================================"

run_start=$SECONDS
completed_this_run=0
for spec in "${GROUPS[@]}"; do
  IFS='|' read -r group label authority learning learn_maintain clean_variant <<< "$spec"
  result_root="$OUTPUT_ROOT/$label/seed_3"

  if find "$result_root" -name summary.json -print -quit 2>/dev/null | grep -q .; then
    echo
    echo "########## 实验组 $group/32：已有完整summary，跳过 ##########"
    continue
  fi

  echo
  echo "########## 实验组 $group/32 ##########"
  echo "条件=$label | seed=3 | steps=$STEPS"
  echo "选择器=$authority | B更新=$learning | maintain学习=$learn_maintain"
  echo "clean evidence=$clean_variant"
  echo "包含本组在内剩余: $((33 - group))组，约$(((33 - group) * 7))分钟"

  group_start=$SECONDS
  log_path="$OUTPUT_ROOT/logs/group_${group}_of_32__${label}__seed_3__isolated_resume.log"
  (
    cd "$RUNTIME_ROOT"
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
        --schedule-seed 3 \
        --output-root "$result_root" \
        --no-clean \
        --replay-scene-interval 20 \
        --metric-log-interval 10
  ) 2>&1 | tee "$log_path"

  completed_this_run=$((completed_this_run + 1))
  group_seconds=$((SECONDS - group_start))
  echo "实验组 $group/32 完成，用时 $((group_seconds / 60))分$((group_seconds % 60))秒"
done

echo
echo "正在重新汇总完整32组结果……"
(
  cd "$RUNTIME_ROOT"
  "$PYTHON_BIN" scripts/summarize_efe_goal_policy_v1.py "$OUTPUT_ROOT"
)

summary_count="$(find "$OUTPUT_ROOT" -name summary.json | wc -l)"
elapsed=$((SECONDS - run_start))
echo "============================================================"
echo "正式实验summary数量: $summary_count（正常目标为32；历史重复run可能使数量更大）"
echo "本次实际补跑: $completed_this_run组"
echo "本次用时: $((elapsed / 60))分$((elapsed % 60))秒"
echo "报告: $OUTPUT_ROOT/goal_policy_report.md"
echo "逐组结果: $OUTPUT_ROOT/goal_policy_runs.csv"
echo "日志: $OUTPUT_ROOT/logs/*__isolated_resume.log"
echo "============================================================"
