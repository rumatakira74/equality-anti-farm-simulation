#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2026 Лапчинский Кирилл (Kirill Lapchinsky)
# SPDX-License-Identifier: LicenseRef-TNP-NC-0.1
"""
Агентная модель защиты от ферм через поручительства (платформа сетей доверия).

Что моделируется (по месяцам):
  * честные люди приходят в сеть по цепочке знакомств и собирают K поручительств;
  * поручитель должен быть активным, не младше voucher_min_age месяцев и иметь свободный слот;
  * слот освобождается, когда поручаемый отмайнил slot_release_mints периодов,
    либо через vouch_lifetime месяцев, если поручаемый не стал активным;
  * ферма покупает устройства, регистрирует кошельки, немного проникает к честным
    поручителям (infiltrate_per_month) и дальше растёт кольцом взаимных поручительств;
  * каждый активный кошелёк выпускает base_mint единиц в месяц; для фермы считаются
    стоимость и доход.

Что НЕ моделируется (упрощения): подписи, сеть, финализация, PoW как вычисление
(он заменён стоимостью power_cost), мораторий на вывод, демередж, комиссия при выпуске.

Главная метрика — безубыточная цена единицы: при какой внешней цене ферма выходит в ноль.
Она не зависит от неизвестного курса, поэтому её удобно сравнивать между сценариями.

Запуск:  python3 farm_model.py            # сравнение сценариев
         python3 farm_model.py --runs 20  # больше прогонов Монте-Карло
"""
import argparse
import csv
import os
import random
import warnings
from dataclasses import dataclass, replace

import numpy as np

warnings.filterwarnings("ignore", message="Mean of empty slice")


@dataclass(frozen=True)
class Params:
    months: int = 60
    # --- правила протокола ---
    K: int = 3                      # поручителей для активации
    slots_young: int = 3            # слотов при возрасте 3–12 мес.
    slots_old: int = 5              # слотов старше 12 мес.
    slots_seed: int = 10            # слотов у посевного круга в первый год
    voucher_min_age: int = 3        # минимальный возраст поручителя (мес. с активации)
    slot_release_mints: int = 3     # слот освобождается после стольких периодов выпуска
    vouch_lifetime: int = 3         # поручительство кандидату без активации сгорает (мес.)
    base_mint: float = 1000.0       # единиц в месяц
    reward_share: float = 0.10      # R: доля от выпуска поручаемого поручителям
    reward_months: int = 12         # сколько первых выпусков делится
    # --- честные люди ---
    seed_count: int = 100           # посевной круг
    honest_cap: int = 20000         # потолок числа честных людей
    recruit_rate: float = 0.10      # новых кандидатов на активного честного поручителя в месяц
    asks_per_month: int = 3         # скольких людей кандидат просит за месяц
    vouch_prob: float = 0.5         # вероятность, что честный человек согласится
    give_up_months: int = 12        # кандидат бросает попытки
    # --- ферма ---
    farm_start: int = 3             # месяц начала
    farm_new_per_month: int = 20    # новых устройств в месяц
    farm_max_wallets: int = 2000    # потолок бюджета (кошельков)
    infiltrate_per_month: float = 2.0  # кошельков в месяц, получающих поручительства честных людей
    # --- экономика фермы (доллары) ---
    device_cost: float = 120.0      # устройство с аппаратной аттестацией
    power_cost: float = 0.5         # электричество и PoW на кошелёк в месяц
    sell_fee: float = 0.01          # потери при выводе (комиссия)
    unit_price: float = 0.01        # внешняя цена единицы, $ (для справки)


class W:
    """Кошелёк."""
    __slots__ = ("kind", "reg", "act", "seed", "vouches", "out", "h_vouchers")

    def __init__(self, kind, reg, seed=False):
        self.kind = kind            # 'h' честный, 'f' ферма
        self.reg = reg              # месяц регистрации
        self.act = None             # месяц активации
        self.seed = seed
        self.vouches = []           # [(id поручителя, месяц)]
        self.out = []               # [(id поручаемого, месяц)] — занятые слоты
        self.h_vouchers = 0         # сколько честных среди поручителей (для утечки награды)


