# 外部数据统计报告

## 数据源

- 来源：`ai2thor`
- 版本：`5.0.0`
- 原始路径：`/home/swzz/anaconda3/gra/lib/python3.10/site-packages/procthor/databases`
- 统计对象：ProcTHOR placement annotations、receptacles，以及随包提供的 AI2-THOR object metadata 数据库。
- 许可：上游 ProcTHOR/AI2-THOR 许可条款仍适用于原始数据；本仓库只保存派生聚合统计，不复制 3D 资产。

## 房间与对象

- **bathroom**：1083 个对象实例；sink (89), drawer (68), cabinet (64), faucet (59), toilet (30), counter (29), shelf (14)
  - 未映射原始标签：ToiletPaper (60), HandTowelHolder (45), TowelHolder (38), Mirror (32), Candle (30), Cloth (30), Floor (30), GarbageCan (30), HandTowel (30), LightSwitch (30), Plunger (30), ScrubBrush (30), SoapBar (30), SoapBottle (30), SprayBottle (30), ToiletPaperHanger (30), Towel (30), Window (26), ShowerHead (25), Bathtub (21), BathtubBasin (19), ShowerDoor (17), ShowerCurtain (13), ShowerGlass (13), TissueBox (9), SideTable (7), DishSponge (6), PaperTowelRoll (4), Dresser (2), Footstool (1), HousePlant (1), Painting (1)
- **bedroom**：1228 个对象实例；drawer (201), shelf (116), chair (38), bed (32), book (30), desk (28), mug (16), cabinet (15), bowl (13), box (12), television (3), coffee_table (1), counter (1), sofa (1)
  - 未映射原始标签：Window (45), Pillow (42), Blinds (41), DeskLamp (35), CD (33), AlarmClock (30), CellPhone (30), CreditCard (30), Floor (30), GarbageCan (30), KeyChain (30), Laptop (30), LightSwitch (30), Mirror (30), Pen (30), Pencil (30), SideTable (30), Painting (21), BaseballBat (14), Dresser (13), BasketBall (11), Poster (10), TeddyBear (10), TennisRacket (10), Cloth (9), LaundryHamper (8), HousePlant (7), ShelvingUnit (7), Dumbbell (5), Safe (5), Vase (5), Statue (4), TissueBox (4), Boots (3), Curtains (3), GarbageBag (3), RemoteControl (3), Desktop (2), Footstool (2), Watch (2), DogBed (1), Stool (1), TableTopDecor (1), VacuumCleaner (1)
- **kitchen**：2088 个对象实例；cabinet (418), drawer (174), counter (71), sink (60), faucet (32), bowl (30), cup (30), microwave (30), mug (30), plate (30), refrigerator (30), shelf (27), table (21), chair (20), book (2)
  - 未映射原始标签：StoveBurner (123), StoveKnob (123), Window (36), Apple (30), Bread (30), ButterKnife (30), CoffeeMachine (30), DishSponge (30), Egg (30), Floor (30), Fork (30), GarbageCan (30), Knife (30), Lettuce (30), LightSwitch (30), Pan (30), PepperShaker (30), Pot (30), Potato (30), SaltShaker (30), SoapBottle (30), Spatula (30), Spoon (30), Toaster (30), Tomato (30), Stool (19), Vase (16), Kettle (15), HousePlant (11), Ladle (11), PaperTowelRoll (10), WineBottle (10), Bottle (7), Blinds (5), ShelvingUnit (5), Statue (5), CellPhone (4), AluminumFoil (3), CreditCard (3), GarbageBag (3), SideTable (3), Curtains (2), Mirror (2), Pen (2), Pencil (2), SprayBottle (2), Safe (1)
- **living_room**：1271 个对象实例；drawer (118), chair (111), shelf (104), sofa (36), box (30), television (30), coffee_table (28), cabinet (19), table (16), plate (10), book (7), bowl (5), desk (2)
  - 未映射原始标签：Window (75), SideTable (54), Statue (54), Painting (53), Vase (46), HousePlant (32), FloorLamp (31), CreditCard (30), Floor (30), GarbageCan (30), KeyChain (30), Laptop (30), LightSwitch (30), Pillow (30), RemoteControl (30), Newspaper (18), DeskLamp (16), Watch (16), Curtains (14), TVStand (14), WateringCan (13), Dresser (11), RoomDecor (9), TissueBox (9), CellPhone (7), ShelvingUnit (7), Boots (5), Candle (5), Pen (5), Ottoman (4), Pencil (4), Blinds (3), Mirror (3), Stool (3), DogBed (2), Safe (2)

