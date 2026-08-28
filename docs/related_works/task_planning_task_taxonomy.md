# GraphWorld 任务与世界状态架构

## 自动化场景生成

当前场景暂定为 **Home、Office、Hospital、Supermarket、Factory**。程序化生成器顺序为“选择场景域 → 选择该域房间 → 采样对象 → 放置 NPC → 校验/PDDL”。房间不是跨域共享的自由标签；`room_types_for_scene(domain)` 是唯一允许的房间词汇入口。

| 场景域 | 房间集合（示例） | 主要任务族 |
|---|---|---|
| Home | 玄关、客厅、卧室、浴室、厨房、阳台 | 家务、烹饪、洗衣、收纳、清洁 |
| Office | 开放办公区、会议室、经理办公室、茶水间、卫生间 | 打印、文件流转、会议、补给、清洁 |
| Hospital | 大厅、挂号处、候诊区、门诊、治疗室、药房、员工区 | 医疗物资归还、处方/药品流转、床位清洁 |
| Supermarket | 生鲜区、货架区、收银区、冷藏库、仓库 | 补货、食品搬运、冷链、收银物流、清洁 |
| Factory | 装配线、车间、仓库、控制室、休息区、收货区 | 零件搬运、装配、质检、维护、交接 |

下表列出各域的代表房间；“任务种类”是具备最小对象集合时的能力声明，不保证每个实例都可解。

| 房间 | 必选/常见物体类别 | 可选物体类别 | 可支撑任务种类 |
|---|---|---|---|
| 玄关 `entrance` | 门、灯、鞋架、鞋、座椅 | 箱子、推车、钥匙链 | 进出、收纳、搬运、清洁 |
| 客厅 `living_room` | 沙发、桌子、电视、遥控器、杯子 | 书、植物、箱子、推车 | 休息/社交、遥控设备、饮用、浇水、清洁、收纳 |
| 卧室 `bedroom` | 床、衣柜、衣物、灯 | 植物、箱子、推车、镜子 | 睡眠、洗衣归位、折叠、浇水、收纳、清洁 |
| 浴室 `bathroom` | 水槽、水龙头、马桶、淋浴、毛巾 | 牙刷、牙膏、喷雾瓶、箱子 | 取水/倒水、清洁、个人卫生、资源补充 |
| 厨房 `kitchen` | 水槽、冰箱、微波炉、炉灶、桌子、盘子、碗 | 食品、杯子、咖啡机、箱子、推车 | 烹饪、盛放食品、饮用、食品处置、清洁、补给搬运 |
| 阳台 `balcony` | 洗衣机、晾衣架、衣物 | 烘干机、植物、推车、箱子 | 洗衣、晾晒、浇水、批量搬运 |
| 办公室 `office` | 书桌、椅子、电脑、打印机 | 文具、纸张、箱子、推车 | 打印/补纸、办公收纳、清洁、搬运 |
| 医疗区 `clinic` | 检查床、医疗推车、药柜/冰箱 | 药盒、处方单、轮椅、箱子 | 医疗补给、归还、清洁、冷藏物品搬运 |

生成器必须记录采样 seed、房间实例、对象模板和 NPC 数量；房间库现有约束（邻接、面积、固定设备）继续作为几何生成的第一层校验。

## 场景图校验与 metadata 合约

每个生成图都应运行：

```bash
python -m backend.tools.validate_scene_graph path/to/scene.json
```

命令生成同目录 `scene.metadata.json`，格式 `scene_metadata.v1`，至少包含：`object_type_counts`（每种模板实例数）、`family_counts`、`room_count`、`npc_count`、`task_candidates`、`verified_task_kinds`、`verified_task_count` 和 `planner`。`task_candidates` 只是根据对象能力生成的待验证集合，绝不能当作可玩任务；在 PDDL 未运行前，`planner.status=required` 且 `verified_task_kinds=[]`。

PDDL 适配器必须读取同一图和 metadata，对 `task_candidates` 中的**每个具体任务实例**分别编译 domain/problem 并运行规划器，回写 `verified_task_kinds`、`verified_task_count`、`planner.solved_task_count`、`planner.unsolved_task_kinds`、`planner.command` 和求解证据（problem 文件、plan 文件、状态摘要）。任何任务缺少成功 plan 都不能进入 `verified_task_kinds`。

场景发布门槛：结构错误为 0；所有声明为支持的任务均有独立 PDDL 成功 plan；失败或超时任务必须列入 `unsolved_task_kinds`；metadata 与图中节点/NPC 计数一致。最终任务数量只取 `verified_task_count`，不取候选数量。

## 一、目前最小原子物体清单

这里的“最小”指当前仿真粒度下不再拆分的实体。`atomic/composite` 与 `movable/fixed` 是正交属性；复合物体由多个实体和组合关系生成。

