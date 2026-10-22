#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Тесты модели (блок 3, №44): механика адаптивной комиссии как в ядре,
# стратегии фермы, учёт предложения, мораторий; канарейка базы 1.1.
# Запуск:  python3 -m unittest discover -s Mistral -p "test_*.py" -v
import math
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, "Mistral")
from farm_model import (Params, simulate, fee_rate_step,  # noqa: E402
                        block3_scenarios, block3_params_scenarios)


class TestFeeRateStep(unittest.TestCase):
    """Шаг ставки — механика core/ledger/fee.go (решение №44)."""

    P = Params(adaptive_fee=True)

    def test_step_up(self):
        # рост выше цели 6% -> +0,05 п.п.
        self.assertAlmostEqual(fee_rate_step(0.07, 0.005, self.P), 0.0055)

    def test_step_down(self):
        # рост ниже цели -> -0,05 п.п.
        self.assertAlmostEqual(fee_rate_step(0.05, 0.01, self.P), 0.0095)

    def test_floor(self):
        # не ниже нижней границы 0,5%
        self.assertAlmostEqual(fee_rate_step(0.0, 0.005, self.P), 0.005)
        self.assertAlmostEqual(fee_rate_step(0.0, 0.0052, self.P), 0.005)

    def test_ceiling(self):
        # зажим на верхней границе 2%
        self.assertAlmostEqual(fee_rate_step(0.5, 0.02, self.P), 0.02)

    def test_growth_equal_target_is_down(self):
        # рост ровно по цели — не выше цели -> шаг вниз (как в ядре: else)
        self.assertAlmostEqual(fee_rate_step(0.06, 0.01, self.P), 0.0095)


class TestAdaptiveInSimulation(unittest.TestCase):
    """Адаптивная ставка внутри simulate(): старт с минимума, шаги 0,05 п.п.,
    границы [0,5; 2]%, окно K+1 снимков (первый пересчёт — после K эпох)."""

    def test_growing_network_rises(self):
        P = replace(Params(adaptive_fee=True), months=30)
        rows = simulate(P, 1)
        rates = [r["fee_rate_pct"] for r in rows]
        self.assertAlmostEqual(rates[0], 0.5)  # старт с нижней границы (FeeRate = RateMin)
        # изменения ставки — только 0 (окно не заполнено / рост не
        # определён) или ровно +0,05 п.п. (растущая сеть); всегда в границах
        for a, b in zip(rates, rates[1:]):
            self.assertIn(round(b - a, 10), (0.0, 0.05))
            self.assertTrue(0.5 - 1e-9 <= b <= 2.0 + 1e-9)
        # растущая сеть: к 30-му месяцу ставка выросла
        self.assertGreater(rates[-1], 0.5)

    def test_first_adjust_not_before_window(self):
        # нужно K+1 снимков: до K=6 эпох включительно ставка не меняется
        P = replace(Params(adaptive_fee=True), months=8)
        rows = simulate(P, 1)
        rates = [r["fee_rate_pct"] for r in rows]
        self.assertAlmostEqual(rates[6], 0.5)  # m=6: снимков ещё 7 -> первый пересчёт
        # (снимок m=0 имеет supply=0 -> рост не определён, ставка не меняется)

    def test_fixed_rate_constant(self):
        P = replace(Params(transfer_fee_rate=0.01), months=20)
        rows = simulate(P, 1)
        rates = {r["fee_rate_pct"] for r in rows}
        self.assertEqual(rates, {1.0})


