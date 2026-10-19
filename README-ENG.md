# Farm-Attack Resistance Simulation (Equality Project — Trust Networks Platform)

An agent-based model: network growth through personal vouching, and a wallet farm's attempt to entrench itself in the network.
**DOI:** [10.5281/zenodo.23452922](https://doi.org/10.5281/zenodo.23452922)

Author: Kirill Lapchinsky (Лапчинский Кирилл), October 13, 2026 (base model, stage 1.1); October 18, 2026 — stage 1.2 extension (demurrage, fees, transferability window, delayed transfers, moratorium).

## Repository structure

- **Mistral/** — the final stage-1.2 model: `farm_model.py`, the report `REPORT.md` (regression against the published stage-1.1 figures, parameter sweeps, recommendations for the platform document) and `results/` — 49 sweep CSVs plus `stage12_summary.csv`.
- **Mistral GLM 5.3/** — stage-1.1 results: per-scenario CSVs (K=2–5, narrow/generous slots, seed circle 50–1000, farm budget 5–100 devices/mo., infiltration 0–20) and three charts.
- **Claude Sonnet 3.6/** — the first version of the model and its charts (historical).
- **KNOWLEDGE.md** — the platform document v9.3, the source of the model's rules.
- **farm-attack-economics.md** — farm-attack economics in plain language.

## Running on your laptop

```
mkdir -p ~/sim && cd ~/sim
# place Mistral/farm_model.py here
uv venv && source .venv/bin/activate
uv pip install numpy
python farm_model.py --regression   # check against the published stage-1.1 figures
python farm_model.py --stage12      # stage-1.2 mechanisms: demurrage, fee, window, P
python farm_model.py --group        # run grouping
```

Scenario parameters live in the `Params` class at the top of the file. To test your own value, add a line to the scenario dictionary inside `main()`, e.g.:
`"K=3, slots 4/6/10": replace(base, slots_young=4, slots_old=6)`.
One run with 8 repetitions takes under a minute.

## What is inside the model

- Honest people arrive through chains of acquaintances: each newcomer asks several active members to vouch for them; consent happens with probability `vouch_prob`.
- A voucher must be active, at least 3 months old, and have a free slot. A slot frees up after 3 issuance periods of the vouched-for wallet, or after 3 months if that wallet never became active.
- The farm registers wallets (paying for devices), buys a small amount of vouching from honest members (`infiltrate_per_month`), and grows as a ring of mutual vouching.
- Every active wallet issues 1000 units per month. For the farm, device and electricity costs and revenue are accounted for; 10% of the first year's issuance goes to vouchers — a loss for farm wallets vouched by honest people.
- Stage 1.2 added: demurrage (effective balance `floor + (balance − floor) × (1 − rate)^n`), a burn fee (`max(fee_min, rate × amount)`), a transferability window for fresh issuance, a threshold P for delayed transfers (delay D = 48 h), and a withdrawal moratorium.

**The main metric is the breakeven unit price:** the external price at which the farm breaks even within the chosen horizon. It does not require guessing the exchange rate.

## Key results

Base scenario (K=3, slots 3/5/10, seed circle 100, farm 20 devices/mo., 8 runs × 60 months): by month 12 the farm reaches 13.9% of the network ($0.234 per unit), by month 24 — 36.8% ($0.0353), peaking at 39.6% in month 27; the breakeven price crosses $0.01 only in month 38, and by month 60 the farm is down to 12.1% ($0.0053). With zero infiltration into honest vouchers the farm never starts at all; a seed circle of ≥ 300 compresses its month-60 share to ~5%.

Stage 1.2: demurrage without a transferability window does not touch the farm (it does not hold — it dumps on issuance); **the transferability window is the only lever**: 3 months push the farm's breakeven to month 44, 12 months — to month 58. The fee adds 1–2% of drain; threshold P and the moratorium are zero at this scale. The $0.01 crossing does not move beyond the 60-month horizon in any combination tolerable for honest members. Recommended network parameters: demurrage 1%/mo. + floor 3000; fee 1% (bounds 0.5–2%, `fee_min` 1); transferability window 3 months; moratorium 14 days; P = 3000, P_max = 30000.

## What is not modeled

Signatures, networking and finalization, PoW as a computation (replaced by cost), collusion of several farms, adaptive farm behavior, deceiving honest people, changing demand. Honest people may repeatedly ask the same acquaintances (a small optimistic bias). Assumptions not backed by data: honest turnover of 0.2–1.0 of issuance and the target supply growth for the adaptive fee — to be calibrated at the first pilot.

## Reading the results

Stage 1.1 — `Mistral GLM 5.3/` (`scenarios.png`, `infiltration.png`, `seed_and_budget.png`, CSVs). Stage 1.2 — `Mistral/results/` (49 sweep CSVs, `stage12_summary.csv`) and `Mistral/REPORT.md`. The numbers are a guide for comparing scenarios, not a forecast: the honest-growth and farm-behavior parameters are plausible assumptions and need calibration on real communities.

## License

Source code is open for non-commercial use; commercial use requires a separate license. Terms — in `LICENSE` (version 0.1, draft). An unofficial English translation is provided as `LICENSE-ENG.md`; the Russian original prevails.
