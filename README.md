# GraphWorld

GraphWorld 是一个面向楼宇级具身智能研究的平台，统一提供可交互场景资产、开放任务评价和多端运行适配。

## 项目摘要

### 任务一：楼宇级可交互物体数据集

构建包含楼层、房间、复合物体、agent、空间关系、状态和时间演化规则的楼宇级场景资产。物体由 `Node + structure Edge + Link/Joint` 描述，普通物体和带门、抽屉、按钮的复合物体使用同一套抽象。

### 任务二：开放任务评价体系

在同一套世界图和规则上评价智能体的观察、导航、状态推理、交互操作、多步任务和长期维护能力。现有评测运行保留 `state_score`、`spatial_score`、`human_event_score` 以及 replay/metrics 接口。

### 任务三：多端集成应用

通过 Web/Three.js、Unity、Isaac 三个运行端展示和操作同一套世界。运行端负责输入、可视化、碰撞、重力和动画；后端负责语义图、状态、关系、动作、规则、过程和快照。

## 架构

```text
backend/
  core/       # Node、Edge、State、Capability、Action、Rule、Process、Transform
  generation/ # 楼宇/资产/任务生成与领域知识
  runtime/    # 一个长期持有的可变 World、事务、动作、规则和时间推进
  adapter/    # 输入、物理/放置、动画和渲染协议适配

frontend/
  web/        # Three.js 客户端
  unity/      # Unity 客户端边界
  isaac/      # Isaac 客户端边界
```

`backend/generation/assets` 是 Generation 的静态对象/NPC/任务模板实现包，避免 Runtime 和 Core 各自维护一份资产定义。

Core 不依赖 HTTP、数据库或具体渲染引擎。图中的 Node 和 `structure` Edge 是结构真值；`PartTree` 只是由结构边计算出的无环单父查询视图。运行时只持有一个 `World`：

```text
InputEvent
  -> ActionResolver
  -> World / Action / Rule / Process
  -> atomic commit
  -> WorldDelta + snapshot
  -> Web / Unity / Isaac
```

节点关系全部由 Edge 表达。`in`、`on`、`held_by_*` 是可变空间关系；`controls` 是控制关系；功能接受条件由 capabilities、states 和 rules 组合表达。运行端可以预测物理表现，但语义关系必须以后端 snapshot/delta 为准。

## 本地运行

项目已提供 Node 环境。推荐使用：

```bash
export PATH=/home/swzz/anaconda3/gra/bin:$PATH
```

启动本地 PostgreSQL/Redis：

```bash
./scripts/web_services.sh start
```

启动 API（端口 `8010`）和 Web（端口 `5173`）：

```bash
GRAPHWORLD_API_PORT=8010 ./scripts/web_api.sh start
npm run dev --prefix frontend
```

打开 `http://127.0.0.1:5173`，使用开发种子账号 `admin / admin123` 登录。

## 验证

```bash
/home/swzz/anaconda3/gra/bin/python -m pytest -q
PATH=/home/swzz/anaconda3/gra/bin:$PATH npm run build --prefix frontend
PATH=/home/swzz/anaconda3/gra/bin:$PATH npm run test:physics --prefix frontend
PATH=/home/swzz/anaconda3/gra/bin:$PATH node frontend/e2e/home-behavior.cjs
```

架构协议见 [`docs/graphworld_architecture_v2.md`](docs/graphworld_architecture_v2.md)，未决实现选择见 [`docs/pending_decisions.md`](docs/pending_decisions.md)。