数量资源不逐个建节点，例如纸巾使用 `tissue_resource.count=100`，焊锡使用 `solder.amount`；花瓶水采用粗粒度 `has_water=true/false`。

当前 `OBJECT_LIBRARY` 共 115 个模板；下表逐个列出

| 物体名称 | 类型 | 移动/不可移动 | 当前默认状态 |
|---|---|---|---|
| 门（`door`） | 结构物 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 按钮（`button`） | 设备 | 不可移动 | `is_on`=False；`is_pressed`=False |
| 灯（`room_light`） | 设备 | 不可移动 | `is_on`=False |
| 空调（`air_conditioner`） | 设备 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 架子（`rack`） | 家具 | 不可移动 | `is_dirty`=False |
| 鞋架（`shoe_rack`） | 家具 | 不可移动 | `is_dirty`=False |
| 座椅（`seat`） | 家具 | 不可移动 | `is_dirty`=False |
| 椅子（`chair`） | 家具 | 不可移动 | `is_dirty`=False |
| 桌子（`table`） | 家具 | 不可移动 | `is_dirty`=False |
| 茶几（`coffee_table`） | 家具 | 不可移动 | `is_dirty`=False |
| 操作台（`counter`） | 家具 | 不可移动 | `is_dirty`=False |
| 书桌（`desk`） | 家具 | 不可移动 | `is_dirty`=False |
| 抽屉（`drawer`） | 家具 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 沙发（`sofa`） | 家具 | 不可移动 | `is_dirty`=False |
| 床（`bed`） | 家具 | 不可移动 | `is_dirty`=False |
| 衣柜（`wardrobe`） | 家具 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 柜子（`cabinet`） | 家具 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 水槽（`sink`） | 容器/家具 | 不可移动 | `is_dirty`=False；`has_water`=False；最多承载 1 个物体 |
| 水龙头（`faucet`） | 设备 | 不可移动 | `is_on`=False |
| 马桶（`toilet`） | 家具 | 不可移动 | `is_dirty`=False |
| 淋浴（`shower`） | 设备 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 冰箱（`refrigerator`） | 设备 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 微波炉（`microwave`） | 设备 | 不可移动 | `is_on`=False；`is_open`=False；`is_dirty`=False |
| 炉灶（`stove`） | 设备 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 洗衣机（`washing_machine`） | 设备 | 不可移动 | `is_on`=False；`is_open`=False；`is_dirty`=False |
| 洗衣机（`washer`） | 设备 | 不可移动 | `is_on`=False；`is_open`=False；`is_dirty`=False |
| 晾衣架（`drying_rack`） | 家具 | 不可移动 | 无显式状态 |
| 电视（`television`） | 设备 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 显示屏（`display`） | 办公用品 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 植物（`plant`） | 日用品 | 可移动 | `is_wilted`=False；`is_wet`=True；`vitality`=1.0 |
| 杯子（`mug`） | 日用品 | 可移动 | `is_dirty`=False；`fill_level`=0.0；`is_full`=False |
| 杯子（`cup`） | 日用品 | 可移动 | `is_dirty`=False；`fill_level`=0.0；`is_full`=False；`is_wet`=False |
| 盘子（`plate`） | 容器 | 可移动 | `is_dirty`=False |
| 碗（`bowl`） | 日用品 | 可移动 | `is_dirty`=False；`is_wet`=False |
| 书（`book`） | 容器 | 可移动 | `is_dirty`=False |
| 遥控器（`remote`） | 容器 | 可移动 | `is_dirty`=False |
| 衣物（`clothes`） | 日用品 | 可移动 | `folded`=True；`is_dirty`=False；`is_wet`=False |
| 鞋（`shoes`） | 日用品 | 可移动 | `is_dirty`=False；`is_wet`=False |
| 箱子（`box`） | 容器 | 可移动 | `is_dirty`=False |
| 推车（`cart`） | 容器 | 可移动 | `is_dirty`=False |
| 电脑（`computer`） | 办公用品 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 洗碗机（`dishwasher`） | 设备 | 不可移动 | `is_on`=False；`is_open`=False；`is_dirty`=False |
| 分配器（`dispenser`） | 设备 | 不可移动 | `fill_level`=1.0；`is_full`=False；`is_on`=False；`is_dirty`=False |
| 医生白大褂（`doctor_coat`） | 日用品 | 可移动 | `is_dirty`=False |
| 饮料（`drink`） | 食品 | 可移动 | `is_open`=False；`is_rotten`=False |
| 水果（`fruit`） | 食品 | 可移动 | `is_rotten`=False |
| 免洗洗手液机（`hand_sanitizer_dispenser`） | 设备 | 不可移动 | `fill_level`=1.0；`is_full`=False；`is_on`=False；`is_dirty`=False |
| 果汁（`juice`） | 食品 | 可移动 | `is_open`=False；`is_rotten`=False |
| 旋钮（`knob`） | 设备 | 不可移动 | `is_on`=False |
| 储物柜（`locker`） | 办公用品 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 机器（`machine`） | 设备 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 医疗推车（`medical_cart`） | 医疗用品 | 可移动 | `is_dirty`=False |
| 医疗表单（`medical_form`） | 医疗用品 | 可移动 | `is_dirty`=False |
| 药盒（`medicine_box`） | 医疗用品 | 可移动 | `is_open`=False |
| 药品冰箱（`medicine_fridge`） | 设备 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 牛奶（`milk`） | 食品 | 可移动 | `is_open`=False；`is_rotten`=False |
| 护士制服（`nurse_uniform`） | 日用品 | 可移动 | `is_dirty`=False |
| 处方单（`prescription_sheet`） | 医疗用品 | 可移动 | `is_dirty`=False |
| 打印机（`printer`） | 设备 | 不可移动 | `is_on`=False；`is_dirty`=False |
| 收据（`receipt`） | 办公用品 | 可移动 | `is_dirty`=False |
| 冷藏药品（`refrigerated_medicine`） | 食品 | 可移动 | `is_rotten`=False；`temperature`=cold |
| 货架（`shelf`） | 家具 | 不可移动 | `is_dirty`=False |
| 标牌（`signboard`） | 家具 | 不可移动 | `is_dirty`=False |
| 文具（`stationery`） | 办公用品 | 可移动 | `is_dirty`=False |
| 注射器（`syringe`） | 医疗用品 | 可移动 | 无显式状态 |
| 马桶刷（`toilet_brush`） | 容器 | 可移动 | `is_dirty`=False |
| 牙刷（`toothbrush`） | 日用品 | 可移动 | `is_dirty`=False |
| 牙膏（`toothpaste`） | 日用品 | 可移动 | `is_dirty`=False |
| 垃圾桶（`trash_bin`） | 容器 | 可移动 | `is_dirty`=False |
| 蔬菜（`vegetable`） | 食品 | 可移动 | `is_rotten`=False |
| 饮水机（`water_dispenser`） | 设备 | 不可移动 | `fill_level`=1.0；`is_full`=False；`is_on`=True；`is_dirty`=False |
| 轮椅（`wheelchair`） | 医疗用品 | 可移动 | `is_dirty`=False |
| 枕头（`pillow`） | 家具 | 可移动 | `is_dirty`=False；`is_wet`=False |
| 画（`painting`） | 装饰 | 不可移动 | `is_dirty`=False |
| 花瓶（`vase`） | 容器 | 可移动 | `is_dirty`=False；`has_water`=False |
| 镜子（`mirror`） | 装饰 | 不可移动 | `is_dirty`=False |
| 毛巾架（`towel_holder`） | 家具 | 不可移动 | 无显式状态 |
| 毛巾（`towel`） | 工具 | 可移动 | `is_dirty`=False；`folded`=True；`is_wet`=False |
| 雕像（`statue`） | 装饰 | 可移动 | `is_dirty`=False |
| 钥匙链（`keychain`） | 日用品 | 可移动 | 无显式状态 |
| 手机（`cellphone`） | 日用品 | 可移动 | `is_dirty`=False |
| 面包（`bread`） | 食品 | 可移动 | `is_rotten`=False；`is_dirty`=False |
| 鸡蛋（`egg`） | 食品 | 可移动 | `is_rotten`=False |
| 叉子（`fork`） | 工具 | 可移动 | `is_dirty`=False |
| 勺子（`spoon`） | 工具 | 可移动 | `is_dirty`=False |
| 汤勺（`ladle`） | 工具 | 可移动 | `is_dirty`=False |
| 胡椒瓶（`peppershaker`） | 容器 | 可移动 | `is_dirty`=False |
| 盐瓶（`saltshaker`） | 容器 | 可移动 | `is_dirty`=False |
| 马桶吸（`plunger`） | 工具 | 可移动 | 无显式状态 |
| 清洁刷（`scrubbrush`） | 工具 | 可移动 | `is_dirty`=False |
| 肥皂（`soapbar`） | 工具 | 可移动 | `is_dirty`=False |
| 纸巾盒（`tissuebox`） | 容器 | 可移动 | `is_dirty`=False |
| 梳妆柜（`dresser`） | 家具 | 不可移动 | `is_open`=False；`is_dirty`=False |
| 浴缸（`bathtub`） | 家具 | 不可移动 | `is_dirty`=False |
| 浴缸盆（`bathtubbasin`） | 容器 | 不可移动 | `is_dirty`=False |
| 报纸（`newspaper`） | 媒体设备 | 可移动 | `is_dirty`=False |
| 手表（`watch`） | 日用品 | 可移动 | `is_dirty`=False |
| 电视柜（`tvstand`） | 家具 | 不可移动 | `is_dirty`=False |
| 泰迪熊（`teddybear`） | 装饰 | 可移动 | `is_dirty`=False |
| 篮球（`basketball`） | 日用品 | 可移动 | 无显式状态 |
| 网球拍（`tennisracket`） | 日用品 | 可移动 | 无显式状态 |
| 棒球棒（`baseballbat`） | 日用品 | 可移动 | 无显式状态 |
| 哑铃（`dumbbell`） | 日用品 | 可移动 | 无显式状态 |
| 瓶子（`bottle`） | 容器 | 可移动 | `is_dirty`=False |
| 酒瓶（`winebottle`） | 容器 | 可移动 | `is_dirty`=False |
| 房间装饰（`roomdecor`） | 装饰 | 可移动 | `is_dirty`=False |
| 海报（`poster`） | 装饰 | 不可移动 | `is_dirty`=False |
| 脚凳（`ottoman`） | 家具 | 不可移动 | `is_dirty`=False |
| 脚踏凳（`footstool`） | 家具 | 不可移动 | `is_dirty`=False |
| 宠物窝（`dogbed`） | 家具 | 不可移动 | `is_dirty`=False |
| 垃圾袋（`garbagebag`） | 容器 | 可移动 | 无显式状态 |
| 铝箔纸（`aluminumfoil`） | 工具 | 可移动 | 无显式状态 |
| 桌面装饰（`tabletopdecor`） | 装饰 | 可移动 | `is_dirty`=False |
| 吸尘器（`vacuumcleaner`） | 工具 | 可移动 | 无显式状态 |
| 洗衣篮（`laundryhamper`） | 容器 | 可移动 | `is_open`=False |

