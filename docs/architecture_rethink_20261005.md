# GraphWorld 架构重思

## 结论

GraphWorld 最核心的产品不是 Web 页面、数据库或 Three.js，而是一个可以被多个客户端观察和修改的 **世界运行时**。

```text
SceneDefinition（不可变场景）
        |
        v
WorldSession（一个运行中的世界）
        |
  Command -> validate -> transaction -> Event/Delta
        |
        +--> Web
        +--> Unity
        +--> Isaac
        +--> agent / evaluator / replay
```

当前复杂的根因是同一个概念被实现了多次：

- 场景编辑器有一套 `scene-simulation` 会话；运行监控又通过 `RunService + GraphWorldAdapter` 重放另一套会话。
- `backend/core`、`backend/runtime`、`backend/app` 都在不同程度上参与动作、状态和场景转换。
- 前端既承担编辑器本地状态，又承担仿真输入、物理预测和运行状态同步。
- HTTP schema、运行时字典、前端 TypeScript 类型之间没有一个自动生成的协议源。

因此目标不是再增加一层抽象，而是只保留一个权威世界和一条命令链路。

## 最小正确分层

```text
backend/
  domain/       # 纯领域模型：Node、Edge、State、Capability、Command、Event
  world/        # 可变 WorldSession、事务、规则、时间推进
  content/      # 场景、对象、任务模板和生成器
  application/  # 用例：创建会话、发送命令、读取观察、回放、评测
  transport/    # FastAPI/HTTP/WebSocket、认证、序列化
  persistence/  # PostgreSQL、对象存储、事件/快照持久化
```

这不是要求立刻重命名目录。当前目录可以先映射为：

| 目标职责 | 当前代码 | 规则 |
|---|---|---|
| domain | `backend/core` | 只定义类型和声明，不读 DB，不处理 HTTP |
| world | `backend/runtime` | 唯一允许改变运行中世界的地方 |
| content | `backend/generation`、场景 JSON | 生成和导入，不参与在线动作执行 |
| application | `backend/app/services` | 编排用例，不复制规则 |
| transport | `backend/app/api`、schemas | 把协议转成 Command，把结果转回 DTO |
| persistence | `backend/app/db`、repositories | 只保存场景、会话、快照、事件、运行记录 |
| client | `frontend/web`、Unity、Isaac | 输入、渲染、碰撞和设备适配，不拥有语义真值 |

初期应继续使用一个 Python 进程和一个数据库。GraphWorld 的复杂度是领域复杂度，不是服务数量不足；现在拆微服务只会增加网络协议、部署和一致性问题。

## 三个必须稳定的对象

### 1. SceneDefinition

场景定义是发布后的不可变版本，包含节点、结构边、初始状态、资源引用和任务元数据。编辑器保存的是新版本，不直接修改运行中的世界。

```text
SceneDefinition
  scene_id
  version
  nodes[]
  edges[]
  initial_world_state
  asset_refs
```

### 2. WorldSession

一次编辑预览、一次人类运行、一次 agent 评测或一次回放都只是一个 `WorldSession`。它持有：

```text
WorldSession
  session_id
  scene_version_id
  world_state
  revision
  event_log
  actor_ids
```

编辑器预览可以创建临时 session，正式实验可以持久化 session；两者不应各自实现一套动作引擎。

### 3. Command / Result

所有输入先变成规范命令。鼠标点击、键盘移动、agent JSON、Unity 控制器输入都只是不同的输入适配器。

```json
{
  "command_id": "cmd_123",
  "session_id": "sess_123",
  "actor_id": "robot_01",
  "type": "interact",
  "target_id": "door_entrance",
  "payload": {"action": "open"},
  "client_revision": 41
}
```

运行时只做一件事：校验命令，在事务中修改 `WorldSession`，产生统一结果。

```json
{
  "accepted": true,
  "revision": 42,
  "events": [{"type": "state_changed", "node_id": "door_entrance", "key": "is_open", "value": true}],
  "delta": {"nodes": [], "edges": [], "world_state": {}},
  "snapshot_uri": null
}
```

## 前端和后端如何匹配

前端只需要三类接口：

