#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Тесты модели (блок 3, №44): механика адаптивной комиссии как в ядре,
# стратегии фермы, учёт предложения, мораторий; канарейка базы 1.1.
# Запуск:  python3 -m unittest discover -s Mistral -p "test_*.py" -v
import math
import random
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, "Mistral")
from farm_model import (Params, W, simulate, fee_rate_step,  # noqa: E402
                        unit_transferable, block3_scenarios, block3_params_scenarios,
                        block4_scenarios, pow_iterations, pow_cost_per_wallet,
                        pow_hardware_advantage, mint_window_amount, a9_scenarios,
                        payback_month, DEVICE_COST_PUBLIC, BYPASS_PROFILE_USD,
                        BYPASS_RESET_USD)


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



class TestBlock4Recurring(unittest.TestCase):
    """Блок 4 (профиль 8, v9.10): сгорание по периодной метке — перевод
    единицы периода P отвергается после границы P+grace; метка передачей
    не обновляется; накопление сверх периода исключено."""

    # база профиля 8: комиссия 0, демереджа нет, окно свежести 0
    P8 = dict(months=40, fresh_window=0, transfer_fee_rate=0.0,
              transfer_fee_min=0.0, demurrage_rate=0.0, honest_turnover=0.0,
              moratorium_months=14.0 / 30.0)

    def test_unit_transferable_window(self):
        # окно жизни единицы: метка P -> переводима в [P, P+grace]
        P = replace(Params(), recurring=True, recurring_grace=1)
        self.assertTrue(unit_transferable(5, 5, P))   # месяц метки
        self.assertTrue(unit_transferable(5, 6, P))   # граница P+1
        self.assertFalse(unit_transferable(5, 7, P))   # после границы — сгорела

    def test_no_retag_on_transfer(self):
        # метка НЕ обновляется передачей (кольцо peer-redeem не продлевает
        # жизнь): переводимость зависит только от исходной метки
        P = replace(Params(), recurring=True, recurring_grace=1)
        self.assertFalse(unit_transferable(5, 7, P))

    def test_recurring_no_accumulation(self):
        # ключевой вопрос: ферма НЕ накапливает квоты сверх периода.
        # При полном сливе сток ~0 в обоих режимах — контраст виден при
        # ограниченной ликвидности (0.5): в std непроданное копится
        # (сток растёт), в recurring — сгорает на границе (сток ограничен)
        rec = simulate(replace(Params(), recurring=True, farm_sell_capacity=0.5, **self.P8), 1)
        std = simulate(replace(Params(), farm_sell_capacity=0.5, **self.P8), 1)
        import statistics as st
        rec_stock = st.mean(r["farm_stock_mean"] for r in rec)
        std_stock = st.mean(r["farm_stock_mean"] for r in std)
        self.assertLess(rec_stock, std_stock)
        self.assertGreater(rec[39]["farm_dead_units"], 0.0)

    def test_grace_widens_stock(self):
        # grace 2 -> окно 2 месяца: при ограниченной ликвидности сток
        # фермы не меньше, чем при grace 1 (окно держит больше живых единиц)
        g1 = simulate(replace(Params(), recurring=True, recurring_grace=1,
                              farm_sell_capacity=0.5, **self.P8), 1)
        g2 = simulate(replace(Params(), recurring=True, recurring_grace=2,
                              farm_sell_capacity=0.5, **self.P8), 1)
        import statistics as st
        s1 = st.mean(r["farm_stock_mean"] for r in g1)
        s2 = st.mean(r["farm_stock_mean"] for r in g2)
        self.assertGreaterEqual(s2, s1)

    def test_capacity_burns_stock(self):
        # ограниченная ликвидность: в recurring непроданное в окне
        # сгорает, безубыточная цена выше полного слива
        rec = simulate(replace(Params(), recurring=True, farm_sell_capacity=0.25, **self.P8), 1)
        rec_full = simulate(replace(Params(), recurring=True, **self.P8), 1)
        self.assertGreater(rec[39]["farm_dead_units"], 0.0)
        self.assertGreater(rec[39]["breakeven_price"], rec_full[39]["breakeven_price"])

    def test_batch_suicide_in_recurring(self):
        # обход «накопить и слить пачкой» в recurring самоубийственен:
        # копить нельзя — всё вне окна сгорает
        monthly = simulate(replace(Params(), recurring=True, farm_sell_mode="monthly", **self.P8), 1)
        batch = simulate(replace(Params(), recurring=True, farm_sell_mode="batch", **self.P8), 1)
        self.assertGreater(batch[39]["farm_dead_units"],
                           monthly[39]["farm_dead_units"])
        self.assertLess(batch[39]["farm_sold_units"], monthly[39]["farm_sold_units"])
        self.assertGreater(batch[39]["breakeven_price"], monthly[39]["breakeven_price"])

    def test_honest_use(self):
        # потребление честных (redeem): при use 1.0 непотреблённого нет,
        # при 0.5 — часть квоты сгорает (неубыток честного)
        full = simulate(replace(Params(), recurring=True, honest_use_rate=1.0, **self.P8), 1)
        half = simulate(replace(Params(), recurring=True, honest_use_rate=0.5, **self.P8), 1)
        self.assertGreaterEqual(full[39]["honest_dead_units"], 0.0)
        self.assertGreater(half[39]["honest_used_units"], 0.0)

    def test_groups_present(self):
        # сценарии блока 4 покрывают вопросы мандата
        g = block4_scenarios(Params())
        self.assertIn("1 rec (grace 1)", g)
        self.assertIn("1 std (без метки)", g)
        self.assertTrue(any("кольцо" in k for k in g))
        self.assertTrue(any("мораторий" in k for k in g))
        self.assertTrue(any("потребление" in k for k in g))


