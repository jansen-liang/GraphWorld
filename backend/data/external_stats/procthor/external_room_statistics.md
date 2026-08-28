# 外部数据统计报告

## 数据源

- 来源：`procthor`
- 版本：`0.0.1.dev2`
- 原始路径：`/home/swzz/anaconda3/gra/lib/python3.10/site-packages/procthor/databases`
- 统计对象：ProcTHOR placement annotations、receptacles，以及随包提供的 AI2-THOR object metadata 数据库。
- 许可：上游 ProcTHOR/AI2-THOR 许可条款仍适用于原始数据；本仓库只保存派生聚合统计，不复制 3D 资产。

## 房间与对象

- **bathroom**：48 个对象实例；faucet (2), toilet (2), washer (1)
  - 未映射原始标签：Candle (2), Cloth (2), GarbageCan (2), HandTowel (2), HandTowelHolder (2), LightSwitch (2), Plunger (2), ScrubBrush (2), ShowerCurtain (2), ShowerHead (2), SoapBar (2), SoapBottle (2), SprayBottle (2), ToiletPaper (2), ToiletPaperHanger (2), Towel (2), TowelHolder (2), ClothesDryer (1), DishSponge (1), Dresser (1), Footstool (1), HousePlant (1), LaundryHamper (1), PaperTowelRoll (1), SideTable (1), TissueBox (1)
- **bedroom**：69 个对象实例；chair (3), bed (2), book (2), bowl (2), box (2), desk (2), coffee_table (1), mug (1), sofa (1)
  - 未映射原始标签：AlarmClock (2), BaseballBat (2), Blinds (2), CD (2), CellPhone (2), CreditCard (2), DeskLamp (2), Dresser (2), GarbageCan (2), KeyChain (2), Laptop (2), LightSwitch (2), Pen (2), Pencil (2), Pillow (2), SideTable (2), BasketBall (1), Boots (1), Cloth (1), Desktop (1), DogBed (1), Dumbbell (1), Footstool (1), HousePlant (1), LaundryHamper (1), RemoteControl (1), Safe (1), ShelvingUnit (1), Statue (1), Stool (1), TableTopDecor (1), TeddyBear (1), TennisRacket (1), TissueBox (1), VacuumCleaner (1), Vase (1), Watch (1)
- **kitchen**：87 个对象实例；bowl (2), chair (2), counter (2), cup (2), faucet (2), microwave (2), mug (2), plate (2), refrigerator (2), book (1), table (1)
  - 未映射原始标签：Apple (2), Bread (2), ButterKnife (2), CoffeeMachine (2), DishSponge (2), Egg (2), Fork (2), GarbageCan (2), Kettle (2), Knife (2), Ladle (2), Lettuce (2), LightSwitch (2), Pan (2), PepperShaker (2), Pot (2), Potato (2), SaltShaker (2), ShelvingUnit (2), SoapBottle (2), Spatula (2), Spoon (2), Stool (2), Toaster (2), Tomato (2), Vase (2), AluminumFoil (1), Blinds (1), Bottle (1), CellPhone (1), CreditCard (1), GarbageBag (1), HousePlant (1), PaperTowelRoll (1), Pen (1), Pencil (1), Safe (1), SideTable (1), SprayBottle (1), Statue (1), WineBottle (1)
- **living_room**：64 个对象实例；chair (4), box (2), sofa (2), book (1), bowl (1), cart (1), coffee_table (1), desk (1), plate (1), table (1)
  - 未映射原始标签：CreditCard (2), DeskLamp (2), Dresser (2), FloorLamp (2), GarbageCan (2), KeyChain (2), Laptop (2), LightSwitch (2), Newspaper (2), Pillow (2), RemoteControl (2), ShelvingUnit (2), SideTable (2), Statue (2), TVStand (2), Vase (2), Watch (2), WateringCan (2), Blinds (1), Boots (1), Candle (1), CellPhone (1), DogBed (1), HousePlant (1), Ottoman (1), Pen (1), Pencil (1), RoomDecor (1), Safe (1), Stool (1), TissueBox (1)

## Parent / receptacle