## 二、外部数据对象覆盖与缺口

来源：`backend/data/generation_priors/object_catalog_report.md`（生成于 2026-08-22）。当前对象库已不是历史统计中的约 72 个模板，而是 **115 个正式模板**；外部数据中有 **113 个候选标签**，其中 78 个已直接覆盖、3 个可作别名、18 个暂缓、14 个为新模板候选。故“已有 115 个对象”不等于“已有 115 个可用于丰富任务的对象”：下表的 32 项缺的是任务语义或运行时系统，而不只是对象名称。

| 外部对象 | 当前归宿 | 缺少的能力/状态/过程 | 应进入的通用原型 |
|---|---|---|---|
| 闹钟（`alarmclock`） | 暂缓 | `alarm_time`、周期事件、通知主体 | `TimedDeviceProcess` + `AlarmEvent` |
| 百叶窗（`blinds`） | 暂缓 | `is_open`、遮光/通风关系 | `EnvironmentControlProcess` |
| 黄油刀（`butterknife`） | 暂缓 | `cut`/涂抹工具效果、目标材料变化 | `ToolTransformProcess` |
| 蜡烛（`candle`） | 暂缓 | `is_lit`、`burn_remaining`、光照、燃尽 | `TimedDeviceProcess` + `LightingProcess` |
| 光盘（`cd`） | 暂缓 | 媒体载体、播放器兼容、`is_playing` | `MediaPlaybackProcess` |
| 烘干机（`clothesdryer`） | 新模板候选 | 容器、开关、`cycle_remaining`、干燥完成效果 | `TimedDeviceProcess` |
| 咖啡机（`coffeemachine`） | 暂缓 | 水/咖啡资源、配方、产物生成 | `ResourceDispenserProcess` + `RecipeProcess` |
| 信用卡（`creditcard`） | 暂缓 | 账户、金额、支付授权 | `PaymentProcess`（后置领域） |
| 窗帘（`curtains`） | 新模板候选 | 开合、遮光/通风关系 | `EnvironmentControlProcess` |
| 台灯（`desklamp`） | 暂缓 | `is_on`、局部照明 | `LightingProcess` |
| 洗碗海绵（`dishsponge`） | 暂缓 | 湿度、清洁效力、可选消耗量 | `ToolTransformProcess` |
| 地面（`floor`） | 新模板候选 | 房间空间/承载面权威语义 | `SpatialSurface` |
| 落地灯（`floorlamp`） | 暂缓 | `is_on`、局部照明 | `LightingProcess` |
| 水壶（`kettle`） | 新模板候选 | 容量、液体、加热、沸腾过程 | `ThermalCookProcess` |
| 刀（`knife`） | 暂缓 | 切割工具效果、目标形态变化 | `ToolTransformProcess` |
| 平底锅（`pan`） | 暂缓 | 容量、热接触、食材烹饪过程 | `ThermalCookProcess` |
| 纸巾卷（`papertowelroll`） | 新模板候选 | 纸巾资源节点、`count`、补充/消耗 | `FiniteResourceProcess` |
| 汤锅（`pot`） | 暂缓 | 容量、热接触、食材烹饪过程 | `ThermalCookProcess` |
| 保险箱（`safe`） | 新模板候选 | `is_open`、`is_locked`、访问控制 | `AccessControlProcess` |
| 浴帘（`showercurtain`） | 新模板候选 | 开合、淋浴区域边界 | `EnvironmentControlProcess` |
| 淋浴门（`showerdoor`） | 新模板候选 | 开合、可达性/区域边界 | `AccessControlProcess` |
| 淋浴玻璃（`showerglass`） | 新模板候选 | 固定边界、可见/阻隔关系 | `SpatialSurface` |
| 花洒（`showerhead`） | 新模板候选 | 水源控制、目标区域湿润 | `ResourceDispenserProcess` |
| 洗手液瓶（`soapbottle`） | 暂缓 | 液体资源、按压分配、`amount` | `FiniteResourceProcess` |
| 锅铲（`spatula`） | 新模板候选 | 翻动工具效果、烹饪前置条件 | `ToolTransformProcess` |
| 喷雾瓶（`spraybottle`） | 暂缓 | `has_water`、`uses_left`、按压目标效果 | `FiniteResourceProcess` |
| 炉头（`stoveburner`） | 暂缓 | 热源、作用范围、设备控制 | `ThermalCookProcess` |
| 烤面包机（`toaster`） | 新模板候选 | 容器、开关、`cycle_remaining`、烤制完成 | `TimedDeviceProcess` + `ThermalCookProcess` |
| 卫生纸（`toiletpaper`） | 暂缓 | 资源节点、`count`、使用/补充 | `FiniteResourceProcess` |
| 卫生纸架（`toiletpaperhanger`） | 新模板候选 | 资源挂载关系、容量 | `ResourceHolder` |
| 浇水壶（`wateringcan`） | 新模板候选 | `has_water`、容量、倾倒/浇灌效果 | `FiniteResourceProcess` |
| 窗户（`window`） | 暂缓 | 开合、温度/湿度/通风交换 | `EnvironmentControlProcess` |