```text
GET  /scenes/{id}/versions/{version}/definition   # 编辑器/加载场景
POST /sessions                                     # 从场景创建 WorldSession
POST /sessions/{id}/commands                       # 发送规范命令
GET  /sessions/{id}/snapshot                       # 首次加载或纠错
WS   /sessions/{id}/events                         # 多端实时 delta，可选
```

编辑器的拖拽、旋转、删除属于 `scene_edit` 命令；运行时的开门、拿取、移动属于 `interact`、`move` 等命令。它们可以共享事务和 World，但权限和是否产生新的 `SceneDefinition` 版本不同。

前端状态分成两类：

- `sceneDefinition`：编辑器草稿和已发布场景；由场景 API 读写。
- `worldProjection`：当前 session 的快照和 delta；只能由 session API/WS 更新。

Three.js、Rapier 和输入设备只更新视觉预测或生成命令。语义状态、关系、动作是否合法，以后端返回的 `revision` 和 delta 为准。收到 revision 不连续的 delta 时，前端重新请求 snapshot。

## 不同语言如何一起工作

语言不需要共享类，也不应该通过直接导入彼此代码来协作。它们共享一个版本化的 **协议**：

```text
Python domain/runtime
        | OpenAPI + JSON Schema
        v
TypeScript web client / C# Unity client / Python Isaac client
```

具体约束：

1. Python 的 Pydantic schema 是协议源；从 OpenAPI 生成 TypeScript 类型和 C# DTO。
2. API 只传 JSON，ID、枚举、坐标系、单位和 revision 写入协议，不依赖 Python pickle 或内部 dict。
3. HTTP 用于查询、创建 session 和发送命令；WebSocket 用于 delta、事件和长时间运行通知。
4. Unity/Isaac 只实现 `ClientAdapter`：输入映射、渲染、碰撞、动画和设备生命周期。它们不能复制 `ActionExecutor`、规则或状态机。
5. 外部物理引擎可以返回 `contact`、`transform` 等事实，后端决定这些事实是否导致语义边变化。

如果暂时不生成 SDK，也必须先固定 JSON schema，并用契约测试验证 Web、Unity 和 Isaac 的请求/响应。

## 数据、生成和实验的位置

```text
外部数据/模板
  -> content generator
  -> SceneDefinition
  -> WorldSession
  -> command/event log
  -> evaluator/replay
```

生成器只负责产出合法的场景定义：房间图、对象放置、资源引用和任务初始条件。它不应该调用在线 runtime。

评测读取 session 的事件和快照，计算指标；指标计算不能反过来修改 WorldSession。回放使用同一组命令或事件重建 session，不再通过 `GraphWorldAdapter` 复制一套动作流程。

## 从当前代码迁移

1. 先把 `backend/runtime` 的 `World + ActionExecutor + Orchestrator` 定为唯一权威执行链，给它加稳定的 `CommandResult`、`revision` 和 `WorldDelta`。
2. 将 `SimulationService` 和 `RunService` 改成 application 用例：二者都创建/取得 `WorldSession`，再调用同一个 `dispatch(command)`。
3. 删除 `GraphWorldAdapter` 中的规则性逻辑，只保留观察投影和兼容转换；最终由 `SessionProjection` 取代。
4. 把 `/scene-simulation/*` 和 `/runs/*` 收敛到 `/sessions/*`。旧路由可以暂时作为薄兼容层，但不能再拥有独立状态。
5. 从 FastAPI OpenAPI 生成前端 `api-types.ts`；前端 `api/runs.ts`、`api/scenes.ts` 只负责调用协议，不拼装运行时规则。
6. 将编辑器本地物理和运行时物理都改成 `Fact -> Command`：例如碰撞检测产生接触事实，不能直接改节点关系。
7. 最后再整理目录名称。目录移动不是架构修复，先消除第二个世界和第二条动作链路。

## 判断架构是否变简单

以后每增加一个功能，只问四个问题：

1. 它是场景定义、运行时状态、命令、事件还是投影？
2. 它是否只能在一个地方修改世界？
3. Web、Unity、Isaac 是否只需改变输入和展示，而不复制规则？
4. 是否能用同一个 session 做编辑预览、正式运行、agent 评测和回放？

如果答案为是，架构就沿着正确方向发展；如果需要再加一个 `*Service`、另一份状态字典或另一套 action executor，说明边界又被打破了。
