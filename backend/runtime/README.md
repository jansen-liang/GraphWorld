# Runtime 运行时

`backend/core` 定义领域词汇和静态声明，包括节点、边、状态类型、能力、动作描述、前置条件、效果和 schema。静态对象、NPC 和任务模板位于 `backend/generation/assets`；过程配置位于 runtime。`core` 不直接修改世界状态。

`backend/runtime` 负责可变的世界实例，并执行 `core` 中声明的规则。一次交互的处理链路如下：

```text
适配器输入 -> 规范化 Action -> runtime ActionExecutor
           -> 检查 Requirement -> 开启事务 -> 应用 Effect -> 返回快照/响应
```

Web、Isaac 和 Unity 三套客户端共享同一组后端接口。每个客户端只负责自己的输入方式和界面展示，不拥有权威世界状态。

## 目录职责

- `backend/core`：静态领域声明，包括 `Node`、`Edge`、状态定义、能力、动作定义、前置条件、效果和 schema。
- `backend/generation/assets`：对象、房间、NPC、任务和组合物体模板及其静态资产目录。
- `backend/runtime`：运行实例级的可变 `World`、事务、动作前置条件检查、过程和时间推进、NPC 日程、资源系统以及动作执行。
- `backend/adapter`：输入、物理/放置、渲染和动画适配器。适配器可以向 runtime 提供射线命中、碰撞等事实，但不拥有语义状态，也不定义设备规则。
- `frontend/web`、`frontend/isaac`、`frontend/unity`：展示和设备输入适配层，通过同一组后端 API 与 GraphWorld 通信。

## 世界和标识

编辑器场景使用稳定的 `editor_id`。运行时创建 `World` 时，会根据 `run_id:editor_id` 生成 `runtime_id`。

包含关系、复合物体的部件关系、控制关系和持有关系都只由边表示。节点本身不再维护第二套父子关系副本，运行时索引只能从规范边重新构建。

## 状态、能力和动作

物体通过能力声明自己支持的状态和交互条件；状态定义声明值类型、适用对象和合法范围；动作通过 `Requirement` 检查前置条件，通过 `Effect` 修改状态或边。

```text
Capability -> 可拥有的状态/能力
State      -> 当前世界值
Action     -> Requirement + Effect
World      -> Transaction 中执行 Action
```

事务失败时会回滚所有状态、边和事件变化，避免动作执行到一半留下不一致的世界状态。