这里不应把 32 个对象逐个补成专用代码。正确的单位是“**对象模板声明能力与参数，通用过程解释能力**”：例如喷壶、浇水壶、洗手液瓶、卫生纸都只是在资源种类、容量、消耗量、目标效果上不同；洗衣机、烘干机、微波炉、烤面包机则共用同一个计时设备过程。

| 通用原型 | 模板声明的参数 | 运行时的统一变化 | 可覆盖对象 |
|---|---|---|---|
| 有限资源/分配 | `resource_kind`、`capacity`、`uses_per_refill`、`effect` | `amount/uses_left -= n`；不足时禁用；`refill` 恢复 | 纸巾、卫生纸、洗手液、喷壶、浇水壶、焊锡 |
| 定时设备 | `duration`、输入容器、完成效果 | 启动后创建 `ProcessInstance`；tick 减少 `cycle_remaining`；完成后提交 effects | 洗衣机、烘干机、微波炉、烤面包机、唱片机、闹钟 |
| 热加工 | `heat_source`、温度阈值、配方/完成效果 | 热源作用范围内累积热量；达到阈值触发 cooked/boiling/burnt | 炉头、平底锅、汤锅、水壶、烤面包机 |
| 工具变换 | `tool_effect`、目标类型、前置条件 | 合法工具作用于目标，修改 `is_dirty`、`cut_state`、`configuration` 等 | 刀、黄油刀、锅铲、海绵、刷子 |
| 配方制作/装配 | `ingredients`、工作台、工具、输出模板 | 校验输入与 edge；消耗材料；`spawn` 复合产物 | 汉堡、焊接电路、咖啡、折纸成品 |
| 环境控制 | `control_target`、作用区域、环境效果 | `open/close/press` 改变环境边或环境变量 | 窗户、百叶窗、窗帘、灯、花洒 |
| 生命周期/衰减 | `tick_rule`、阈值、后果 | 时间事件修改资源/活力；阈值触发状态和任务 | 花瓶水、花、食物、蜡烛 |

