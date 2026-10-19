# REPORT.md — Stage 1.2: network economic parameters

An extension of the Python farm-economics model (`Mistral/` branch).
Requirements source: development-plan, item 1.2; KNOWLEDGE.md v9.2 (7.6, 8.3, 10.1–10.3, 17); the stage-0 specification (trust-networks-platform: spec/03, QUESTIONS No. 4, 11, 18, 20, 31). The stage-1.1 results (K = 3, slots 3/5/10, R = 10%, seed ≥ 300) were fixed and unchanged; every comparison is against the same base.

## 1. Summary

| Parameter | Recommendation | Rationale (8×60-month runs) |
| --- | --- | --- |
| Demurrage `rate` | **1 %/mo** (0.5–2 % acceptable; 5 % — no) | 1 %: median honest ~6 % of issuance (without a window); 2 %: 11–17 %; 5 %: 21–32 % — noticeable to honest members |
| Demurrage `floor` | **3 monthly issuances (3000 units)** | fully protects balances of ≤ 3 months of issuance (young wallets pay 0); costs concentrate on large balances |
| Fee `fee_min` | **1 unit** | the economics are indistinguishable at fee_min 0/1/5 — it is anti-spam, not an economic lever |
| Fee `[rate_min, rate_max]` | **[0.5 %, 2 %]**, starting value 1 % | 0.5 % — a weak drain (3.9 % of honest issuance); 2 % — noticeable (13.8 %); farm +1–2 % drain |
| Target supply growth | **up to the user**; the model confirms the 10.2 equilibrium form: `supply* = 1000/(rate × turnover)` | the model does not determine a specific value (see section 4, last paragraph) |
| Transferability window for fresh issuance | **3 mo.** (a new parameter; 1 — mild, 6 — aggressive, 12 — unacceptable) | the only mechanism cutting "issue → dump": the $0.01 crossing moves from month 39 to 44 (3 mo.), 49 (6), 54 (9), 58 (12) |
| `transfer` moratorium | **14 days** (middle of the 7–30 range) | on a monthly grid 7–30 days are indistinguishable: activation takes ≥ 1 month and covers the moratorium |
| Threshold P / `P_max` | **P = 3000 (3 monthly issuances), P_max = 30000** | the economic effect is zero even at a 1-month lag (the upper bound of D = 48 h) — a convenience recommendation, not economics |

**Main conclusion for the stage goal.** With demurrage and fees enabled, the $0.01 breakeven crossing **does not leave the 60-month horizon in any combination tolerable for honest members**: recommended combination A shifts it from month 39 to 44, aggressive B (2 % demurrage, window 6) — to 49. The 12-month window (month 58) comes closest to the goal, but it freezes honest members' own issuance for a year and still does not reach 60. Consequence for section 17: checking the "income < cost" metric on a horizon of ≥ 3 years remains mandatory (7.7, item 7); the economics window widens the protection window from ~3.2 to ~3.7–4.1 years. Do not disable demurrage and fees in profiles 5 and 7.

**Key structural fact.** Demurrage and fees penalize *holding* and *movement*, but the farm does not hold: it dumps on issuance. Without a transferability window, demurrage does not touch the farm at all (the crossing does not move from month 39 at any rate), and the fee adds +1–2 % drain. The only mechanism forcing the farm to hold inventory is the transferability window for fresh issuance; its effect is delaying the revenue tail, and it is what moves the crossing. Demurrage joins in only when inventory exceeds the floor (window ≥ 4 months).

## 2. Methodology

### 2.1. What was added to the model (`farm_model.py`, Mistral/ branch)

