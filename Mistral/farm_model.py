#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2026 Лапчинский Кирилл (Kirill Lapchinsky)
# SPDX-License-Identifier: LicenseRef-TNP-NC-0.1
"""
Агентная модель защиты от ферм через поручительства (платформа сетей доверия).
Расширение этапа 1.2 (ветка Mistral/): демередж, комиссия на движение, окно
переводимости свежих выпусков, мораторий, отложенный перевод, экономика честных.

Что моделируется (по месяцам):
  * честные люди приходят в сеть по цепочке знакомств и собирают K поручительств;
  * поручитель должен быть активным, не младше voucher_min_age месяцев и иметь свободный слот;
  * слот освобождается, когда поручаемый отмайнил slot_release_mints периодов,
    либо через vouch_lifetime месяцев, если поручаемый не стал активным;
  * ферма покупает устройства, регистрирует кошельки, немного проникает к честным
    поручителям (infiltrate_per_month) и дальше растёт кольцом взаимных поручительств;
  * каждый активный кошелёк выпускает base_mint единиц в месяц; для фермы считаются
    стоимость и доход.

Этап 1.2 (экономические механизмы; по умолчанию ВЫКЛЮЧЕНЫ = база 1.1):
  * демередж: burn = (bal − floor) × rate в месяц на остаток выше floor;
    n — месяц от последней операции, менявшей баланс (в месячной сетке — раз в месяц);
    списанное сжигается, транзакций списания нет (10.3; QUESTIONS №31);
  * комиссия на движение: fee = max(fee_min, rate × amount), сжигается,
    платит отправитель сверх суммы (10.2; QUESTIONS №20);
  * окно переводимости fresh_window: выпуск месяца t переводим с месяца t + fresh_window
    (10.1 «свежевыпущенные средства переводимы не сразу»; QUESTIONS №11);
  * мораторий transfer после register: moratorium_months (7.6; 7–30 дней);
  * отложенный перевод выше порога P: исполнение с лагом delay_lag_months
    (8.3; D = 48 ч ≈ 0,067 мес. -> лаг 0; вариант 1 мес. — верхняя граница);
  * экономика честных: оборот honest_turnover (доля переводимого остатка в месяц) —
    для оценки потерь честных от демереджа и комиссии (вторая метрика).

Поведение фермы: продаёт всё переводимое сразу (оптимально против демереджа,
консервативно для защитных утверждений). Вынужденный запас — только свежие
выпуски в окне fresh_window.

Что НЕ моделируется (упрощения): подписи, сеть, финализация, PoW как вычисление
(он заменён стоимостью power_cost), адаптация поведения честных к демереджу/комиссии,
ограниченная ликвидность сбыта фермы, рынок курса. Результаты 1.1 (K, слоты,
R, посевной круг) зафиксированы и не меняются.

Главная метрика — безубыточная цена единицы фермы: при какой внешней цене ферма
выходит в ноль. Вторая метрика — потери медианного честного активного участника
(демередж + комиссия) в долях его месячного выпуска.

Запуск:  python3 farm_model.py                 # сценарии 1.1 (без изменений)
         python3 farm_model.py --regression    # проверка воспроизведения базы 1.1
         python3 farm_model.py --stage12       # свеепы этапа 1.2
         python3 farm_model.py --stage12 --group демередж   # одна группа
         python3 farm_model.py --runs 20       # больше прогонов Монте-Карло
"""
import argparse
import csv
import math
import os
import random
import statistics
import warnings
from dataclasses import dataclass, replace

try:
    import numpy as np
except ImportError:  # патч без numpy: точная выборка Пуассона (разбиение λ по 30 + Кнут)
    np = None

warnings.filterwarnings("ignore", message="Mean of empty slice")

CROSS_PRICE = 0.01  # порог безубыточной цены для метрики «месяц пересечения», $

