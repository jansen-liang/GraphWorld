# GraphWorld 运行源码包目录说明

这是一份只包含运行源码、算法实现、测试脚本、实验脚本和设计文档的精简包。
包内不包含前端、Web API、实验结果、日志、回放、TensorBoard、模型权重或密钥。

## 推荐阅读顺序

1. `README_PACKAGE_CN.md`：当前文件，快速了解目录结构；
2. `EFE_README.md`：EFE 工程整体介绍、不同评分模式和实验入口；
3. `docs/efe_complete_design_current.md`：当前 EFE 的 A/B/C 矩阵、评分和更新公式；
4. `backend/run_experiment.py`：统一实验入口；
5. `backend/runtime/agent/efe_agent/`：当前 EFE 主线实现。

## 根目录

| 文件 | 用途 |
|---|---|
| `README.md` | GraphWorld 项目、场景、引擎、评分和各 Agent 方法的总体说明 |
| `EFE_README.md` | EFE 专项工程说明和实验指南 |
| `README_PACKAGE_CN.md` | 精简包的中文目录导航 |
| `PACKAGE_RUNTIME_README.md` | 安装、最小运行和测试命令 |
| `requirements-runtime.txt` | 精简后的后端运行与测试依赖 |
| `pytest.ini` | Pytest 配置 |
| `testbench_yuling.py` | Yuling Agent 的补充测试入口 |

## backend/

后端仿真、Agent 和实验运行代码。这个精简包不包含 `backend/app` Web 服务代码。

### 主要入口

| 文件 | 用途 |
|---|---|
| `backend/run_experiment.py` | 统一实验入口；支持场景、步数、Agent 模式、EFE 模式、seed 和输出目录 |
| `backend/run_experiment.sh` | 基础 Shell 运行入口 |
| `backend/run_efe_*.py` | 不同阶段或消融版本的 EFE 实验入口 |
| `backend/core.py` | 早期/兼容性的核心入口 |
| `backend/deploy.py` | 部署相关入口 |

### backend/core/

GraphWorld 的基础场景图和规则层：

- `nodes.py`、`edges.py`、`scenegraph.py`：节点、边和场景图数据结构；
- `states.py`、`predicates.py`：对象状态和条件判断；
- `actions.py`、`action_schemas.py`、`effects.py`：动作定义、合法性与状态效果；
- `timed_transitions.py`：随时间发生的状态变化；
- `domain_rules.py`：领域规则；
- `assets/`：房间、物体、NPC 和任务模板库。

### backend/runtime/

仿真运行时，负责把场景、动作、Agent 和评分连接起来。

| 子目录 | 用途 |
|---|---|
| `runtime/engine/` | 动作校验、执行和世界状态推进 |
| `runtime/world/` | 世界状态与场景运行逻辑 |
| `runtime/eval/` | state、spatial、human-event 和综合分数计算 |
| `runtime/schema/` | 运行时数据结构 |
| `runtime/agent/` | 所有 Agent、规划、感知、记忆和决策方法 |

### backend/runtime/agent/

| 文件或目录 | 用途 |
|---|---|
| `decision.py` | 合法动作候选、Goal-aware 动作排序、LLM 动作选择和 EFE explore BFS 导航 |
| `planning.py` | 低层规划辅助 |
| `perception.py` | Agent 观测处理 |
| `memory.py`、`retrospective_memory.py` | 普通记忆和回顾式事件记忆 |
| `reflection.py` | 反思/Goal review 辅助 |
| `yuling/` | Yuling Agent 的 Goal 推理、动作空间、记忆、提示词和部署循环 |
| `efe_agent/` | 当前主线 EFE Agent |
| `efe_*.py` | 不同阶段 EFE 修复、消融或兼容包装器 |
| `test_*.py` | EFE 接线、公式、导航和信用分配测试 |

### backend/runtime/agent/efe_agent/

当前 EFE 主线的核心目录：