def simulate(P: Params, run_seed: int):
    rng = np.random.default_rng(run_seed)
    rnd = random.Random(run_seed)
    wallets = []
    for _ in range(P.seed_count):
        w = W("h", -999, seed=True)
        w.act = -999
        wallets.append(w)
    pend_h, pend_f = [], []
    farm_total = 0
    farm_cost = 0.0
    farm_units_net = 0.0
    rows = []

    for m in range(P.months):
        def capacity(w):
            if w.seed and m < 12:
                return P.slots_seed
            age = 10 ** 6 if w.seed else m - w.act
            return P.slots_old if age >= 12 else P.slots_young

        def used(w):
            keep = []
            for vid, vm in w.out:
                v = wallets[vid]
                if v.act is None:
                    if m - vm < P.vouch_lifetime:
                        keep.append((vid, vm))
                elif m - v.act < P.slot_release_mints:
                    keep.append((vid, vm))
            w.out = keep
            return len(keep)

        def activate(cid):
            w = wallets[cid]
            w.act = m
            w.h_vouchers = sum(1 for v, _ in w.vouches if wallets[v].kind == "h")

        def process(cid, pool, prob):
            w = wallets[cid]
            w.vouches = [(v, vm) for v, vm in w.vouches if m - vm < P.vouch_lifetime]
            have = {v for v, _ in w.vouches}
            if len(w.vouches) < P.K and pool:
                for _ in range(P.asks_per_month):
                    vid = pool[rnd.randrange(len(pool))]
                    if vid in have or vid == cid:
                        continue
                    v = wallets[vid]
                    if used(v) < capacity(v) and rnd.random() < prob:
                        w.vouches.append((vid, m))
                        v.out.append((cid, m))
                        have.add(vid)
                    if len(w.vouches) >= P.K:
                        break
            if len(w.vouches) >= P.K:
                activate(cid)

        # допустимые поручители
        h_el = [i for i, w in enumerate(wallets)
                if w.kind == "h" and w.act is not None and m - w.act >= P.voucher_min_age]
        f_el = [i for i, w in enumerate(wallets)
                if w.kind == "f" and w.act is not None and m - w.act >= P.voucher_min_age]

        # приход честных людей
        h_total = sum(1 for w in wallets if w.kind == "h")
        n_new = int(rng.poisson(P.recruit_rate * len(h_el))) if h_el else 0
        n_new = max(0, min(n_new, P.honest_cap - h_total))
        for _ in range(n_new):
            wallets.append(W("h", m))
            pend_h.append(len(wallets) - 1)
        for cid in pend_h:
            process(cid, h_el, P.vouch_prob)
        pend_h = [c for c in pend_h
                  if wallets[c].act is None and m - wallets[c].reg < P.give_up_months]

        # ферма
        if m >= P.farm_start:
            n_reg = max(0, min(P.farm_new_per_month, P.farm_max_wallets - farm_total))
            for _ in range(n_reg):
                wallets.append(W("f", m))
                pend_f.append(len(wallets) - 1)
                farm_total += 1
                farm_cost += P.device_cost
            # проникновение к честным поручителям
            k_inf = int(rng.poisson(P.infiltrate_per_month))
            fresh = [c for c in pend_f if not wallets[c].vouches]
            for cid in fresh[:k_inf]:
                w = wallets[cid]
                tries = 0
                while len(w.vouches) < P.K and tries < 60 and h_el:
                    tries += 1
                    vid = h_el[rnd.randrange(len(h_el))]
                    v = wallets[vid]
                    if vid in {x for x, _ in w.vouches}:
                        continue
                    if used(v) < capacity(v):
                        w.vouches.append((vid, m))
                        v.out.append((cid, m))
                if len(w.vouches) >= P.K:
                    activate(cid)
            # кольцо взаимных поручительств
            for cid in pend_f:
                if wallets[cid].act is None:
                    process(cid, f_el, 1.0)
            pend_f = [c for c in pend_f if wallets[c].act is None and m - wallets[c].reg < 36]

        # выпуск и экономика
        n_h = n_f = 0
        for w in wallets:
            if w.act is None or w.act >= m:
                continue
            if w.kind == "h":
                n_h += 1
            else:
                n_f += 1
                amount = P.base_mint
                idx = m - w.act
                leak = amount * P.reward_share * (w.h_vouchers / P.K) if idx <= P.reward_months else 0.0
                farm_units_net += amount - leak
                farm_cost += P.power_cost

        active_h = sum(1 for w in wallets if w.kind == "h" and w.act is not None)
        active_f = sum(1 for w in wallets if w.kind == "f" and w.act is not None)
        revenue_units = farm_units_net * (1 - P.sell_fee)
        breakeven = farm_cost / revenue_units if revenue_units > 0 else float("nan")
        rows.append({
            "month": m + 1,
            "honest_active": active_h,
            "honest_pending": len(pend_h),
            "farm_active": active_f,
            "farm_pending": len(pend_f),
            "farm_share": active_f / max(1, active_h + active_f),
            "farm_cost_usd": farm_cost,
            "farm_units_net": farm_units_net,
            "breakeven_price": breakeven,
            "farm_profit_usd": revenue_units * P.unit_price - farm_cost,
        })
    return rows