## 三、目前状态空间

状态由 `backend/core/states.py` 的离散状态空间约束；数量、配置和主体状态可继续扩展。当前共注册 25 个状态：17 个布尔状态、7 个数值状态（`cycle_remaining`、`fill_level`、`vitality`、`uses_left`、`count`、`amount`、`capacity`）和 1 个数值/枚举状态（`temperature`）。其中水槽使用独立的布尔 `has_water`，不使用 `fill_level`；水槽的容量语义是“可承载一个物体”，不是液体体积。整体状态空间仍以布尔量为主，尚不足以表达库存、有限使用次数、连续加工阶段和复杂配置。

| 状态名称 | 可被哪种动作改变 |
|---|---|
| `is_dirty` | `brush`；使用、泼洒等外部事件 |
| `is_wet` | `press`/清洗过程/干燥过程 |
| `is_clean`（建议补充或由 `is_dirty=false` 推导） | `brush`、清洗过程 |
| `has_water` | 水龙头开关、容器入水槽、蒸发/消耗事件；水槽和花瓶采用二值水状态 |
| `fill_level`、`is_full` | 仅用于需要数量容量的容器/资源，不用于水槽 |
| `is_open` | `open`、`close` |
| `is_on`、`is_pressed` | `press`、`open`、`close` 或设备控制逻辑 |
| `cycle_remaining`、`cycle` | `press` 启动过程、时间推进 |
| `is_cooked`、`is_burnt` | 加热/烹饪过程、时间事件 |
| `temperature`、`is_frozen`、`is_boiling` | 加热、冷却、时间事件 |
| `is_folded` / `fold_state` | `fold`、`unfold` |
| `orientation`、`configuration` | `rotate`、`fold`、`connect` |
| `is_connected` / `is_assembled` | `connect`、装配过程 |
| `vitality`、`is_wilted` | 浇水、时间衰减 |
| `health`、`mood` | 社交、唱片播放、环境事件、长期状态影响 |
| `count`、`amount`、`uses_left` | `consume`、`refill/fill`、制作过程 |
| `lifecycle`（active/discarded/consumed） | `discard`、`consume`、制作生成/销毁 |