class TestSupplyAccounting(unittest.TestCase):
    """total_supply = выпуск - сжигания; при выключенных механизмах
    сжиганий нет: предложение = суммарный выпуск активных."""

    def test_no_burn(self):
        P = Params(months=3)  # механизмы выкл.
        rows = simulate(P, 1)
        # 1-й месяц: 100 посевных выпускают по 1000, сжиганий нет
        self.assertAlmostEqual(rows[0]["total_supply"], 100 * 1000.0)

    def test_burn_reduces(self):
        P = replace(Params(months=3), demurrage_rate=0.01, demurrage_floor=0.0,
                    honest_turnover=0.5, transfer_fee_rate=0.01, transfer_fee_min=0.01)
        rows = simulate(P, 1)
        # со сжиганиями предложение меньше полного выпуска
        self.assertLess(rows[2]["total_supply"], rows[2]["total_supply"] + 1)  # sanity
        # без сжиганий предложение росло бы быстрее: сверка с чистым прогоном
        clean = simulate(Params(months=3), 1)
        self.assertLess(rows[2]["total_supply"], clean[2]["total_supply"])


class TestFarmStrategies(unittest.TestCase):
    """Стратегии фермы против адаптивности: batch копит, low_rate ждёт
    нижней границы, monthly сливает сразу."""

    BASE = dict(months=40, adaptive_fee=True, demurrage_rate=0.01,
                demurrage_floor=3000.0, fresh_window=3,
                moratorium_months=0.5, transfer_fee_min=0.01,
                honest_turnover=0.5)

    def test_batch_holds_stock(self):
        monthly = simulate(replace(Params(), farm_sell_mode="monthly", **self.BASE), 1)
        batch = simulate(replace(Params(), farm_sell_mode="batch", **self.BASE), 1)
        # при накоплении средний за прогон сток фермы больше, продано меньше
        # (точечный замер на месяце слива дал бы артефакт периодичности batch)
        import statistics as st
        batch_stock = st.mean(r["farm_stock_mean"] for r in batch if r["farm_stock_mean"] > 0)
        monthly_stock = st.mean(r["farm_stock_mean"] for r in monthly if r["farm_stock_mean"] > 0)
        self.assertGreater(batch_stock, monthly_stock)
        self.assertLess(batch[39]["farm_sold_units"], monthly[39]["farm_sold_units"])

    def test_low_rate_waits_bottom(self):
        rows = simulate(replace(Params(), farm_sell_mode="low_rate", **self.BASE), 1)
        # на растущей сети ставка уходит вверх: ферма копит, сток растёт
        self.assertGreater(rows[39]["farm_stock_mean"], 0.0)
        # продажи монотонны (копит и сливает порциями)
        sold = [r["farm_sold_units"] for r in rows]
        self.assertTrue(all(b >= a for a, b in zip(sold, sold[1:])))


class TestMoratorium(unittest.TestCase):
    """Мораторий 7-30 дней задерживает первый слив фермы (схема
    «зарегистрировал -> слил»); при окне 6 мес. мораторий на его фоне мал."""

    def test_moratorium_delays_first_sale(self):
        # месячная сетка не различает 7 и 30 дней (оба < шаг модели);
        # разрешимый контраст: мораторий 0 против 1 мес.
        def first_sale_month(mor):
            P = replace(Params(months=20), fresh_window=0,
                        moratorium_months=mor, honest_turnover=0.5)
            rows = simulate(P, 1)
            for r in rows:
                if r["farm_sold_units"] > 0:
                    return r["month"]
            return None
        m0 = first_sale_month(0.0)
        m1 = first_sale_month(1.0)
        self.assertIsNotNone(m0)
        self.assertIsNotNone(m1)
        self.assertGreaterEqual(m1, m0)
        # 7 и 30 дней в месячной сетке дают один и тот же месяц первого слива
        self.assertEqual(first_sale_month(7 / 30), first_sale_month(30 / 30))


class TestBaseCanary(unittest.TestCase):
    """Канарейка базы 1.1: потоки RNG не тронуты расширениями блока 3 —
    ключевые числа прогона seed=1 совпадают с зафиксированными."""

    def test_seed1_numbers(self):
        rows = simulate(Params(), 1)
        self.assertEqual(rows[11]["honest_active"], 230)
        self.assertEqual(rows[59]["farm_active"], 1139)
        self.assertAlmostEqual(rows[59]["breakeven_price"], 0.005317, places=5)
        self.assertAlmostEqual(rows[37]["breakeven_price"], 0.010204, places=5)