- **book**：desk (36), coffee_table (24), chair (21), bed (15), table (15), sofa (6), counter (2)
- **bowl**：table (30), coffee_table (19), counter (19), desk (14), chair (5), plate (1)
- **box**：coffee_table (17), table (5), chair (3), bed (1), desk (1)
- **cup**：counter (16), table (12), coffee_table (8), desk (6), sink (3), box (1)
- **faucet**：counter (27), sink (27)
- **microwave**：counter (17), table (1)
- **mug**：table (20), desk (19), coffee_table (13), counter (13), sink (7), chair (1)
- **plate**：table (33), counter (15), coffee_table (11), desk (6), sink (3), chair (2)
- **unmapped::AlarmClock**：coffee_table (6), desk (6), chair (2), bed (1), sofa (1), table (1)
- **unmapped::Apple**：table (20), counter (16), desk (12), coffee_table (8), chair (6), refrigerator (5), bed (3), sink (3), sofa (3), plate (2)
- **unmapped::BaseballBat**：coffee_table (3), desk (3), bed (2), sofa (1), table (1)
- **unmapped::BasketBall**：chair (7), coffee_table (4), bed (2), box (2), sofa (1), table (1)
- **unmapped::Bottle**：table (14), desk (12), coffee_table (9), counter (3), chair (2)
- **unmapped::Bread**：counter (21), table (9)
- **unmapped::ButterKnife**：counter (25), table (8), sink (1)
- **unmapped::CD**：desk (16), chair (2), coffee_table (2), table (1)
- **unmapped::Candle**：counter (12), coffee_table (5), table (5), toilet (3)
- **unmapped::CellPhone**：desk (18), coffee_table (10), bed (5), chair (5), table (4), counter (2), sofa (1)
- **unmapped::Cloth**：counter (10), toilet (7)
- **unmapped::CoffeeMachine**：counter (27), table (2)
- **unmapped::CreditCard**：desk (19), coffee_table (13), table (4), counter (3), bowl (1), chair (1)
- **unmapped::DeskLamp**：desk (22), coffee_table (11), table (11)
- **unmapped::Desktop**：desk (2)
- **unmapped::DishSponge**：counter (16), sink (14), toilet (2)
- **unmapped::Dumbbell**：desk (1)
- **unmapped::Egg**：refrigerator (17), sink (7), counter (6)
- **unmapped::Fork**：counter (18), table (10), plate (7), sink (5), desk (1)
- **unmapped::HandTowel**：counter (1)
- **unmapped::HousePlant**：coffee_table (17), table (15), counter (9), desk (4)
- **unmapped::Kettle**：counter (10), table (1)
- **unmapped::KeyChain**：desk (17), coffee_table (9), chair (4), table (2)
- **unmapped::Knife**：counter (18), sink (4), table (3)
- **unmapped::Ladle**：counter (9), table (1)
- **unmapped::Laptop**：desk (33), table (20), coffee_table (19), bed (18), sofa (15), chair (13)
- **unmapped::Lettuce**：counter (10), refrigerator (8), sink (8), table (4)
- **unmapped::Newspaper**：sofa (8), table (5), chair (4), coffee_table (3), desk (2)
- **unmapped::Painting**：chair (1)
- **unmapped::Pan**：counter (13), table (2)
- **unmapped::PaperTowelRoll**：counter (11), toilet (1)
- **unmapped::Pen**：desk (24), coffee_table (4), table (4), chair (1), counter (1)
- **unmapped::Pencil**：desk (26), table (7), coffee_table (3), box (2), chair (1), counter (1), sofa (1)
- **unmapped::PepperShaker**：counter (27), coffee_table (4), table (3)
- **unmapped::Pillow**：bed (82), sofa (49), chair (23)
- **unmapped::Pot**：counter (13), coffee_table (8), table (8), desk (5), sink (1)
- **unmapped::Potato**：counter (18), table (8), refrigerator (2), sink (2)
- **unmapped::RemoteControl**：coffee_table (22), chair (15), sofa (13), desk (7), table (7), bed (3)
- **unmapped::Safe**：无已映射 parent
- **unmapped::SaltShaker**：counter (27), coffee_table (4), table (3)
- **unmapped::ShowerCurtain**：无已映射 parent
- **unmapped::SoapBar**：counter (16), toilet (1)
- **unmapped::SoapBottle**：counter (51), sink (2), toilet (1)
- **unmapped::Spatula**：counter (27), sink (1)
- **unmapped::Spoon**：counter (18), sink (5), table (2)
- **unmapped::SprayBottle**：counter (9), coffee_table (7), toilet (6), desk (4), table (4)
- **unmapped::Statue**：coffee_table (17), table (13), desk (6), counter (1)
- **unmapped::TableTopDecor**：desk (1)
- **unmapped::TeddyBear**：bed (10), chair (1), desk (1)
- **unmapped::TennisRacket**：coffee_table (2), bed (1), table (1)
- **unmapped::TissueBox**：counter (4), coffee_table (3), desk (2)
- **unmapped::Toaster**：counter (27), table (3)
- **unmapped::ToiletPaper**：toilet (22), counter (13)
- **unmapped::Tomato**：counter (13), refrigerator (6), table (6), sink (5), plate (1)
- **unmapped::Towel**：无已映射 parent
- **unmapped::Vase**：coffee_table (17), table (13), desk (6), counter (3), plate (1)
- **unmapped::Watch**：coffee_table (6), desk (3), chair (1), table (1)
- **unmapped::Window**：counter (2), table (1)
- **unmapped::WineBottle**：counter (5), table (3), refrigerator (1)