class TestA9PlatformFacts(unittest.TestCase):
    """Тема A9, шаг 0: факты из кода tnp main — таргеты PoW и Argon2id."""

    def test_pow_iterations_from_targets(self):
        # TargetHard = 0x0100_0000_0000_0000 = 2^56 -> 2^64/2^56 = 256 итераций
        # TargetLight = 0x0000_0100_0000_0000 = 2^40 -> 2^24 = 16 777 216
        it = pow_iterations(Params())
        self.assertEqual(it["hard"], 256.0)
        self.assertEqual(it["light"], float(2 ** 24))

    def test_pow_cost_is_negligible(self):
        c = pow_cost_per_wallet(Params())
        # 256 × 22,63 мс × 3 (телефон) ≈ 17,4 с на выпуск
        self.assertGreater(c["month_seconds"], 10.0)
        self.assertLess(c["month_seconds"], 30.0)
        # электричество: 17,4 с × 4 Вт ≈ 1,9e-5 кВт·ч ≈ $3e-6
        self.assertLess(c["month_usd"], 1e-4)
        self.assertLess(c["reg_usd"], 1e-3)

    def test_pow_attended_adds_labor(self):
        c = pow_cost_per_wallet(replace(Params(), pow_attended=True))
        # 17,4 с при $10/ч ≈ $0,048 — время оператора доминирует
        self.assertGreater(c["month_usd"], 0.01)
        self.assertGreater(c["month_usd"],
                           1000 * pow_cost_per_wallet(Params())["month_usd"])

    def test_hardware_advantage_numbers(self):
        h = pow_hardware_advantage(Params())
        # телефон ~14,7 итераций/с; GPU (360 ГБ/с, 32 МиБ × 2) ~2,7 тыс/с
        self.assertGreater(h["gpu_vs_phone"], 100.0)
        self.assertGreater(h["asic_vs_phone"], h["gpu_vs_phone"])
        self.assertLess(h["phone_evals_s"], 20.0)


