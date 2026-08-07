# GraphWorld EFE 完整设计文档（当前主线）

本文以当前主干代码为准，说明 GraphWorld 中 EFE Agent 的完整设计，重点描述
`goal_conditioned_b` 模式下参数矩阵的定义、先验、推断、评分和在线更新。

对应代码状态：2026-08-07。

> 阅读提示：本文公式统一使用 GitHub/KaTeX 兼容语法。请在 VS Code 中打开
> 本文件后按 `Ctrl+Shift+V`（macOS 为 `Cmd+Shift+V`）进入 Markdown 预览；
> 直接查看源码时会看到 `$...$` 和 `$$...$$` 分隔符。

## 1. 设计目标与当前结论

当前 EFE 主线要验证的命题是：

> Agent 能否通过实际执行结果，学习“某一类 Goal 会把世界从什么状态带到什么状态”，并逐渐改善 Goal 选择，而不是只学习 Goal 是否容易完成。

因此，当前学习对象不是标量 reward、完成率 bonus 或 world score，而是
Goal-conditioned 状态转移矩阵：

$$
B^\sigma_{ij}
=P(s_{t+1}=i\mid s_t=j,\sigma(g)).
$$

其中 $\sigma(g)$ 是 Goal 的结构化语义签名。当前实验固定观测模型
$A$ 和偏好 $C$，只允许 $B^\sigma$ 在线学习。这样 Learned/Frozen
之间的差异可以归因于转移学习，而不是奖励塑形或同时修改多个模型。

当前主线具有以下性质：

- pipeline 和 skill builder 负责产生可执行候选，不负责普通 Goal 的最终排序；
- EFE 对 task、explore、maintain 候选统一打分；
- 选中的 Goal 会持续持有到完成或无进展失败；
- 任务完成后的真实目标状态被转换为离散观测；
- 该观测通过贝叶斯联合转移后验更新分层 Dirichlet $B^\sigma$；
- Goal 评分只使用 `risk + ambiguity`，不附加人工 reward；
- 参数不确定性会被记录，但当前尚未进入 Goal 评分。

必须注意：`run_experiment.py` 的 `--efe-mode` 默认值仍是 `generative`。
运行当前主线时必须显式指定 `--efe-mode goal_conditioned_b`。

## 2. 系统分层与数据流

EFE Agent 分为四层：

```text
环境 scene / observation / deviations
                 │
                 ▼
候选生成层：pipeline + skill builder + LLM（可选）+ explore + maintain
                 │
                 ▼
候选治理层：刷新 phase、补齐 object/target/room、去重、对象 ownership
                 │
                 ▼
高层决策层：构造 Goal signature 和 Q(s_t)，用 A/B^sigma/C 计算 EFE
                 │
                 ▼
执行层：持有 Goal；LLM/确定性 ranker 选低层动作；explore 可用 BFS 导航
                 │
                 ▼
结果层：完成/失败检测 → 目标级或环境级观测 → 更新 B^sigma
```

主要文件职责如下：

| 文件 | 职责 |
|---|---|
| `backend/runtime/agent/efe_agent/goal_transition_model.py` | 当前主线的 A、C、分层 $B^\sigma$、EFE 和学习公式 |
| `backend/runtime/agent/efe_agent/efe_core.py` | 候选池、Goal 生命周期、模型调用、学习时机、序列化 |
| `backend/runtime/agent/efe_agent/efe_goal_builder.py` | 结构化 task workflow、phase 和完成条件 |
| `backend/runtime/agent/efe_agent/efe_scorer.py` | 四种评分模式的统一入口 |
| `backend/runtime/agent/decision.py` | Goal-aware 低层动作排序和 explore BFS 导航 |
| `backend/runtime/agent/efe_agent/efe_model.py` | 通用 A/B/C 数值运算及旧共享-B模型 |
| `backend/run_experiment.py` | 实验参数、Agent 接线、日志与结果保存 |

### 2.1 Pipeline 的角色

在 `goal_conditioned_b` 中，pipeline 仍然必要，但它的角色是：