# Опубликованные средние базы 1.1 (KNOWLEDGE.md 7.7; 8 прогонов): месяц -> (честные, ферма, доля %)
PUBLISHED_BASE = {12: (232, 38, 13.9), 24: (568, 334, 36.8), 60: (8348, 1140, 12.1)}
# Допуски регрессии: измеренный шум Монте-Карло 8-прогоновых средних по 4 блокам сидов
# (см. REPORT.md): месяц -> (относит. допуск честных, абс. допуск фермы, допуск доли п.п.)
REGRESSION_TOL = {12: (0.06, 12.0, 3.0), 24: (0.10, 40.0, 4.0), 60: (0.05, 60.0, 1.5)}


@dataclass(frozen=True)
class Params:
    months: int = 60
    # --- правила протокола (зафиксированы этапом 1.1; не меняются) ---
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
    # --- этап 1.2: экономические механизмы (по умолчанию ВЫКЛЮЧЕНЫ = база 1.1) ---
    demurrage_rate: float = 0.0      # доля в месяц на остаток выше floor
    demurrage_floor: float = 0.0     # необлагаемый остаток (единиц)
    transfer_fee_rate: float = 0.0   # rate комиссии на движение (доля)
    transfer_fee_min: float = 0.0    # fee_min (единиц)
    fresh_window: int = 0           # окно переводимости свежих выпусков (мес.)
    moratorium_months: float = 0.0  # мораторий transfer после register (мес.)
    delay_threshold: float = float("inf")  # P отложенного перевода (единиц)
    delay_lag_months: int = 0        # лаг исполнения выше P (мес.; D=48ч -> 0)
    honest_turnover: float = 0.0    # доля переводимого остатка честного в месяц (0 = не моделировать)


class W:
    """Кошелёк."""
    __slots__ = ("kind", "reg", "act", "seed", "vouches", "out", "h_vouchers",
                 "bal", "fresh")

    def __init__(self, kind, reg, seed=False):
        self.kind = kind            # 'h' честный, 'f' ферма
        self.reg = reg              # месяц регистрации
        self.act = None             # месяц активации
        self.seed = seed
        self.vouches = []           # [(id поручителя, месяц)]
        self.out = []               # [(id поручаемого, месяц)] — занятые слоты
        self.h_vouchers = 0          # сколько честных среди поручителей (для утечки награды)
        self.bal = 0.0               # номинальный остаток (демередж применяется к нему)
        self.fresh = []             # [(сумма, месяц переводимости)] — свежие выпуски


