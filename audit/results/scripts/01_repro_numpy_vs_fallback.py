import os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
MISTRAL=os.path.normpath(os.path.join(HERE,'..','..','..','Mistral'))
import sys, importlib.util, statistics as st
sys.path.insert(0,MISTRAL)
import farm_model as fm
from dataclasses import replace

def run(P, seeds):
    return [fm.simulate(P, s) for s in seeds]
def at(rows, m, key): return rows[m-1][key]
def mean_at(allrows, m, key): return sum(at(r,m,key) for r in allrows)/len(allrows)

base = fm.Params()
seeds8 = range(1,9)
print("== E1: воспроизведение опубликованной базы (8 сидов 1..8) ==")
print("опубликовано: m12 232/38/13.9  m24 568/334/36.8  m60 8348/1140/12.1; пик 39.6% на 27 мес.; пересечение $0.01 на 38")
def report(label, allrows):
    out=[]
    for m in (12,24,60):
        h=mean_at(allrows,m,'honest_active'); f=mean_at(allrows,m,'farm_active'); s=100*mean_at(allrows,m,'farm_share')
        out.append(f"m{m}: {h:.0f}/{f:.0f}/{s:.1f}%")
    agg = fm.aggregate(allrows)
    peak = max(agg, key=lambda r:r['farm_share'])
    cross = fm.crossing_month(agg)
    print(f"{label:34s} " + "  ".join(out) + f"  пик {100*peak['farm_share']:.1f}% на {peak['month']} мес.; пересечение: {cross}")
report("numpy-путь (текущий код)", run(base, seeds8))
saved = fm.np
fm.np = None
report("без numpy (fallback-Пуассон)", run(base, seeds8))
fm.np = saved

# оригинальная версия (Claude Sonnet 3.6)
spec = importlib.util.spec_from_file_location("orig", os.path.join(MISTRAL,'..','Claude Sonnet 3.6','farm_model.py'))
print("\n== оригинальный Claude Sonnet 3.6/farm_model.py: интерфейс ==")
src=open(os.path.join(MISTRAL,'..','Claude Sonnet 3.6','farm_model.py'),encoding='utf-8',errors='replace').read()
import re
print([l.strip()[:120] for l in src.split('\n') if re.match(r'\s*(def |class )',l)][:15])
print("device_cost в оригинале:", [l.strip()[:100] for l in src.split('\n') if 'device_cost' in l or 'cost' in l.lower()][:4])

print("\n== детерминизм: два запуска одного сида ==")
a=fm.simulate(base,1); b=fm.simulate(base,1)
print("идентичны:", a==b)

print("\n== RNG-поток: fallback-Пуассон и er используют один seed ==")
import random
seed=1
prnd=random.Random(seed*7919+1); er=random.Random(seed*7919+1)
print("первые 3 значения prnd:", [round(prnd.random(),6) for _ in range(3)])
print("первые 3 значения er  :", [round(er.random(),6) for _ in range(3)])