状态变化必须记录 `old_value -> new_value`，并注明触发动作或时间事件。

## 四、目前动作空间

动作名称是无对象的原子接口；绑定主体、对象、目标后才形成实例化动作。

| 动作名称 | 可改变哪些状态 | 前置条件 |
|---|---|---|
| `move` | 机器人/人的位置状态；位置 edge | 目标空间节点可达、路径未阻塞 |
| `pick` | 持有状态；`held_by` edge | 对象可移动、可抓取、同房间且手为空 |
| `place` | 对象位置/容器归属；`in/on/at` edge | 主体持有对象、目标可放置且容量允许 |
| `open` | `is_open`、相关设备访问状态 | 目标可打开、同位置、未被锁定 |
| `close` | `is_open` | 目标可关闭且当前打开 |
| `press` | `is_pressed`、`is_on`、设备模式；可触发过程 | 目标可按压、主体可达 |
| `brush` | `is_dirty`、清洁状态 | 目标可清洁、主体可达 |
| `fold` | `folded`、`fold_state` | 目标可折叠、满足干燥/可操作条件 |
| `dump` | 容器内容、数量资源；容器/内容 edge | 主体持有可倾倒容器、目标兼容 |
| `consume`（建议新增） | `count`、`amount`、`uses_left`、`lifecycle` | 资源数量足够、消费条件满足 |
| `discard`（建议新增） | `lifecycle=discarded` | 对象允许丢弃；必要时主体持有或位于垃圾桶附近 |
| `connect`（建议新增） | `is_connected`、`is_assembled` | 部件兼容、位置/工具/材料满足 |
| `rotate`（建议新增） | `orientation`、`configuration` | 对象可旋转、目标面/方向参数合法 |

动作效果统一为：`state_updates + resource_updates + add_edges + remove_edges + spawn + despawn`。

`fill` 不应注册为自由原子动作。以花瓶为例，`place(vase, sink)` 先建立 `in(vase, sink)`，随后 `open(faucet)` 在水龙头控制该水槽且花瓶在槽内时，立即产生 `vase.has_water: false -> true`；这是一条由操作动作触发的领域规则，不允许机器人在任何位置直接执行 `fill(vase)`。

## 五、最小任务集合

### 5.1 任务不是物体模板：Domain、Grounding、PDDL 三层

任务与物体的建模粒度不同。物体模板可以预先声明 `semantic_type`、状态和能力；任务模板只能预先声明“需要什么能力、如何绑定参数、要达到什么目标”，不能预先写死对象 ID、房间 ID 或路线。建议把任务定义为以下三层：

