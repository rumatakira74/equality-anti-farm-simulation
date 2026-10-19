# equality-simulation results (reproduction)

- Model: https://github.com/rumatakira74/equality-simulation (`farm_model.py`, Python).
- Run: 8 Monte-Carlo runs per scenario × 60 months, averaged over runs.
- Patch `farm_model_pure.py`: numpy was unavailable in the sandbox and pip was blocked, so Poisson sampling was replaced with an exact standard-library implementation (splitting λ into parts of 30 + Knuth's algorithm, a separate `random.Random(seed*7919+1)` stream); `nanmean` — by NaN filtering. The result is statistically equivalent to the author's but not bit-identical (a different RNG stream).
- Conclusions are integrated into KNOWLEDGE.md v9.2, section 7.7.

## Base scenario

K = 3, slots 3/5/10, seed circle 100, farm 20 devices/mo., farm cap, recruit = 0.1 newcomers/person/mo., vouch_prob = 0.5, $200 per device.

- Month 12: honest 232, farm 38 (13.9%), breakeven price $0.234.
- Month 24: 568 / 334 (36.8%), $0.035.
- Month 27: peak farm share ≈ 40%.
- Month 38: breakeven price crosses $0.01 — the farm pays off at a unit price of $0.01.
- Month 60: 8348 / 1140 (12.1%), $0.0053.

## Scenario groups

1. **Vouching rules** — `base`, `narrow` (2/2/10), `generous` (5/8/15), K = 2/3/4/5.
2. **Farm infiltration** — bought vouching of 0 / 0.5 / 2 / 8 / 20 wallets/mo.
3. **Seed circle** — 50 / 100 / 300 / 1000 wallets.
4. **Farm budget** — 5 / 20 / 50 / 100 devices/mo.

## CSV format

Columns: `month, honest_active, honest_pending, farm_active, farm_pending, farm_share, farm_cost_usd, farm_units_net, breakeven_price, farm_profit_usd` — averages over 8 runs; `farm_profit_usd` — at a unit price of $0.01.
