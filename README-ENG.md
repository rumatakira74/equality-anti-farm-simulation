# Farm-Attack Resistance Simulation (Equality Project — Trust Networks Platform)

An agent-based model: network growth through personal vouching, and a wallet farm's attempt to entrench itself in the network.
**DOI:** [10.5281/zenodo.23474357](https://doi.org/10.5281/zenodo.23474357)

Author: Kirill Lapchinsky (Лапчинский Кирилл), October 13, 2026 (base model, stage 1.1); October 18, 2026 — stage 1.2 extension (demurrage, fees, transferability window, delayed transfers, moratorium).

## Repository structure

- **Mistral/** — the final stage-1.2 model: `farm_model.py`, the report `REPORT.md`, `requirements.txt` (a pinned numpy — the single RNG path) and `results/` — the stage-1.1 canon (`base/`, 19 CSVs, the numpy path), the stage 1.2/3/4 sweeps, the A9 topic (the $120 canon, the device_cost × wallets_per_device sensitivity grid) and the SHA-256 manifests (`MANIFEST-S01-S08.sha256`, `a9_manifest.sha256`, per-seed — `a9_seed*.sha256`).
- **Mistral GLM 5.3/** — the stage-1.1 results (a historical directory, an archive): per-scenario CSVs (K=2–5, narrow/generous slots, a seed circle of 50–1000, a farm budget of 5–100 devices/mo., infiltration 0–20) and three charts.
- **Claude Sonnet 3.6/** — the first version of the model and its charts (historical).
- **KNOWLEDGE.md** — the platform document v9.3, the source of the model's rules.
- **farm-attack-economics.md** — farm-attack economics in plain language.

## Running on your laptop

```
mkdir -p ~/sim && cd ~/sim
# place Mistral/farm_model.py and Mistral/requirements.txt here
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
python farm_model.py --regression   # check against the canonical stage-1.1 figures
python farm_model.py --stage12      # stage-1.2 mechanisms: demurrage, fee, window, P
python farm_model.py --stage12 --group SUBSTRING  # run grouping (a stage12 scenario filter; without a group mode --group is ignored)
python farm_model.py --a9           # the A9 topic: the $120 canon and the sensitivity grid
```

Scenario parameters live in the `Params` class at the top of the file. To test your own value, add a line to the scenario dictionary inside `main()`, e.g.:
`"K=3, slots 4/6/10": replace(base, slots_young=4, slots_old=6)`.
One run with 8 repetitions takes under a minute.

## What is inside the model

- Honest people arrive through chains of acquaintances: each newcomer asks several active members to vouch for them; consent happens with probability `vouch_prob`.
- A vouching member must be active, at least 3 months old, and have a free slot. A slot frees up after 3 issuance periods of the vouched-for wallet, or after 3 months if that wallet never became active.
- The farm registers wallets (paying for devices), buys a small amount of vouching from honest members (`infiltrate_per_month`), and grows as a ring of mutual vouching.
- Every active wallet issues 1000 units per month. For the farm, the cost (device + electricity) and the revenue are accounted for; 10% of the first year's issuance goes to vouching members, and for wallets vouched by honest people this is a loss for the farm.
- Stage 1.2 added: demurrage (the effective balance `floor + (balance − floor) × (1 − rate)^n`), a burn fee (`max(fee_min, rate × amount)`), a transferability window for fresh issuance, a threshold P for delayed transfers (delay D = 48 h), and a withdrawal moratorium.

**The main metric is the breakeven unit price:** the external price at which the farm breaks even within the chosen horizon. It does not require guessing the exchange rate.

## Key results

The base (K=3, slots 3/5/10, seed circle 100, farm 20 devices/mo., device_cost $120 — the canon, 8 runs × 60 months): by month 12 the farm reaches 11.5% of the network ($0.294 per unit), by month 24 — 34.3% ($0.0394), peaking at 38.6% in month 28; the breakeven price crosses $0.01 only in month 39, and by month 60 the farm is down to 12.0% ($0.0053). With zero infiltration into honest vouching members the farm never starts at all; a seed circle of ≥ 300 compresses its month-60 share to ~5%.

The assumption "one device = one wallet" is not verified by the protocol — several wallets on a device lower the effective cost of a wallet (device_cost / wallets_per_device). The robustness of the conclusion is verified by the sensitivity grid device_cost {120, 200} × wallets_per_device {1, 2, 4} (`python farm_model.py --a9`; the $120 canon is conservative for the platform's conclusion: even with a cheap device the farm does not break even; $200 — only in the grid).

Stage 1.2: demurrage without a transferability window does not touch the farm (it does not hold — it dumps on issuance); **the transferability window is the only lever**: 3 months push the farm's breakeven to month 44, 12 months — to month 58. The fee adds 1–2% of drain; threshold P and the moratorium are zero at this scale. The $0.01 crossing does not move beyond the 60-month horizon in any combination tolerable for honest members. Recommended network parameters: demurrage 1%/mo. + floor 3000; fee 1% (bounds 0.5–2%, `fee_min` 1); transferability window 3 months; moratorium 14 days; P = 3000, P_max = 30000.

## What is not modeled

Signatures, networking and finalization, PoW as a computation (replaced by cost), collusion of several farms, adaptive farm behavior, deceiving honest people, changing demand. Honest people may repeatedly ask the same acquaintances (a small optimistic bias). Assumptions not backed by data: honest turnover of 0.2–1.0 of issuance and the target supply growth for the adaptive fee — to be calibrated at the first pilot.

## Reading the results

The stage-1.1 canon (the numpy path, 8 runs) — `Mistral/results/base/`; the historical stage-1.1 directory — `Mistral GLM 5.3/` (an archive, runs from before the single RNG path was pinned). The stage 1.2/3/4 sweeps and the A9 topic — `Mistral/results/` and `Mistral/REPORT.md`; reproducibility — the SHA-256 manifests (`Mistral/results/MANIFEST-S01-S08.sha256`, `a9_manifest.sha256`, a byte-wise seed check — `./Mistral/reproduce_a9.sh`). The numbers are a guide for comparing scenarios, not a forecast: the honest-growth and farm-behavior parameters are plausible assumptions and need calibration on real communities.

## License

Source code is open for non-commercial use; commercial use requires a separate license. Terms — in the `LICENSE` file (version 0.1, draft). An unofficial English translation is provided as `LICENSE-ENG.md`; the Russian original prevails.