- 检测环境中的结构化问题；
- 生成合法且可执行的 Goal；
- 提供 object、target、room、skill、phase 等执行字段；
- 刷新 workflow phase；
- 判断 Goal 是否仍然需要；
- 限制对象归属，避免同一对象同时被多个冲突 workflow 使用。

Pipeline 不直接决定普通 Goal 的优先级。即使
`--efe-goal-authority current`，`goal_conditioned_b` 也会关闭旧的 pipeline
直接提交路径，把 pipeline Goal 放入统一候选池。

## 3. 当前主线的随机变量

### 3.1 隐状态 $S$

隐状态由“问题程度”和“认知状态”做笛卡尔积：

$$
s=(c,k),\qquad
c\in\{normal,mild,severe\},\quad
k\in\{unknown,known\}.
$$

共 6 个状态，代码顺序固定为：

| 索引 | 状态 |
|---:|---|
| 0 | `normal_unknown` |
| 1 | `mild_unknown` |
| 2 | `severe_unknown` |
| 3 | `normal_known` |
| 4 | `mild_known` |
| 5 | `severe_known` |

这个分解的意图是同时表示：

- 世界是否处于需要处理的状态；
- Agent 是否已经获得足够明确的观测。

### 3.2 观测 $O$

离散观测共有 4 类：

| 索引 | 观测 | 含义 |
|---:|---|---|
| 0 | `unobserved` | 没有可靠后验观测 |
| 1 | `low` | 目标/环境处于低问题状态 |
| 2 | `medium` | 目标/环境仍有中等问题 |
| 3 | `high` | 目标/环境仍有高紧急度问题 |

### 3.3 Goal 条件 $\sigma$

每个宏观 Goal 被映射成四元签名：

$$
\sigma(g)=(family,target\_class,workflow,domain).
$$

例如：

```text
restore_object|cup|direct_restore|home
dispose_waste|food|dispose_food|home
bed_linen|bed_sheet|restock_clean_sheet|hospital
explore|room|inspect_room|hospital
maintain|room|wait|home
```

四个字段的构造规则是：

- `family`：Goal 的因果/任务大类；
- `target_class`：优先取问题对象 `object` 的 `semantic_type`，没有 object
  时才取 `target`；
- `workflow`：优先取 skill 名；restore/explore/maintain 分别映射为
  `direct_restore`、`inspect_room`、`wait`；
- `domain`：由场景名归为 home、hospital、supermarket、office、factory 或 generic。

签名不包含具体 object id。这样，同一类杯子之间可以共享经验，但清洁杯子、
处理垃圾、归位物体、补充床单不会被压缩为同一个 `act`。

当前 family 的主要映射为：

- explore/patrol → `explore`；
- maintain/idle/wait → `maintain`；
- restore → `restore_object`；
- dispose_food 或 waste skill → `dispose_waste`；
- laundry_clothes → `laundry`；
- linen/sheet → `bed_linen`；
- clean_waiting_area、clean_exam_bed、empty_cup → `clean_state`；
- 其余由旧 family 映射补齐，如 `return_supply`、`deliver_to_human`、
  `generic_skill` 和 `other`。

## 4. 参数矩阵的设计总览

当前主线使用：

$$
A_{oi}=P(o_{t+1}=o\mid s_{t+1}=i),
$$

$$
B^\sigma_{ij}=P(s_{t+1}=i\mid s_t=j,\sigma),
$$

$$
C_o=\log P_C(o),\qquad P_C=\operatorname{softmax}(C).
$$

矩阵约定非常重要：

- $A$ 的行是观测 $o$，列是隐状态 $s$，每列和为 1；
- $B$ 的行是下一状态 $s_{t+1}$，列是当前状态 $s_t$，每列和为 1；
- $C$ 是观测空间上的 log preference，不是 reward 权重；
- 当前 `goal_conditioned_b` 固定 $A,C$，只更新 $B^\sigma$。

## 5. 当前观测矩阵 A

代码中的固定矩阵为：

$$
A=
\begin{bmatrix}
0.85&0.85&0.85&0.02&0.02&0.02\\
0.12&0.06&0.02&0.88&0.15&0.03\\
0.02&0.07&0.05&0.08&0.70&0.17\\
0.01&0.02&0.08&0.02&0.13&0.78
\end{bmatrix}.
$$

