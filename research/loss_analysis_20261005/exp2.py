import pickle,random,statistics as st,calendar,time,bisect,collections
random.seed(11)
trips,*_=pickle.load(open('trips.pkl','rb')); C=pickle.load(open('candles15.pkl','rb'))
d=[t for t in trips if t['agent']=='6' and 'net' in t and t['dir'] in('long','short')]
ts=lambda s: calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))*1000
idx={s:[x[0] for x in v['c']] for s,v in C.items()}
def ci(sym,t):
    a=idx[sym]; i=bisect.bisect_right(a,t)-1
    return None if (i<0 or t-a[i]>=30*60000) else i
# (a) equal-weight universe drift by period
def drift(t0s,t1s):
    out=[]
    for s in C:
        i=ci(s,ts(t0s)); j=ci(s,ts(t1s))
        if i is not None and j is not None: out.append((C[s]['c'][j][4]/C[s]['c'][i][4]-1)*100)
    return st.mean(out),st.median(out),len(out)
for a,b in (('2026-09-05T08:00:00','2026-09-11T00:00:00'),('2026-09-11T00:00:00','2026-09-18T00:00:00'),('2026-09-18T00:00:00','2026-09-25T00:00:00'),('2026-09-25T00:00:00','2026-10-02T00:00:00'),('2026-10-02T00:00:00','2026-10-05T15:00:00'),('2026-09-05T08:00:00','2026-10-05T15:00:00')):
    m,md,n=drift(a,b); print(f"universe drift {a[:10]}..{b[:10]}: mean {m:6.1f}% median {md:6.1f}% (n={n})")
# daily universe drift on the worst days
for day in ('2026-09-07','2026-09-08','2026-09-09'):
    m,md,n=drift(day+'T00:00:00',day+'T23:45:00'); print(' day',day,f"mean {m:5.1f}%")
# (b) H1 with LOCAL null: random time within +-24h of the actual entry (keeps regime), same symbol+side
H={'1h':1,'4h':4,'12h':12,'24h':24,'48h':48}
print('\nH1-local: desk vs random time within +-24h of the real entry (2000 shuffles)')
for name,h in H.items():
    rows=[]
    for t in d:
        s=1 if t['dir']=='long' else -1; i=ci(t['symbol'],ts(t['t0']))
        if i is None or i+h*4>=len(idx[t['symbol']]): continue
        c=C[t['symbol']]['c']; rows.append((t['symbol'],s,i,s*(c[i+h*4][4]/t['entry_px']-1)*1e4))
    m=st.mean(r[3] for r in rows); nulls=[]
    for k in range(2000):
        tot=0
        for sym,s,i,_ in rows:
            c=C[sym]['c']; lo=max(0,i-96); hi=min(len(c)-1-h*4,i+96); j=random.randint(lo,hi)
            tot+=s*(c[j+h*4][4]/c[j][4]-1)*1e4
        nulls.append(tot/len(rows))
    nm=st.mean(nulls); sd=st.pstdev(nulls); p=sum(1 for x in nulls if x>=m)/2000
    print(f" T={name:3s} n={len(rows)} desk={m:7.1f}bp null={nm:7.1f} diff={m-nm:7.1f} z={(m-nm)/sd:5.2f} p={p:.3f}")
# (c) H2 schedule vs random-time SAME schedule (beta control), and by regime
print('\nH2 beta control: non-overlapping fixed hold, desk entries vs same symbols/sides at random time within +-24h (500 sims)')
def sched(h,period=None):
    busy={}; rows=[]
    for t in sorted(d,key=lambda t:t['t0']):
        if period and not (period[0]<=t['t0']<period[1]): continue
        t0=ts(t['t0']); sym=t['symbol']
        if busy.get(sym,0)>t0: continue
        i=ci(sym,t0)
        if i is None or i+h*4>=len(idx[sym]): continue
        busy[sym]=t0+h*3600000
        s=1 if t['dir']=='long' else -1; base=t['notional']/(1+t['adds'])
        rows.append((sym,s,i,base,t['entry_px'],t['net']))
    return rows
for label,per in (('ALL',None),('A 09-05..09-10',('2026-09-05','2026-09-11')),('B 09-11..10-05',('2026-09-11','2026-10-06'))):
  for name,h in (('4h',4),('12h',12),('24h',24),('48h',48)):
    rows=sched(h,per)
    if len(rows)<10: continue
    desk=sum(((s*(C[sym]['c'][i+h*4][4]/px-1))-0.0009)*base for sym,s,i,base,px,_ in rows)
    act=sum(r[5] for r in rows); sims=[]
    for k in range(500):
        tot=0
        for sym,s,i,base,px,_ in rows:
            c=C[sym]['c']; lo=max(0,i-96); hi=min(len(c)-1-h*4,i+96); j=random.randint(lo,hi)
            tot+=((s*(c[j+h*4][4]/c[j][4]-1))-0.0009)*base
        sims.append(tot)
    sims.sort(); p=sum(1 for x in sims if x>=desk)/500
    longs=sum(1 for r in rows if r[1]>0)/len(rows)
    print(f" {label:16s} T={name:3s} trades={len(rows):3d} long%={longs:.2f} desk-entry hold=${desk:7.2f} | random-entry hold mean=${st.mean(sims):7.2f} [5%..95%: {sims[25]:.0f}..{sims[474]:.0f}] p(desk>=rand)={p:.2f} | actual on these entries=${act:7.2f}")
