import os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
MISTRAL=os.path.normpath(os.path.join(HERE,'..','..','..','Mistral'))
import sys, json, time, os
sys.path.insert(0,MISTRAL)
import farm_model as fm
from dataclasses import replace
base = fm.Params()
OUT=os.path.join(HERE,'..','data','exp4_per_seed.jsonl')
def summarize(rows):
    r12,r24,r60=rows[11],rows[23],rows[59]
    peak=max(rows,key=lambda r:r['farm_share'])
    return {'s12':100*r12['farm_share'],'s24':100*r24['farm_share'],'s60':100*r60['farm_share'],
            'peak':100*peak['farm_share'],'peak_m':peak['month'],'h60':r60['honest_active'],'f60':r60['farm_active'],
            'fp60':r60['farm_pending'],'be60':r60['breakeven_price'],'cost60':r60['farm_cost_usd'],'sold60':r60['farm_sold_units']}
def stage(name,P,seeds):
    t=time.time(); res=[]
    for s in seeds:
        res.append(summarize(fm.simulate(P,s)))
    with open(OUT,'a') as f: f.write(json.dumps({'name':name,'seeds':list(seeds),'res':res,'sec':round(time.time()-t,1)})+'\n')
open(OUT,'w').close()
A=range(1,101); B=range(1,61)
stage('base',base,A)
for nm,P in (('K=2',replace(base,K=2)),('K=4',replace(base,K=4)),('K=5',replace(base,K=5)),
             ('slots 2/2/10',replace(base,slots_young=2,slots_old=2)),
             ('slots 5/8/15',replace(base,slots_young=5,slots_old=8,slots_seed=15))):
    stage(nm,P,B)
C=range(1,13)
for cap in (20000,100000):
    stage(f'seed 300 cap={cap}',replace(base,seed_count=300,honest_cap=cap),C)
    stage(f'seed 1000 cap={cap}',replace(base,seed_count=1000,honest_cap=cap),C)
D=range(1,21)
for rr in (0.05,0.10,0.15):
    for vp in (0.3,0.5,0.7):
        if rr==0.10 and vp==0.5: continue
        stage(f'recruit={rr} vouch_prob={vp}',replace(base,recruit_rate=rr,vouch_prob=vp),D)
E=range(1,9)
for dc in (120.0,60.0,12.0,0.0):
    for pc in (0.5,0.05):
        stage(f'device={dc} power={pc}',replace(base,device_cost=dc,power_cost=pc),E)
pass