行依次是 `unobserved/low/medium/high`，列依次是前述 6 个隐状态。

设计解释：

- unknown 三列均以 0.85 概率产生 `unobserved`；
- `normal_known` 以 0.88 概率产生 `low`；
- `mild_known` 以 0.70 概率产生 `medium`；
- `severe_known` 以 0.78 概率产生 `high`；
- 非零的交叉概率保留了观测噪声，不把状态和观测做成绝对等价。

每个状态对应观测分布的熵为：

$$
H(A_{\cdot,s})
\approx(0.5169,0.5713,0.5682,0.4710,0.8777,0.6785).
$$

这些熵直接进入 EFE 的 ambiguity 项。注意 `mild_known` 的观测列最分散，
所以其 ambiguity 最大。

## 6. 当前偏好向量 C

期望观测分布固定为：

$$
P_C(o)=(0.08,0.72,0.15,0.05).
$$

因此：

$$
C=\log P_C
\approx(-2.5257,-0.3285,-1.8971,-2.9957).
$$

其含义是：

- 最偏好 `low`，概率质量 0.72；
- 允许少量 `medium`，概率质量 0.15；
- 不把 `unobserved` 当成好结果，只有 0.08；
- 最不偏好 `high`，只有 0.05。

因为 $P_C$ 本身已归一化，所以
$\operatorname{softmax}(\log P_C)=P_C$。它描述“希望看到什么”，并不表示
完成一个 Goal 得多少 reward。

## 7. B 的根先验

所有具体 Goal 的 $B^\sigma$ 都从三种可解释的根动作先验开始：

```text
wait     : maintain
explore  : explore/patrol
task     : 其余结构化修复 Goal
```

### 7.1 wait 先验

$$
B^0_{wait}=I_6.
$$

先验假设一次 maintain/wait 不主动改变问题程度或认知状态。

### 7.2 explore 先验

$$
B^0_{explore}=
\begin{bmatrix}
0.2&0&0&0&0&0\\
0&0.2&0&0&0&0\\
0&0&0.2&0&0&0\\
0.8&0&0&1&0&0\\
0&0.8&0&0&1&0\\
0&0&0.8&0&0&1
\end{bmatrix}.
$$

先验假设 explore 主要把 unknown 变成相同问题程度下的 known：

$$
P(k_{t+1}=known\mid k_t=unknown,explore)=0.8,
$$

而已知状态保持已知。它不直接假设 explore 能修复问题程度。

### 7.3 task 先验

先定义问题程度的转移：

$$
T_c=
\begin{bmatrix}
0.90&0.55&0.35\\
0.08&0.40&0.40\\
0.02&0.05&0.25
\end{bmatrix},
$$

行是下一 condition，列是当前 condition。它表达通用任务通常能改善问题，
但对 severe 问题的先验修复能力更弱。

对 unknown 当前状态，任务后 known 概率设为 0.90；对 known 当前状态，保持
known 的概率设为 0.98。展开后的完整矩阵为：

$$
B^0_{task}=\begin{bmatrix}
0.090&0.055&0.035&0.0180&0.011&0.007\\
0.008&0.040&0.040&0.0016&0.008&0.008\\
0.002&0.005&0.025&0.0004&0.001&0.005\\
0.810&0.495&0.315&0.8820&0.539&0.343\\
0.072&0.360&0.360&0.0784&0.392&0.392\\
0.018&0.045&0.225&0.0196&0.049&0.245
\end{bmatrix}.
$$

这只是弱先验。不同 family、target 和 workflow 的实际差异由后续
Dirichlet evidence 学出来。

## 8. 分层 Dirichlet B

如果为每个完整签名单独学习 6×6 矩阵，样本会非常稀疏。当前实现使用四级
回退层级：

$$
action\ kind
\rightarrow family
\rightarrow family\times target\_class
\rightarrow family\times target\_class\times workflow\times domain.
$$

例如 `restore_object|cup|direct_restore|home` 使用：

