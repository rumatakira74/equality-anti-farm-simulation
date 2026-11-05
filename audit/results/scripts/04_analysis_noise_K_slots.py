import os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
MISTRAL=os.path.normpath(os.path.join(HERE,'..','..','..','Mistral'))
import json, math, statistics as st, random
D={}
for l in open(os.path.join(HERE,'..','data','exp4_per_seed.jsonl')):
    d=json.loads(l); D[d['name']]=d
def col(n,k): return [r[k] for r in D[n]['res']]
def ms(x): return st.mean(x), (st.stdev(x) if len(x)>1 else 0.0)
def ci95(x):
    m,s=ms(x); h=1.96*s/math.sqrt(len(x)); return m-h,m+h
def welch(a,b):
    ma,sa=ms(a); mb,sb=ms(b); na,nb=len(a),len(b)
    se=math.sqrt(sa*sa/na+sb*sb/nb); t=(ma-mb)/se if se>0 else float('inf'); return t
print("== Шум базы: 100 сидов ==")
for k,lab in (('s12','доля фермы m12, %'),('s24','m24'),('s60','m60'),('peak','пик'),('h60','честные m60'),('be60','безубыточная цена m60')):
    x=col('base',k); m,s=ms(x); lo,hi=ci95(x)
    print(f"  {lab:24s} среднее {m:9.4f}  SD по прогонам {s:8.4f}  95% ДИ среднего (N=100) [{lo:.4f}; {hi:.4f}]")
# 8-прогоновые блоки: распределение «опубликованного» среднего
blocks=[col('base','s60')[i:i+8] for i in range(0,96,8)]
bm=[st.mean(b) for b in blocks]
print(f"\n== 8-прогоновое среднее доли фермы m60 по 12 непересекающимся блокам сидов ==")
print("  значения:", [round(v,1) for v in bm])
print(f"  min {min(bm):.1f}  max {max(bm):.1f}  SD {st.stdev(bm):.2f} п.п.")
for k,lab in (('s24','m24'),('peak','пик')):
    bb=[st.mean(col('base',k)[i:i+8]) for i in range(0,96,8)]
    print(f"  {lab}: min {min(bb):.1f} max {max(bb):.1f} SD {st.stdev(bb):.2f} п.п.")
bh=[st.mean(col('base','h60')[i:i+8]) for i in range(0,96,8)]
print(f"  честные m60: min {min(bh):.0f} max {max(bh):.0f}")
print("\n== Сравнения (60 сидов; Welch t, |t|>2 ≈ значимо на 5%) ==")
print(f"{'сценарий':16s} {'s60 %':>13s} {'peak %':>13s} {'пик месяц':>9s} {'s24 %':>13s} {'честные m60':>12s} {'farm m60':>9s}")
for n in ('base','K=2','K=4','K=5','slots 2/2/10','slots 5/8/15'):
    sl=slice(0,60)
    s60=col(n,'s60')[sl]; pk=col(n,'peak')[sl]; s24=col(n,'s24')[sl]; h=col(n,'h60')[sl]; f=col(n,'f60')[sl]; pm=col(n,'peak_m')[sl]
    print(f"{n:16s} {st.mean(s60):6.1f}±{1.96*st.stdev(s60)/math.sqrt(60):4.1f} {st.mean(pk):6.1f}±{1.96*st.stdev(pk)/math.sqrt(60):4.1f} {st.mean(pm):9.1f} {st.mean(s24):6.1f}±{1.96*st.stdev(s24)/math.sqrt(60):4.1f} {st.mean(h):12.0f} {st.mean(f):9.0f}")
b60=col('base','s60')[:60]; bpk=col('base','peak')[:60]
print("\nWelch t относительно базы (s60 / peak):")
for n in ('K=2','K=4','K=5','slots 2/2/10','slots 5/8/15'):
    print(f"  {n:14s} s60 t={welch(col(n,'s60'),b60):6.2f}   peak t={welch(col(n,'peak'),bpk):6.2f}")
print("\nслоты: узкие против щедрых:  s60 t=%.2f   peak t=%.2f" % (welch(col('slots 2/2/10','s60'),col('slots 5/8/15','s60')), welch(col('slots 2/2/10','peak'),col('slots 5/8/15','peak'))))
