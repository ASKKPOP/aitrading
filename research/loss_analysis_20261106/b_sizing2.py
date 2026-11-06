import pickle, csv, json, collections, statistics as st, datetime as dt, random
csv.field_size_limit(10**9); random.seed(3)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
trips=pickle.load(open('b_trips.pkl','rb')); A6=[t for t in trips if t['agent']=='6']
want={int(t['sigs'][0]['run_id']) for t in A6 if t['sigs'][0]['run_id']!='NULL'}
rows=collections.defaultdict(list)
for r in csv.DictReader(open('d/events.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE):
    rid=int(r['run_id'])
    if rid in want and r['event_type']=='order_params': rows[rid].append((r['ts'],json.loads(r['payload'])))
for t in A6:
    rid=int(t['sigs'][0]['run_id']); op=None
    for ts,p in rows[rid]:
        if -200<=(T(ts)-T(t['t0'])).total_seconds()<=5: op=p
    t['op']=op
def bp(tr): return [t['gross']/t['entry_notional']*1e4 for t in tr]
def ci(x,B=3000):
    bs=sorted(st.mean(random.choices(x,k=len(x))) for _ in range(B)); return round(bs[int(.025*B)],1),round(bs[int(.975*B)],1)
c=collections.defaultdict(list)
for t in A6:
    o=t['op'] or {}; sf=(o.get('params') or {}).get('size_frac')
    key=(o.get('outcome'), None if sf is None else ('size_frac<=0.05' if sf<=0.05 else 'size_frac<=0.1' if sf<=0.1 else 'size_frac>0.1'))
    c[key].append(t)
print('by order_params outcome x size_frac bucket:')
for k in sorted(c,key=str):
    tr=c[k]; print(f"  {str(k):40s} n={len(tr):3d} medNotl={st.median(t['entry_notional'] for t in tr):6.1f} net={sum(t['net'] for t in tr):7.2f} gross={sum(t['gross'] for t in tr):7.2f} fees={sum(t['fees'] for t in tr):5.2f} clamped={sum(1 for t in tr if t['clamp']):3d} grossBp mean={st.mean(bp(tr)):6.1f} CI{ci(bp(tr))} WR={sum(1 for t in tr if t['net']>0)/len(tr):.2f}")
sf=[(t['op']['params']['size_frac']) for t in A6 if t.get('op') and (t['op'].get('params') or {}).get('size_frac') is not None]
print('size_frac distinct:',collections.Counter(sf).most_common(8))
# budget per slot implied: notional / size_frac
imp=[t['entry_notional']/t['op']['params']['size_frac'] for t in A6 if t.get('op') and (t['op'].get('params') or {}).get('size_frac') and not t['clamp']]
print('implied budget (notional/size_frac) median',round(st.median(imp),1),'distinct',collections.Counter(round(x) for x in imp).most_common(5))
# by week: share of desk-sized vs clamp-sized entries
wk=collections.defaultdict(lambda:[0,0])
for t in A6:
    k=T(t['t0']).isocalendar()[1]; wk[k][0 if t['clamp'] else 1]+=1
print('per ISO week [clamped, desk-sized]:',dict(wk))
