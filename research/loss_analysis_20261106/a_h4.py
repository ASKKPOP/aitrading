# Agent A: PREREG H4 — was the short tilt a market read? symbol-matched buy-and-hold over each short trip's hold window; window drift.
import pickle,statistics as st,calendar,time,bisect,collections,datetime as dt,random
random.seed(11)
trips=pickle.load(open('trips1.pkl','rb')); C=pickle.load(open('a_candles15.pkl','rb'))
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0=T('2026-10-05T15:49:00')
ts=lambda s: calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))*1000
idx={s:[x[0] for x in v['c']] for s,v in C.items()}
def px(sym,t):
    a=idx[sym]; i=bisect.bisect_right(a,t)-1
    if i<0 or t-a[i]>=15*60000*2: return None
    return C[sym]['c'][i][4]
d=[t for t in trips if t['agent']=='6' and 'net' in t and T(t['t0'])>=WIN0 and t['symbol'] in C]
W0=ts('2026-10-05T15:49:00'); W1=ts('2026-11-06T20:30:00')
print('window drift per symbol (10-05 15:49 -> 11-06 20:30):')
dr={}
for s,v in C.items():
    p0=px(s,W0); p1=px(s,W1-15*60000)
    if p0 and p1: dr[s]=(p1/p0-1)*100
print('  mean %.1f%% median %.1f%% up %d/%d'%(st.mean(dr.values()),st.median(dr.values()),sum(1 for x in dr.values() if x>0),len(dr)))
print('  per symbol:',{k:round(v,1) for k,v in sorted(dr.items(),key=lambda kv:kv[1])})
def summ(label,tr):
    if not tr: print(label,'n=0'); return
    n=len(tr); g=sum(t['gross'] for t in tr); net=sum(t['net'] for t in tr)
    mk=[t['_mkt'] for t in tr]; gb=[t['gross']/t['notional']*1e4 for t in tr]
    big=max(tr,key=lambda t:abs(t['gross']))
    # symbol-clustered CI of mean market move over hold windows
    bys=collections.defaultdict(list)
    for t in tr: bys[t['symbol']].append(t['_mkt'])
    sy=list(bys); bs=[]
    for k in range(2000):
        pick=[random.choice(sy) for _ in sy]; v=[x for q in pick for x in bys[q]]; bs.append(st.mean(v))
    bs.sort()
    print(f"{label:28s} n={n:3d} gross=${g:7.2f} net=${net:7.2f} mean gross bp={st.mean(gb):6.1f} | market move over hold (long=+) mean={st.mean(mk):6.1f}bp median={st.median(mk):6.1f} CI95=[{bs[50]:.1f},{bs[1949]:.1f}] frac down={sum(1 for x in mk if x<0)/n:.2f} | ex-largest({big['symbol']} {big['gross']:+.2f}) gross=${g-big['gross']:7.2f} mkt mean={st.mean([t['_mkt'] for t in tr if t is not big]):6.1f}bp")
for t in d:
    p0=px(t['symbol'],ts(t['t0'])); p1=px(t['symbol'],ts(t['t1']))
    t['_mkt']=(p1/p0-1)*1e4 if p0 and p1 else None
d=[t for t in d if t['_mkt'] is not None]
print('\n=== H4: symbol-matched buy-and-hold over each trip\'s own hold window ===')
summ('shorts',[t for t in d if t['dir']=='short']); summ('longs',[t for t in d if t['dir']=='long'])
summ('shorts hold<60m',[t for t in d if t['dir']=='short' and t['hold_min']<60]); summ('shorts hold>=60m',[t for t in d if t['dir']=='short' and t['hold_min']>=60])
# by ISO week
wk=collections.defaultdict(list)
for t in d: wk[T(t['t0']).isocalendar()[1]].append(t)
for k in sorted(wk):
    sh=[t for t in wk[k] if t['dir']=='short']
    if sh: summ(f'shorts ISO wk {k}',sh)
# the short's realised gross vs the market move should be ~ -mkt (short) minus slippage; check sign agreement
sh=[t for t in d if t['dir']=='short']
agree=sum(1 for t in sh if (t['gross']>0)==(t['_mkt']<0))
print(f"\nshorts: gross sign agrees with -market move in {agree}/{len(sh)}")
# whole-window alternative: if the desk had simply been short the same notional over the same windows with 0 fee -> that IS -mkt*notional:
cf=sum(-t['_mkt']/1e4*t['notional'] for t in sh); print(f"shorts: -market move x notional (frictionless short over same windows) = ${cf:.2f} vs actual gross ${sum(t['gross'] for t in sh):.2f}")
