#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_PATH="${1:-$REPO_ROOT/dist/graphworld_efe_review_${STAMP}.tar.gz}"
BUNDLE_TMP="$(mktemp -d /tmp/graphworld_efe_review.XXXXXX)"
BUNDLE_ROOT="$BUNDLE_TMP/graphworld_efe_review"

cleanup() {
  if [[ -n "${BUNDLE_TMP:-}" && "$BUNDLE_TMP" == /tmp/graphworld_efe_review.* ]]; then
    rm -rf -- "$BUNDLE_TMP"
  fi
}
trap cleanup EXIT

mkdir -p "$BUNDLE_ROOT" "$(dirname "$OUTPUT_PATH")"

FILES=(
  EFE_README.md
  backend/run_experiment.py
  backend/run_efe_explore_navigation_v1.py
  backend/run_efe_explore_navigation_v2_budgeted.py
  backend/runtime/agent/efe_agent/__init__.py
  backend/runtime/agent/efe_agent/efe_core.py
  backend/runtime/agent/efe_agent/efe_goal_builder.py
  backend/runtime/agent/efe_agent/efe_model.py
  backend/runtime/agent/efe_agent/efe_scorer.py
  backend/runtime/agent/efe_agent/goal_outcome_model.py
  backend/runtime/agent/efe_agent/goal_transition_model.py
  backend/runtime/agent/efe_agent/thinker_post.py
  backend/runtime/agent/efe_agent/world_belief.py
  backend/runtime/agent/efe_agent/test_efe_numerical.py
  backend/runtime/agent/efe_explore_navigation_v1.py
  backend/runtime/agent/efe_explore_navigation_v2_budgeted.py
  backend/runtime/agent/test_efe_explore_navigation_v1.py
  docs/efe_goal_authority_experiment.md
  docs/efe_goal_policy_v1.md
  docs/efe_goal_conditioned_b_v1.md
  scripts/run_efe_goal_authority_ablation.sh
  scripts/run_efe_explore_navigation_v1_hospital.sh
  scripts/run_efe_explore_navigation_v2_budgeted_hospital.sh
  scripts/run_efe_formula_goal_conditioned_screen_v1.sh
  scripts/run_efe_goal_policy_v1_quick.sh
  scripts/run_efe_goal_b_v1_quick.sh
  scripts/summarize_efe_goal_authority.py
  scripts/summarize_efe_explore_navigation_v1.py
  scripts/summarize_efe_goal_policy_v1.py
)

OPTIONAL_RESULTS=(
  backend/data/experiments/efe_goal_authority_v1/aggregate_report.md
  backend/data/experiments/efe_goal_authority_v1/aggregate_summary.csv
  backend/data/experiments/efe_goal_authority_v3_quickcheck/aggregate_report.md
  backend/data/experiments/efe_goal_authority_v3_quickcheck/aggregate_summary.csv
  backend/data/experiments/efe_explore_navigation_v1_hospital/navigation_runs.csv
  backend/data/experiments/efe_explore_navigation_v1_hospital/navigation_aggregate_summary.csv
  backend/data/experiments/efe_explore_navigation_v1_hospital/navigation_aggregate_summary.json
)

for path in "${FILES[@]}" "${OPTIONAL_RESULTS[@]}"; do
  if [[ -f "$path" ]]; then
    mkdir -p "$BUNDLE_ROOT/$(dirname "$path")"
    cp -- "$path" "$BUNDLE_ROOT/$path"
  fi
done

{
  echo "created_at=$(date -Is)"
  echo "repository=$REPO_ROOT"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unavailable)"
  echo "git_branch=$(git branch --show-current 2>/dev/null || echo unavailable)"
  echo ""
  echo "git_status:"
  git status --short 2>/dev/null || true
} > "$BUNDLE_ROOT/VERSION.txt"

(
  cd "$BUNDLE_ROOT"
  find . -type f ! -name MANIFEST.sha256 -print0 \
    | sort -z \
    | xargs -0 sha256sum > MANIFEST.sha256
)

tar -C "$BUNDLE_TMP" -czf "$OUTPUT_PATH" graphworld_efe_review

echo "EFE review bundle created: $OUTPUT_PATH"
echo "Contents: source, tests, scripts, docs, aggregate results, VERSION.txt"
