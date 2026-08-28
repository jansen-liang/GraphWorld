# 缺失模板人工决策清单

以下对象无法在不改变语义的情况下自动映射到现有 `OBJECT_LIBRARY`。每项需要选择：复用已有模板、创建新模板，或 deferred/unsupported。

| 原始对象 | 证据 | 房间 | parent | 功能 | 任务引用 |
|---|---:|---|---|---|---|
| window | 182 | bathroom, bedroom, kitchen, living_room | counter, floor, table, sidetable |  | - |
| stoveburner | 123 | kitchen |  | receptacle | - |
| pillow | 76 | bedroom, living_room | bed, sofa, chair, floor, sidetable | pickupable | - |
| painting | 75 | bathroom, bedroom, living_room | chair, floor |  | - |
| vase | 72 | bedroom, kitchen, living_room | shelf, sidetable, table, coffee_table, dresser, floor, desk, counter, shelvingunit, tvstand, plate | pickupable | - |
| creditcard | 68 | bedroom, kitchen, living_room | desk, coffee_table, sidetable, dresser, table, tvstand, counter, floor, shelf, bowl, chair | pickupable | - |
| mirror | 67 | bathroom, bedroom, kitchen, living_room | counter, sink, dresser, floor |  | - |
| statue | 67 | bedroom, kitchen, living_room | sidetable, shelf, coffee_table, table, dresser, floor, desk, tvstand, shelvingunit, counter | pickupable | - |
| keychain | 64 | bedroom, living_room | sidetable, desk, coffee_table, chair, dresser, tvstand, floor, table, shelf | pickupable | - |
| soapbottle | 64 | bathroom, kitchen | counter, sidetable, sink, toilet, shelf, bathtub, cabinet | pickupable | - |
| toiletpaper | 62 | bathroom | toilet, counter, garbagecan, floor, cabinet, toiletpaperhanger, shelf, drawer, bathtub | pickupable | - |
| desklamp | 55 | bedroom, living_room | sidetable, desk, dresser, coffee_table, table, shelf, tvstand, shelvingunit | moveable, toggleable | - |
| blinds | 53 | bedroom, kitchen, living_room |  | openable | - |
| handtowelholder | 47 | bathroom |  | receptacle | - |
| cellphone | 45 | bedroom, kitchen, living_room | desk, sidetable, dresser, coffee_table, bed, table, chair, counter, shelf, sofa, tvstand, floor | pickupable, toggleable | - |
| towelholder | 40 | bathroom |  | receptacle | - |
| dishsponge | 39 | bathroom, kitchen | counter, sink, sidetable, toilet, cabinet, bathtub, floor | pickupable | - |
| candle | 38 | bathroom, living_room | counter, sidetable, dresser, coffee_table, table, toilet, bathtub, tvstand, floor, shelf, garbagecan, cabinet | pickupable, toggleable | - |
| cd | 35 | bedroom | desk, sidetable, dresser, shelf, chair, coffee_table, drawer, table | pickupable | - |
| spraybottle | 35 | bathroom, kitchen | counter, sidetable, toilet, cabinet, dresser, coffee_table, desk, table, shelvingunit, floor, shelf | pickupable | - |
| floorlamp | 33 | living_room | floor | moveable, toggleable | - |
| alarmclock | 32 | bedroom | sidetable, dresser, desk, coffee_table, tvstand, shelf, chair, shelvingunit, bed, table, sofa | pickupable | - |
| bread | 32 | kitchen | counter, table | pickupable | - |
| butterknife | 32 | kitchen | counter, table, sidetable, sink, drawer | pickupable | - |
| coffeemachine | 32 | kitchen | counter, table | moveable, receptacle, toggleable | - |
| egg | 32 | kitchen | refrigerator, sink, counter, floor | pickupable | - |
| fork | 32 | kitchen | counter, table, sink, plate, drawer, sidetable, desk | pickupable | - |
| handtowel | 32 | bathroom | handtowelholder, counter | pickupable | - |
| knife | 32 | kitchen | counter, sink, table, drawer | pickupable | - |
| pan | 32 | kitchen | counter, stoveburner, table, cabinet | pickupable, receptacle | - |
| peppershaker | 32 | kitchen | counter, table, coffee_table, sidetable | pickupable | - |
| plunger | 32 | bathroom | floor | pickupable | - |
| pot | 32 | kitchen | counter, table, sidetable, stoveburner, coffee_table, desk, cabinet, shelvingunit, sink, dresser, tvstand | pickupable, receptacle | - |
| saltshaker | 32 | kitchen | counter, table, coffee_table, sidetable | pickupable | - |
| scrubbrush | 32 | bathroom | floor | pickupable | - |
| soapbar | 32 | bathroom | counter, bathtub, shelf, dresser, toilet, cabinet | pickupable | - |
| spatula | 32 | kitchen | counter, pot, sink, stoveburner, drawer | pickupable | - |
| spoon | 32 | kitchen | counter, sink, drawer, table | pickupable | - |
| toaster | 32 | kitchen | counter, table | moveable, receptacle, toggleable | - |
| toiletpaperhanger | 32 | bathroom |  | receptacle | - |
| towel | 32 | bathroom | towelholder, floor | pickupable | - |
| dresser | 31 | bathroom, bedroom, living_room | floor | moveable, receptacle | - |
| showerhead | 27 | bathroom | floor, bathtub, shelf | toggleable | - |
| tissuebox | 25 | bathroom, bedroom, living_room | sidetable, counter, coffee_table, shelf, desk, dresser, tvstand, floor, cabinet | pickupable | - |
| bathtub | 21 | bathroom | floor, counter | receptacle | - |
| watch | 21 | bedroom, living_room | coffee_table, sidetable, tvstand, desk, dresser, shelf, chair, table | pickupable | - |
| newspaper | 20 | living_room | sofa, table, sidetable, chair, floor, coffee_table, dresser, shelf, desk, ottoman, shelvingunit, tvstand | pickupable | - |
| bathtubbasin | 19 | bathroom | floor | receptacle | - |
| curtains | 19 | bedroom, kitchen, living_room | floor |  | - |
| kettle | 17 | kitchen | counter, stoveburner, table, cabinet | openable, pickupable | - |
| showerdoor | 17 | bathroom | floor | openable | - |
| baseballbat | 16 | bedroom | floor, coffee_table, desk, bed, tvstand, table, sidetable, sofa | pickupable | - |
| papertowelroll | 16 | bathroom, kitchen | counter, sidetable, toilet, cabinet | pickupable | - |
| tvstand | 16 | living_room | floor | moveable, receptacle | - |
| showercurtain | 15 | bathroom | bathtub, floor, towelholder, bathtubbasin, sink | openable | - |
| wateringcan | 15 | living_room | floor, shelf | pickupable | - |
| ladle | 13 | kitchen | counter, table, drawer | pickupable | - |
| showerglass | 13 | bathroom | floor, counter, shelf |  | - |
| basketball | 12 | bedroom | floor, chair, sidetable, coffee_table, bed, box, dresser, shelvingunit, table, sofa | pickupable | - |
| safe | 11 | bedroom, kitchen, living_room | floor, dresser, cabinet | moveable, openable, receptacle | - |
| teddybear | 11 | bedroom | bed, sidetable, floor, chair, desk | pickupable | - |
| tennisracket | 11 | bedroom | floor, coffee_table, sidetable, bed, table | pickupable | - |
| winebottle | 11 | kitchen | counter, table, refrigerator, cabinet | pickupable | - |
| laundryhamper | 10 | bathroom, bedroom | floor | moveable, openable, receptacle | - |
| poster | 10 | bedroom | shelf |  | - |
| roomdecor | 10 | living_room | floor | moveable | - |
| bottle | 8 | kitchen | sidetable, table, desk, coffee_table, tvstand, counter, chair, shelf, dresser | pickupable | - |
| garbagebag | 7 | bedroom, kitchen | floor | moveable | - |
| dumbbell | 6 | bedroom | floor, desk | pickupable | - |
| dogbed | 5 | bedroom, living_room | floor | moveable, receptacle | - |
| footstool | 5 | bathroom, bedroom | floor | pickupable, receptacle | - |
| ottoman | 5 | living_room | floor | moveable, receptacle | - |
| aluminumfoil | 4 | kitchen | shelf | pickupable | - |
| tabletopdecor | 2 | bedroom | desk | pickupable | - |
| vacuumcleaner | 2 | bedroom | floor | moveable | - |
| clothesdryer | 1 | bathroom |  |  | - |
| doorframe | 0 |  |  |  | - |
| doorway | 0 |  |  |  | - |

## 决策字段

- `reuse:<template>`：复用已有模板并补 alias。
- `new_template`：进入 ObjectTemplate 设计。
- `deferred`：暂不生成，仅保留外部统计。
- `unsupported`：当前 GraphWorld 运行时不支持。
