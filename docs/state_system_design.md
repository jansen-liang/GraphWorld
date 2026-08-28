# GraphWorld 状态系统设计

## 核心原则

每个对象实例都有自己的状态表，但状态字段必须来自全局状态定义，并经过对象语义和能力过滤。全局定义不是每个对象的默认状态表。

```text
StateDefinition
  -> ObjectTemplate.state_schema
  -> instance.states
  -> transition / task / validator
```

## 状态分类

| 类别 | 例子 | 典型适用对象 |
|---|---|---|
| `control` | `is_open`, `is_on`, `is_pressed` | 门、柜子、设备、按钮 |
| `condition` | `is_dirty`, `is_wet`, `is_broken`, `is_blocked`, `folded` | 可清洁、可折叠、可损坏对象 |
| `quantity` | `fill_level`, `is_full`, `cycle_remaining`, `uses_left`, `count`, `amount`, `has_water` | 容器、资源、运行周期设备；水槽/花瓶用二值有水状态 |
| `thermal` | `temperature`, `is_boiling` | 食物、饮料、液体、可加热对象 |
| `material` | `is_cooked`, `is_burnt`, `is_frozen`, `is_rotten` | 食物、易腐物、温度敏感材料 |
| `life` | `vitality`, `is_wilted` | 植物或其他生命对象 |

## 温度和烹饪

`temperature` 是源状态，可以使用数值（例如摄氏度），旧场景中的 `cold/room/warm/hot` 仍作为迁移格式接受。热学系统以后根据数值推导阶段：

```text
temperature
  -> thermal phase
  -> is_boiling (仅液体且达到 boiling_point)
  -> is_cooked / is_burnt (仅 cookable food)
```

因此：

- 锅具可以有温度，但不会自动拥有 `is_cooked`。
- 水或其他液体达到沸点后才有 `is_boiling`。
- 食物只有声明 `cookable` 后，温度变化才可以影响 `is_cooked/is_burnt`。
- 普通椅子、镜子、衣柜不会拥有温度/沸腾/烹饪状态。

## 当前实现边界

当前已实现：状态分类、状态定义、对象状态表过滤和 schema 输出。

当前未实现：真实温度连续变化、沸点配置、加热源传播、烹饪转移。这些属于后续 `Cooking/Climate` domain system，不能在模板层伪造。

代码位置：`backend/core/states.py`，对象模板通过 `ObjectTemplate.state_schema` 暴露过滤后的状态表。
