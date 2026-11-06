# Agent A: H3 (fee share, gross CI), H5 (clamp bp), agent-60 cash reconciliation, 24h-hold counterfactual, big-loss attribution.
import pickle,random,statistics as st,collections,datetime as dt,bisect,calendar,time
random.seed(5)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0=T('2026-10-05T15:49:00')
trips=pickle.load(open('trips1.pkl','rb')); C=pickle.load(open('a_candles15.pkl','rb')); ex=pickle.load(open('a_exits.pkl','rb')); rows=pickle.load(open('a_entries.pkl','rb'))
ent={(r['agent'],r['sym'],r['ts']):r for r in rows}
d=[t for t in trips if t['agent']=='6' and 'net' in t and T(t['t0'])>=WIN0]
def ci(vals_by_sym,n=4000):
    sy=list(vals_by_sym); bs=[]
    for k in range(n):
        pick=[random.choice(sy) for _ in sy]; v=[x for q in pick for x in vals_by_sym[q]]; bs.append(st.mean(v))
    bs.sort(); return bs[int(.025*n)],bs[int(.975*n)]
g=collections.defaultdict(list)
for t in d: g[t['symbol']].append(t['gross']/t['notional']*1e4)
lo,hi=ci(g); allbp=[x for v in g.values() for x in v]
fees=sum(t['entry_fee']+t['exit_fee'] for t in d); net=sum(t['net'] for t in d); gross=sum(t['gross'] for t in d)
print(f"H3: n={len(d)} gross=${gross:.2f} fees=${fees:.2f} net=${net:.2f} fees/|net|={fees/abs(net)*100:.0f}% ; mean gross bp/trip={st.mean(allbp):.1f} symbol-clustered CI95=[{lo:.1f},{hi:.1f}] (contains 0: {lo<0<hi}); fee bp/trip={st.mean([(t['entry_fee']+t['exit_fee'])/t['notional']*1e4 for t in d]):.1f}")
# ex largest symbol by |gross|
cs={s:sum(t['gross'] for t in d if t['symbol']==s) for s in g}; big=max(cs,key=lambda s:abs(cs[s]))
g2={s:v for s,v in g.items() if s!=big}; lo2,hi2=ci(g2)
print(f"    ex-{big} (gross {cs[big]:+.2f}): mean gross bp={st.mean([x for v in g2.values() for x in v]):.1f} CI95=[{lo2:.1f},{hi2:.1f}]")
# H5 clamp
for lab,sel in (('clamped',lambda t:len(ent[('6',t['symbol'],t['t0'])]['clamp'])>0),('unclamped',lambda t:len(ent[('6',t['symbol'],t['t0'])]['clamp'])==0)):
    s=[t for t in d if sel(t)]; gg=collections.defaultdict(list)
    for t in s: gg[t['symbol']].append(t['gross']/t['notional']*1e4)
    l,h=ci(gg)
    print(f"H5 {lab:9s}: n={len(s)} medNotional=${st.median(t['notional'] for t in s):.1f} gross bp mean={st.mean([x for v in gg.values() for x in v]):.1f} CI95=[{l:.1f},{h:.1f}] net=${sum(t['net'] for t in s):.2f} fees=${sum(t['entry_fee']+t['exit_fee'] for t in s):.2f}")
print('H5 median notional all window trips: $%.1f ; median notional by week:'%st.median(t['notional'] for t in d),{k:round(st.median(t['notional'] for t in d if T(t['t0']).isocalendar()[1]==k),1) for k in sorted(set(T(t['t0']).isocalendar()[1] for t in d))})
# agent 60 reconciliation
a60=[t for t in trips if t['agent']=='60' and 'net' in t]
pre=[t for t in a60 if T(t['t0'])<WIN0 and T(t['t1'])>=WIN0]; win=[t for t in a60 if T(t['t0'])>=WIN0]
print(f"\nagent 60: window trips net={sum(t['net'] for t in win):.2f}; pre-window-opened trips closed in window: {[(t['symbol'],round(t['net'],2),round(t['pnl'],2),t['t1'][:10]) for t in pre]} ; open now: {[t['symbol'] for t in a60 if 'net' not in t] + [t['symbol'] for t in trips if t['agent']=='60' and 'net' not in t]}")
print("   cash now 9995.945 ; 10-05 cash = 10000 - 5.22 (closed) - 0.007 (MSFT entry fee) = 9994.77 ; delta = %.2f ; trips in-window realised = %.2f"%(9995.94527847-9994.773, sum(t['net'] for t in win)+sum(t['pnl'] for t in pre)))
# 24h-hold counterfactual on the shorts (frictionless except 9bp), non-overlapping per symbol
ts=lambda s: calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))*1000
idx={s:[x[0] for x in v['c']] for s,v in C.items()}
def px(sym,t):
    a=idx[sym]; i=bisect.bisect_right(a,t)-1
    if i<0 or t-a[i]>=15*60000*2: return None
    return C[sym]['c'][i][4]
for h in (4,24,48):
    busy={}; cf=0; act=0; n=0
    for t in sorted(d,key=lambda t:t['t0']):
        if t['dir']!='short': continue
        t0=ts(t['t0']); sym=t['symbol']
        if busy.get(sym,0)>t0: continue
        p=px(sym,t0+h*3600000)
        if p is None: continue
        busy[sym]=t0+h*3600000; base=t['notional']/(1+t['adds']) if t['adds'] else t['notional']
        cf+=(-(p/t['entry_px']-1)*1e4-9)/1e4*base; act+=t['net']; n+=1
    print(f"shorts held fixed {h}h (non-overlapping, 9bp RT): n={n} counterfactual net=${cf:.2f} vs actual on same entries ${act:.2f}")
# big losses by author
big=[t for t in ex if t['net']<-1]
print(f"\ntrips net<-$1: n={len(big)} sum={sum(t['net'] for t in big):.2f}; by exit author:")
for k,v in collections.Counter((t['exit_kind'],t['auth'][:45]) for t in big).most_common(): print('  ',k,v,round(sum(t['net'] for t in big if (t['exit_kind'],t['auth'][:45])==k),2))
rest=[t for t in ex if t['net']>=-1]; print(f"the other {len(rest)} trips sum={sum(t['net'] for t in rest):.2f}")
# fee-only trips (hold<=1 min) agent 6 and 60
for ag in ('6','60'):
    z=[t for t in trips if t['agent']==ag and 'net' in t and T(t['t0'])>=WIN0 and t['hold_min']<=1]
    print(f"agent {ag} trips held <=1 min: n={len(z)} net={sum(t['net'] for t in z):.2f}")