class TestBlock3Scenarios(unittest.TestCase):
    """Сценарии блока 3 собираются и параметры согласованы с №44."""

    def test_groups_present(self):
        g = block3_scenarios(Params())
        names = " ".join(g)
        for prefix in ("1 ", "2 ", "3 ", "4 ", "5 ", "6 "):
            self.assertIn(prefix, names)
        # дефолты №44: K=6, цель 6%, шаг 0,05 п.п., границы [0,5; 2]%, fee_min 0,01
        adaptive = g["1 адаптивная (старт 0.5%)"]
        self.assertTrue(adaptive.adaptive_fee)
        self.assertEqual(adaptive.fee_adjust_epochs, 6)
        self.assertAlmostEqual(adaptive.fee_target_growth, 0.06)
        self.assertAlmostEqual(adaptive.fee_step, 0.0005)
        self.assertAlmostEqual(adaptive.fee_rate_min, 0.005)
        self.assertAlmostEqual(adaptive.fee_rate_max, 0.02)
        self.assertAlmostEqual(adaptive.transfer_fee_min, 0.01)
        # фиксированные сценарии не адаптивны
        self.assertFalse(g["1 фикс 1%"].adaptive_fee)


class TestBlock3ParamsScenarios(unittest.TestCase):
    """Контрольные сценарии цели 15%/окно (мини-этап 11.4, решение
    владельца 22.10.2026 по итогам блока 3)."""

    def test_groups_present(self):
        g = block3_params_scenarios(Params())
        self.assertEqual(len(g), 9)
        for name in ("оборот 0.25", "оборот 0.5", "оборот 1",
                     "равномерный рост", "сжатие (приток -3%/мес)",
                     "шок притока x5 (мес 24-26)", "зрелая сеть (потолок 2000)",
                     "зрелая сеть 120 мес (потолок 2000)",
                     "сжатие 120 мес (приток -3%/мес)"):
            self.assertIn(name, g)
        # цель 15%/окно в каждом сценарии; механика №44 не меняется
        for name, P in g.items():
            self.assertTrue(P.adaptive_fee, name)
            self.assertAlmostEqual(P.fee_target_growth, 0.15)
            self.assertEqual(P.fee_adjust_epochs, 6)
            self.assertAlmostEqual(P.fee_step, 0.0005)
            self.assertAlmostEqual(P.fee_rate_min, 0.005)
            self.assertAlmostEqual(P.fee_rate_max, 0.02)
            self.assertAlmostEqual(P.transfer_fee_min, 0.01)
            # база «профиль 7»: демередж 1%/мес, floor 3000, окно 3, мораторий 14 д
            self.assertAlmostEqual(P.demurrage_rate, 0.01)
            self.assertAlmostEqual(P.demurrage_floor, 3000.0)
            self.assertEqual(P.fresh_window, 3)
            self.assertAlmostEqual(P.moratorium_months, 14.0 / 30.0)
        # сценарии динамики сети
        self.assertAlmostEqual(g["сжатие (приток -3%/мес)"].recruit_decay, 0.97)
        shock = g["шок притока x5 (мес 24-26)"]
        self.assertEqual((shock.recruit_shock_month, shock.recruit_shock_mult,
                          shock.recruit_shock_len), (24, 5.0, 3))
        self.assertEqual(g["зрелая сеть (потолок 2000)"].honest_cap, 2000)
        # обороты честных
        self.assertAlmostEqual(g["оборот 0.25"].honest_turnover, 0.25)
        self.assertAlmostEqual(g["оборот 0.5"].honest_turnover, 0.5)
        self.assertAlmostEqual(g["оборот 1"].honest_turnover, 1.0)


if __name__ == "__main__":
    unittest.main()
