import pickle,random,statistics as st,calendar,time,bisect,collections,math
random.seed(7)
trips,*_=pickle.load(open('trips.pkl','rb')); C=pickle.load(open('candles15.pkl','rb'))
d=[t for t in trips if t['agent']=='6' and 'net' in t and t['dir'] in('long','short')]
ts=lambda s: calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))*1000
idx={s:[x[0] for x in v['c']] for s,v in C.items()}
def px(sym,t):  # close of 15m candle containing t (None if out of range/gap)
    a=idx[sym]; i=bisect.bisect_right(a,t)-1
    if i<0 or t-a[i]>=15*60000*2: return None
    return C[sym]['c'][i][4]
# feed check: fill vs candle close containing entry
dev=[abs(px(t['symbol'],ts(t['t0']))/t['entry_px']-1)*1e4 for t in d if px(t['symbol'],ts(t['t0']))]
print('feed check: |candle close/fill-1| median bp',round(st.median(dev),1),'p90',round(sorted(dev)[int(.9*len(dev))],1),'n',len(dev))
H={'1h':1,'4h':4,'12h':12,'24h':24,'48h':48}
def fwd(sym,t0,p0,side,h):
    p=px(sym,t0+h*3600000)
    return None if p is None else side*(p/p0-1)*1e4
print('\n=== H1 entry edge: desk vs same-symbol same-side random minute (2000 shuffles) ===')
for name,h in H.items():
    obs=[];keys=[]
    for t in d:
        s=1 if t['dir']=='long' else -1
        f=fwd(t['symbol'],ts(t['t0']),t['entry_px'],s,h)
        if f is not None: obs.append(f); keys.append((t['symbol'],s))
    m=st.mean(obs)
    nulls=[]
    for k in range(2000):
        tot=0
        for sym,s in keys:
            a=idx[sym]; hi=len(a)-1-h*4-1
            i=random.randint(0,hi); p0=C[sym]['c'][i][4]; p1=C[sym]['c'][i+h*4][4]
            tot+=s*(p1/p0-1)*1e4
        nulls.append(tot/len(keys))
    nm=st.mean(nulls); sd=st.pstdev(nulls); p=sum(1 for x in nulls if x>=m)/len(nulls)
    # symbol-clustered bootstrap CI of desk mean
    bys=collections.defaultdict(list)
    for o,(sym,s) in zip(obs,keys): bys[sym].append(o)
    sy=list(bys); bs=[]
    for k in range(2000):
        pick=[random.choice(sy) for _ in sy]; v=[x for q in pick for x in bys[q]]
        bs.append(st.mean(v))
    bs.sort()
    wr=sum(1 for o in obs if o>9)/len(obs)
    print(f"T={name:3s} n={len(obs):3d} desk mean={m:7.1f}bp median={st.median(obs):6.1f} null mean={nm:6.1f} desk-null={m-nm:7.1f} z={(m-nm)/sd:5.2f} p(one-sided)={p:.3f} clusterCI95=[{bs[50]:.1f},{bs[1949]:.1f}] frac>9bp={wr:.2f}")
print('\n=== H2 hold-longer counterfactual (fixed hold T, 9bp RT, NON-overlapping per symbol) vs actual on same entries ===')
for name,h in H.items():
    busy={}; rows=[]
    for t in sorted(d,key=lambda t:t['t0']):
        t0=ts(t['t0']); sym=t['symbol']
        if busy.get(sym,0)>t0: continue
        s=1 if t['dir']=='long' else -1
        f=fwd(sym,t0,t['entry_px'],s,h)
        if f is None: continue
        busy[sym]=t0+h*3600000
        base=t['notional']/(1+t['adds']) if t['adds'] else t['notional']
        rows.append((sym,(f-9)/1e4*base,t['net'],f))
    n=len(rows); cf=sum(r[1] for r in rows); act=sum(r[2] for r in rows)
    srt=sorted(rows,key=lambda r:r[1]); bysym=collections.defaultdict(float)
    for r in rows: bysym[r[0]]+=r[1]
    topsym=max(bysym,key=bysym.get)
    wr=sum(1 for r in rows if r[1]>0)/n
    print(f"T={name:3s} trades={n:3d} counterfactual net=${cf:7.2f} (actual on same entries ${act:7.2f}) WR={wr:.2f} mean bp={st.mean(r[3] for r in rows):6.1f} ex-best trip=${cf-srt[-1][1]:7.2f} ex-best symbol({topsym} ${bysym[topsym]:.2f})=${cf-bysym[topsym]:7.2f} ex-worst trip=${cf-srt[0][1]:7.2f}")
print('\n=== H3 actual gross bp/trip, symbol-clustered CI ===')
g=[(t['symbol'],t['gross']/t['notional']*1e4) for t in d]
bys=collections.defaultdict(list)
for s,x in g: bys[s].append(x)
sy=list(bys); bs=[]
for k in range(4000):
    pick=[random.choice(sy) for _ in sy]; v=[x for q in pick for x in bys[q]]; bs.append(st.mean(v))
bs.sort(); print('mean gross bp/trip',round(st.mean(x for s,x in g),2),'clusterCI95',[round(bs[100],1),round(bs[3899],1)],'n',len(g),'symbols',len(sy))
# market drift over window per symbol (beta context)
dr=[(v['c'][-1][4]/v['c'][0][4]-1)*100 for v in C.values()]
print('window drift per symbol: mean %.1f%% median %.1f%% up %d/%d'%(st.mean(dr),st.median(dr),sum(1 for x in dr if x>0),len(dr)))
print('desk long share',round(sum(1 for t in d if t['dir']=='long')/len(d),2))