```text
kind:task
family:restore_object
target:restore_object|cup
signature:restore_object|cup|direct_restore|home
```

每一级保存一个 6×6 的非负 evidence count 矩阵 $N^{(l)}$。根层参数为：

$$
\alpha^{kind}=\kappa_0 B^0_{kind}+N^{kind},
\qquad \kappa_0=6.
$$

归一化得到：

$$
B^{kind}_{ij}=
\frac{\alpha^{kind}_{ij}}
{\sum_r\alpha^{kind}_{rj}}.
$$

每个子层使用父层的归一化矩阵作为经验贝叶斯先验：

$$
\alpha^{(l)}=\kappa B^{(l-1)}+N^{(l)},
\qquad \kappa=8,
$$

$$
B^{(l)}_{ij}=
\frac{\alpha^{(l)}_{ij}}
{\sum_r\alpha^{(l)}_{rj}}.
$$

最终叶子层的 $B^{(l)}$ 就是评分使用的 $B^\sigma$。

解释如下：

- 新签名没有样本时，完全继承父类经验；
- 少量样本时，8 个伪计数强度的父先验防止估计剧烈摆动；
- 样本增加后，本层 $N^{(l)}$ 逐渐压过父先验；
- 相同 evidence 同时更新四级，使新经验既能帮助该具体签名，也能迁移给同类
  Goal。

由于每次转移 evidence $\xi$ 的全矩阵元素和为 1，一个叶子签名的
`leaf_samples` 等于该签名累计获得的软样本数。

## 9. 候选 Goal 的当前状态先验 Q(s_t)

EFE 评分前，需要为每个候选单独构造：

$$
q_t^g=Q(s_t\mid observation,g).
$$

这不是全局唯一状态，而是“从该 Goal 的因果作用对象看，当前处于什么状态”。

### 9.1 condition 先验

首先得到三维 condition 分布 $q_c$：

| 条件 | $q_c=(normal,mild,severe)$ |
|---|---|
| 匹配 urgency ≥ 5 | (0.05, 0.20, 0.75) |
| 匹配 urgency > 0 | (0.15, 0.70, 0.15) |
| explore/maintain 且有待处理 task、但无显式 deviation | (0.10, 0.75, 0.15) |
| explore 且无当前任务 | 由房间 risk 计算 |
| pipeline/skill/LLM 结构化 task，但暂未匹配 deviation | (0.15, 0.70, 0.15) |
| 其他情况 | (0.85, 0.10, 0.05) |

对无当前任务的 explore，设房间风险 $r\in[0.05,0.90]$，默认 0.35：

$$
q_c\propto(1-r,0.65r,0.35r).
$$

对 task，匹配范围仅包括它能因果改变的目标对象：优先 `object`，没有 object
时才使用 `target`。不会因为同房间另一个对象有问题，就把当前 task 判成
mild/severe。

若结构化 detector 已确认 `_efe_target_issue_before=True`，即使 deviation
列表未包含该对象，也至少把 urgency 视为 1，避免部分可观测或 top-k 截断把
真实任务错误标为 normal。

explore/maintain 没有单个修复对象，所以使用环境级语义：只要候选池仍有 task，
它们的先验不能因为当前房间安静而被标为 normal。

### 9.2 knowledge 先验

未访问过的 explore 目标设：

$$
P(known)=0.10,
$$

其余候选设：

$$
P(known)=0.95.
$$

最终 6 维先验为：

$$
q_t^g=
\begin{bmatrix}
(1-p_k)q_c\\
p_k q_c
\end{bmatrix},
$$

并再次归一化。这个先验会在 Goal 被评分时附着到 Goal 上，Goal 完成学习时
复用同一个先验，避免执行过程中状态变化后重新构造起点造成信用错位。

## 10. EFE 评分公式

对候选 Goal $g$，先用对应签名的转移矩阵预测下一状态：

$$
q_{t+1}^g(i)
=\sum_j B^{\sigma(g)}_{ij}q_t^g(j).
$$

再预测观测：

$$
q_{t+1}^g(o)
=\sum_i A_{oi}q_{t+1}^g(i).
$$

### 10.1 Risk

