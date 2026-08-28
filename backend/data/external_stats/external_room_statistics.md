# 外部数据统计报告

## 数据源

- 生成时间：`2026-08-22T08:31:06.297802+00:00`
- ontology 版本：`0.1`
- 原始数据未复制进仓库；输出仅包含派生统计。
- 许可：ProcTHOR、AI2-THOR 和 PRIOR 的原始数据/代码许可仍需按上游条款执行。

## procthor

- **bathroom**：candle (2), cloth (2), faucet (2), garbagecan (2), handtowel (2), handtowelholder (2), lightswitch (2), plunger (2), scrubbrush (2), showercurtain (2), showerhead (2), soapbar (2)
- **bedroom**：chair (3), alarmclock (2), baseballbat (2), bed (2), blinds (2), book (2), bowl (2), box (2), cd (2), cellphone (2), creditcard (2), desk (2)
- **kitchen**：apple (2), bowl (2), bread (2), butterknife (2), chair (2), coffeemachine (2), counter (2), cup (2), dishsponge (2), egg (2), faucet (2), fork (2)
- **living_room**：chair (4), box (2), creditcard (2), desklamp (2), dresser (2), floorlamp (2), garbagecan (2), keychain (2), laptop (2), lightswitch (2), newspaper (2), pillow (2)
- 房间共现/邻接：`不可用`；These databases contain room-weight priors, not multi-room house instances or room adjacency edges.
- 可拾取对象类别：alarmclock, aluminumfoil, apple, baseballbat, basketball, book, boots, bottle, bowl, box, bread, butterknife, candle, cd, cellphone, cloth, creditcard, cup, dishsponge, dumbbell, egg, footstool, fork, handtowel, kettle, keychain, knife, ladle, laptop, lettuce

## ai2thor

- **bathroom**：sink (89), drawer (68), cabinet (64), toiletpaper (60), faucet (59), handtowelholder (45), towelholder (38), mirror (32), floor (30), towel (30), handtowel (30), plunger (30)
- **bedroom**：drawer (201), shelf (116), window (45), pillow (42), blinds (41), chair (38), desklamp (35), cd (33), bed (32), floor (30), book (30), laptop (30)
- **kitchen**：cabinet (418), drawer (174), stoveburner (123), stoveknob (123), counter (71), sink (60), window (36), faucet (32), floor (30), knife (30), microwave (30), bread (30)
- **living_room**：drawer (118), chair (111), shelf (104), window (75), statue (54), sidetable (54), painting (53), vase (46), sofa (36), houseplant (32), floorlamp (31), floor (30)
- 房间样本数：bathroom=30, bedroom=30, kitchen=30, living_room=30
- 房间共现/邻接：`不可用`；This metadata export is grouped by single room family; it has no multi-room scene adjacency graph.
- 可拾取对象类别：alarmclock, aluminumfoil, apple, baseballbat, basketball, book, boots, bottle, bowl, box, bread, butterknife, candle, cd, cellphone, cloth, creditcard, cup, dishsponge, dumbbell, egg, footstool, fork, handtowel, kettle, keychain, knife, ladle, laptop, lettuce

## 结论与未覆盖项

- ProcTHOR 与随包 AI2-THOR metadata 均主要覆盖 Kitchen、LivingRoom、Bedroom、Bathroom；不能据此推导 Hospital、Supermarket、Factory 的领域房间。
- 当前输入不含多房间 house 实例，因此房间邻接和跨房间共现被明确标记为不可用，不应当当作零频率。
- 统计是 RoomTypeSpec/ObjectTemplate 的外部先验，仍需 GraphWorld 的任务规则、状态转移和 PDDL/可解性验证。
- 未映射对象保留为原始归一化标签，后续应补 ontology mapping 后再生成 core 模板。