| 层 | 输入/输出 | 是否写入 domain JSON | 说明 |
|---|---|---|---|
| 任务模板（schema） | 参数查询、触发条件、需求能力、目标表达式、PDDL compiler | 是 | 例如 `clean_surface` 需要可清洁目标和清洁工具 |
| 场景实例化（grounding） | scene graph + 模板 -> task instance | 否，写入 scene metadata | 解析 `target=bed_1`、`tool=vacuum_1`、`destination=wardrobe_1`，并检查房间拓扑可达 |
| 规划验证（PDDL） | task instance -> problem/plan/result | 否，保存 evidence | 将已绑定的节点、初始状态、门和 `connected` 边编译为一个具体 problem；只有成功 plan 才算支持 |

因此，`clean` 在 domain 中不是“清洁客厅”，而是一个可复用模板：

```json
{
  "task_id": "clean_surface",
  "family": "clean",
  "parameters": {
    "target": {"object_query": {"state": {"is_dirty": true}}},
    "tool": {"object_query": {"capability": "cleaning"}}
  },
  "requirements": {"actions": ["move", "brush"]},
  "goal": [{"target.state.is_dirty": false}],
  "pddl": {"compiler": "graphworld.generic.clean_surface.v1"}
}
```

实例化器随后对图执行：

```text
候选 target/tool -> 同房间或 connected 路径检查 -> 解析门与容器约束
                 -> 生成 task_instance.json -> 编译 PDDL -> Fast Downward
```

`move` 不需要在任务先验里枚举。它是满足任务所需的支撑动作，由 PDDL 根据当前 `room_edge`、结构门 `connected_rooms` 和 `blocks_navigation` 自动产生路线。若图中没有清洁工具、目标不可达、门无法打开或目标状态不满足，grounding 阶段丢弃该候选；若 grounding 成功但 PDDL 无解，则记录为 `unsolved`，不能计入任务数量。

任务模板应分为三类约束：`requirements`（能力/动作/资源）、`binding`（对象和节点查询）、`goal`（状态和关系终态）。路径、具体步骤、代价和 plan 长度均属于实例或验证结果，不属于领域先验。

### 任务统计与 PDDL 覆盖现状

当前统计分三层，不能混为一个数字：

| 层级 | 当前数量 | 来源 | 含义 |
|---|---:|---|---|
| 一级任务类型 | 6 | 本文任务 taxonomy | `clean/make/relocate/operate/interact/navigate` |
| Core 具体技能 | 12 | `backend/core/assets/task_library.py` | 已有运行时任务/维护技能注册，不等于都有 PDDL |
| PDDL 已验证任务族 | 1 | `backend/tools/try_laundry_fastdownward.py` | 洗衣子任务，Fast Downward 成功，已知计划长度 17 |

现阶段没有“全部任务的 PDDL 解法统计”。`task_pddl_coverage.json` 保存这个缺口和统计口径；后续每增加一个任务，必须登记任务 schema、实例化参数、PDDL problem、planner 状态、plan 长度和证据路径。任务数量最终按成功 PDDL plan 的**任务实例**统计，而不是按一级类型或 core 技能数量统计。

任务由目标状态/edge 定义；复杂任务由多个最小任务或过程组合。`navigate` 当到达位置是目标时是任务，否则只是支撑动作。

| 任务名称 | 典型展开举例 |
|---|---|
| 清洁 `clean` | `pick(brush) -> move(target) -> brush(target)`；目标 `is_dirty: true -> false` |
| 制作 `make` | 汉堡：收集原料 -> 灶台加工 -> `connect/stack` -> 生成 `burger`；焊接：收集电线/电路板/焊锡 -> 焊台操作 -> `connect` -> 生成焊接组件 |
| 迁移 `relocate` | `pick(object) -> move(destination) -> place(object,destination)`；目标是 `in/on/at/held_by` edge 变化 |
| 操作 `operate` | 花瓶：`place(vase,sink) -> open(faucet)`，满足位置和控制关系后立即 `has_water=false -> true`，再 `close(faucet)`；洗衣机：`press(start) -> process -> clothes.clean/wet`；纸巾盒补给：`count=0 -> refill -> count=100` |
| 交互 `interact` | `move(person) -> approach -> give/receive`；唱片机播放期间改变 `human.mood` |
| 移动 `navigate` | `move(robot, room_B)`；目标是机器人位置 edge 从 `room_A` 变为 `room_B` |
| 迁移 `relocate` | 枯萎花：`pick -> move(trash_bin) -> place`，同时 `lifecycle=discarded`；喷壶装水后移动到花旁再执行 `press` |

时间过程不是新的原子动作，而是带 `duration/tick/finish_effects` 的过程：花耗水、花枯萎、洗衣完成、唱片停止都由时间事件推进。

## 六、边界情况

