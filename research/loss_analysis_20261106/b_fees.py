# Sections B/C/D: fee rate per leg, legs/adds/partials, size clamp, fee counterfactuals, run-level peak for losers.
import pickle, csv, collections, statistics as st, random
csv.field_size_limit(10**9)
random.seed(11)
trips=pickle.load(open('b_trips.pkl','rb')); A6=[t for t in trips if t['agent']=='6']
runs={r['id']:r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
ev=pickle.load(open('b_events.pkl','rb'))
# --- fee rate verification on every agent-6 leg in window
rates=[s['_fee']/s['_notional']*1e4 for t in A6 for s in t['sigs'] if s['_notional']>0]
print(f"fee bp per leg: n={len(rates)} min={min(rates):.3f} max={max(rates):.3f} median={st.median(rates):.3f}")
legs=sum(len(t['sigs']) for t in A6); adds=sum(t['adds'] for t in A6); partial=sum(t['n_exit_legs']-1 for t in A6)
add_fee=sum(s['_fee'] for t in A6 for s in t['sigs'][1:] if not s['_isexit']); part_fee=sum(sum(s['_fee'] for s in t['sigs'] if s['_isexit'])-[s for s in t['sigs'] if s['_isexit']][-1]['_fee'] for t in A6)
print(f"legs={legs} ({legs/len(A6):.2f}/trip): entry legs={sum(t['n_entry_legs'] for t in A6)} (adds={adds}, fee {add_fee:.2f}), exit legs={sum(t['n_exit_legs'] for t in A6)} (partials before final={partial}, fee {part_fee:.2f}); trips with adds={sum(1 for t in A6 if t['adds'])}, with partial exits={sum(1 for t in A6 if t['n_exit_legs']>1)}")
ta=[t for t in A6 if t['adds']>0 or t['n_exit_legs']>1]; tb=[t for t in A6 if not(t['adds']>0 or t['n_exit_legs']>1)]
print(f"multi-leg trips n={len(ta)} net={sum(t['net'] for t in ta):.2f} gross={sum(t['gross'] for t in ta):.2f} fees={sum(t['fees'] for t in ta):.2f} | single in/out n={len(tb)} net={sum(t['net'] for t in tb):.2f} gross={sum(t['gross'] for t in tb):.2f} fees={sum(t['fees'] for t in tb):.2f}")
# who authored the adds / partials
print('add coid kinds:',collections.Counter(s['_kind'] for t in A6 for s in t['sigs'][1:] if not s['_isexit']).most_common())
print('partial-exit coid kinds:',collections.Counter(s['_kind'] for t in A6 for s in [x for x in t['sigs'] if x['_isexit']][:-1]).most_common())
# --- size clamp
sc=[e for e in ev if e[3]=='size_clamp' and e[0]=='6' and '2026-10-05T15:49'<=e[4]<='2026-11-06T20:30']
print(f"\nsize_clamp events agent6={len(sc)}; stages={collections.Counter(e[5]['stage'] for e in sc)}; cap_frac={collections.Counter(e[5]['cap_frac'] for e in sc)}; params_state={collections.Counter(e[5]['params_state'] for e in sc)}")
print(f"size_before median={st.median(e[5]['size_before'] for e in sc):.1f} after median={st.median(e[5]['size_after'] for e in sc):.1f}; after/before median={st.median(e[5]['size_after']/e[5]['size_before'] for e in sc):.3f}; sum before={sum(e[5]['size_before'] for e in sc):.0f} after={sum(e[5]['size_after'] for e in sc):.0f}")
print('after/before distinct:',collections.Counter(round(e[5]['size_after']/e[5]['size_before'],3) for e in sc).most_common(6))
cl=[t for t in A6 if t['clamp']]; un=[t for t in A6 if not t['clamp']]
def bp(tr): return [t['gross']/t['entry_notional']*1e4 for t in tr]
def ci(x,B=4000):
    bs=sorted(st.mean(random.choices(x,k=len(x))) for _ in range(B)); return bs[int(.025*B)],bs[int(.975*B)]
for name,tr in (('clamped',cl),('unclamped',un)):
    b=bp(tr); lo,hi=ci(b)
    print(f"{name:10s} n={len(tr)} net={sum(t['net'] for t in tr):.2f} gross={sum(t['gross'] for t in tr):.2f} fees={sum(t['fees'] for t in tr):.2f} medNotl={st.median(t['entry_notional'] for t in tr):.1f} meanNotl={st.mean(t['entry_notional'] for t in tr):.1f} grossBp mean={st.mean(b):.1f} CI[{lo:.1f},{hi:.1f}] median={st.median(b):.1f} WR={sum(1 for t in tr if t['net']>0)/len(tr):.2f} medHold={st.median(t['hold_min'] for t in tr):.0f}")
d=[st.mean(bp(random.choices(cl,k=len(cl))))-st.mean(bp(random.choices(un,k=len(un)))) for _ in range(4000)]; d.sort()
print(f"clamped - unclamped gross bp: {st.mean(bp(cl))-st.mean(bp(un)):.1f} CI[{d[100]:.1f},{d[3899]:.1f}]")
# clamped first-entry notional vs clamp size_after
m=[(t['sigs'][0]['_notional'],t['clamp']['size_after'],t['clamp']['size_before']) for t in cl]
print('first-leg notional / clamp size_after median',round(st.median(a/b for a,b,c in m),3),'; sum first-leg',round(sum(a for a,b,c in m)),'sum size_before',round(sum(c for a,b,c in m)))
# what did the uncapped size_before correspond to (max_bet)? and overall notional stats
print(f"all trips: entry notional median={st.median(t['entry_notional'] for t in A6):.1f} mean={st.mean(t['entry_notional'] for t in A6):.1f} sum={sum(t['entry_notional'] for t in A6):.0f}; mean gross bp={st.mean(bp(A6)):.1f} CI{tuple(round(x,1) for x in ci(bp(A6)))} median={st.median(bp(A6)):.1f}")
# symbol-clustered CI for gross bp (H3)
bys=collections.defaultdict(list)
for t in A6: bys[t['symbol']].append(t['gross']/t['entry_notional']*1e4)
sy=list(bys); bs=[]
for _ in range(4000):
    pick=random.choices(sy,k=len(sy)); v=[x for q in pick for x in bys[q]]; bs.append(st.mean(v))
bs.sort(); print(f"H3 gross bp symbol-clustered CI95 [{bs[100]:.1f},{bs[3899]:.1f}] (symbols={len(sy)}); fees/|net| = {sum(t['fees'] for t in A6)/abs(sum(t['net'] for t in A6)):.2f}")
# dollar-weighted: gross $ bootstrap CI
g=[t['gross'] for t in A6]; lo,hi=ci(g); print(f"gross $ total={sum(g):.2f}, trip-bootstrap CI of total [{lo*len(g):.2f},{hi*len(g):.2f}]")
# --- fee counterfactuals on THIS tape (same fills, same legs)
def cf(entry_bp,exit_bp):
    tot=0
    for t in A6:
        fee=sum(s['_notional']*(exit_bp if s['_isexit'] else entry_bp)/1e4 for s in t['sigs'])
        tot+=t['gross']-fee
    return tot
print("\nfee counterfactuals (agent 6, 468 trips, gross %.2f):"%sum(t['gross'] for t in A6))
for name,a,b in (('actual 4.5bp/leg',4.5,4.5),('zero fee',0,0),('Binance spot taker 10bp/leg',10,10),('Binance maker 0 entry + 10bp taker exit',0,10),('Hyperliquid maker 1.5bp/leg',1.5,1.5),('2.25bp/leg',2.25,2.25),('Binance VIP0 w/ BNB 7.5bp/leg',7.5,7.5)):
    v=cf(a,b); big=min(A6,key=lambda t:t['net']); print(f"  {name:42s} net={v:8.2f}   (ex-worst trip {big['symbol']}: {v-big['net']-(big['fees'])+sum(s['_notional']*(b if s['_isexit'] else a)/1e4 for s in big['sigs']):8.2f})")
# break-even fee rate
import math
lo_,hi_=0.0,50.0
for _ in range(60):
    mid=(lo_+hi_)/2
    if cf(mid,mid)>0: lo_=mid
    else: hi_=mid
print(f"  break-even flat fee on this tape: {lo_:.2f} bp/leg")
# --- run-level peak for big losers (peak_pnl_usd - peak_realized_usd), and trips/run
tpr=collections.Counter(t['final_run'] for t in A6)
print('\ntrips per run:',collections.Counter(tpr.values()))
big=sorted([t for t in A6 if t['net']<-1],key=lambda t:t['net'])
print('big losers run-level peak excursion (peak_pnl - peak_realized), arm est 0.16% notional:')
for t in big:
    r=runs.get(str(t['final_run']))
    if not r: print(' ',t['symbol'],'no run'); continue
    try: pk=float(r['peak_pnl_usd']); pr=float(r['peak_realized_usd'])
    except: print(' ',t['symbol'],'peak NULL',r['peak_pnl_usd'],r['peak_realized_usd']); continue
    exc=pk-pr; arm=t['entry_notional']*0.0016
    print(f"  {t['symbol']:9s} {t['dir']:5s} net={t['net']:6.2f} notl={t['entry_notional']:6.1f} trips_in_run={tpr[t['final_run']]} peak_exc=${exc:6.3f} ({exc/t['entry_notional']*1e4:5.0f}bp) arm=${arm:.3f} armed={exc>=arm} mech={t['mech']}")