## Parent / receptacle

- **AlarmClock**：shelf (4), desk (1)
- **AluminumFoil**：shelf (3)
- **Apple**：counter (16), table (6), refrigerator (5), sink (3)
- **BaseballBat**：无已映射 parent
- **BasketBall**：无已映射 parent
- **Bathtub**：counter (1)
- **BathtubBasin**：无已映射 parent
- **Boots**：无已映射 parent
- **Bottle**：counter (3), shelf (2), table (2)
- **Bread**：counter (21), table (9)
- **ButterKnife**：counter (25), drawer (2), sink (1), table (1)
- **CD**：desk (16), shelf (4), drawer (2)
- **Candle**：counter (12), shelf (3), toilet (3), cabinet (2), coffee_table (1), table (1)
- **CellPhone**：desk (14), shelf (3), table (3), bed (2), coffee_table (2), counter (2), chair (1)
- **Cloth**：counter (10), toilet (7), shelf (2), cabinet (1)
- **CoffeeMachine**：counter (27), table (2)
- **CreditCard**：desk (19), coffee_table (13), table (4), counter (3), shelf (3), bowl (1), chair (1)
- **Curtains**：无已映射 parent
- **DeskLamp**：desk (16), shelf (4)
- **Desktop**：desk (2)
- **DishSponge**：counter (16), sink (14), toilet (2), cabinet (1)
- **DogBed**：无已映射 parent
- **Dresser**：无已映射 parent
- **Dumbbell**：desk (1)
- **Egg**：refrigerator (17), sink (7), counter (6)
- **Floor**：cabinet (4)
- **FloorLamp**：无已映射 parent
- **Footstool**：无已映射 parent
- **Fork**：counter (18), drawer (5), sink (5), table (2)
- **GarbageBag**：无已映射 parent
- **GarbageCan**：无已映射 parent
- **HandTowel**：counter (1)
- **HousePlant**：counter (9), coffee_table (4), shelf (3), table (3), desk (1)
- **Kettle**：counter (10), cabinet (1), table (1)
- **KeyChain**：desk (17), coffee_table (9), chair (4), shelf (4), table (2)
- **Knife**：counter (18), drawer (5), sink (4), table (3)
- **Ladle**：counter (9), drawer (1), table (1)
- **Laptop**：desk (23), coffee_table (10), table (6), bed (4), chair (4), sofa (4)
- **LaundryHamper**：无已映射 parent
- **Lettuce**：counter (10), refrigerator (8), sink (8), table (4)
- **Mirror**：counter (4), sink (2)
- **Newspaper**：sofa (6), table (4), shelf (3), chair (2)
- **Ottoman**：无已映射 parent
- **Painting**：chair (1)
- **Pan**：counter (13), cabinet (4), table (2)
- **PaperTowelRoll**：counter (11), cabinet (1), toilet (1)
- **Pen**：desk (22), table (2), chair (1), counter (1), shelf (1)
- **Pencil**：desk (22), table (3), chair (1), counter (1), shelf (1)
- **PepperShaker**：counter (27), table (2)
- **Pillow**：bed (42), sofa (24), chair (6)
- **Plunger**：无已映射 parent
- **Poster**：shelf (1)
- **Pot**：counter (13), table (4), cabinet (3), sink (1)
- **Potato**：counter (18), table (8), refrigerator (2), sink (2)
- **RemoteControl**：coffee_table (11), sofa (5), chair (2), desk (2)
- **RoomDecor**：无已映射 parent
- **Safe**：cabinet (1)
- **SaltShaker**：counter (27), table (2)
- **ScrubBrush**：无已映射 parent
- **ShelvingUnit**：无已映射 parent
- **ShowerCurtain**：无已映射 parent
- **ShowerDoor**：无已映射 parent
- **ShowerGlass**：counter (1), shelf (1)
- **ShowerHead**：shelf (1)
- **SideTable**：无已映射 parent
- **SoapBar**：counter (16), shelf (4), cabinet (1), toilet (1)
- **SoapBottle**：counter (51), sink (2), cabinet (1), shelf (1), toilet (1)
- **Spatula**：counter (27), drawer (1), sink (1)
- **Spoon**：counter (18), drawer (5), sink (5), table (2)
- **SprayBottle**：cabinet (11), counter (9), toilet (6), shelf (2)
- **Statue**：shelf (31), coffee_table (7), table (5), counter (1)
- **Stool**：无已映射 parent
- **TVStand**：无已映射 parent
- **TableTopDecor**：desk (1)
- **TeddyBear**：bed (8)
- **TennisRacket**：无已映射 parent
- **TissueBox**：shelf (5), counter (4), coffee_table (3), desk (2), cabinet (1)
- **Toaster**：counter (27), table (3)
- **ToiletPaper**：toilet (22), counter (13), cabinet (7), shelf (4), drawer (1)
- **Tomato**：counter (13), refrigerator (6), table (6), sink (5), plate (1)
- **Towel**：无已映射 parent
- **VacuumCleaner**：无已映射 parent
- **Vase**：shelf (50), table (6), counter (3), coffee_table (1)
- **Watch**：coffee_table (6), shelf (2), desk (1)
- **WateringCan**：shelf (3)
- **Window**：counter (2), table (1)
- **WineBottle**：counter (5), table (3), cabinet (1), refrigerator (1)
- **bed**：无已映射 parent
- **book**：desk (19), chair (4), bed (2), counter (2), table (2), coffee_table (1), shelf (1)
- **bowl**：counter (19), table (10), desk (6), shelf (6), coffee_table (4), cabinet (3), chair (1)
- **box**：coffee_table (9), shelf (4), table (3), desk (1)
- **cabinet**：cabinet (6), counter (1)
- **chair**：desk (1), table (1)
- **coffee_table**：无已映射 parent
- **counter**：sink (8), cup (1), plate (1)
- **cup**：counter (16), cabinet (6), table (5), sink (3)
- **desk**：chair (5), desk (1)
- **drawer**：无已映射 parent
- **faucet**：counter (27), sink (27)
- **microwave**：counter (17), table (1)
- **mug**：counter (13), desk (9), sink (7), table (7), cabinet (3)
- **plate**：table (16), counter (15), cabinet (5), sink (3), chair (2), coffee_table (1)
- **refrigerator**：cabinet (2), counter (1), drawer (1)
- **shelf**：desk (2), shelf (1)
- **sink**：counter (16)
- **sofa**：chair (1)
- **table**：chair (36), plate (1)
- **television**：coffee_table (3), shelf (1)
- **toilet**：无已映射 parent