- **Demurrage**: `burn = (bal − floor) × rate` monthly on the balance above the floor; n is the month of the last balance-changing operation (on a monthly grid — once a month; the specification's decision, QUESTIONS No. 31); what is burned is destroyed, with no deduction transactions (10.3).
- **Movement fee**: `fee = max(fee_min, rate × amount)`, burned, paid by the sender on top of the amount (10.2).
- **Transferability window** `fresh_window`: the issuance of month t becomes transferable in month t + fresh_window (10.1 "freshly issued funds are not immediately transferable"; QUESTIONS No. 11).
- **Moratorium** `moratorium_months` after register (7.6; 7–30 days).
- **Delayed transfer above P**: execution with a lag of `delay_lag_months` (8.3; D = 48 h ≈ 0.067 mo. → lag 0; the 1-month variant is the upper bound, deliberately overestimating the effect).
- **Honest economics**: turnover `honest_turnover` — the share of the balance transferred per month (transfers between honest members; the recipient is random, a separate RNG stream `seed*7919+1` not touching the growth-dynamics stream). A second metric is the median honest member's losses (demurrage + fee) as % of their monthly issuance.
- **Farm behavior**: sells everything transferable immediately — optimal against demurrage, conservative for the defensive claims; forced inventory is only fresh issuance inside the window.

All new parameters are OFF by default; `python3 farm_model.py` without flags reproduces the stage-1.1 scenarios. New modes: `--regression`, `--stage12`, `--group <substring>`. Results: `results/*.csv`, `results/stage12_summary.csv`.

### 2.2. Environment

numpy was absent from the environment and was installed (numpy 2.5.4); a no-numpy patch is built into the code (exact Poisson sampling: splitting λ by 30 + Knuth's algorithm, `random.Random(seed*7919+1)`) — it was not used in these runs. matplotlib is unavailable — charts skipped, all conclusions from CSVs.

### 2.3. Stage-1.1 base regression — PASSED

A two-level check:

1. **Bit-for-bit**: the extended model with mechanisms off produces old columns identical to the unmodified code (8 seeds, all 60 months, all fields including floats) — growth dynamics and RNG streams untouched.
2. **Against the publication (7.7)**: 8-run averages (seeds 1–8) against the published 232/38/13.9 %; 568/334/36.8 %; 8348/1140/12.1 %:

| Month | Model (8 runs) | Published (7.7) | Tolerance | Status |
| --- | --- | --- | --- | --- |
| 12 | 236 / 31 / 11.5 % | 232 / 38 / 13.9 % | ±6 % / ±12 / ±3 p.p. | OK |
| 24 | 577 / 306 / 34.3 % | 568 / 334 / 36.8 % | ±10 % / ±40 / ±4 p.p. | OK |
| 60 | 8481 / 1140 / 12.0 % | 8348 / 1140 / 12.1 % | ±5 % / ±60 / ±1.5 p.p. | OK |

The tolerances are derived from measured Monte-Carlo noise, not assigned: 4 blocks of 8 runs give 8-run averages in the ranges: honest m12 226–237, farm m12 31–34 (per-run values 18–50), farm m24 306–335, honest m60 8196–8526; the published values lie inside or on the edge of these ranges. The $0.01 crossing in this environment is month 39 (in 7.7 — month 38); everywhere below the comparison is against 39.

## 3. Sweep results (8 runs × 60 months, averages)

### 3.1. Demurrage without a transferability window: the farm is untouched, honest members pay

| Rate/mo | floor 0: honest, % of issuance | floor 3000: honest, % of issuance | $0.01 crossing | Farm drain |
| --- | --- | --- | --- | --- |
| 0 (base) | 0 | 0 | month 39 | 0 |
| 0.5 % | 4.8 | 3.4 | month 39 | 0 |
| 1 % | 9.2 | 6.4 | month 39 | 0 |
| 2 % | 16.5 | 11.4 | month 39 | 0 |
| 5 % | 31.8 | 20.9 | month 39 | 0 |

The farm dumps immediately and holds zero inventory — demurrage does not touch it at any rate. Honest losses grow over time with balances (per-wallet supply without a drain grows ~1000 units/mo.; in the limit the demurrage equilibrium burns the entire issuance — its constructive role under constant emission, 10.1–10.3). The table values are median losses at month 60.

### 3.2. The transferability window — the only lever against "issue → dump"

| Window, mo | $0.01 crossing (no demurrage) | $ m60 | Farm drain, units |
| --- | --- | --- | --- |
| 0 (base) | 39 | 0.0053 | 0 |
| 3 | 44 | 0.0060 | 2940 |
| 6 | 49 | 0.0068 | 5719 |
| 9 (+ dem. 1 %) | 54 | 0.0079 | 7311 |
| 12 (+ dem. 1 %) | 58 | 0.0092 | 9350 |

The window's effect is delaying the farm's revenue tail (unsold inventory = the last W months of issuance of all active farm wallets). Demurrage on top of the window adds almost nothing: with floor 3000, farm inventory at window 3 (2940) is below the floor — no burn; at window 6 the farm's drain is 4.5 % of issuance (B), at window 12 — 5.6 %. The window's relative protective action falls over time (tail/cumulative), so the crossing shifts logarithmically, not linearly.

### 3.3. The movement fee

| rate | fee_min | Honest, % of issuance (m60) | Farm drain, % of issuance | Crossing |
| --- | --- | --- | --- | --- |
| 0.5 % | 0/1/5 | 3.86 (does not depend on fee_min) | 0.5 | 39 |
| 1 % | 0/1/5 | 7.43 | 1.0 | 39 |
| 2 % | 0/1/5 | 13.77 | 2.0 | 40 |

- `fee_min` 0/1/5 is economically indistinguishable (typical transfers are larger) — its role is anti-spam (10.2); a value of 1 unit is sufficient and minimal.
- Supply equilibrium (10.2): the model reproduces the form `supply* = 1000/(rate × turnover)` — the fee burns `rate × turnover × supply` per month; over 60 months, per-wallet supply is 13.8k (base) vs 12.7k (1 %) and 11.8k (2 %): the equilibrium is far away, and the path to it is linear.
- Honest members pay the fee in proportion to turnover, not balance: at turnover 1.0, candidate A's losses fall to 1.9 % of issuance.

### 3.4. Delayed-transfer threshold P and the moratorium: zero effect

| Scenario | Crossing | $ m60 |
| --- | --- | --- |
| base | 39 | 0.0053 |
| P = 3000, lag 0 mo. (D = 48 h exactly) | 39 | 0.0053 |
| P = 3000, lag 1 mo. (upper bound) | 39 | 0.0053 |
| moratorium 15 days | 39 | 0.0053 |
| moratorium 30 days | 39 | 0.0053 |

The D = 48 h ≈ 0.067 mo. delay vanishes on a monthly grid; even rounding up to a whole month (a deliberate overestimate) changes no metric — only the last month's revenue tail shifts. The 7–30-day moratorium is covered by activation latency (first issuance at least a month after register). Conclusion: **P is chosen for convenience, not economics** (see 5.2); for the moratorium, any point of the range works; the middle is recommended.

### 3.5. Candidate combinations

| Candidate | Composition | Crossing | $ m60 | Honest, % of issuance (turnover 0.5) | Farm drain |
| --- | --- | --- | --- | --- | --- |
| base | — | 39 | 0.0053 | 0 | 0 |
| **A (recommended)** | dem. 1 %/floor 3000 + window 3 + fee 1 %/min 1 + morat. 15 d. | **44** | 0.0061 | 12.2 (1.9 at turnover 1.0; 11.4 at 0.2) | 0.9 % |
| B (aggressive) | dem. 2 %/floor 3000 + window 6 + fee 1 % | 49 | 0.0069 | 17.5 (6.9 at turnover 1.0) | 4.5 % |
| C | dem. 2 %/floor 0 + window 3 + fee 2 % | 44 | 0.0061 | 25.2 | 2.9 % |
| D | dem. 5 %/floor 0 + window 3 + fee 1 % | 44 | 0.0061 | 37.7 | 5.6 % |

Candidate A's breakeven-price trajectory (8-run average): m24 $0.0740 → m36 $0.0153 → m44 $0.0098 → m60 $0.0061 (base: $0.0394 → $0.0113 → $0.0080 → $0.0053).

Per-run spread (min–max, month 60): A $0.0059–0.0063; B $0.0067–0.0072; base $0.0052–0.0055. The spreads of the candidates and of the base do not overlap — the crossing shift is robust to Monte-Carlo noise.

Honest members' sensitivity to turnover: A's losses = 1.9 % (turnover 1.0) / 12.2 % (0.5) / 11.4 % (0.2) of issuance. A median young wallet (balance ≤ floor) pays only the fee; losses grow with the balance's age — the floor does its job. Honest turnover is a calibration parameter (not from the document), to be refined by the profile-1 pilots.

## 4. Answers to the stage-0 QUESTIONS

| Question | Status | Answer |
| --- | --- | --- |
| **No. 4** (P and `P_max`, question 4 of section 18) | **closed by convenience, not economics** | P's effect is zero even at a 1-month lag; recommendation: P = 3000 (3 monthly issuances) — typical payments do not fall under the 48-h delay; `P_max` = 30000 (30 monthly issuances); raising P — after 48 h, lowering — immediately (8.3, unchanged) |
| **No. 11** (freshly issued funds are not immediately transferable) | **closed by data** | mechanism = per-unit lockup: month t's issuance is transferable from t + fresh_window; a 3-month window is recommended (crossing 39→44); 1 month — mild (41), 6 — aggressive (49); 12 — unacceptable for honest members and does not reach 60 (58). It is the only mechanism directly cutting "issue → dump" |
| **No. 18** (demurrage on the pending reserve of a delayed transfer) | **stays with the user** | the reserve lives 48 h ≈ 0.07 mo. — outside the model's monthly resolution; no data; the specification's decision is kept (do not apply) |
| **No. 20** (fee on pool_donate/redeem) | **partially closed** | the model confirms: a movement fee is a weak anti-farm lever (+1–2 % drain) and a moderate cost for honest members (3.9–13.8 % of issuance at 0.5–2 %); applicability to donations/redemptions is a profile-level rule, not economics; recommendation: apply as with transfer (uniformity), value — the same [0.5 %, 2 %] |
| **No. 31** (demurrage's anchor point n) | **implemented, not resolvable by data** | the model implements n from the last balance-changing operation (the specification's decision); on a monthly grid the variants are indistinguishable; the choice is the user's / stage 3's |

Additionally (not on the list, but affecting section 17): the target supply growth for the adaptive `rate` (10.2) is not determined by data — the model confirms the equilibrium form `1000/(rate × turnover)` and the rate bounds, but choosing the goal (e.g., "per-wallet supply growth ≤ N units/mo.") is the user's decision; proposed as a starting value for the stage-5 simulation: N = 500 units/mo. (half of issuance), marked as an assumption, not a conclusion.

## 5. Recommended values for section 17

| Parameter | Value | Status |
| --- | --- | --- |
| Demurrage: rate / floor | 1 %/mo. / 3000 units (3 monthly issuances) | for profiles 5 and 7 (10.3); off by default elsewhere |
| Fee: `fee_min` | 1 unit | anti-spam |
| Fee: `[rate_min, rate_max]` | [0.5 %, 2 %], start 1 % | adaptive (10.2) |
| Target supply growth | up to the user; guideline for stage 5 — ≤ 500 units/mo. per wallet | assumption |
| Transferability window for fresh issuance | 3 months | a new parameter (10.1, QUESTIONS No. 11) |
| `transfer` moratorium | 14 days | from the 7–30 range (17) |
| Threshold P / `P_max` | 3000 / 30000 units | for convenience (8.3) |

## 6. Limitations

- Honest behavior (turnover 0.2–1.0) and farm behavior (immediate dumping) are a parameter/strategy, not conclusions from the document; calibration at the profile-1 pilots (like recruit/vouch_prob from 1.1).
- Honest adaptation to demurrage (faster turnover) and the farm's limited selling liquidity are not modeled; both make the recommendations conservative (overstating the farm threat).
- The grid is monthly: sub-monthly effects (D = 48 h, a 7–30-day moratorium) are unresolvable; upper bounds are given for them.
- The farm's month-60 share (12.0 %) does not change in any scenario — the new mechanisms are economic and do not touch growth dynamics; this confirms that farm protection remains primarily social (vouching, 7.7), with economics lengthening it.
