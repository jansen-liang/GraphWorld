# Goal-conditioned B v1

`goal_conditioned_b` is the first GraphWorld goal selector whose learned
quantity remains entirely inside an A/B/C Active-Inference generative model.
It does not learn a scalar reward or completion utility.

## Model

The hidden state is the product of condition and knowledge:

```text
condition: normal / mild / severe
knowledge: unknown / known
```

This gives six states.  The fixed observation model is

```text
A[o,s] = P(o | s)
o: unobserved / low / medium / high urgency
```

The fixed preference is

```text
P_C(o) = softmax(C) = [0.08, 0.72, 0.15, 0.05]
```

Only the Goal-conditioned transition is learned:

```text
B^sigma[i,j] = P(s_next=i | s_current=j, goal_signature=sigma)
```

## Structured signatures and back-off

```text
sigma(g) = family | target_class | workflow | domain
```

For example:

```text
restore_object|cup|direct_restore|home
bed_linen|bed_sheet|restock_clean_sheet|hospital
```

The posterior uses four levels:

```text
action kind -> family -> family×target -> complete signature
```

At each child level,

```text
b_child = N_child + kappa * B_parent
B_child[:,j] = b_child[:,j] / sum_i b_child[i,j]
```

Sparse signatures therefore inherit general experience.  With more samples,
their own transition evidence dominates.

## Explainable update

After executing goal `g` and observing `o_next`, the pair posterior is

```text
xi[i,j] proportional to A[o_next,i] * B^sigma[i,j] * Q_before[j]
sum_ij xi[i,j] = 1
```

Every hierarchy level receives the same transition evidence:

```text
N_level[i,j] <- N_level[i,j] + xi[i,j]
```

There is no reward update.  Completion that leaves a medium/high-urgency
condition supplies medium/high transition evidence rather than an automatic
positive label.

## Goal score

```text
Q_next(s) = B^sigma Q_before(s)
Q_next(o) = A Q_next(s)

risk      = KL(Q_next(o) || softmax(C))
ambiguity = E_Q_next(s)[H(A[:,s])]
G(g)      = risk + ambiguity
```

The selected Goal is `argmin G`.

## Modes

| Mode | Meaning |
|---|---|
| `generative` | existing shared wait/explore/act B |
| `goal_conditioned_b` + learning off | hierarchical B with fixed priors |
| `goal_conditioned_b` + learning on | hierarchical B with online Dirichlet updates |
| `goal_conditioned` | earlier engineering objective; retained as a baseline |

## Quick experiment

Home, 100 steps per group:

```bash
SCENE=simple_home_1f STEPS=100 \
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_goal_b_v1_quick.sh
```

Hospital, 400 steps per group:

```bash
SCENE=simple_hospital_1f STEPS=400 \
OUTPUT_ROOT=/home/autumn/GraphWorld/backend/data/experiments/efe_goal_b_v1_hospital_400 \
PYTHON_BIN=/home/autumn/miniconda3/envs/py311/bin/python3.11 \
bash scripts/run_efe_goal_b_v1_quick.sh
```

Each command runs four groups: shared-B Generative, Goal-B Frozen, Goal-B
Learned, and Rule.  Scene-specific default output directories prevent Home
and Hospital summaries from being mixed.

## Learning diagnostics

`authority_diagnostics.goal_transition_model` reports:

```text
updates
observations
mean_prequential_nll
recent_20_prequential_nll
learned_signatures
signature_samples
last_update.goal_signature
last_update.observation
last_update.prior
last_update.posterior
last_update.transition_evidence
```

The Frozen condition records observations and prequential NLL but leaves
`updates=0`; the Learned condition records the same prediction metric and
updates B.  Falling recent NLL is direct evidence that transition prediction
is becoming better calibrated.

The full transition counts are serialised by `EfeLoop.to_dict()`.

## Current scope

- A and C are fixed; only B-learning is under test.
- EFE is one macro-goal step (`risk + ambiguity`).
- Parameter information gain is not yet subtracted from G.
- Distance and duration are not hand-added to this mode; a later version can
  represent effort as another generative observation modality.
- Performance should be evaluated with several seeds and by comparing
  Learned with Frozen in successive time windows.
