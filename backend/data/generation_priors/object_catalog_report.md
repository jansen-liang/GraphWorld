# Canonical Object Catalog Report

- 正式模板：`115`
- 外部候选标签：`113`

| 归宿 | 数量 |
|---|---:|
| `alias` | 3 |
| `deferred` | 18 |
| `new_template_candidate` | 14 |
| `template` | 78 |

| 外部标签 | 归宿 | canonical | 证据 | 房间 | parent | 原因 |
|---|---|---|---:|---|---|---|
| alarmclock | `deferred` |  | 0 | bedroom | bed, chair, coffee_table, desk, dresser, shelf, sofa, table, tvstand | 闹钟需要周期计时和 NPC 联动 |
| aluminumfoil | `template` | aluminumfoil | 0 | kitchen | shelf | already present in canonical library |
| baseballbat | `template` | baseballbat | 0 | bedroom | bed, coffee_table, desk, floor, sofa, table, tvstand | already present in canonical library |
| basketball | `template` | basketball | 0 | bedroom | bed, box, chair, coffee_table, dresser, floor, shelf, sofa, table | already present in canonical library |
| bathtub | `template` | bathtub | 0 | bathroom | counter, floor | already present in canonical library |
| bathtubbasin | `template` | bathtubbasin | 0 | bathroom | floor | already present in canonical library |
| bed | `template` | bed | 0 | bedroom | floor | already present in canonical library |
| blinds | `deferred` |  | 0 | bedroom, kitchen, living_room |  | 百叶窗需要透光/遮挡或环境交换语义 |
| book | `template` | book | 0 | bedroom, kitchen, living_room | bed, chair, coffee_table, counter, desk, dresser, shelf, sofa, table, tvstand | already present in canonical library |
| bottle | `template` | bottle | 0 | kitchen | chair, coffee_table, counter, desk, dresser, shelf, table, tvstand | already present in canonical library |
| bowl | `template` | bowl | 0 | bedroom, kitchen, living_room | cabinet, chair, coffee_table, counter, desk, dresser, plate, shelf, table, tvstand | already present in canonical library |
| box | `template` | box | 0 | bedroom, living_room | bed, chair, coffee_table, desk, floor, shelf, table, tvstand | already present in canonical library |
| bread | `template` | bread | 0 | kitchen | counter, table | already present in canonical library |
| butterknife | `deferred` |  | 0 | kitchen | counter, drawer, sink, table | 黄油刀需要切割效果 |
| button | `template` | button | 0 | bathroom, bedroom, kitchen, living_room |  | already present in canonical library |
| cabinet | `template` | cabinet | 0 | bathroom, bedroom, kitchen, living_room | cabinet, counter, floor | already present in canonical library |
| candle | `deferred` |  | 0 | bathroom, living_room | bathtub, cabinet, coffee_table, counter, dresser, floor, shelf, table, toilet, trash_bin, tvstand | 蜡烛需要点火、燃烧计时和光照效果 |
| cart | `template` | cart | 0 | living_room |  | already present in canonical library |
| cd | `deferred` |  | 0 | bedroom | chair, coffee_table, desk, drawer, dresser, shelf, table | CD 需要播放器和播放状态 |
| cellphone | `template` | cellphone | 0 | bedroom, kitchen, living_room | bed, chair, coffee_table, counter, desk, dresser, floor, shelf, sofa, table, tvstand | already present in canonical library |
| chair | `template` | chair | 0 | bedroom, kitchen, living_room | desk, floor, table | already present in canonical library |
| clothes | `template` | clothes | 0 | bathroom, bedroom | bathtub, bathtubbasin, cabinet, counter, floor, shelf, sink, table, toilet | already present in canonical library |
| clothesdryer | `new_template_candidate` |  | 0 | bathroom |  | needs explicit states, capabilities, and placement policy |
| coffee_table | `template` | coffee_table | 0 | bedroom, living_room | floor | already present in canonical library |
| coffeemachine | `deferred` |  | 0 | kitchen | counter, table | 咖啡机需要制作饮品和资源消耗 |
| computer | `template` | computer | 0 | bedroom, living_room | bed, chair, coffee_table, desk, dresser, floor, sofa, table, tvstand | already present in canonical library |
| counter | `template` | counter | 0 | bathroom, bedroom, kitchen | cup, footstool, pan, plate, sink | already present in canonical library |
| creditcard | `deferred` |  | 0 | bedroom, kitchen, living_room | bowl, chair, coffee_table, counter, desk, dresser, floor, shelf, table, tvstand | 信用卡需要刷卡机和支付系统 |
| cup | `template` | cup | 0 | kitchen | box, cabinet, coffee_table, counter, desk, dresser, sink, table, tvstand | already present in canonical library |
| curtains | `new_template_candidate` |  | 0 | bedroom, kitchen, living_room | floor | needs explicit states, capabilities, and placement policy |
| desk | `template` | desk | 0 | bedroom, living_room | chair, desk, floor | already present in canonical library |
| desklamp | `deferred` |  | 0 | bedroom, living_room | coffee_table, desk, dresser, shelf, table, tvstand | 台灯需要光照传播或可见性效果 |
| dishsponge | `deferred` |  | 0 | bathroom, kitchen | bathtub, cabinet, counter, floor, sink, table, toilet | 海绵需要湿度和工具化清洁效果 |
| dogbed | `template` | dogbed | 0 | bedroom, living_room | floor | already present in canonical library |
| drawer | `template` | drawer | 0 | bathroom, bedroom, kitchen, living_room | floor | already present in canonical library |
| dresser | `template` | dresser | 0 | bathroom, bedroom, living_room | floor | already present in canonical library |
| dumbbell | `template` | dumbbell | 0 | bedroom | desk, floor | already present in canonical library |
| egg | `template` | egg | 0 | kitchen | counter, floor, refrigerator, sink | already present in canonical library |
| faucet | `template` | faucet | 0 | bathroom, kitchen | bathtub, bathtubbasin, counter, floor, sink | already present in canonical library |
| floor | `new_template_candidate` |  | 0 | bathroom, bedroom, kitchen, living_room | cabinet, trash_bin | not yet assigned a canonical runtime meaning |
| floorlamp | `deferred` |  | 0 | living_room | floor | 落地灯需要光照传播或可见性效果 |
| footstool | `template` | footstool | 0 | bathroom, bedroom | floor | already present in canonical library |
| fork | `template` | fork | 0 | kitchen | counter, desk, drawer, plate, sink, table | already present in canonical library |
| fruit | `template` | fruit | 0 | kitchen | bed, chair, coffee_table, counter, desk, plate, refrigerator, shelf, sink, sofa, table, tvstand | already present in canonical library |
| garbagebag | `template` | garbagebag | 0 | bedroom, kitchen | floor | already present in canonical library |
| handtowel | `alias` | towel | 0 | bathroom | counter, handtowelholder | same holder/towel semantics |
| handtowelholder | `alias` | towel_holder | 0 | bathroom |  | same holder/towel semantics |
| kettle | `new_template_candidate` |  | 0 | kitchen | cabinet, counter, stoveburner, table | needs explicit states, capabilities, and placement policy |
| keychain | `template` | keychain | 0 | bedroom, living_room | chair, coffee_table, desk, dresser, floor, shelf, table, tvstand | already present in canonical library |
| knife | `deferred` |  | 0 | kitchen | counter, drawer, sink, table | 刀具需要切割工具使用规则 |
| knob | `template` | knob | 0 | kitchen |  | already present in canonical library |
| ladle | `template` | ladle | 0 | kitchen | counter, drawer, table | already present in canonical library |
| laundryhamper | `template` | laundryhamper | 0 | bathroom, bedroom | floor | already present in canonical library |
| microwave | `template` | microwave | 0 | kitchen | counter, table | already present in canonical library |
| mirror | `template` | mirror | 0 | bathroom, bedroom, kitchen, living_room | counter, dresser, floor, sink | already present in canonical library |
| mug | `template` | mug | 0 | bedroom, kitchen | cabinet, chair, coffee_table, coffeemachine, counter, desk, dresser, sink, table, tvstand | already present in canonical library |
| newspaper | `template` | newspaper | 0 | living_room | chair, coffee_table, desk, dresser, floor, ottoman, shelf, sofa, table, tvstand | already present in canonical library |
| ottoman | `template` | ottoman | 0 | living_room | floor | already present in canonical library |
| painting | `template` | painting | 0 | bathroom, bedroom, living_room | chair, floor | already present in canonical library |
| pan | `deferred` |  | 0 | kitchen | cabinet, counter, stoveburner, table | 锅具需要加热、容量和烹饪状态 |
| papertowelroll | `new_template_candidate` |  | 0 | bathroom, kitchen | cabinet, counter, table, toilet | needs explicit states, capabilities, and placement policy |
| peppershaker | `template` | peppershaker | 0 | kitchen | coffee_table, counter, table | already present in canonical library |
| pillow | `template` | pillow | 0 | bedroom, living_room | bed, chair, floor, sofa, table | already present in canonical library |
| plant | `template` | plant | 0 | bathroom, bedroom, kitchen, living_room | coffee_table, counter, desk, dresser, floor, seat, shelf, table, tvstand | already present in canonical library |
| plate | `template` | plate | 0 | kitchen, living_room | cabinet, chair, coffee_table, counter, desk, dresser, sink, table, tvstand | already present in canonical library |
| plunger | `template` | plunger | 0 | bathroom | floor | already present in canonical library |
| poster | `template` | poster | 0 | bedroom | shelf | already present in canonical library |
| pot | `deferred` |  | 0 | kitchen | cabinet, coffee_table, counter, desk, dresser, shelf, sink, stoveburner, table, tvstand | 锅具需要加热、容量和烹饪状态 |
| refrigerator | `template` | refrigerator | 0 | kitchen | cabinet, counter, drawer, floor | already present in canonical library |
| remote | `template` | remote | 0 | bedroom, living_room | bed, chair, coffee_table, desk, dresser, floor, ottoman, sofa, table, tvstand | already present in canonical library |
| roomdecor | `template` | roomdecor | 0 | living_room | floor | already present in canonical library |
| safe | `new_template_candidate` |  | 0 | bedroom, kitchen, living_room | cabinet, dresser, floor | needs explicit states, capabilities, and placement policy |
| saltshaker | `template` | saltshaker | 0 | kitchen | coffee_table, counter, table | already present in canonical library |
| scrubbrush | `template` | scrubbrush | 0 | bathroom | floor | already present in canonical library |
| seat | `template` | seat | 0 | bedroom, kitchen, living_room | floor | already present in canonical library |
| shelf | `template` | shelf | 0 | bathroom, bedroom, kitchen, living_room | desk, floor, shelf | already present in canonical library |
| shoes | `template` | shoes | 0 | bedroom, living_room | floor | already present in canonical library |
| showercurtain | `new_template_candidate` |  | 0 | bathroom | bathtub, bathtubbasin, floor, sink, towelholder | needs explicit states, capabilities, and placement policy |
| showerdoor | `new_template_candidate` |  | 0 | bathroom | floor | needs explicit states, capabilities, and placement policy |
| showerglass | `new_template_candidate` |  | 0 | bathroom | counter, floor, shelf | needs explicit states, capabilities, and placement policy |
| showerhead | `new_template_candidate` |  | 0 | bathroom | bathtub, floor, shelf | not yet assigned a canonical runtime meaning |
| sink | `template` | sink | 0 | bathroom, kitchen | counter, floor | already present in canonical library |
| soapbar | `template` | soapbar | 0 | bathroom | bathtub, cabinet, counter, dresser, shelf, toilet | already present in canonical library |
| soapbottle | `deferred` |  | 0 | bathroom, kitchen | bathtub, cabinet, counter, shelf, sink, table, toilet | 肥皂瓶需要分配和消耗语义 |
| sofa | `template` | sofa | 0 | bedroom, living_room | chair, floor, table | already present in canonical library |
| spatula | `new_template_candidate` |  | 0 | kitchen | counter, drawer, pot, sink, stoveburner | needs explicit states, capabilities, and placement policy |
| spoon | `template` | spoon | 0 | kitchen | counter, drawer, sink, table | already present in canonical library |
| spraybottle | `deferred` |  | 0 | bathroom, kitchen | cabinet, coffee_table, counter, desk, dresser, floor, shelf, table, toilet | 喷雾需要液体、按压和目标状态效果 |
| stationery | `template` | stationery | 0 | bedroom, kitchen, living_room | box, chair, coffee_table, counter, desk, dresser, floor, shelf, sofa, table, tvstand | already present in canonical library |
| statue | `template` | statue | 0 | bedroom, kitchen, living_room | coffee_table, counter, desk, dresser, floor, shelf, table, tvstand | already present in canonical library |
| stoveburner | `deferred` |  | 0 | kitchen |  | 炉灶组件需要 heat source 和烹饪闭环 |
| table | `template` | table | 0 | bathroom, bedroom, kitchen, living_room | chair, floor, plate | already present in canonical library |
| tabletopdecor | `template` | tabletopdecor | 0 | bedroom | desk | already present in canonical library |
| teddybear | `template` | teddybear | 0 | bedroom | bed, chair, desk, floor, table | already present in canonical library |
| television | `template` | television | 0 | bedroom, living_room | coffee_table, dresser, floor, shelf, table, tvstand | already present in canonical library |
| tennisracket | `template` | tennisracket | 0 | bedroom | bed, coffee_table, floor, table | already present in canonical library |
| tissuebox | `template` | tissuebox | 0 | bathroom, bedroom, living_room | cabinet, coffee_table, counter, desk, dresser, floor, shelf, table, tvstand | already present in canonical library |
| toaster | `new_template_candidate` |  | 0 | kitchen | counter, table | needs explicit states, capabilities, and placement policy |
| toilet | `template` | toilet | 0 | bathroom | floor, toiletpaperhanger | already present in canonical library |
| toiletpaper | `deferred` |  | 0 | bathroom | bathtub, cabinet, counter, drawer, floor, shelf, toilet, toiletpaperhanger, trash_bin | 卫生纸需要使用和消耗语义 |
| toiletpaperhanger | `new_template_candidate` |  | 0 | bathroom |  | not yet assigned a canonical runtime meaning |
| towel | `template` | towel | 0 | bathroom | floor, towelholder | already present in canonical library |
| towelholder | `alias` | towel_holder | 0 | bathroom |  | same holder/towel semantics |
| trash_bin | `template` | trash_bin | 0 | bathroom, bedroom, kitchen, living_room | floor | already present in canonical library |
| tvstand | `template` | tvstand | 0 | living_room | floor | already present in canonical library |
| vacuumcleaner | `template` | vacuumcleaner | 0 | bedroom | floor | already present in canonical library |
| vase | `template` | vase | 0 | bedroom, kitchen, living_room | coffee_table, counter, desk, dresser, floor, plate, shelf, table, tvstand | already present in canonical library |
| vegetable | `template` | vegetable | 0 | kitchen | counter, floor, plate, refrigerator, sink, table | already present in canonical library |
| washer | `template` | washer | 0 | bathroom |  | already present in canonical library |
| watch | `template` | watch | 0 | bedroom, living_room | chair, coffee_table, desk, dresser, shelf, table, tvstand | already present in canonical library |
| wateringcan | `new_template_candidate` |  | 0 | living_room | floor, shelf | needs explicit states, capabilities, and placement policy |
| window | `deferred` |  | 0 | bathroom, bedroom, kitchen, living_room | counter, floor, table | 开窗需要温度、湿度、天气和通风转移 |
| winebottle | `template` | winebottle | 0 | kitchen | cabinet, counter, refrigerator, table | already present in canonical library |