## 房间共现与邻接

- 可用：`否`；house 文件数：`0`
- 说明：未发现 house JSON，ProcTHOR 包内数据库无法提供房间共现/邻接统计

## 能力先验

能力字段来自 ProcTHOR 的聚合 placement annotations，表示对象类别级先验，不等同于 GraphWorld 的完整动作合法性。
- 可拾取类别：book, bowl, box, cup, mug, plate, unmapped::AlarmClock, unmapped::AluminumFoil, unmapped::Apple, unmapped::BaseballBat, unmapped::BasketBall, unmapped::Boots, unmapped::Bottle, unmapped::Bread, unmapped::ButterKnife, unmapped::CD, unmapped::Candle, unmapped::CellPhone, unmapped::Cloth, unmapped::CreditCard, unmapped::DishSponge, unmapped::Dumbbell, unmapped::Egg, unmapped::Footstool, unmapped::Fork, unmapped::HandTowel, unmapped::Kettle, unmapped::KeyChain, unmapped::Knife, unmapped::Ladle, unmapped::Laptop, unmapped::Lettuce, unmapped::Newspaper, unmapped::Pan, unmapped::PaperTowelRoll, unmapped::Pen, unmapped::Pencil, unmapped::PepperShaker, unmapped::Pillow, unmapped::Plunger, unmapped::Pot, unmapped::Potato, unmapped::RemoteControl, unmapped::SaltShaker, unmapped::ScrubBrush, unmapped::SoapBar, unmapped::SoapBottle, unmapped::Spatula, unmapped::Spoon, unmapped::SprayBottle, unmapped::Statue, unmapped::TableTopDecor, unmapped::TeddyBear, unmapped::TennisRacket, unmapped::TissueBox, unmapped::ToiletPaper, unmapped::Tomato, unmapped::Towel, unmapped::Vase, unmapped::Watch, unmapped::WateringCan, unmapped::WineBottle

## 未覆盖项与下一步

- 当前 ProcTHOR 聚合库主要覆盖 Kitchen、LivingRoom、Bedroom、Bathroom；不能据此推导 Hospital、Supermarket、Factory 的领域房间。
- 包内数据库没有生成房屋级 room id、门连接和完整房间共现样本，因此邻接统计只有在 `--root` 提供 house JSON 时才会出现。
- 未映射对象保留在各房间的 `unmapped_objects` 或能力表的 `unmapped::...` 中，需后续补充 ontology mapping，不应直接作为 GraphWorld ObjectTemplate。
- 统计结果是生成 RoomTypeSpec/ObjectTemplate 的先验，还需要 GraphWorld 的任务规则、状态闭环和可解性验证。
