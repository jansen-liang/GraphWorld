#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_PATH="${1:-$REPO_ROOT/dist/graphworld_runtime_efe_source_${STAMP}.tar.gz}"
BUNDLE_TMP="$(mktemp -d /tmp/graphworld_runtime_efe.XXXXXX)"
BUNDLE_NAME="GraphWorld_runtime_efe"
BUNDLE_ROOT="$BUNDLE_TMP/$BUNDLE_NAME"

cleanup() {
  if [[ -n "${BUNDLE_TMP:-}" && "$BUNDLE_TMP" == /tmp/graphworld_runtime_efe.* ]]; then
    rm -rf -- "$BUNDLE_TMP"
  fi
}
trap cleanup EXIT

mkdir -p "$BUNDLE_ROOT" "$(dirname "$OUTPUT_PATH")"

copy_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "ERROR: required package file is missing: $path" >&2
    exit 2
  fi
  mkdir -p "$BUNDLE_ROOT/$(dirname "$path")"
  cp -- "$path" "$BUNDLE_ROOT/$path"
}

copy_tree_files() {
  local source="$1"
  while IFS= read -r -d '' path; do
    mkdir -p "$BUNDLE_ROOT/$(dirname "$path")"
    cp -- "$path" "$BUNDLE_ROOT/$path"
  done < <(
    find "$source" -type f \
      ! -path '*/__pycache__/*' \
      ! -path '*/.pytest_cache/*' \
      ! -path '*/.hypothesis/*' \
      ! -name '*.pyc' \
      ! -name '*.pyo' \
      ! -name '*.bak' \
      ! -name '.DS_Store' \
      -print0
  )
}

# Root-level runtime metadata and entry points.
for path in \
  README.md \
  EFE_README.md \
  README_PACKAGE_CN.md \
  PACKAGE_RUNTIME_README.md \
  requirements-runtime.txt \
  pytest.ini \
  testbench_yuling.py \
  backend/__init__.py \
  backend/core.py \
  backend/deploy.py \
  backend/run_experiment.py \
  backend/run_experiment.sh; do
  copy_file "$path"
done

# All maintained experiment/method entry points.  Deliberately exclude .bak.
while IFS= read -r -d '' path; do
  copy_file "$path"
done < <(find backend -maxdepth 1 -type f -name 'run_efe*.py' -print0 | sort -z)

# Runtime implementation, all agent variants, engine, evaluator, assets and tests.
copy_tree_files backend/core
copy_tree_files backend/runtime
copy_tree_files backend/tools
copy_tree_files backend/generation

# The working repository contains historical hard-coded provider credentials.
# Preserve the provider configurations but make the distributable copy read a
# user-supplied environment variable.  Never mutate the working source here.
perl -0pi -e \
  's/"api_key": "(?!EMPTY)[^"]+"/"api_key": "", "api_key_env": "GRAPHWORLD_API_KEY"/g; s/api_key="[^"]+"/api_key="<redacted>"/g' \
  "$BUNDLE_ROOT/backend/tools/agent.py"

# Static scene definitions are executable assets required by run_experiment.py.
# No generated experiment/replay/tensorboard/checkpoint data is copied.
copy_tree_files backend/data/sg_output/simple_graph

# Experiment runners, analyzers, resumable runners and supplementary checks.
# Web/API service helpers and the older result-bundling script are not included.
while IFS= read -r -d '' path; do
  case "$path" in
    scripts/web_*|scripts/package_efe_review_bundle.sh) continue ;;
  esac
  copy_file "$path"
done < <(find scripts -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' \) -print0 | sort -z)

# Design documents from the main project and successive EFE stages.
for path in \
  docs/README.md \
  docs/GraphWorld.md \
  docs/progress_update_2026-05-30.md \
  docs/human_blocking_recovery_definition.md \
  docs/diagnostic_metrics_800_v2_summary.md \
  docs/goal_review_version_results.md \
  docs/goal_review_version_results.csv \
  docs/goal_review_single_efe_comparison.md \
  docs/goal_review_single_efe_comparison.csv; do
  copy_file "$path"
done
while IFS= read -r -d '' path; do
  copy_file "$path"
done < <(find docs -maxdepth 1 -type f -name 'efe*.md' -print0 | sort -z)

{
  echo "created_at=$(date -Is)"
  echo "source_repository=$REPO_ROOT"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unavailable)"
  echo "git_branch=$(git branch --show-current 2>/dev/null || echo unavailable)"
  echo "bundle_scope=runtime_source_methods_tests_design_docs_static_scenes"
  echo "excluded=frontend,backend_app,experiment_data,replays,tensorboard,checkpoints,caches,paper,git"
} > "$BUNDLE_ROOT/VERSION.txt"

# Refuse to create a distributable if a token/private key pattern survived.
if rg -q --hidden \
  'sk-[A-Za-z0-9_-]{16,}|[a-fA-F0-9]{32}\.[A-Za-z0-9_-]{8,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
  "$BUNDLE_ROOT"; then
  echo "ERROR: possible credential material remains in the staged bundle" >&2
  exit 3
fi

(
  cd "$BUNDLE_ROOT"
  find . -type f ! -name MANIFEST.sha256 -print0 \
    | sort -z \
    | xargs -0 sha256sum > MANIFEST.sha256
  find . -type f -printf '%P\n' | sort > FILE_LIST.txt
)

tar -C "$BUNDLE_TMP" -czf "$OUTPUT_PATH" "$BUNDLE_NAME"

echo "GraphWorld runtime/EFE source bundle created: $OUTPUT_PATH"
echo "Archive size: $(du -h "$OUTPUT_PATH" | awk '{print $1}')"
echo "Files: $(find "$BUNDLE_ROOT" -type f | wc -l)"