$$
\operatorname{risk}(g)
=D_{KL}\left[q_{t+1}^g(o)\Vert P_C(o)\right]
=\sum_o q_{t+1}^g(o)
\log\frac{q_{t+1}^g(o)}{P_C(o)}.
$$

它衡量预测观测与偏好观测分布之间的距离。预测越接近 `low` 为主的
$P_C$，risk 越小。

### 10.2 Ambiguity

$$
\operatorname{ambiguity}(g)
=\mathbb E_{q_{t+1}^g(s)}[H(P(o\mid s))]
=\sum_i q_{t+1}^g(i)
\left[-\sum_o A_{oi}\log A_{oi}\right].
$$

它惩罚会到达“即使知道隐状态也难预测观测”的状态。

### 10.3 总分和选择

$$
G(g)=\operatorname{risk}(g)+\operatorname{ambiguity}(g),
$$

$$
g^*=\arg\min_{g\in\mathcal G_t}G(g).
$$

当前 `goal_conditioned_b` 直接确定性选择最小值，没有使用
$\operatorname{softmax}(-\gamma G)$ 采样；`gamma` 只存在于旧通用模型 API，
不影响当前主线。发生严格同分时，Python 稳定排序会保留候选生成顺序，同时
日志记录 tie opportunity。

当前分数中明确没有：

- scalar reward；
- Goal 完成 bonus；
- world score delta bonus；
- distance/duration 人工惩罚；
- maintain/explore 人工 penalty；
- 参数不确定性 bonus。

## 11. Goal 结束后的观测构造

学习必须使用 Goal 实际造成的结果，而不是简单把 `completed` 当成正奖励。

### 11.1 Task Goal：目标级信用分配

task 提交时记录：

```text
_efe_target_issue_before = goal_still_needed(...)
```

结束时对同一个目标重新计算 `target_issue_after`。后验观测规则为：

| 条件 | 观测 |
|---|---|
| `target_issue_after=False` | `low` |
| `target_issue_after=True` 且目标 urgency ≥ 5 | `high` |
| `target_issue_after=True` 且 urgency < 5 | `medium` |
| detector 不确定，但目标 urgency ≥ 5 | `high` |
| detector 不确定，但仍匹配 deviation 或 Goal failed | `medium` |
| detector 不确定，但 Goal completed | `low` |
| 其余 | `unobserved` |

因此一个 Goal 即使生命周期形式上结束，只要目标问题仍存在，就会给
$B^\sigma$ 提供 medium/high 转移证据，而不是自动记为成功。

### 11.2 Explore/Maintain：环境级信用分配

explore/maintain 不宣称修复某个具体对象，所以后验按全局剩余问题判断：

- 候选池仍有 task 且环境有 deviation 时，按全局最高 urgency 输出
  `medium/high`；
- 无匹配问题且 Goal completed 时输出 `low`；
- 其余输出 `unobserved`。

这避免“查看了一个安静房间”被错误解释为“整个世界已经改善”。日志中的
`credit_assignment` 会分别记录 `target_condition` 或
`environment_condition`。

## 12. 贝叶斯后验和 B 更新

设执行前先验为 $q_t(j)$，执行的 Goal 签名为 $\sigma$，最终观测为
$o_{t+1}$。预测状态为：

$$
\bar q_{t+1}(i)=\sum_j B^\sigma_{ij}q_t(j).
$$

单时刻状态后验为：

$$
q_{t+1}(i)
=\frac{A_{o_{t+1},i}\bar q_{t+1}(i)}
{\sum_r A_{o_{t+1},r}\bar q_{t+1}(r)}.
$$

但更新转移矩阵需要的是当前状态和下一状态的联合后验：

$$
\xi_{ij}
=Q(s_{t+1}=i,s_t=j\mid o_{t+1},\sigma)
=\frac{A_{o_{t+1},i}B^\sigma_{ij}q_t(j)}
{\sum_{r,k}A_{o_{t+1},r}B^\sigma_{rk}q_t(k)}.
$$

它满足：

$$
\sum_{i,j}\xi_{ij}=1.
$$

然后对该签名路径上的四个层级都更新：

