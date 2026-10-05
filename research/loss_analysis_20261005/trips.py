import csv, json, re, collections, statistics as st, datetime as dt, pickle
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
sig=list(csv.DictReader(open('signals.tsv'),delimiter='\t'))
runs={r['id']:r for r in csv.DictReader(open('runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
ev=list(csv.DictReader(open('events.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE))
stopmech=collections.defaultdict(list); status=collections.defaultdict(list); clamp=collections.defaultdict(list)
for e in ev:
    try:p=json.loads(e['payload'])
    except: continue
    if e['event_type']=='stop_mechanism': stopmech[e['run_id']].append((e['ts'],p))
    if e['event_type']=='run_status': status[e['run_id']].append((e['ts'],p.get('reason')))
    if e['event_type']=='size_clamp': clamp[e['run_id']].append((e['ts'],p))
# trips: per run, walk legs; a trip = flat -> nonflat -> flat
trips=[]
byrun=collections.defaultdict(list)
for s in sig: byrun[(s['agent_id'],s['symbol'])].append(s)
for (ag,_sym),legs in byrun.items():
    legs.sort(key=lambda s:int(s['id']))
    pos=0.0; cur=None; mx=0.0
    for s in legs:
        rid=cur['run'] if cur else s['run_id']
        q=float(s['quantity']); fee=float(s['fee_usd'] or 0); side=s['side']
        if side in('buy','short'):
            if cur is None: cur=dict(agent=ag,run=rid,symbol=s['symbol'],dir='long' if side=='buy' else 'short',t0=s['created_at'],entry_fee=0,exit_fee=0,pnl=0,notional=0,adds=0,entry_px=float(s['entry_price']),legs=[])
            else: cur['adds']+=1
            cur['entry_fee']+=fee; cur['notional']+=q*float(s['entry_price']); pos+=q; mx=max(mx,pos)
        else:
            if cur is None: cur=dict(agent=ag,run=rid,symbol=s['symbol'],dir='?',t0=s['created_at'],entry_fee=0,exit_fee=0,pnl=0,notional=0,adds=0,entry_px=None,legs=[],orphan=True)
            cur['exit_fee']+=fee; cur['pnl']+=float(s['pnl'] or 0); pos-=q
            cur['t1']=s['created_at']; cur['exit_px']=float(s['exit_price']) if s['exit_price']!='NULL' else None
            coid=s['client_order_id']
            cur['exit_kind']='flatten' if 'flatten' in coid else 'arm' if ':arm:' in coid else 'cyc' if ':cyc:' in coid else 'reclaim' if 'reclaim' in coid else 'null'
        cur['legs'].append(s['id'])
        if cur and abs(pos)<=max(1e-9,1e-5*mx) and 't1' in cur:
            cur['net']=cur['pnl']-cur['entry_fee']; cur['gross']=cur['pnl']+cur['exit_fee']
            cur['hold_min']=(T(cur['t1'])-T(cur['t0'])).total_seconds()/60
            # exit author
            ek=cur['exit_kind']; why=ek
            if ek=='flatten':
                reasons=[r for ts,r in status.get(rid,[]) if r and abs((T(ts)-T(cur['t1'])).total_seconds())<=180 and r not in('created','start')]
                why='flatten:'+(reasons[-1] if reasons else '?')
            cur['why']=why
            trips.append(cur); cur=None; pos=0.0; mx=0.0
    if cur: cur['open']=True; trips.append(cur)
pickle.dump((trips,runs,stopmech,status,clamp),open('trips.pkl','wb'))
def summ(name,tr):
    tr=[t for t in tr if 'net' in t]
    if not tr: return
    n=len(tr); net=sum(t['net'] for t in tr); gross=sum(t['gross'] for t in tr); fees=sum(t['entry_fee']+t['exit_fee'] for t in tr)
    w=[t['net'] for t in tr if t['net']>0]; l=[t['net'] for t in tr if t['net']<=0]
    gw=[t for t in tr if t['gross']>0]
    aw=st.mean(w) if w else 0; al=st.mean(l) if l else 0
    notl=st.median([t['notional'] for t in tr if t['notional']>0] or [0])
    bp=[t['gross']/t['notional']*1e4 for t in tr if t['notional']>0]
    print(f"{name:42s} n={n:4d} net={net:8.2f} gross={gross:8.2f} fees={fees:6.2f} WRnet={len(w)/n*100:5.1f}% WRgross={len(gw)/n*100:5.1f}% avgW={aw:6.3f} avgL={al:7.3f} payoff={(aw/-al if al else 0):5.2f} medHold={st.median([t['hold_min'] for t in tr]):7.1f}m medNotl={notl:7.1f} medGrossBp={st.median(bp) if bp else 0:6.1f} meanGrossBp={st.mean(bp) if bp else 0:6.1f}")
for ag in ('6','60'):
    tr=[t for t in trips if t['agent']==ag]
    print('==== agent',ag,'open/unclosed:',sum(1 for t in tr if 'net' not in t))
    summ('ALL',tr)
    for k in sorted(set(t.get('why','') for t in tr if 'net' in t)): summ(' exit='+k,[t for t in tr if t.get('why')==k])
    for d in ('long','short'): summ(' dir='+d,[t for t in tr if t['dir']==d])
    # hold buckets
    for lo,hi in ((0,15),(15,60),(60,240),(240,720),(720,1e9)): summ(f' hold {lo}-{hi}m',[t for t in tr if 'net' in t and lo<=t['hold_min']<hi])
    # weekly
    wk=collections.defaultdict(list)
    for t in tr:
        if 'net' in t: wk[T(t['t1']).strftime('%G-W%V')].append(t)
    for k in sorted(wk): summ(' week '+k,wk[k])
    done=sorted([t for t in tr if 'net' in t],key=lambda t:t['net'])
    print(' worst5:',[(t['symbol'],t['run'],round(t['net'],2),t['why'],round(t['hold_min'])) for t in done[:5]])
    print(' best5 :',[(t['symbol'],t['run'],round(t['net'],2),t['why'],round(t['hold_min'])) for t in done[-5:]])
    tot=sum(t['net'] for t in done); print(' net ex-worst1:',round(tot-done[0]['net'],2),' ex-best1:',round(tot-done[-1]['net'],2), ' ex-worst5:',round(tot-sum(t['net'] for t in done[:5]),2))