def run_many(P: Params, runs: int):
    all_rows = [simulate(P, seed) for seed in range(1, runs + 1)]
    keys = all_rows[0][0].keys()
    out = []
    for t in range(P.months):
        row = {}
        for k in keys:
            vals = [r[t][k] for r in all_rows]
            row[k] = float(np.nanmean(vals)) if k != "month" else vals[0]
        out.append(row)
    return out


def fmt(row):
    return (f"честные {row['honest_active']:7.0f} | ферма {row['farm_active']:6.0f} | "
            f"доля фермы {100 * row['farm_share']:5.1f}% | безубыточная цена ${row['breakeven_price']:.4f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=8, help="число прогонов Монте-Карло на сценарий")
    ap.add_argument("--out", default="results", help="каталог для CSV и графиков")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    base = Params()
    scenarios = {
        "база: K=3, слоты 3/5/10": base,
        "узко: K=3, слоты 2/2/10": replace(base, slots_young=2, slots_old=2),
        "щедро: K=3, слоты 5/8/15": replace(base, slots_young=5, slots_old=8, slots_seed=15),
        "K=2, слоты 3/5/10": replace(base, K=2),
        "K=4, слоты 3/5/10": replace(base, K=4),
        "K=5, слоты 3/5/10": replace(base, K=5),
    }
    infiltration = {f"проникновение {x}/мес": replace(base, infiltrate_per_month=x)
                    for x in (0, 0.5, 2, 8, 20)}

    seed_sizes = {f"посев {n} кошельков": replace(base, seed_count=n) for n in (50, 100, 300, 1000)}
    farm_budget = {f"ферма {n} устройств/мес": replace(base, farm_new_per_month=n, farm_max_wallets=20000)
                   for n in (5, 20, 50, 100)}

    results = {}
    groups = (("Правила поручительств", scenarios),
              ("Сила проникновения фермы", infiltration),
              ("Размер посевного круга", seed_sizes),
              ("Бюджет фермы", farm_budget))
    for title, group in groups:
        print(f"\n=== {title} (прогонов: {args.runs}) ===")
        for name, P in group.items():
            res = run_many(P, args.runs)
            results[name] = res
            print(f"\n{name}")
            for mo in (12, 24, 60):
                print(f"  месяц {mo:>2}: {fmt(res[mo - 1])}")
            fname = os.path.join(args.out, name.replace(" ", "_").replace("/", "-").replace(":", "") + ".csv")
            with open(fname, "w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=list(res[0].keys()))
                wr.writeheader()
                wr.writerows(res)

    if not args.no_plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
        for name in scenarios:
            r = results[name]
            ax[0].plot([x["month"] for x in r], [100 * x["farm_share"] for x in r], label=name)
            ax[1].plot([x["month"] for x in r], [x["honest_active"] for x in r], label=name)
        ax[0].set_title("Доля фермы среди активных кошельков, %")
        ax[1].set_title("Честные активные кошельки")
        for a in ax:
            a.set_xlabel("месяц")
            a.grid(alpha=0.3)
        ax[0].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "scenarios.png"), dpi=130)

        fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
        for name in infiltration:
            r = results[name]
            ax[0].plot([x["month"] for x in r], [100 * x["farm_share"] for x in r], label=name)
            ax[1].plot([x["month"] for x in r], [x["breakeven_price"] for x in r], label=name)
        ax[0].set_title("Доля фермы, %")
        ax[1].set_title("Безубыточная цена единицы, $")
        ax[1].set_ylim(0, 0.02)
        for a in ax:
            a.set_xlabel("месяц")
            a.grid(alpha=0.3)
        ax[0].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "infiltration.png"), dpi=130)
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
        for name in seed_sizes:
            r = results[name]
            ax[0].plot([x["month"] for x in r], [100 * x["farm_share"] for x in r], label=name)
        for name in farm_budget:
            r = results[name]
            ax[1].plot([x["month"] for x in r], [100 * x["farm_share"] for x in r], label=name)
        ax[0].set_title("Доля фермы при разном посевном круге, %")
        ax[1].set_title("Доля фермы при разном бюджете фермы, %")
        for a in ax:
            a.set_xlabel("месяц")
            a.grid(alpha=0.3)
            a.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "seed_and_budget.png"), dpi=130)
        print(f"\nГрафики и CSV сохранены в каталоге: {args.out}")


if __name__ == "__main__":
    main()
