import os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
MISTRAL=os.path.normpath(os.path.join(HERE,'..','..','..','Mistral'))
import json, math, statistics as st
D={}
for l in open(os.path.join(HERE,'..','data','exp4_per_seed.jsonl')):
    d=json.loads(l); D[d['name']]=d
def col(n,k): return [r[k] for r in D[n]['res']]
def m(n,k): return st.mean(col(n,k))
print("== Потолок honest_cap и «насыщение посевного круга» (12 сидов) ==")
print(f"{'сценарий':26s} {'честные m60':>12s} {'ферма m60':>10s} {'доля m60 %':>11s} {'пик %':>7s}")
for n in ('seed 300 cap=20000','seed 1000 cap=20000','seed 300 cap=100000','seed 1000 cap=100000'):
    if n in D: print(f"{n:26s} {m(n,'h60'):12.0f} {m(n,'f60'):10.0f} {m(n,'s60'):11.2f} {m(n,'peak'):7.2f}")
print("\n== Чувствительность к некалиброванным параметрам (20 сидов) ==")
print(f"{'recruit / vouch_prob':26s} {'честные m60':>12s} {'ферма m60':>10s} {'доля m60 %':>11s} {'пик %':>7s} {'пик мес.':>8s} {'be60 $':>8s}")
for n in sorted([k for k in D if k.startswith('recruit')]):
    print(f"{n.replace('recruit=','r=').replace(' vouch_prob=',' p='):26s} {m(n,'h60'):12.0f} {m(n,'f60'):10.0f} {m(n,'s60'):11.2f} {m(n,'peak'):7.2f} {m(n,'peak_m'):8.1f} {m(n,'be60'):8.4f}")
n='base'; print(f"{'r=0.1 p=0.5 (база, 100 сидов)':26s} {m(n,'h60'):12.0f} {m(n,'f60'):10.0f} {m(n,'s60'):11.2f} {m(n,'peak'):7.2f} {m(n,'peak_m'):8.1f} {m(n,'be60'):8.4f}")
print("\n== Стоимость устройства / электричество (8 сидов): безубыточная цена m60 ==")
print(f"{'device / power':22s} {'be60 $/ед.':>11s} {'стоимость фермы $':>18s} {'продано ед.':>14s}")
for n in sorted([k for k in D if k.startswith('device')], key=lambda s:(-float(s.split()[0].split('=')[1]), -float(s.split()[1].split('=')[1]))):
    print(f"{n:22s} {m(n,'be60'):11.5f} {m(n,'cost60'):18.0f} {m(n,'sold60'):14.0f}")
# $200 — линейный пересчёт от базы (device=120, power=0.5)
b=D['device=120.0 power=0.5']; cost=m('device=120.0 power=0.5','cost60'); sold=m('device=120.0 power=0.5','sold60')
reg=1140
cost200=cost+(200-120)*reg
print(f"\nпересчёт на $200 за устройство (линейно): стоимость ${cost200:,.0f}, безубыточная цена m60 ≈ ${cost200/(sold*0.99):.4f} (при $120: ${cost/(sold*0.99):.4f})")