| 文件 | 用途 |
|---|---|
| `efe_core.py` | 候选 Goal、统一选择、Goal 生命周期、低层执行接线和在线学习时机 |
| `goal_transition_model.py` | Goal-conditioned 分层 B、固定 A/C、EFE 打分、NLL 和 Dirichlet 更新 |
| `efe_scorer.py` | phase1、generative、goal_conditioned、goal_conditioned_b 四种评分入口 |
| `efe_model.py` | 通用 A/B/C 数值运算和旧共享-B生成模型 |
| `efe_goal_builder.py` | restore、清洁、垃圾、洗衣、医院任务等结构化 Goal workflow |
| `goal_outcome_model.py` | 旧 goal_conditioned 模式的完成率和时长模型 |
| `world_belief.py` | 房间级 Beta belief 和不确定性 |
| `thinker_post.py` | 执行结果到 belief 的后验更新 |
| `test_efe_numerical.py` | A/B/C、EFE 和更新公式的数值回归测试 |

### backend/tools/

通用工具：

- `agent.py`：模型配置和 LLM 调用；分享包中的外部密钥已清除，使用环境变量；
- `analyze_*.py`：结果和即时分数分析；
- `benchmark_all.py`：批量 benchmark 辅助；
- `build_scene_variants.py`：生成场景变体；
- `plot_replay_comparison.py`：回放对比绘图；
- 其余文件用于场景检查和特定 workflow 调试。

### backend/generation/

场景生成相关的保留入口。目前主要生成逻辑也会调用 `backend/core/assets/`。

### backend/data/sg_output/simple_graph/

这里只保留20个静态场景 JSON，包括 Home、Hospital、Office、Factory、
Supermarket 及其场景变体。它们是 `run_experiment.py` 必需的只读运行输入，
不是实验结果。

包中没有以下数据目录：

```text
backend/data/experiments
backend/data/tensorboard
backend/data/replay_logs
```

## scripts/

实验运行、恢复、分析和汇总脚本：

- `run_main*.sh`：传统方法或主 benchmark 批量运行；
- `run_efe_*.sh`：各阶段 EFE 实验和消融；
- `run_mainline_efe_*.sh`：当前主线 EFE、Frozen、single_round 对比；
- `resume_*.sh`：中断实验恢复；
- `summarize_*.py`：汇总逐组结果、聚合指标和报告；
- `analyze_*.py`：B 学习、反事实选择和参数敏感性分析；
- `check_*.py`：B 更新、接线和 smoke 结果检查；
- `package_graphworld_runtime_efe.sh`：重新生成当前精简源码包。

Web 服务启动和前端相关脚本没有收入本包。

## docs/

GraphWorld 和 EFE 各阶段设计文档：

| 文档 | 用途 |
|---|---|
| `GraphWorld.md` | GraphWorld 场景图和整体设计 |
| `efe_goal_policy_v1.md` | 早期 Goal policy 设计 |
| `efe_goal_authority_experiment.md` | Pipeline、EFE、Rule、Random 的 Goal authority 对照 |
| `efe_goal_conditioned_b_v1.md` | 第一版 Goal-conditioned B |
| `efe_goal_conditioned_b_v2_design.md` | 目标级信用分配和生命周期修复 |
| `efe_complete_design_current.md` | 当前完整 EFE 设计、矩阵与数学公式 |
| `diagnostic_metrics_800_v2_summary.md` | 长程诊断指标说明 |
| `human_blocking_recovery_definition.md` | human blocking 指标定义 |
| `goal_review_version_results.md/.csv` | Goal Review 的 V0、SA-fix 五场景原始记录 |
| `goal_review_single_efe_comparison.md/.csv` | Goal Review、Rule、single_round、EFE Learned 合并对照表 |
| `progress_update_2026-05-30.md` | 项目阶段进展记录 |

## 最常用的运行方式

无 LLM 快速检查：

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

使用本地 vLLM 时，先设置：

```bash
export VLLM_BASE_URL=http://127.0.0.1:8000/v1
export VLLM_MODEL=qwen3.5-9b
```

然后去掉命令中的 `--no-llm`，并设置：

```text
--agent-model vllm-qwen3.5-9b
```
