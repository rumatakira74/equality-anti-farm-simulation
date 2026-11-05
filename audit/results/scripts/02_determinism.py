import os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
MISTRAL=os.path.normpath(os.path.join(HERE,'..','..','..','Mistral'))
import sys, math
sys.path.insert(0,MISTRAL)
import farm_model as fm
def same(a,b):
    if len(a)!=len(b): return False
    for ra,rb in zip(a,b):
        for k in ra:
            x,y=ra[k],rb[k]
            if isinstance(x,float) and isinstance(y,float):
                if math.isnan(x) and math.isnan(y): continue
                if x!=y: return False
            elif x!=y: return False
    return True
P=fm.Params()
print("numpy-путь, сид 1 дважды: идентичны =", same(fm.simulate(P,1), fm.simulate(P,1)))
saved=fm.np; fm.np=None
print("без numpy,  сид 1 дважды: идентичны =", same(fm.simulate(P,1), fm.simulate(P,1)))
fm.np=saved
# сколько NaN в строках (причина прежнего False)
r=fm.simulate(P,1)
print("NaN в breakeven_price в строках:", sum(1 for x in r if math.isnan(x['breakeven_price'])), "из", len(r))
