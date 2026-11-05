import os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
MISTRAL=os.path.normpath(os.path.join(HERE,'..','..','..','Mistral'))
import sys
sys.path.insert(0,MISTRAL)
import farm_model as fm
from dataclasses import replace
base=fm.Params()
print("device_cost -> месяц пересечения $0,01 (8 сидов, numpy-путь), be60:")
for dc in (200.0,120.0,60.0,12.0,0.0):
    allrows=[fm.simulate(replace(base,device_cost=dc),s) for s in range(1,9)]
    agg=fm.aggregate(allrows)
    cr=fm.crossing_month(agg)
    print(f"  ${dc:>5.0f}: пересечение m{cr}; be60=${agg[59]['breakeven_price']:.5f}; be24=${agg[23]['breakeven_price']:.4f}; be12=${agg[11]['breakeven_price']:.4f}")
print("\nприбыль фермы на m60 при цене единицы $0,01 (farm_profit_usd, ср. 8 сидов):")
for dc in (200.0,120.0,12.0):
    allrows=[fm.simulate(replace(base,device_cost=dc),s) for s in range(1,9)]
    agg=fm.aggregate(allrows)
    print(f"  ${dc:>5.0f}: прибыль m60 = ${agg[59]['farm_profit_usd']:,.0f}; стоимость ${agg[59]['farm_cost_usd']:,.0f}")
