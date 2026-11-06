# Agent A: PREREG H1 (4th replication) — side-signed forward return of agent-6 entries vs same-symbol same-side random entry time.
import pickle,random,statistics as st,calendar,time,bisect,collections,datetime as dt,sys
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 7)
trips=pickle.load(open('trips1.pkl','rb')); C=pickle.load(open('a_candles15.pkl','rb'))
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0=T('2026-10-05T15:49:00'); WIN1=T('2026-11-06T20:30:00')
d=[t for t in trips if t['agent']=='6' and 'net' in t and t['dir'] in('long','short') and T(t['t0'])>=WIN0 and t['symbol'] in C]
print('trips',len(d),'missing candles',sorted(set(t['symbol'] for t in trips if t['agent']=='6' and 'net' in t and T(t['t0'])>=WIN0 and t['symbol'] not in C)))
ts=lambda s: calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))*1000
idx={s:[x[0] for x in v['c']] for s,v in C.items()}
def px(sym,t):
    a=idx[sym]; i=bisect.bisect_right(a,t)-1
    if i<0 or t-a[i]>=15*60000*2: return None
    return C[sym]['c'][i][4]
dev=[abs(px(t['symbol'],ts(t['t0']))/t['entry_px']-1)*1e4 for t in d if px(t['symbol'],ts(t['t0']))]
print('feed check |candle close/fill-1| median bp',round(st.median(dev),1),'p90',round(sorted(dev)[int(.9*len(dev))],1),'n',len(dev))
H={'1h':1,'4h':4,'12h':12,'24h':24,'48h':48}
W0=ts('2026-10-05T15:49:00'); W1=ts('2026-11-06T20:30:00')
USE_CANDLE_P0=len(sys.argv)>2 and sys.argv[2]=="candle"
def fwd(sym,t0,p0,side,h):
    if USE_CANDLE_P0:
        q=px(sym,t0)
        if q is None: return None
        p0=q
    p=px(sym,t0+h*3600000); return None if p is None else side*(p/p0-1)*1e4
NEAR=len(sys.argv)>3 and sys.argv[3]=='near'
def run(label,window_null,exclude_sym=None):
    print(f"\n=== H1 {label} (null={'+-24h of entry' if NEAR else ('window-only' if window_null else 'all candles')}{' ex '+exclude_sym if exclude_sym else ''}) ===")
    res={}
    for name,h in H.items():
        obs=[];keys=[]
        for t in d:
            if t['symbol']==exclude_sym: continue
            s=1 if t['dir']=='long' else -1
            f=fwd(t['symbol'],ts(t['t0']),t['entry_px'],s,h)
            if f is not None: obs.append(f); keys.append((t['symbol'],s,ts(t['t0'])))
        m=st.mean(obs); nulls=[]
        for k in range(2000):
            tot=0
            for sym,s,t0 in keys:
                a=idx[sym]
                if NEAR:
                    lo=max(0,bisect.bisect_left(a,t0-86400000)); hi=min(bisect.bisect_right(a,t0+86400000)-1,len(a)-1-h*4-1)
                elif window_null:
                    lo=bisect.bisect_left(a,W0); hi=min(bisect.bisect_right(a,W1-h*3600000)-1,len(a)-1-h*4-1)
                else: lo=0; hi=len(a)-1-h*4-1
                i=random.randint(lo,hi); p0=C[sym]['c'][i][4]; p1=C[sym]['c'][i+h*4][4]
                tot+=s*(p1/p0-1)*1e4
            nulls.append(tot/len(keys))
        nm=st.mean(nulls); sd=st.pstdev(nulls); p=sum(1 for x in nulls if x>=m)/len(nulls)
        bys=collections.defaultdict(list)
        for o,(sym,s,_t) in zip(obs,keys): bys[sym].append(o)
        sy=list(bys); bs=[]
        for k in range(2000):
            pick=[random.choice(sy) for _ in sy]; v=[x for q in pick for x in bys[q]]; bs.append(st.mean(v))
        bs.sort()
        # largest contributor symbol (by |sum of obs|)
        contrib={s:sum(v) for s,v in bys.items()}; big=max(contrib,key=lambda s:abs(contrib[s]))
        print(f"T={name:3s} n={len(obs):3d} desk={m:7.1f}bp null={nm:6.1f} desk-null={m-nm:7.1f} z={(m-nm)/sd:5.2f} p1s={p:.3f} clusterCI95=[{bs[50]:.1f},{bs[1949]:.1f}] frac>9bp={sum(1 for o in obs if o>9)/len(obs):.2f} largest={big}({contrib[big]/len(obs):+.1f}bp of mean)")
        res[name]=(m,nm,sd,p,big)
    return res
r1=run('desk entries',True)
run('desk entries',False)
# without the largest contributor at 24h
big=r1['24h'][4]; run('desk entries',True,exclude_sym=big)
# shorts only and longs only
d_all=d
for side in ('short','long'):
    d=[t for t in d_all if t['dir']==side]; run(side+'s only',True)