| 情况 | 现有六类/动作是否直接覆盖 | 处理方式 |
|---|---|---|
| 资源消耗：纸巾、焊锡、喷壶次数 | 部分覆盖 | 增加 `count/amount/uses_left`，由 `consume` 改变 |
| 时间过程：洗衣、唱片、花耗水 | 不能由瞬时动作独立表达 | `ProcessInstance + Scheduler` |
| 复合物生成：汉堡、焊接组件 | 不能只靠 edge 表示 | `spawn` 新实体，或将部件升级为 composite |
| 配置空间：折纸、魔方 | 不是普通位置 edge | `fold_state/configuration/orientation` |
| 纯信息任务：问答、识别、记忆 | 没有物理 state/edge 变化 | 增加 belief/information 状态，或标注为非物理任务 |
| 持续约束：保持温度、花鲜活、设备运行 | 不是一次性终态 | 增加 `duration/invariant` |
| 多主体同步：协同抬物、分工 | 单一动作不足 | 增加角色、同步和联合前置条件 |
| 代价优化：最短路径、低能耗、安全 | 不是状态完成条件 | 单独记录 `cost/safety` 目标 |

## 七、理想架构

```text
Entity Catalog
  -> Entity Instances
  -> State / Resource / Configuration Store
  -> Relation Graph
  -> Primitive Action Registry
  -> Transition Engine
  -> Process Definitions + Scheduler
  -> Event / Decay / Consumption Rules
  -> Task Triggers
  -> Task Goals + Validator
  -> Replay / Score
```

```python
WorldState:
    entities: dict[EntityId, Entity]
    states: dict[EntityId, dict[str, Any]]
    resources: dict[EntityId, dict[str, float]]
    edges: Graph
    processes: list[ProcessInstance]
    events: PriorityQueue
    tasks: list[TaskInstance]
    clock: int
```

模板只描述“它能参与什么过程”和参数；过程定义才描述状态与 edge 如何变化。下面是应该落到数据文件/注册表的最小形式，而不是每加一个对象都新增 `if semantic == ...`：

```yaml
spraybottle:
  capabilities: [movable, refillable, finite_resource, target_effect]
  resources: {water: {capacity: 5, current: 5}}
  processes:
    - kind: finite_resource
      trigger: press
      requires: [held_by(actor), near(target, actor), resource.water >= 1]
      effects:
        - resource.water: -1
        - target.vitality: +0.2

washer:
  capabilities: [openable, switchable, container, timed_device]
  processes:
    - kind: timed_device
      trigger: press
      duration: 10
      requires: [is_open == false, contains(clothes)]
      finish_effects:
        - child.is_dirty: false
        - child.is_wet: true
```

花瓶/水槽使用同一机制，但不建立 `fill` 动作：水龙头的过程规则写成 `trigger: open`、`requires: controls(faucet, sink) and in(container, sink)`、`effects: container.has_water=true`。因此 edge 是前置条件和过程作用域，state/resource 才是结果；更换为杯子、喷壶或浇水壶时只需模板参数不同。

水槽本身只有二值状态 `has_water`，没有 `fill_level`。`open(faucet)` 将其设为 `true`，`close(faucet)` 将其设为 `false`。水槽最多承载一个对象：若当前水槽有水，`place(container, sink)` 立即把该容器的 `has_water` 设为 `true`；若 `place(cloth, sink)`，则把布类对象的 `is_wet` 设为 `true`。因此“水槽有水”与“容器被水槽装满”是两个不同节点的状态变化。

| 当前模块 | 理想职责 |
|---|---|
| `scenegraph.py` | `WorldState` 的实体与关系存储适配层 |
| `nodes.py`、`object_library.py` | Entity Catalog、对象能力和复合对象模板 |
| `states.py` | State/Resource/Configuration 定义和校验 |
| `edges.py` | Relation Graph、边约束和 edge validator |
| `actions.py`、`action_schemas.py`、`effects.py` | Primitive Action Registry + Transition Engine |
| `timed_transitions.py` | Process Scheduler；从语义分支改为声明式过程 |
| `domain_rules.py` | 过程、资源和事件规则目录 |
| `goal_lifecycle.py` | Task Trigger/Goal/Validator；减少硬编码 phase 分支 |
| `scene_preparation.py` | 初始实体、资源、关系和过程实例化 |

建议新增：

```text
backend/core/world/{world_state.py,entities.py,resources.py,lifecycle.py}
backend/core/processes/{definitions.py,scheduler.py,builtin.py}
backend/core/tasks/{definitions.py,triggers.py,validators.py}
```

重构顺序：先引入 `WorldState` 兼容层；再统一 Entity/Resource；然后统一动作 transition；接着把 `timed_transitions` 改为 scheduler；最后将 `goal_lifecycle` 改为声明式任务。旧 JSON 和旧动作接口先通过 adapter 兼容，不要一次性重写。
