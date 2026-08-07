# GraphWorld runtime + EFE source bundle

This is a source-only review/runtime bundle. It contains:

- the GraphWorld simulation core, runtime engine and evaluator;
- all maintained agent implementations, including EFE and comparison methods;
- experiment entry points, runners, analyzers and supplementary tests;
- EFE design documents from successive development stages;
- the static JSON scene definitions required by `backend/run_experiment.py`.

It intentionally does **not** contain:

- `frontend/` or Web API/service code;
- experiment results, replay files, metrics, checkpoints or TensorBoard logs;
- generated images, paper assets, caches, Git metadata or existing archives;
- model weights, API keys or environment files.

The only files retained below `backend/data/` are static scene definitions in
`backend/data/sg_output/simple_graph/`. They are runtime inputs, not experiment
outputs. New runs will create their own output directories.

## Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-runtime.txt
```

## Minimal no-LLM smoke run

```bash
python backend/run_experiment.py \
  --scene simple_home_1f \
  --steps 20 \
  --only with_robot \
  --robots 1 \
  --humans 1 \
  --no-llm \
  --agent-mode efe \
  --efe-mode goal_conditioned_b \
  --efe-goal-b-learning on \
  --efe-goal-authority efe_all \
  --efe-candidate-source skill_only \
  --efe-explore-navigation v1 \
  --schedule-mode stochastic \
  --schedule-seed 0 \
  --no-clean
```

## Tests

```bash
pytest -q backend/runtime/agent/efe_agent/test_efe_numerical.py \
  backend/runtime/agent/test_efe_explore_navigation_v1.py \
  backend/runtime/agent/test_efe_b_connected_task_learning_v3.py \
  backend/runtime/agent/test_efe_clean_entry_evidence_v1.py \
  backend/runtime/agent/test_efe_formula_staleness_v1.py
```

Start with `EFE_README.md` and `docs/efe_complete_design_current.md` for the
architecture, matrices and mathematical update rules.

Some historical runner scripts show the original machine's Python path. On a
different machine, invoke them with `PYTHON_BIN=/path/to/python` or use the
active virtual environment's `python` directly. External API credentials are
not included; configure them through environment variables. Local vLLM uses
`VLLM_BASE_URL`, `VLLM_MODEL` and optionally `VLLM_API_KEY`.
