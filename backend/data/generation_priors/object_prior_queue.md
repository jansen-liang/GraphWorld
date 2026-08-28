# Object Prior 处理队列

排序规则：`evidence_count + 100 * task_reference_count`。任务引用优先于单纯出现频率。

| 排名 | 对象 | 状态 | 分数 | 外部证据 | 任务引用 | 建议动作 |
|---:|---|---|---:|---:|---:|---|
| 1 | clothes | `needs_rule` | 1642 | 42 | 16 | review_allowed_rooms_parents_functional_class |
| 2 | bed | `needs_rule` | 1434 | 34 | 14 | review_allowed_rooms_parents_functional_class |
| 3 | trash_bin | `needs_rule` | 1128 | 128 | 10 | review_allowed_rooms_parents_functional_class |
| 4 | cup | `needs_rule` | 1032 | 32 | 10 | review_allowed_rooms_parents_functional_class |
| 5 | refrigerator | `needs_rule` | 232 | 32 | 2 | review_allowed_rooms_parents_functional_class |
| 6 | window | `needs_mapping` | 182 | 182 | 0 | review_mapping_or_defer |
| 7 | stoveburner | `needs_mapping` | 123 | 123 | 0 | review_mapping_or_defer |
| 8 | counter | `needs_rule` | 103 | 103 | 0 | review_allowed_rooms_parents_functional_class |
| 9 | faucet | `needs_rule` | 95 | 95 | 0 | review_allowed_rooms_parents_functional_class |
| 10 | stationery | `needs_rule` | 81 | 81 | 0 | review_allowed_rooms_parents_functional_class |
| 11 | pillow | `needs_mapping` | 76 | 76 | 0 | review_mapping_or_defer |
| 12 | painting | `needs_mapping` | 75 | 75 | 0 | review_mapping_or_defer |
| 13 | vase | `needs_mapping` | 72 | 72 | 0 | review_mapping_or_defer |
| 14 | creditcard | `needs_mapping` | 68 | 68 | 0 | review_mapping_or_defer |
| 15 | computer | `needs_rule` | 67 | 67 | 0 | review_allowed_rooms_parents_functional_class |
| 16 | mirror | `needs_mapping` | 67 | 67 | 0 | review_mapping_or_defer |
| 17 | statue | `needs_mapping` | 67 | 67 | 0 | review_mapping_or_defer |
| 18 | keychain | `needs_mapping` | 64 | 64 | 0 | review_mapping_or_defer |
| 19 | soapbottle | `needs_mapping` | 64 | 64 | 0 | review_mapping_or_defer |
| 20 | toiletpaper | `needs_mapping` | 62 | 62 | 0 | review_mapping_or_defer |
| 21 | desklamp | `needs_mapping` | 55 | 55 | 0 | review_mapping_or_defer |
| 22 | plant | `needs_rule` | 55 | 55 | 0 | review_allowed_rooms_parents_functional_class |
| 23 | blinds | `needs_mapping` | 53 | 53 | 0 | review_mapping_or_defer |
| 24 | bowl | `needs_rule` | 53 | 53 | 0 | review_allowed_rooms_parents_functional_class |
| 25 | mug | `needs_rule` | 49 | 49 | 0 | review_allowed_rooms_parents_functional_class |
| 26 | handtowelholder | `needs_mapping` | 47 | 47 | 0 | review_mapping_or_defer |
| 27 | box | `needs_rule` | 46 | 46 | 0 | review_allowed_rooms_parents_functional_class |
| 28 | cellphone | `needs_mapping` | 45 | 45 | 0 | review_mapping_or_defer |
| 29 | book | `needs_rule` | 43 | 43 | 0 | review_allowed_rooms_parents_functional_class |
| 30 | plate | `needs_rule` | 43 | 43 | 0 | review_allowed_rooms_parents_functional_class |
| 31 | towelholder | `needs_mapping` | 40 | 40 | 0 | review_mapping_or_defer |
| 32 | dishsponge | `needs_mapping` | 39 | 39 | 0 | review_mapping_or_defer |
| 33 | candle | `needs_mapping` | 38 | 38 | 0 | review_mapping_or_defer |
| 34 | remote | `needs_rule` | 36 | 36 | 0 | review_allowed_rooms_parents_functional_class |
| 35 | cd | `needs_mapping` | 35 | 35 | 0 | review_mapping_or_defer |
| 36 | spraybottle | `needs_mapping` | 35 | 35 | 0 | review_mapping_or_defer |
| 37 | floorlamp | `needs_mapping` | 33 | 33 | 0 | review_mapping_or_defer |
| 38 | television | `needs_rule` | 33 | 33 | 0 | review_allowed_rooms_parents_functional_class |
| 39 | alarmclock | `needs_mapping` | 32 | 32 | 0 | review_mapping_or_defer |
| 40 | bread | `needs_mapping` | 32 | 32 | 0 | review_mapping_or_defer |

## 处理顺序

1. 优先处理有任务引用的对象。
2. 再处理高频 `needs_mapping` 对象，补 ontology alias。
3. 对映射后仍不存在的对象补 `ObjectTemplate`。
4. 对已有模板但出现规则冲突的对象审查房间、parent 和功能能力。
5. 低频且无任务引用对象进入 deferred，不阻塞当前生成器。