## 房间共现与邻接

- 可用：`否`；house 文件数：`0`
- 说明：AI2-THOR object metadata按房间类别提供对象样本，不包含多房间 house 图。

## 能力先验

能力字段来自 ProcTHOR 的聚合 placement annotations，表示对象类别级先验，不等同于 GraphWorld 的完整动作合法性。
- 可拾取类别：AlarmClock, AluminumFoil, Apple, BaseballBat, BasketBall, Boots, Bottle, Bread, ButterKnife, CD, Candle, CellPhone, Cloth, CreditCard, DishSponge, Dumbbell, Egg, Footstool, Fork, HandTowel, Kettle, KeyChain, Knife, Ladle, Laptop, Lettuce, Newspaper, Pan, PaperTowelRoll, Pen, Pencil, PepperShaker, Pillow, Plunger, Pot, Potato, RemoteControl, SaltShaker, ScrubBrush, SoapBar, SoapBottle, Spatula, Spoon, SprayBottle, Statue, TableTopDecor, TeddyBear, TennisRacket, TissueBox, ToiletPaper, Tomato, Towel, Vase, Watch, WateringCan, WineBottle, book, bowl, box, cup, mug, plate

## 未覆盖项与下一步

- 当前 ProcTHOR 聚合库主要覆盖 Kitchen、LivingRoom、Bedroom、Bathroom；不能据此推导 Hospital、Supermarket、Factory 的领域房间。
- 包内数据库没有生成房屋级 room id、门连接和完整房间共现样本，因此邻接统计只有在 `--root` 提供 house JSON 时才会出现。
- 未映射对象保留在各房间的 `unmapped_objects` 或能力表的 `unmapped::...` 中，需后续补充 ontology mapping，不应直接作为 GraphWorld ObjectTemplate。
- 统计结果是生成 RoomTypeSpec/ObjectTemplate 的先验，还需要 GraphWorld 的任务规则、状态闭环和可解性验证。
