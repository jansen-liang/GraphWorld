#!/usr/bin/env bash
set -euo pipefail

# Entry point after the two overlapping launchers stopped during group 14.
# The underlying script skips every condition/seed with a complete summary,
# so groups 1-13 remain untouched and group 14 is rerun cleanly from step 0.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-$REPO_ROOT/backend/data/experiments/efe_b_connected_large_v3}"

# Host-launched jobs may be invisible inside another PID namespace.  Treat a
# recently growing formal log as authoritative evidence that a launcher lives.
latest_epoch="$(find "$OUTPUT_ROOT/logs" -type f -printf '%T@\n' 2>/dev/null \
  | sort -nr | head -1 | cut -d. -f1)"
now_epoch="$(date +%s)"
if [[ -n "$latest_epoch" ]] && (( now_epoch - latest_epoch < 900 )); then
  echo "检测到正式实验日志在最近15分钟内仍有更新。" >&2
  echo "为避免并行重复，本续跑脚本未启动。" >&2
  exit 1
fi

echo "============================================================"
echo "EFE connected-B large v3：从第14/32组恢复"
echo "第1-13组: 已有完整结果，将自动跳过"
echo "第14组: 从0/400干净重跑"
echo "第15-32组: 依次继续"
echo "并发保护: 已启用文件锁"
echo "============================================================"

RUN_TAG="restart_from14" \
  bash "$SCRIPT_DIR/resume_efe_b_connected_large_v3_from_group9.sh"
