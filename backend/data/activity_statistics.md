# VirtualHome / ALFRED 活动统计

本报告只统计活动、任务和动作先验，不用于推导房间几何。

## virtualhome

- 数据可用：`False`
- 记录数：`0`
- 说明：未提供本地数据目录；没有把缺失数据当成零统计。

## alfred

- 数据可用：`True`
- 记录数：`8051`
- 高频任务类型：pick_two_obj_and_place (1165), pick_and_place_simple (1110), pick_and_place_with_movable_recep (1055), pick_cool_then_place_in_recep (994), pick_heat_then_place_in_recep (994), pick_clean_then_place_in_recep (968), look_at_obj_in_light (794)
- 高频动作词：turn (84924), walk (36234), pick (32458), go (23395), put (22378), place (17591), take (12972), move (11189), slice (9819), open (9141), close (7418), look (2423), heat (1507), clean (649), cool (513), drop (375), pickup (22)
- 高频对象：SoapBottle (10741), Bowl (9536), Mug (9520), DishSponge (8918), Plate (8666), Apple (8514), PepperShaker (8487), Tomato (8442), Spoon (8380), Egg (8380), Potato (8373), Fork (8344), Cup (8329), SaltShaker (8329), Knife (8232), Spatula (8175), ButterKnife (7743), Lettuce (7578), Bread (6663), Pot (6456)
- 说明：动作/活动先验，不用于推导房间几何。

## 用途

- ALFRED 统计用于任务模板、动作序列和前置条件候选。
- VirtualHome 统计用于 NPC 活动、角色日程和活动-房间关联候选。
- 两者都不能替代 ProcTHOR/3D-FRONT 的房间和物体空间统计。