$$
N^{(l)}_{ij}\leftarrow N^{(l)}_{ij}+\xi_{ij},
\quad l\in\{kind,family,target,signature\}.
$$

更新之后，下次评分时重新通过分层归一化构造新的 $B^\sigma$。整个过程没有
梯度下降，也没有反向传播；学习记忆就是可解释、可序列化的 Dirichlet 软计数。

如果数值异常导致 $\sum\xi=0$，实现回退到
$\xi=q_{t+1}\otimes q_t$。正常参数下不会触发该分支。

### 12.1 Learned 与 Frozen

- Learned：计算 NLL、后验和 $\xi$，并执行四级 count 更新；
- Frozen：计算完全相同的预测、NLL、后验和 $\xi$，但不写入 count。

CLI 中由以下参数控制：

```text
--efe-goal-b-learning on/off
```

内部复用了 `goal_outcome_learning` 变量名，但在 `goal_conditioned_b` 下它控制的
是 $B^\sigma$ 更新，不是旧的 Beta completion model。

## 13. “越来越强”如何衡量

### 13.1 预序列 NLL

每次更新前，先用尚未看到本次结果的模型计算：

$$
p_t(o_{t+1})
=\sum_i A_{o_{t+1},i}
\sum_j B^\sigma_{ij}q_t(j),
$$

$$
NLL_t=-\log\max(10^{-12},p_t(o_{t+1})).
$$

NLL 下降表示模型对 Goal 后果的预测越来越准。代码记录：

- 全程 `mean_prequential_nll`；
- 最近 20 次 `recent_20_prequential_nll`；
- 各 family 的 count、mean、recent-20 NLL。

这是“学会了转移规律”的直接指标，但不是“策略性能提高”的充分条件。

### 13.2 Dirichlet 参数不确定性

对叶子层有效参数 $\alpha_{ij}$，每个当前状态列 $j$ 的总强度为：

$$
\alpha_{0j}=\sum_i\alpha_{ij}.
$$

Dirichlet 分量方差为：

$$
\operatorname{Var}(B_{ij})
=\frac{\alpha_{ij}(\alpha_{0j}-\alpha_{ij})}
{\alpha_{0j}^2(\alpha_{0j}+1)}.
$$

代码把每列方差求和后再对 6 列取平均，记录为
`parameter_uncertainty`。

重要限制：这个量目前只用于诊断，没有进入 $G(g)$。所以当前 Agent 会因为
learned B 改变预测结果而改变 Goal 排序，但不会主动选择“参数最不确定的 Goal”
来学习它。

### 13.3 策略层指标

要证明“策略越来越强”，还应同时满足：

1. Learned 的 NLL 随时间或相对 Frozen 下降；
2. Learned/Frozen 的候选 EFE 分数出现分化，tie rate 下降；
3. 学到的差异产生严格 Goal ranking flip，而不只是小数变化；
4. 后半程的目标问题消除率、完成数或 world score 优于前半程/Frozen；
5. 改善在多个 seed 和多个场景成立。

目前已有实验说明 NLL 和 tie rate 能改善，Home 400 步实验中 Learned 的平均
最终分略高于 Frozen；但样本规模仍不足以证明稳定、普适的长期性能提升。

## 14. Goal 生命周期与学习时机

选中 Goal 后不会每步重新选，而是持有到：

- detector 判定完成；
- 连续 12 步没有可观察进展；
- 或达到 160 步硬上限。

可观察进展包括 workflow phase、object parent、robot room 或规划距离等真实
变化。来回移动不应重置进展计数。maintain 被定义为一个时间步的时序动作，
下一步即闭合一次转移。

Goal 结束时的处理顺序是：

1. 计算 `completed/failed`；
2. 对 task 重新运行 detector 得到 `target_issue_after`；
3. 用 Goal 提交时缓存的 $q_t$ 和结束后的观测计算 NLL、后验与 $\xi$；
4. Learned 条件更新分层 $B^\sigma$；
5. 清空高层承诺，下一次进入统一候选选择。

临时放下错误手持物只是低层执行约束，不会替换原 Goal，也不会产生错误的
`generic` B 样本。

