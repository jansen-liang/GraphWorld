# Object and Environment Design Notes

## 目标

外部数据中的对象名称不能直接一一转换成 `ObjectTemplate`。模板粒度应由 GraphWorld 的运行时语义、任务引用和状态转移决定，而不是由 3D 数据集的 asset label 决定。

对象建模分为四层：

```text
外部 asset label
  -> ontology canonical semantic_type
  -> functional capabilities / placement constraints
  -> runtime state transitions and task effects
```

只有最后一层确实不同的对象，才需要独立模板。仅仅外观或名称不同的对象，应使用同一功能模板加 variant/placement metadata。

## 模板粒度规则

1. 如果两个对象拥有相同的状态、动作和任务效果，只保留一个模板，用 alias 或 variant 区分名称。
2. 如果对象的 parent 规则不同但运行时能力相同，优先使用同一模板，差异放入 `allowed_parents`/placement profile。
3. 如果对象需要新的状态转移、动作或任务效果，才建立独立模板，并同时补 validator、transition、任务和可解性测试。
4. `functional_class` 描述对象能做什么；`semantic_type` 描述对象是什么。不能用大量 semantic type 替代能力模型。

建议的功能类别包括：

```text
pickupable, movable, cleanable, wettable, foldable,
receptacle, heat_source, cookable, light_source,
openable, switchable, consumable, perishable,
cutting_tool, cleaning_tool, media_device, alarm_device
```

## Window / 环境系统

### 最小系统分层

这些系统不需要一次性全部实现。它们先作为架构边界登记，只有对象真正依赖的系统实现后，对象才从 deferred 进入正式模板。

```text
基础世界
├── TimeSystem       step / time_min / day
└── SpaceSystem      room / containment / reachability

派生环境
├── SeasonSystem     由时间推导季节
└── DayNightSystem   由时间推导昼夜阶段

环境效果
├── WeatherSystem    室外天气 profile
├── ClimateSystem    温度、湿度、通风交换
└── AirQualitySystem 空气质量、污染和净化

领域效果
└── Domain systems   照明、烹饪、工具、消耗、媒体、闹钟、支付
```

这四层是架构层，不是要求实现四个巨大类。当前只把时间、空间作为基础能力；昼夜是时间的部分派生能力。季节、天气、温度、湿度和空气质量暂时是 planned，不阻塞房间图、对象先验和任务生成器。

代码中的 `SYSTEM_REGISTRY` 记录每个系统的层级、状态、依赖和 world state keys。它是架构登记表，不是要求现在创建十几个空系统类。

Window 暂不进入正式模板。仅有 `open/close` 时，当前 GraphWorld 只会改变 `is_open`，不会改变温度、湿度、可见性或任务结果，属于无因果效果的交互。

后续如果引入环境维护玩法，应独立设计 `EnvironmentSystem`：

```text
weather/outside profile
  -> outside temperature / humidity / air quality
room environment state
  -> temperature / humidity / ventilation level
window, air conditioner, heater, humidifier
  -> environment transition
NPC comfort / equipment conditions / maintenance tasks
```

至少需要定义：环境状态、时间推进、窗户通风率、空调目标温度、室外天气 profile、设备受温湿度影响的规则，以及对应的任务和可解性验证。Window、blinds 和 weather 不应分别独立实现后再临时拼接。

## 当前对象建议

| 外部对象 | 当前建议 | 原因 |
|---|---|---|
| `stoveburner` | 暂不独立模板；作为 `stove` 的 burner/component 候选 | 真正需要 heat source、锅具和烹饪状态；当前没有加热/烹饪闭环 |
| `pillow` | 可建立 movable + pickupable + dirty/wet 状态模板 | 不需要新动作；后续可服务于整理、清洁和床铺任务 |
| `painting` | fixed + cleanable，placement=wall | 装饰物，当前只需要可脏和刷洗；不应有 pickup |
| `vase` | movable + pickupable + receptacle + cleanable | 花瓶承载花；容量属于 placement/containment 规则，不应硬编码成普通 fill_level |
| `creditcard` | deferred | 需要 card reader/payment 设备和交互效果 |
| `mirror` | fixed + cleanable，placement=wall | 当前开关/移动没有意义，清洁是唯一合理维护效果 |
| `statue` | fixed + cleanable，placement=room/surface | 装饰物；外部可拾取不代表 GraphWorld 应允许移动 |
| `keychain` | deferred 或 generic clutter | 没有当前任务或状态效果 |
| `soapbottle` | deferred | 更接近 soap dispenser/consumable container，需要使用和消耗规则 |
| `toiletpaper` | deferred | 需要使用/消耗动作，当前 9 个动作没有对应语义 |
| `desklamp` / `floorlamp` | 一个 light-source family，是否独立模板取决于 movable/placement 差异 | 当前只有 `is_on`，照明对世界没有影响；灯光效果需要 visibility/comfort 模型 |
| `blinds` | 不等同于 window；deferred | 是窗户遮挡/透光控制器，可能影响可见性和环境交换 |
| `handtowelholder` / `towelholder` | 统一为 holder family，按 allowed item 区分 | 两者的核心能力都是承载毛巾，除非任务需要精确区分 |
| `cellphone` | movable + pickupable，暂不增加使用效果 | 没有通话/消息系统时只能作为可移动物体 |
| `dishsponge` | cleaning_tool，暂不正式加入 | 需要 sponge wetness 和对目标清洁效果的工具依赖 |
| `candle` | deferred | 需要点火源、持续燃烧、耗尽和光照效果 |
| `cd` | deferred | 需要 CD player、播放状态、声音或 NPC 情绪效果 |
| `spraybottle` | deferred | 需要 fill/dispense/spray 语义，当前动作空间不支持 |
| `alarmclock` | deferred | 需要周期计时、响铃和 NPC 起床事件联动 |
| `bread` / `egg` | food/ingredient family，暂不新增烹饪模板 | 需要 cookable、temperature、edible 和 heat source 闭环 |
| `butterknife` / `knife` | cutting-tool family，暂不拆多个动作模板 | 只有当任务区分切黄油、切食材时才拆 subtype/effect |
| `fork` / `spoon` | utensil family，暂不增加新动作 | 当前只能作为 pickupable clutter，缺少 eating/use 效果 |
| `pan` / `pot` | cookware family，暂不正式加入 | 需要 stoveburner、温度、烹饪和容量关系 |
| `pepper shaker` | deferred | 需要 seasoning/use 效果 |
| `plunger` | cleaning_tool family，暂不加入 | 需要 unclogged/blocked 状态和专用效果 |

## 当前实施顺序

1. 先合并不依赖新玩法系统的对象：pillow、painting、vase、mirror，以及必要的 holder family。
2. 继续保留 window、blinds、stoveburner、灯光、烹饪、消耗品和媒体对象为 deferred。
3. 设计 EnvironmentSystem、CookingSystem、ToolUse/ConsumptionSystem 后，再批量释放对应对象模板。
4. 每个新系统必须同时提供状态、动作约束、transition、NPC 影响、任务和可解性测试。