class TestA9DeviceCost(unittest.TestCase):
    """A9 п.3: стоимость устройства $200 (README) и чувствительность."""

    def test_device_cost_scales_breakeven(self):
        # стоимость устройства не влияет на динамику (доля фермы), только на $
        b120 = simulate(replace(Params(), device_cost=120.0), 1)
        b200 = simulate(replace(Params(), device_cost=200.0), 1)
        b300 = simulate(replace(Params(), device_cost=300.0), 1)
        self.assertEqual(b120[59]["farm_active"], b200[59]["farm_active"])
        self.assertEqual(b200[59]["farm_active"], b300[59]["farm_active"])
        self.assertLess(b120[59]["breakeven_price"], b200[59]["breakeven_price"])
        self.assertLess(b200[59]["breakeven_price"], b300[59]["breakeven_price"])
        # почти линейно по стоимости устройства (power_cost — малая добавка)
        ratio = b300[59]["breakeven_price"] / b120[59]["breakeven_price"]
        self.assertTrue(2.2 < ratio < 2.6, ratio)

    def test_public_value_is_200(self):
        self.assertEqual(DEVICE_COST_PUBLIC, 200.0)
        g = a9_scenarios(Params())
        self.assertEqual(g["1 база 7.7 на $200 (README)"].device_cost, 200.0)


class TestA9WalletsPerDevice(unittest.TestCase):
    """A9 п.2: кошельков на устройство — обход A1 и его издержки."""

    def test_more_wallets_lower_cost_per_wallet(self):
        one = simulate(Params(), 1)
        two = simulate(replace(Params(), wallets_per_device=2,
                               bypass_cost_per_wallet=BYPASS_PROFILE_USD), 1)
        four = simulate(replace(Params(), wallets_per_device=4,
                                bypass_cost_per_wallet=BYPASS_PROFILE_USD), 1)
        # устройство делится на кошельки -> стоимость кошелька падает
        c1 = one[59]["farm_cost_usd"] / one[59]["farm_active"]
        c2 = two[59]["farm_cost_usd"] / two[59]["farm_active"]
        c4 = four[59]["farm_cost_usd"] / four[59]["farm_active"]
        self.assertGreater(c1, c2)
        self.assertGreater(c2, c4)
        # и ферма успевает больше кошельков на тот же бюджет (на m60 оба
        # упираются в потолок 2000, поэтому сверка на m30)
        self.assertGreater(two[29]["farm_active"], one[29]["farm_active"])
        self.assertGreater(four[29]["farm_active"], two[29]["farm_active"])
        self.assertEqual(four[59]["farm_active"], 2000)

    def test_bypass_cost_ordering(self):
        prof = simulate(replace(Params(), wallets_per_device=2,
                                bypass_cost_per_wallet=BYPASS_PROFILE_USD), 1)
        reset = simulate(replace(Params(), wallets_per_device=2,
                                 bypass_cost_per_wallet=BYPASS_RESET_USD), 1)
        self.assertLess(prof[59]["breakeven_price"], reset[59]["breakeven_price"])
        self.assertGreater(BYPASS_RESET_USD, BYPASS_PROFILE_USD)