## 15. 高层选择与低层动作的边界

EFE 只决定“现在执行哪个 Goal”。选中 Goal 后：

- 若提供 LLM，LLM 在合法动作候选中选择低层动作；
- LLM 不可用或没有返回合法动作时，使用 engine ranker/fallback；
- `--efe-explore-navigation v1` 会在 LLM 调用之后，仅对 explore/patrol 的
  导航动作使用确定性 BFS 覆盖；
- task Goal 的执行动作不受 BFS explore 覆盖。

因此比较 EFE 与 single_round 时，高层 Goal 策略和 explore 导航都可能造成差异；
若要单独证明 $B^\sigma$ 学习的作用，应比较导航、候选池、seed 完全相同的
Learned 与 Frozen。

## 16. 参数、持久化和结果审计

当前主线默认模型参数：

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `root_strength` | 6.0 | 根动作先验每列的伪计数强度 |
| `backoff_strength` | 8.0 | 每个子层继承父层的伪计数强度 |
| Goal no-progress | 12 steps | 连续无进展失败阈值 |
| Goal hard timeout | 160 steps | 单 Goal 最大持续时间 |
| explore navigation | `v1` | 默认使用确定性 BFS |
| Goal selection | `argmin G` | 当前不采样 |

`EfeLoop.to_dict()` 会保存：

- 当前 `efe_mode` 和 authority/candidate/navigation 配置；
- WorldBelief；
- 旧共享 GenerativeModel；
- GoalOutcomeModel；
- 当前 GoalTransitionModel 的 A、C、全部层级 counts、NLL 和最后更新；
- 房间访问、失败目标和 authority diagnostics。

`authority_diagnostics.goal_transition_model` 主要字段包括：

```text
updates
observations
mean_prequential_nll
recent_20_prequential_nll
family_nll
learned_signatures
signature_samples
last_update.goal_signature
last_update.observation
last_update.credit_assignment
last_update.target_issue_before/after
last_update.predictive_probability
last_update.prequential_nll
last_update.prior
last_update.posterior
last_update.transition_evidence
```

设置 `EFE_CANDIDATE_LOG=1` 后，每次重新选择还会记录每个候选的 signature、
prior、risk、ambiguity、parameter_uncertainty、leaf_samples 和 G，便于离线
反事实重排。

## 17. 当前主线推荐运行配置

仅写 `--agent-mode efe` 不会自动启用当前主线。建议显式给出全部关键参数：

```bash
VLLM_MODEL=qwen3.5-9b \
VLLM_BASE_URL=http://127.0.0.1:8000/v1 \
python backend/run_experiment.py \
  --scene simple_home_1f \
  --steps 400 \
  --only with_robot \
  --robots 1 \
  --humans 1 \
  --agent-model vllm-qwen3.5-9b \
  --agent-mode efe \
  --efe-mode goal_conditioned_b \
  --efe-goal-b-learning on \
  --efe-goal-authority efe_all \
  --efe-candidate-source skill_only \
  --efe-explore-navigation v1 \
  --schedule-mode stochastic \
  --schedule-seed 0 \
  --no-clean
```

推荐实验对照是：

```text
Learned: --efe-goal-b-learning on
Frozen : --efe-goal-b-learning off
```

两组必须保持 scene、steps、seed、LLM、候选来源和导航模式相同。

## 18. 仓库中其余三种评分模式

### 18.1 `generative`：旧共享 A/B/C

旧模型只有 2 个状态、3 个观测和 3 个动作：

```text
state  : needs_attention / normal
obs    : low / medium / high
action : wait / explore / act
```

$$
A_{old}=\begin{bmatrix}
0.30&0.80\\
0.40&0.15\\
0.30&0.05
\end{bmatrix},
$$

$$
B_{wait}=\begin{bmatrix}1&0\\0&1\end{bmatrix},\quad
B_{explore}=\begin{bmatrix}0.50&0.10\\0.50&0.90\end{bmatrix},\quad
B_{act}=\begin{bmatrix}0.25&0.05\\0.75&0.95\end{bmatrix},
$$

