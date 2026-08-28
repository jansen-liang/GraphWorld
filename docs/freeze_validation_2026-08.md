# GraphWorld 版本冻结验收记录（2026-08）

## 1. 验收环境

- Python 环境：`/home/swzz/anaconda3/gra`
- Fast Downward：`/home/swzz/data/HSG-RTP/third_party/DELTA/downward/fast-downward.py`
- Fast Downward build：`release`
- 工作区：`/home/swzz/data/GraphWorld`

## 2. Laundry PDDL 与 runtime 回放

执行：

```bash
PATH=/home/swzz/anaconda3/gra/bin:$PATH \
/home/swzz/anaconda3/gra/bin/python backend/tools/try_laundry_fastdownward.py \
  --fast-downward /home/swzz/data/HSG-RTP/third_party/DELTA/downward/fast-downward.py \
  --fd-build release
```

结果：

- Fast Downward：`ok=true`
- PDDL 计划长度：15
- PDDL 计划代价：15
- runtime trace：13 个 runtime 原子动作全部 `ok=true`
- 状态闭环：衣物 `is_dirty=true -> false`、`is_wet=false -> true -> false`、`folded=false -> true`
- 关系闭环：`laundry_room -> washing_machine_01 -> drying_rack_01 -> wardrobe_01`
- 回放报告：`backend/tmp/laundry_fd/report.json`

说明：PDDL 计划把同房间移动显式化，而 mini scene 的 runtime 不需要重复移动到当前房间，因此回放使用了等价的同房间动作序列。该工具目前是 laundry 子任务验证器，不代表完整 home 场景的通用 PDDL 编译器。

## 3. Home NPC-only 800 步

执行：

```bash
/home/swzz/anaconda3/gra/bin/python backend/run_experiment.py \
  --scene simple_home_1f --steps 800 --only no_robot --robots 0 --humans 1 \
  --no-clean --replay-scene-interval 100 --metric-log-interval 100
```

结果：

- run id：`20260827T095754Z_1a8d15d9`
- replay：800 行
- `final_score=0.6506`
- `state_score=0.5774`
- `spatial_score=0.6187`
- `human_event_score=0.871`
- `human_blocking_total=22`
- `human_blocking_recovered=0`
- TensorBoard、replay、metrics CSV 均成功写出

输出目录：

`backend/data/experiments/simple_home_1f/steps_800__robots_0__humans_1__model_npc_only_baseline/20260827T103643Z_f16d5e64/no_robot/`

本次重新运行（启用默认自然变脏后）：`final_score=0.6792`、`state_score=0.5882`、`spatial_score=0.7167`、`human_event_score=0.8182`，`replay_count=800`，`human_blocking_total=15`。

## 4. 原始 Home 图的 PDDL 子任务验证

输入文件确实是仓库原有的：

`backend/data/sg_output/simple_graph/simple_home_1f.json`

验证器不修改源文件，只在内存中：

- 添加临时 `robot_01`；
- 选取原图中的 `clothes_bedroom_1`，设置为脏、未湿、未折叠；
- 使用原图中的 `washer_bathroom`、`drying_rack_balcony`、`wardrobe_bedroom`；
- 投影出与洗衣任务相关的真实节点，避免无关对象造成搜索空间膨胀。

Fast Downward 结果：`ok=true`，计划长度 17，计划代价 17。计划包含：从衣柜取衣、洗衣机开门/放入/关门/启动、取出、移至阳台晾晒、干燥、折叠并放回衣柜。报告位置仍为 `backend/tmp/laundry_fd/report.json`（该文件记录最近一次运行）。

## 5. 当前冻结边界

本版本可冻结的内容包括：资源补充/消耗、配方生产、设备运行倒计时、洗衣-晾晒状态链、水槽二值供水语义，以及 NPC-only 基线运行链路。

尚未宣称完成：完整 home 场景所有任务的通用 PDDL 自动编译与求解、所有设备/配方的系统性可解性覆盖、复杂组合物体的全量回放测试。这些应作为下一版本的独立验收项。当前 home PDDL 结果是基于真实 home 图的洗衣任务相关子图验证。

## 6. 过程层回归补充

可重复验收命令：

```bash
/home/swzz/anaconda3/gra/bin/python backend/tools/validate_timed_systems.py
```

输出：`timed system validation: PASS`。

- 打印机：`count=1, amount=1` 启动后各扣 1，两个 tick 后仅生成一个 `receipt`，过程注册表清空。
- 咖啡机：水、咖啡豆和杯子齐备时启动，两个 tick 后消耗咖啡豆并生成 `coffee`，过程注册表清空。
- 烘干机：湿衣物放入并关闭设备后启动，四个 tick 后 `is_wet=false` 且设备 `is_running=false`。
- 晾衣架：晴天 6、阴天 8、雨天 12 tick，均慢于烘干机的 4 tick。
- 温度：冷物体在一 tick 后向 `room` 离散状态回归。
- 空调控制：`remote --controls--> air_conditioner`；第一次按下使空调开启并持续维持所在房间为 `cold`，再次按下关闭并恢复到世界基准温度。
