#!/usr/bin/env python3
"""Аудит A9: независимый пересчёт метрик из CSV (без импорта модели).

Проверяет, что сводка `Mistral/results/a9_summary.csv` соответствует CSV
сценариев, пересчитывая метрики по определениям из farm_model.py:

  farm_share = farm_active / (honest_active + farm_active), среднее по прогонам
  пик        = максимум по месяцам средней по прогонам доли
  breakeven  = farm_cost_usd / (farm_sold_units * (1 - sell_fee))  [колонка CSV]
  crossing   = первый месяц, где breakeven_price < 0.01 (медиана по прогонам)
  payback    = первый месяц, где farm_cost_usd > 0 и farm_profit_usd >= 0

Средний CSV сценария есть в репозитории; per-seed CSV — нет (в репо только
манифесты SHA-256), поэтому при отсутствии они пересчитываются моделью в
временный каталог одной командой на seed (по одному прогону за раз).

Запуск: python3 reports/audit-a9-simulation/recheck_metrics.py [--seeds-dir DIR]
"""
import argparse
import csv
import os
import statistics
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "Mistral", "results")
MODEL = os.path.join(ROOT, "Mistral", "farm_model.py")

SCENARIOS = [
    ("1 база 7.7 на $200 (README)", "на $200"),
    ("5 окно mint: как в коде (ферма страдает)", "ферма страдает"),
]


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]


def share(row):
    return row["farm_active"] / (row["honest_active"] + row["farm_active"])


def crossing(rows, price=0.01):
    for r in rows:
        if r["breakeven_price"] < price:
            return r["month"]
    return None


def payback(rows):
    for r in rows:
        if r["farm_cost_usd"] > 0.0 and r["farm_profit_usd"] >= 0.0:
            return r["month"]
    return None


def ensure_seeds(group, seeds_dir):
    """Per-seed CSV для сценария; при отсутствии — прогон модели по одному seed."""
    os.makedirs(seeds_dir, exist_ok=True)
    paths = []
    for seed in range(1, 9):
        found = [f for f in os.listdir(seeds_dir)
                 if f.endswith(f"_seed{seed}.csv") and group.replace(" ", "_") in f]
        if found:
            paths.append(os.path.join(seeds_dir, found[0]))
            continue
        subprocess.run([sys.executable, MODEL, "--a9", "--seed", str(seed),
                        "--group", group, "--out", seeds_dir],
                       check=True, stdout=subprocess.DEVNULL)
        found = [f for f in os.listdir(seeds_dir)
                 if f.endswith(f"_seed{seed}.csv") and group.replace(" ", "_") in f]
        paths.append(os.path.join(seeds_dir, found[0]))
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds-dir", default=None,
                    help="каталог per-seed CSV (по умолчанию временный)")
    args = ap.parse_args()
    seeds_dir = args.seeds_dir or tempfile.mkdtemp(prefix="a9_audit_seeds_")

    summary = {r["scenario"]: r for r in csv.DictReader(
        open(os.path.join(RES, "a9_summary.csv"), newline="", encoding="utf-8"))}
    ok = True
    for label, group in SCENARIOS:
        s = summary[label]
        mean_rows = read(os.path.join(RES,
            "a9_" + label.replace(" ", "_").replace("/", "-").replace(":", "")
            .replace("%", "proc").replace(",", "") + ".csv"))
        runs = [read(p) for p in ensure_seeds(group, seeds_dir)]
        share_m60 = 100 * statistics.mean(share(r[59]) for r in runs)
        series = [statistics.mean(share(r[m]) for r in runs) for m in range(len(runs[0]))]
        peak = 100 * max(series)
        peak_month = series.index(max(series)) + 1
        crosses = [crossing(r) for r in runs]
        pays = [payback(r) for r in runs]
        months = len(runs[0])
        cross_med = statistics.median([c if c is not None else months + 1 for c in crosses])
        pay_med = statistics.median([p if p is not None else months + 1 for p in pays])
        checks = [
            ("доля фермы m60, %", share_m60, float(s["farm_share_m60"])),
            ("пик доли, %", peak, float(s["farm_share_peak"])),
            ("месяц пика", float(peak_month), float(s["farm_share_peak_month"])),
            ("безубыточная цена m60", mean_rows[59]["breakeven_price"], float(s["breakeven_m60"])),
            ("пересечение $0,01 (медиана)", cross_med, float(s["crossing_001_median"])),
            ("окупаемость (медиана)", pay_med, float(s["payback_month_median"])),
        ]
        print(f"--- {label} ---")
        for name, got, want in checks:
            good = abs(got - want) < 1e-6
            ok = ok and good
            print(f"  {name:32s} пересчёт {got:14.6f}  сводка {want:14.6f}  {'OK' if good else 'РАСХОЖДЕНИЕ'}")
        print(f"  per-run пересечение: {crosses}")
    print("ИТОГ:", "все метрики совпали" if ok else "ЕСТЬ РАСХОЖДЕНИЯ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