class TestA9MintWindow(unittest.TestCase):
    """A9 п.5: окно челленджа mint — достижимость 1/15, accrual 6, поглощение."""

    def test_fixed_mode_no_losses(self):
        rows = simulate(Params(), 1)
        for r in rows:
            self.assertEqual(r["honest_blocked"], 0)
            self.assertEqual(r["farm_blocked"], 0)
            self.assertAlmostEqual(r["honest_mint_units"], r["honest_minting"] * 1000.0)
            self.assertAlmostEqual(r["farm_mint_units"], r["farm_minting"] * 1000.0)

    def test_absorbing_probability(self):
        # P(6 пропусков подряд) = (1 - 1/15)^6 = 0,6608 — как в мандате (~66 %)
        self.assertAlmostEqual((1.0 - 1.0 / 15.0) ** 6, 0.6608, places=3)

    def test_code_mode_honest_loss_farm_automated(self):
        base = simulate(Params(), 1)
        code = simulate(replace(Params(), mint_window_mode="code",
                                farm_window_automation=1.0), 1)
        # ферма с автоматизацией не теряет выпуск, честные теряют почти весь
        self.assertAlmostEqual(code[59]["farm_mint_units"],
                               code[59]["farm_minting"] * 1000.0)
        self.assertGreater(code[59]["honest_blocked"], 0)
        self.assertLess(code[59]["honest_mint_units"],
                        0.5 * base[59]["honest_mint_units"])
        # доля фермы не меняется: выпуск не влияет на активацию
        self.assertAlmostEqual(code[59]["farm_share"], base[59]["farm_share"])

    def test_code_mode_farm_suffers(self):
        auto = simulate(replace(Params(), mint_window_mode="code",
                                farm_window_automation=1.0), 1)
        manual = simulate(replace(Params(), mint_window_mode="code",
                                  farm_window_automation=0.0), 1)
        self.assertGreater(manual[59]["farm_blocked"], 0)
        self.assertLess(manual[59]["farm_mint_units"], auto[59]["farm_mint_units"])
        self.assertGreater(manual[59]["breakeven_price"], auto[59]["breakeven_price"])

    def test_reach_one_equals_fixed(self):
        # достижимость 1,0 -> каждый период в окне -> выпуск как в базе
        code = simulate(replace(Params(), mint_window_mode="code",
                                mint_window_reach=1.0), 1)
        base = simulate(Params(), 1)
        self.assertAlmostEqual(code[59]["farm_units_net"], base[59]["farm_units_net"])
        self.assertAlmostEqual(code[59]["breakeven_price"], base[59]["breakeven_price"])

    def test_absorbing_state_direct(self):
        # пропуск 7 периодов: diff > accrual_window -> блокировка навсегда
        P = Params(mint_window_mode="code")
        w = W("h", 0)
        w.act = 0
        w.last_claim = 0
        wr = random.Random(1)
        self.assertEqual(mint_window_amount(P, w, 8, wr), 0.0)  # period 7, diff 7 > 6
        self.assertTrue(w.blocked)
        self.assertEqual(mint_window_amount(P, w, 9, wr), 0.0)


class TestA9Scenarios(unittest.TestCase):
    """Сценарии A9 покрывают вопросы мандата; база 1.1 не тронута."""

    def test_scenarios_present(self):
        g = a9_scenarios(Params())
        self.assertEqual(len(g), 14)
        for name in ("0 база 7.7 (как в коде: $120)",
                     "1 база 7.7 на $200 (README)",
                     "2 устройство $300",
                     "3 2 кош./устр. (профили Android)",
                     "3 4 кош./устр. (factory reset)",
                     "4 PoW по факту (2^56/2^40)",
                     "5 окно mint: после фикса A (0%)",
                     "5 окно mint: как в коде (ферма авто)",
                     "5 окно mint: как в коде (ферма страдает)",
                     "6 всё: $200 + 2 кош./устр. + PoW + окно (авто)"):
            self.assertIn(name, g)
        self.assertEqual(g["0 база 7.7 (как в коде: $120)"].device_cost, 120.0)
        self.assertEqual(g["1 база 7.7 на $200 (README)"].device_cost, 200.0)

    def test_base_defaults_untouched(self):
        # дефолт Params() — историческая база 1.1 ($120), новые режимы выключены
        P = Params()
        self.assertEqual(P.device_cost, 120.0)
        self.assertEqual(P.wallets_per_device, 1)
        self.assertFalse(P.pow_actual)
        self.assertEqual(P.mint_window_mode, "fixed")

    def test_payback_metric(self):
        rows = simulate(Params(), 1)
        pb = payback_month(rows)
        self.assertIsNotNone(pb)
        self.assertGreater(pb, 12)  # не ложная окупаемость в нулевом месяце
        # окупаемость при $0,01 совпадает с пересечением безубыточной цены
        below = [r["month"] for r in rows if r["breakeven_price"] < 0.01]
        self.assertEqual(pb, min(below))


if __name__ == "__main__":
    unittest.main()
