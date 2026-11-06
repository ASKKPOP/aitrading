# First-pass trip reconstruction (signals only; exit author needs events.tsv from dump2).
import csv, collections, statistics as st, datetime as dt, pickle, sys
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0=T('2026-10-05T15:49:00'); WIN1=T('2026-11-06T20:30:00')
sig=list(csv.DictReader(open('d/signals.tsv'),delimiter='\t'))
runs={r['id']:r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
trips=[]; byrun=collections.defaultdict(list)
for s in sig: byrun[(s['agent_id'],s['symbol'])].append(s)
for (ag,_sym),legs in byrun.items():
    legs.sort(key=lambda s:int(s['id'])); pos=0.0; cur=None; mx=0.0
    for s in legs:
        q=float(s['quantity']); fee=float(s['fee_usd'] or 0); side=s['side']
        if side in('buy','short'):
            if cur is None: cur=dict(agent=ag,run=s['run_id'],symbol=s['symbol'],dir='long' if side=='buy' else 'short',t0=s['created_at'],entry_fee=0,exit_fee=0,pnl=0,notional=0,adds=0,legs=0,entry_px=float(s['entry_price']))
            else: cur['adds']+=1
            cur['entry_fee']+=fee; cur['notional']+=q*float(s['entry_price']); pos+=q; mx=max(mx,pos)
        else:
            if cur is None: cur=dict(agent=ag,run=s['run_id'],symbol=s['symbol'],dir='?',t0=s['created_at'],entry_fee=0,exit_fee=0,pnl=0,notional=0,adds=0,legs=0,entry_px=None,orphan=True)
            cur['exit_fee']+=fee; cur['pnl']+=float(s['pnl'] or 0) if s['pnl']!='NULL' else 0; pos-=q
            cur['t1']=s['created_at']; coid=s['client_order_id'] or ''
            cur['exit_kind']='flatten' if 'flatten' in coid else 'arm' if ':arm:' in coid else 'cyc' if ':cyc:' in coid else 'reclaim' if 'reclaim' in coid else 'other'
        cur['legs']+=1
        if cur and abs(pos)<=max(1e-9,1e-5*mx) and 't1' in cur:
            cur['net']=cur['pnl']-cur['entry_fee']; cur['gross']=cur['pnl']+cur['exit_fee']
            cur['hold_min']=(T(cur['t1'])-T(cur['t0'])).total_seconds()/60
            trips.append(cur); cur=None; pos=0.0; mx=0.0
    if cur: cur['open']=True; trips.append(cur)
pickle.dump(trips,open('trips1.pkl','wb'))
def summ(name,tr):
    tr=[t for t in tr if 'net' in t]
    if not tr: print(f"{name:40s} n=0"); return
    n=len(tr); net=sum(t['net'] for t in tr); gross=sum(t['gross'] for t in tr); fees=sum(t['entry_fee']+t['exit_fee'] for t in tr)
    w=[t['net'] for t in tr if t['net']>0]; l=[t['net'] for t in tr if t['net']<=0]
    aw=st.mean(w) if w else 0; al=st.mean(l) if l else 0
    bp=[t['gross']/t['notional']*1e4 for t in tr if t['notional']>0]
    legs=sum(t['legs'] for t in tr)
    print(f"{name:40s} n={n:4d} net={net:8.2f} gross={gross:8.2f} fees={fees:6.2f} WR={len(w)/n*100:5.1f}% avgW={aw:6.3f} avgL={al:7.3f} payoff={(aw/-al if al else 0):5.2f} medHold={st.median([t['hold_min'] for t in tr]):7.1f}m medNotl={st.median([t['notional'] for t in tr]):7.1f} meanGrossBp={st.mean(bp) if bp else 0:6.1f} legs/trip={legs/n:4.2f}")
for ag in ('6','60','63'):
    allt=[t for t in trips if t['agent']==ag]
    win=[t for t in allt if T(t['t0'])>=WIN0]
    pre=[t for t in allt if T(t['t0'])<WIN0]
    print(f"\n==== agent {ag}: open now {sum(1 for t in allt if 'net' not in t)}")
    summ('window 10-05 15:49 -> 11-06',win)
    summ('  long',[t for t in win if t['dir']=='long']); summ('  short',[t for t in win if t['dir']=='short'])
    for k in ('flatten','arm','cyc','reclaim','other'): summ(f'  exit={k}',[t for t in win if t.get('exit_kind')==k])
    summ('pre-window 09-25 -> 10-05 (overlap check)',pre)
    # by week
    wk=collections.defaultdict(list)
    for t in win: wk[T(t['t0']).strftime('%m-%d')[:5] if False else T(t['t0']).isocalendar()[1]].append(t)
    for k in sorted(wk): summ(f'  ISO week {k}',wk[k])
    # worst / best
    cl=[t for t in win if 'net' in t]
    if cl:
        cl.sort(key=lambda t:t['net'])
        print('  worst 5:',[(t['symbol'],t['dir'],round(t['net'],2),round(t['hold_min']),t.get('exit_kind')) for t in cl[:5]])
        print('  best 5 :',[(t['symbol'],t['dir'],round(t['net'],2),round(t['hold_min']),t.get('exit_kind')) for t in cl[-5:]])
        big=[t for t in cl if t['net']<-1]; print(f"  trips net<-$1: {len(big)} sum={sum(t['net'] for t in big):.2f}; rest sum={sum(t['net'] for t in cl if t['net']>=-1):.2f}")