$$
C_{old}=(4,0,-4).
$$

它也使用 risk + ambiguity，并通过浓度 20 的 Dirichlet 伪计数在线更新 A/B：

$$
\alpha_{o,s}\leftarrow\alpha_{o,s}
+\mathbf 1[o=o_{obs}]Q_{post}(s),
$$

$$
\beta_{s',s,a}\leftarrow\beta_{s',s,a}
+Q_{post}(s')Q_{prior}(s).
$$

问题是所有具体任务都映射成共享动作 `act`，无法区分 restore、clean、waste、
linen 等不同 Goal 的实际效果，因此它是历史基线，不是当前推荐模型。

### 18.2 `goal_conditioned`：工程目标函数基线

该模式按 family 学 Beta-Bernoulli 完成概率和平均时长：

$$
p_{success}=\frac{\alpha}{\alpha+\beta},
$$

$$
G=failure\ risk+distance+duration+revisit+switch
-expected\ value-information\ gain.
$$

其中包含显式人工系数。它可作为实用策略基线，但不是当前要求的纯 A/B/C
转移学习。

### 18.3 `phase1`：早期混合基线

$$
G(g)=-(P(g)+E(g)+\beta N(g)),\qquad \beta=0.15.
$$

它组合 preference-weighted urgency、房间 Beta belief uncertainty 和 novelty，
主要用于历史消融。

## 19. 当前设计的局限与下一步

### 19.1 当前已经解决的问题

- 不再把所有 task 压缩为同一个 `act`；
- Goal 分类达到 family × target × workflow × domain 的粒度；
- 稀疏类别可以通过分层 back-off 共享经验；
- task 使用目标对象级信用分配，避免同房间其他问题污染结果；
- explore/maintain 使用全局语义，避免局部安静造成虚假改善；
- Frozen/Learned 可以在完全相同公式下做干净对照；
- NLL、完整 $\xi$ 和参数计数均可审计。

### 19.2 尚未解决的问题

1. 当前只做一步宏观 Goal 预测，没有多步 policy horizon；
2. `parameter_uncertainty` 不进入 EFE，缺少对 $B$ 参数的主动信息增益；
3. 距离、耗时和资源成本没有建模为观测模态，远距离 Goal 可能被高估；
4. A 和 C 是设计者固定的，尚未通过系统标定实验验证；
5. domain 放在叶子签名中，跨场景迁移主要依赖父层，尚无显式相似度；
6. 每次 $\xi$ 同时更新四层，样本共享很强，需要通过 backoff strength
   敏感性实验验证；
7. 当前确定性 argmin 不会为学习主动试错，早期错误先验可能长期限制数据覆盖；
8. NLL 变好可能只说明预测更准，不保证排名跨越决策边界或 world score 上升。

### 19.3 推荐后续顺序

1. 先做相同 seed、相同执行器下的 Learned/Frozen 长程对照，分前后 25% 报告
   NLL、严格 ranking flip、目标问题消除率和 world score；
2. 做 `root_strength ∈ {2,6,12}`、`backoff_strength ∈ {2,8,16}` 的小型敏感性
   实验，判断当前先验是否压制个性化学习；
3. 若 NLL 明显下降但严格翻转仍少，再加入可解释的参数信息增益：
   $G'=G-\eta I(B^\sigma;o_{t+1})$，并单独消融 $\eta$；
4. 若远距离或耗时任务仍系统性误选，把 effort 作为独立观测模态和偏好建模，
   不直接添加 reward penalty；
5. 最后再扩展到多步宏观 policy EFE，检查长期 Goal 序列而不只是单步 Goal。

## 20. 一句话概括

当前 GraphWorld EFE 的核心不是“给完成 Goal 加分”，而是：用固定的观测模型
$A$ 和偏好 $C$，从每类 Goal 的真实前后状态中学习分层
Goal-conditioned $B^\sigma$，再选择预测后验观测最符合偏好且观测歧义最小的
Goal。它已经能表现为预测 NLL 下降和候选分数分化，但要证明随时间稳定提升任务
性能，还需要更多跨 seed、跨场景的长程 Learned/Frozen 决策翻转证据。