def _poisson_fallback(rnd, lam):
    """Точная выборка Пуассона без numpy: разбиение λ по 30 + алгоритм Кнута."""
    if lam <= 0:
        return 0
    k = 0
    full = int(lam // 30)
    rem = lam - 30.0 * full
    for _ in range(full):
        L = math.exp(-30.0)
        p = 1.0
        while True:
            p *= rnd.random()
            k += 1
            if p <= L:
                break
        k -= 1
    L = math.exp(-rem)
    p = 1.0
    while True:
        p *= rnd.random()
        k += 1
        if p <= L:
            break
    return k - 1


def simulate(P: Params, run_seed: int):
    if np is not None:
        rng = np.random.default_rng(run_seed)
        poisson = rng.poisson
    else:
        prnd = random.Random(run_seed * 7919 + 1)
        poisson = lambda lam: _poisson_fallback(prnd, lam)
    rnd = random.Random(run_seed)
    # отдельный поток для экономики честных (не трогает поток динамики роста)
    er = random.Random(run_seed * 7919 + 1)
    wallets = []
    for _ in range(P.seed_count):
        w = W("h", -999, seed=True)
        w.act = -999
        wallets.append(w)
    pend_h, pend_f = [], []
    farm_total = 0
    farm_cost = 0.0
    farm_units_net = 0.0          # суммарный чистый выпуск фермы (как в базе 1.1)
    farm_sold = 0.0               # суммарно продано (после комиссий и лагов)
    farm_burned = 0.0             # сгорело у фермы: демередж + комиссии движения
    sales_queue = []              # [(месяц исполнения, сумма)]
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
        n_new = int(poisson(P.recruit_rate * len(h_el))) if h_el else 0
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
            k_inf = int(poisson(P.infiltrate_per_month))
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

        # выпуск, демередж, комиссия, продажи (этап 1.2; при выключенных механизмах
        # численно идентично базе 1.1 — динамика роста и потоки RNG не тронуты)
        n_h = n_f = 0
        h_act = []
        h_cost = {}
        h_bal_sum = 0.0
        f_bal_sum = 0.0
        f_cnt = 0
        sales_new = []
        for i, w in enumerate(wallets):
            if w.act is None or w.act >= m:
                continue
            # демередж на входящий остаток (раз в месяц; n = 1 от последней операции)
            cost = 0.0
            if P.demurrage_rate > 0.0 and w.bal > P.demurrage_floor:
                burn = (w.bal - P.demurrage_floor) * P.demurrage_rate
                w.bal -= burn
                cost += burn
                if w.kind == "f":
                    farm_burned += burn
            amount = P.base_mint
            if w.kind == "h":
                n_h += 1
                w.bal += amount
                if P.fresh_window > 0:
                    w.fresh.append((amount, m + P.fresh_window))
                h_act.append(i)
                h_cost[i] = cost
                h_bal_sum += w.bal
            else:
                n_f += 1
                idx = m - w.act
                leak = amount * P.reward_share * (w.h_vouchers / P.K) if idx <= P.reward_months else 0.0
                net = amount - leak
                farm_units_net += net
                farm_cost += P.power_cost
                w.bal += net
                w.fresh.append((net, m + P.fresh_window))
                f_cnt += 1
                f_bal_sum += w.bal
                # продажа переводимого (мораторий считается от register)
                if m - w.reg >= P.moratorium_months:
                    amt = 0.0
                    keep = []
                    for a, rel in w.fresh:
                        if rel <= m:
                            amt += a
                        else:
                            keep.append((a, rel))
                    if amt > 0.0:
                        w.fresh = keep
                        w.bal -= amt
                        f_bal_sum -= amt
                        exec_m = m + P.delay_lag_months if amt > P.delay_threshold else m
                        sales_new.append((exec_m, amt))

        # траты честных (экономика честных; отдельный поток er)
        if P.honest_turnover > 0.0 and h_act:
            for i in h_act:
                w = wallets[i]
                if w.fresh:
                    w.fresh = [(a, rel) for a, rel in w.fresh if rel > m]
                locked = sum(a for a, _ in w.fresh)
                spendable = w.bal - locked
                if spendable <= 0.0:
                    continue
                s = spendable * P.honest_turnover
                fee = max(P.transfer_fee_min, P.transfer_fee_rate * s) if s > 0.0 else 0.0
                w.bal -= s + fee
                h_cost[i] = h_cost.get(i, 0.0) + fee
                j = h_act[int(er.random() * len(h_act))]
                wallets[j].bal += s

        # исполнение продаж фермы (лаг отложенного перевода)
        sales_queue.extend(sales_new)
        still = []
        for exec_m, amt in sales_queue:
            if exec_m <= m:
                fee = max(P.transfer_fee_min, P.transfer_fee_rate * amt)
                farm_burned += fee
                farm_sold += amt - fee
            else:
                still.append((exec_m, amt))
        sales_queue = still

        active_h = sum(1 for w in wallets if w.kind == "h" and w.act is not None)
        active_f = sum(1 for w in wallets if w.kind == "f" and w.act is not None)
        revenue_units = farm_sold * (1 - P.sell_fee)
        breakeven = farm_cost / revenue_units if revenue_units > 0 else float("nan")
        hcost_med = statistics.median(h_cost.values()) if h_cost else 0.0
        rows.append({
            "month": m + 1,
            "honest_active": active_h,
            "honest_pending": len(pend_h),
            "farm_active": active_f,
            "farm_pending": len(pend_f),
            "farm_share": active_f / max(1, active_h + active_f),
            "farm_cost_usd": farm_cost,
            "farm_units_net": farm_units_net,
            "farm_sold_units": farm_sold,
            "farm_burned_units": farm_burned,
            "breakeven_price": breakeven,
            "farm_profit_usd": revenue_units * P.unit_price - farm_cost,
            "honest_cost_median": hcost_med,
            "honest_cost_pct": 100.0 * hcost_med / P.base_mint,
            "honest_supply_per_wallet": (h_bal_sum / len(h_act)) if h_act else 0.0,
            "farm_stock_mean": (f_bal_sum / f_cnt) if f_cnt else 0.0,
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
            if k == "month":
                row[k] = vals[0]
            elif np is not None:
                row[k] = float(np.nanmean(vals))
            else:
                vals2 = [v for v in vals if not (isinstance(v, float) and math.isnan(v))]
                row[k] = float(sum(vals2) / len(vals2)) if vals2 else float("nan")
        out.append(row)
    return out


def aggregate(all_rows):
    """Средние по прогонам из уже выполненных simulate() (без повторного запуска)."""
    keys = all_rows[0][0].keys()
    out = []
    for t in range(len(all_rows[0])):
        row = {}
        for k in keys:
            vals = [r[t][k] for r in all_rows]
            if k == "month":
                row[k] = vals[0]
            elif np is not None:
                row[k] = float(np.nanmean(vals))
            else:
                vals2 = [v for v in vals if not (isinstance(v, float) and math.isnan(v))]
                row[k] = float(sum(vals2) / len(vals2)) if vals2 else float("nan")
        out.append(row)
    return out


def crossing_month(rows, price=CROSS_PRICE):
    """Первый месяц, когда безубыточная цена опустилась ниже price."""
    below = [r["month"] for r in rows if r["breakeven_price"] < price]
    return min(below) if below else None


def fmt(row):
    return (f"честные {row['honest_active']:7.0f} | ферма {row['farm_active']:6.0f} | "
            f"доля фермы {100 * row['farm_share']:5.1f}% | безубыточная цена ${row['breakeven_price']:.4f}")


def regression(runs: int):
    """Воспроизведение опубликованных цифр базы 1.1 (раздел 7.7) при выключенных новых механизмах."""
    res = run_many(Params(), runs)
    print(f"Регрессия базы 1.1: {runs} прогонов, механизмы этапа 1.2 выключены")
    ok = True
    for mo, (h0, f0, s0) in PUBLISHED_BASE.items():
        r = res[mo - 1]
        h, f, s = r["honest_active"], r["farm_active"], 100 * r["farm_share"]
        th, tf, ts = REGRESSION_TOL[mo]
        okh, okf, oks = abs(h - h0) <= th * h0, abs(f - f0) <= tf, abs(s - s0) <= ts
        ok = ok and okh and okf and oks
        print(f"  месяц {mo:>2}: {h:7.0f}/{f:6.0f}/{s:4.1f}%  (опубликовано {h0}/{f0}/{s0}%; "
              f"допуск ±{100*th:g}%/±{tf:g}/±{ts:g} п.п.) -> {'OK' if okh and okf and oks else 'FAIL'}")
    cross = crossing_month(res)
    print(f"  пересечение ${CROSS_PRICE}: месяц {cross} (в 7.7 — 38-й)")
    print("РЕГРЕССИЯ:", "ПРОЙДЕНА" if ok else "ПРОВАЛЕНА")
    return ok


def stage12_scenarios(base: Params):
    mint3 = 3.0 * base.base_mint      # floor «3 месячных выпуска»
    T = 0.5                           # оборот честных по умолчанию (экономика честных)
    fee1 = dict(transfer_fee_rate=0.01, transfer_fee_min=1.0)
    g = {}

    # база для сравнения (механизмы выкл., экономика честных включена для полей затрат)
    g["база 1.1 (механизмы выкл.)"] = replace(base, honest_turnover=T)

    # 1) демередж без окна переводимости (ферма сливает сразу)
    for fl_name, fl in (("floor=0", 0.0), ("floor=3мес", mint3)):
        for r_ in (0.005, 0.01, 0.02, 0.05):
            g[f"демередж {r_*100:g}%/мес, {fl_name}, окно 0"] = replace(
                base, demurrage_rate=r_, demurrage_floor=fl, honest_turnover=T)

    # 2а) изолированное окно (демередж выкл.) — отделяет задержку хвоста от сжигания
    for w_ in (3, 6):
        g[f"окно {w_} мес, демередж 0 (изолированное)"] = replace(
            base, fresh_window=w_, honest_turnover=T)

    # 2) окно переводимости x демередж (связка; окно заставляет ферму держать запас)
    for w_ in (1, 3, 6, 9, 12):
        for r_, fl in ((0.01, mint3), (0.02, 0.0), (0.02, mint3)):
            fl_name = "floor=3мес" if fl else "floor=0"
            g[f"окно {w_} мес + демередж {r_*100:g}%, {fl_name}"] = replace(
                base, demurrage_rate=r_, demurrage_floor=fl, fresh_window=w_, honest_turnover=T)

    # 3) комиссия на движение
    for fmin in (0.0, 1.0, 5.0):
        for rate in (0.005, 0.01, 0.02):
            g[f"комиссия rate={rate*100:g}%, fee_min={fmin:g}"] = replace(
                base, transfer_fee_rate=rate, transfer_fee_min=fmin, honest_turnover=T)

    # 4) P отложенного перевода и мораторий
    g["P=3000, лаг 0 мес (D=48ч)"] = replace(base, delay_threshold=3000.0,
                                            delay_lag_months=0, honest_turnover=T)
    g["P=3000, лаг 1 мес (верхняя граница)"] = replace(base, delay_threshold=3000.0,
                                                      delay_lag_months=1, honest_turnover=T)
    g["мораторий 0.5 мес (15 дней)"] = replace(base, moratorium_months=0.5, honest_turnover=T)
    g["мораторий 1 мес (30 дней)"] = replace(base, moratorium_months=1.0, honest_turnover=T)

    # 5) комбинации-кандидаты в рекомендацию
    g["A: дем1%/floor3м + окно3 + комиссия1%/min1 + морат0.5"] = replace(
        base, demurrage_rate=0.01, demurrage_floor=mint3, fresh_window=3,
        moratorium_months=0.5, honest_turnover=T, **fee1)
    g["B: дем2%/floor3м + окно6 + комиссия1%/min1 + морат0.5"] = replace(
        base, demurrage_rate=0.02, demurrage_floor=mint3, fresh_window=6,
        moratorium_months=0.5, honest_turnover=T, **fee1)
    g["C: дем2%/floor0 + окно3 + комиссия2%/min1 + морат0.5"] = replace(
        base, demurrage_rate=0.02, demurrage_floor=0.0, fresh_window=3,
        moratorium_months=0.5, transfer_fee_rate=0.02, transfer_fee_min=1.0, honest_turnover=T)
    g["D: дем5%/floor0 + окно3 + комиссия1%/min1 + морат0.5"] = replace(
        base, demurrage_rate=0.05, demurrage_floor=0.0, fresh_window=3,
        moratorium_months=0.5, honest_turnover=T, **fee1)

    # 6) чувствительность честных к обороту (на кандидатах A и B)
    for t_ in (0.2, 1.0):
        g[f"B, оборот честных {t_:g}"] = replace(
            base, demurrage_rate=0.02, demurrage_floor=mint3, fresh_window=6,
            moratorium_months=0.5, honest_turnover=t_, **fee1)
        g[f"A, оборот честных {t_:g}"] = replace(
            base, demurrage_rate=0.01, demurrage_floor=mint3, fresh_window=3,
            moratorium_months=0.5, honest_turnover=t_, **fee1)

    return g


def stage12(runs: int, out: str, group_filter=None):
    base = Params()
    groups = stage12_scenarios(base)
    if group_filter:
        groups = {k: v for k, v in groups.items() if group_filter.lower() in k.lower()}
    os.makedirs(out, exist_ok=True)
    print(f"Свеепы этапа 1.2: {runs} прогонов на сценарий; порог пересечения ${CROSS_PRICE}")
    hdr = (f"{'сценарий':58s} | {'доля ф. m60':>10s} | {'$ m38':>7s} | {'$ m60':>7s} | "
           f"{'перес. $0.01':>12s} | {'честные, % вып.':>14s} | {'сток фермы':>9s}")
    print(hdr)
    summary = []
    for name, P in groups.items():
        runs_rows = [simulate(P, s) for s in range(1, runs + 1)]
        mean_rows = aggregate(runs_rows)
        crosses = [crossing_month(r) for r in runs_rows]
        cross_med = statistics.median([c if c is not None else P.months + 1 for c in crosses])
        cross_txt = "60+" if cross_med > P.months else f"{cross_med:.0f} мес"
        be60 = [r[59]["breakeven_price"] for r in runs_rows]
        hcost60 = [r[59]["honest_cost_pct"] for r in runs_rows]
        m60 = mean_rows[59]
        m38 = mean_rows[37]
        drain = 100.0 * m60["farm_burned_units"] / m60["farm_units_net"] if m60["farm_units_net"] else 0.0
        print(f"{name:58s} | {100*m60['farm_share']:9.1f}% | {m38['breakeven_price']:7.4f} | "
              f"{m60['breakeven_price']:7.4f} | {cross_txt:>12s} | {m60['honest_cost_pct']:13.2f}% | "
              f"{m60['farm_stock_mean']:9.0f}")
        summary.append({
            "scenario": name, "farm_share_m60": 100 * m60["farm_share"],
            "breakeven_m38": m38["breakeven_price"], "breakeven_m60": m60["breakeven_price"],
            "breakeven_m60_min": min(be60), "breakeven_m60_max": max(be60),
            "crossing_001_median": cross_med,
            "honest_cost_pct_m60": m60["honest_cost_pct"],
            "honest_cost_pct_m60_min": min(hcost60), "honest_cost_pct_m60_max": max(hcost60),
            "farm_drain_pct_m60": drain,
            "honest_supply_per_wallet_m60": m60["honest_supply_per_wallet"],
            "farm_stock_mean_m60": m60["farm_stock_mean"],
        })
        fname = os.path.join(out, "s12_" + name.replace(" ", "_").replace("/", "-").replace(":", "").replace("%", "proc").replace(",", "") + ".csv")
        with open(fname, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(mean_rows[0].keys()))
            wr.writeheader()
            wr.writerows(mean_rows)
    sname = os.path.join(out, "stage12_summary.csv")
    with open(sname, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        wr.writeheader()
        wr.writerows(summary)
    print(f"\nCSV сохранены в: {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=8, help="число прогонов Монте-Карло на сценарий")
    ap.add_argument("--out", default="results", help="каталог для CSV и графиков")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--regression", action="store_true", help="проверка воспроизведения базы 1.1")
    ap.add_argument("--stage12", action="store_true", help="свеепы экономических параметров этапа 1.2")
    ap.add_argument("--group", default=None, help="фильтр сценариев stage12 по подстроке имени")
    args = ap.parse_args()

    if args.regression:
        ok = regression(args.runs)
        raise SystemExit(0 if ok else 1)

    if args.stage12:
        stage12(args.runs, args.out, args.group)
        return

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
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib недоступен — графики пропущены")
            return
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
            a.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "seed_and_budget.png"), dpi=130)
        print(f"\nГрафики и CSV сохранены в каталоге: {args.out}")


if __name__ == "__main__":
    main()
