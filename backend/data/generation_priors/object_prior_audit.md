# Object Prior Audit

本报告审计外部 ProcTHOR/AI2-THOR 先验能否接入 GraphWorld，不会自动修改 core。

## 汇总

- 外部先验对象：`114`
- 审计对象总数（含无外部证据 core 模板）：`150`

| 状态 | 数量 | 含义 |
|---|---:|---|
| `needs_mapping` | 78 | 外部标签尚未映射到 ontology，不进入模板生成。 |
| `needs_rule` | 20 | 有模板，但房间/parent/功能先验仍需规则审查。 |
| `no_external_prior` | 36 | core 模板存在，但当前外部数据没有证据；不能据此判定不合理。 |
| `ready` | 16 | 已有 core 模板，且房间、parent、功能先验都能被当前 ontology/runtime 解释。 |

## 需要处理的对象

| 对象 | 状态 | 证据 | 房间 | parent | 功能 | 问题 |
|---|---|---:|---|---|---|---|
| alarmclock | `needs_mapping` | 32 | bedroom | sidetable, dresser, desk, coffee_table, tvstand, shelf, chair, shelvingunit, bed, table, sofa | pickupable | ontology_mapping_missing |
| aluminumfoil | `needs_mapping` | 4 | kitchen | shelf | pickupable | ontology_mapping_missing |
| baseballbat | `needs_mapping` | 16 | bedroom | floor, coffee_table, desk, bed, tvstand, table, sidetable, sofa | pickupable | ontology_mapping_missing |
| basketball | `needs_mapping` | 12 | bedroom | floor, chair, sidetable, coffee_table, bed, box, dresser, shelvingunit, table, sofa | pickupable | ontology_mapping_missing |
| bathtub | `needs_mapping` | 21 | bathroom | floor, counter | receptacle | ontology_mapping_missing |
| bathtubbasin | `needs_mapping` | 19 | bathroom | floor | receptacle | ontology_mapping_missing |
| blinds | `needs_mapping` | 53 | bedroom, kitchen, living_room |  | openable | ontology_mapping_missing |
| bottle | `needs_mapping` | 8 | kitchen | sidetable, table, desk, coffee_table, tvstand, counter, chair, shelf, dresser | pickupable | ontology_mapping_missing |
| bread | `needs_mapping` | 32 | kitchen | counter, table | pickupable | ontology_mapping_missing |
| butterknife | `needs_mapping` | 32 | kitchen | counter, table, sidetable, sink, drawer | pickupable | ontology_mapping_missing |
| candle | `needs_mapping` | 38 | bathroom, living_room | counter, sidetable, dresser, coffee_table, table, toilet, bathtub, tvstand, floor, shelf, garbagecan, cabinet | pickupable, toggleable | ontology_mapping_missing |
| cd | `needs_mapping` | 35 | bedroom | desk, sidetable, dresser, shelf, chair, coffee_table, drawer, table | pickupable | ontology_mapping_missing |
| cellphone | `needs_mapping` | 45 | bedroom, kitchen, living_room | desk, sidetable, dresser, coffee_table, bed, table, chair, counter, shelf, sofa, tvstand, floor | pickupable, toggleable | ontology_mapping_missing |
| clothesdryer | `needs_mapping` | 1 | bathroom |  |  | ontology_mapping_missing |
| coffeemachine | `needs_mapping` | 32 | kitchen | counter, table | moveable, receptacle, toggleable | ontology_mapping_missing |
| creditcard | `needs_mapping` | 68 | bedroom, kitchen, living_room | desk, coffee_table, sidetable, dresser, table, tvstand, counter, floor, shelf, bowl, chair | pickupable | ontology_mapping_missing |
| curtains | `needs_mapping` | 19 | bedroom, kitchen, living_room | floor |  | ontology_mapping_missing |
| desklamp | `needs_mapping` | 55 | bedroom, living_room | sidetable, desk, dresser, coffee_table, table, shelf, tvstand, shelvingunit | moveable, toggleable | ontology_mapping_missing |
| dishsponge | `needs_mapping` | 39 | bathroom, kitchen | counter, sink, sidetable, toilet, cabinet, bathtub, floor | pickupable | ontology_mapping_missing |
| dogbed | `needs_mapping` | 5 | bedroom, living_room | floor | moveable, receptacle | ontology_mapping_missing |
| doorframe | `needs_mapping` | 0 |  |  |  | ontology_mapping_missing |
| doorway | `needs_mapping` | 0 |  |  |  | ontology_mapping_missing |
| dresser | `needs_mapping` | 31 | bathroom, bedroom, living_room | floor | moveable, receptacle | ontology_mapping_missing |
| dumbbell | `needs_mapping` | 6 | bedroom | floor, desk | pickupable | ontology_mapping_missing |
| egg | `needs_mapping` | 32 | kitchen | refrigerator, sink, counter, floor | pickupable | ontology_mapping_missing |
| floorlamp | `needs_mapping` | 33 | living_room | floor | moveable, toggleable | ontology_mapping_missing |
| footstool | `needs_mapping` | 5 | bathroom, bedroom | floor | pickupable, receptacle | ontology_mapping_missing |
| fork | `needs_mapping` | 32 | kitchen | counter, table, sink, plate, drawer, sidetable, desk | pickupable | ontology_mapping_missing |
| garbagebag | `needs_mapping` | 7 | bedroom, kitchen | floor | moveable | ontology_mapping_missing |
| handtowel | `needs_mapping` | 32 | bathroom | handtowelholder, counter | pickupable | ontology_mapping_missing |
| handtowelholder | `needs_mapping` | 47 | bathroom |  | receptacle | ontology_mapping_missing |
| kettle | `needs_mapping` | 17 | kitchen | counter, stoveburner, table, cabinet | openable, pickupable | ontology_mapping_missing |
| keychain | `needs_mapping` | 64 | bedroom, living_room | sidetable, desk, coffee_table, chair, dresser, tvstand, floor, table, shelf | pickupable | ontology_mapping_missing |
| knife | `needs_mapping` | 32 | kitchen | counter, sink, table, drawer | pickupable | ontology_mapping_missing |
| ladle | `needs_mapping` | 13 | kitchen | counter, table, drawer | pickupable | ontology_mapping_missing |
| laundryhamper | `needs_mapping` | 10 | bathroom, bedroom | floor | moveable, openable, receptacle | ontology_mapping_missing |
| mirror | `needs_mapping` | 67 | bathroom, bedroom, kitchen, living_room | counter, sink, dresser, floor |  | ontology_mapping_missing |
| newspaper | `needs_mapping` | 20 | living_room | sofa, table, sidetable, chair, floor, coffee_table, dresser, shelf, desk, ottoman, shelvingunit, tvstand | pickupable | ontology_mapping_missing |
| ottoman | `needs_mapping` | 5 | living_room | floor | moveable, receptacle | ontology_mapping_missing |
| painting | `needs_mapping` | 75 | bathroom, bedroom, living_room | chair, floor |  | ontology_mapping_missing |
| pan | `needs_mapping` | 32 | kitchen | counter, stoveburner, table, cabinet | pickupable, receptacle | ontology_mapping_missing |
| papertowelroll | `needs_mapping` | 16 | bathroom, kitchen | counter, sidetable, toilet, cabinet | pickupable | ontology_mapping_missing |
| peppershaker | `needs_mapping` | 32 | kitchen | counter, table, coffee_table, sidetable | pickupable | ontology_mapping_missing |
| pillow | `needs_mapping` | 76 | bedroom, living_room | bed, sofa, chair, floor, sidetable | pickupable | ontology_mapping_missing |
| plunger | `needs_mapping` | 32 | bathroom | floor | pickupable | ontology_mapping_missing |
| poster | `needs_mapping` | 10 | bedroom | shelf |  | ontology_mapping_missing |
| pot | `needs_mapping` | 32 | kitchen | counter, table, sidetable, stoveburner, coffee_table, desk, cabinet, shelvingunit, sink, dresser, tvstand | pickupable, receptacle | ontology_mapping_missing |
| roomdecor | `needs_mapping` | 10 | living_room | floor | moveable | ontology_mapping_missing |
| safe | `needs_mapping` | 11 | bedroom, kitchen, living_room | floor, dresser, cabinet | moveable, openable, receptacle | ontology_mapping_missing |
| saltshaker | `needs_mapping` | 32 | kitchen | counter, table, coffee_table, sidetable | pickupable | ontology_mapping_missing |
| scrubbrush | `needs_mapping` | 32 | bathroom | floor | pickupable | ontology_mapping_missing |
| showercurtain | `needs_mapping` | 15 | bathroom | bathtub, floor, towelholder, bathtubbasin, sink | openable | ontology_mapping_missing |
| showerdoor | `needs_mapping` | 17 | bathroom | floor | openable | ontology_mapping_missing |
| showerglass | `needs_mapping` | 13 | bathroom | floor, counter, shelf |  | ontology_mapping_missing |
| showerhead | `needs_mapping` | 27 | bathroom | floor, bathtub, shelf | toggleable | ontology_mapping_missing |
| soapbar | `needs_mapping` | 32 | bathroom | counter, bathtub, shelf, dresser, toilet, cabinet | pickupable | ontology_mapping_missing |
| soapbottle | `needs_mapping` | 64 | bathroom, kitchen | counter, sidetable, sink, toilet, shelf, bathtub, cabinet | pickupable | ontology_mapping_missing |
| spatula | `needs_mapping` | 32 | kitchen | counter, pot, sink, stoveburner, drawer | pickupable | ontology_mapping_missing |
| spoon | `needs_mapping` | 32 | kitchen | counter, sink, drawer, table | pickupable | ontology_mapping_missing |
| spraybottle | `needs_mapping` | 35 | bathroom, kitchen | counter, sidetable, toilet, cabinet, dresser, coffee_table, desk, table, shelvingunit, floor, shelf | pickupable | ontology_mapping_missing |
| statue | `needs_mapping` | 67 | bedroom, kitchen, living_room | sidetable, shelf, coffee_table, table, dresser, floor, desk, tvstand, shelvingunit, counter | pickupable | ontology_mapping_missing |
| stoveburner | `needs_mapping` | 123 | kitchen |  | receptacle | ontology_mapping_missing |
| tabletopdecor | `needs_mapping` | 2 | bedroom | desk | pickupable | ontology_mapping_missing |
| teddybear | `needs_mapping` | 11 | bedroom | bed, sidetable, floor, chair, desk | pickupable | ontology_mapping_missing |
| tennisracket | `needs_mapping` | 11 | bedroom | floor, coffee_table, sidetable, bed, table | pickupable | ontology_mapping_missing |
| tissuebox | `needs_mapping` | 25 | bathroom, bedroom, living_room | sidetable, counter, coffee_table, shelf, desk, dresser, tvstand, floor, cabinet | pickupable | ontology_mapping_missing |
| toaster | `needs_mapping` | 32 | kitchen | counter, table | moveable, receptacle, toggleable | ontology_mapping_missing |
| toiletpaper | `needs_mapping` | 62 | bathroom | toilet, counter, garbagecan, floor, cabinet, toiletpaperhanger, shelf, drawer, bathtub | pickupable | ontology_mapping_missing |
| toiletpaperhanger | `needs_mapping` | 32 | bathroom |  | receptacle | ontology_mapping_missing |
| towel | `needs_mapping` | 32 | bathroom | towelholder, floor | pickupable | ontology_mapping_missing |
| towelholder | `needs_mapping` | 40 | bathroom |  | receptacle | ontology_mapping_missing |
| tvstand | `needs_mapping` | 16 | living_room | floor | moveable, receptacle | ontology_mapping_missing |
| vacuumcleaner | `needs_mapping` | 2 | bedroom | floor | moveable | ontology_mapping_missing |
| vase | `needs_mapping` | 72 | bedroom, kitchen, living_room | shelf, sidetable, table, coffee_table, dresser, floor, desk, counter, shelvingunit, tvstand, plate | pickupable | ontology_mapping_missing |
| watch | `needs_mapping` | 21 | bedroom, living_room | coffee_table, sidetable, tvstand, desk, dresser, shelf, chair, table | pickupable | ontology_mapping_missing |
| wateringcan | `needs_mapping` | 15 | living_room | floor, shelf | pickupable | ontology_mapping_missing |
| window | `needs_mapping` | 182 | bathroom, bedroom, kitchen, living_room | counter, floor, table, sidetable |  | ontology_mapping_missing |
| winebottle | `needs_mapping` | 11 | kitchen | counter, table, refrigerator, cabinet | pickupable | ontology_mapping_missing |
| bed | `needs_rule` | 34 | bedroom | floor | moveable, receptacle | functional_class_not_supported |
| book | `needs_rule` | 43 | bedroom, kitchen, living_room | desk, dresser, coffee_table, chair, sidetable, bed, table, sofa, counter, shelvingunit, tvstand, shelf | openable, pickupable | parent_rule_unmapped, functional_class_not_supported |
| bowl | `needs_rule` | 53 | bedroom, kitchen, living_room | table, counter, coffee_table, desk, sidetable, chair, shelf, dresser, tvstand, cabinet, plate | pickupable, receptacle | parent_rule_unmapped |
| box | `needs_rule` | 46 | bedroom, living_room | coffee_table, floor, sidetable, table, tvstand, shelvingunit, shelf, chair, desk, bed | openable, pickupable, receptacle | parent_rule_unmapped, functional_class_not_supported |
| clothes | `needs_rule` | 42 | bathroom, bedroom | counter, toilet, floor, bathtubbasin, sidetable, shelf, bathtub, sink, cabinet | pickupable | parent_rule_unmapped |
| computer | `needs_rule` | 67 | bedroom, living_room | desk, coffee_table, table, bed, sofa, chair, dresser, sidetable, tvstand, floor | moveable, openable, pickupable, toggleable | parent_rule_unmapped, functional_class_not_supported |
| counter | `needs_rule` | 103 | bathroom, bedroom, kitchen | sink, footstool, plate, cup, pan | receptacle | parent_rule_unmapped |
| cup | `needs_rule` | 32 | kitchen | counter, sidetable, table, coffee_table, desk, sink, cabinet, dresser, tvstand, box | pickupable, receptacle | parent_rule_unmapped |
| faucet | `needs_rule` | 95 | bathroom, kitchen | counter, sink, bathtub, bathtubbasin, floor | toggleable | parent_rule_unmapped |
| fruit | `needs_rule` | 32 | kitchen | counter, table, sidetable, desk, refrigerator, coffee_table, chair, sink, bed, sofa, plate, shelvingunit, tvstand | pickupable | parent_rule_unmapped |
| microwave | `needs_rule` | 32 | kitchen | counter, table | moveable, openable, receptacle, toggleable | functional_class_not_supported |
| mug | `needs_rule` | 49 | bedroom, kitchen | sidetable, desk, table, counter, sink, coffee_table, coffeemachine, dresser, cabinet, tvstand, chair | pickupable, receptacle | parent_rule_unmapped |
| plant | `needs_rule` | 55 | bathroom, bedroom, kitchen, living_room | sidetable, coffee_table, table, counter, dresser, tvstand, desk, stool, shelvingunit, shelf, floor | moveable | parent_rule_unmapped, functional_class_not_supported |
| plate | `needs_rule` | 43 | kitchen, living_room | table, counter, coffee_table, sidetable, desk, sink, cabinet, chair, dresser, tvstand | pickupable, receptacle | parent_rule_unmapped |
| refrigerator | `needs_rule` | 32 | kitchen | floor, cabinet, counter, drawer | openable, receptacle | functional_class_not_supported |
| remote | `needs_rule` | 36 | bedroom, living_room | coffee_table, sidetable, sofa, chair, dresser, tvstand, desk, table, floor, bed, ottoman | pickupable | parent_rule_unmapped |
| stationery | `needs_rule` | 81 | bedroom, kitchen, living_room | desk, sidetable, dresser, table, coffee_table, chair, counter, box, floor, shelf, sofa, tvstand | pickupable | parent_rule_unmapped |
| television | `needs_rule` | 33 | bedroom, living_room | tvstand, dresser, coffee_table, shelf, floor, sidetable | moveable, toggleable | parent_rule_unmapped |
| toilet | `needs_rule` | 32 | bathroom | floor, toiletpaperhanger | openable, receptacle | parent_rule_unmapped, functional_class_not_supported |
| trash_bin | `needs_rule` | 128 | bathroom, bedroom, kitchen, living_room | floor | moveable, receptacle | functional_class_not_supported |

## 判定边界

- `ready` 只表示可以进入候选生成阶段，不表示已经自动写入 `ObjectTemplate`。
- `needs_template` 与 `needs_mapping` 是最优先的补齐项。
- `needs_rule` 需要人工确认 `allowed_rooms`、`allowed_parents` 和 `functional_class`，然后再做任务/PDDL 可解性验证。
- 当前家庭数据不能证明 Office、Hospital、Supermarket、Factory 的领域先验。
