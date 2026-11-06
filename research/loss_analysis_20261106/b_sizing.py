# What sized the unclamped (small) trips? Read raw decision/order_params payloads at the entry cycle.
import pickle, csv, json, collections, statistics as st, datetime as dt
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
trips=pickle.load(open('b_trips.pkl','rb')); A6=[t for t in trips if t['agent']=='6']
want={}
for t in A6:
    rid=t['sigs'][0]['run_id']
    if rid!='NULL': want.setdefault(int(rid),[]).append(t)
rows=collections.defaultdict(list)
for r in csv.DictReader(open('d/events.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE):
    rid=int(r['run_id'])
    if rid in want and r['event_type'] in ('decision','order_params','order_plan','size_clamp'):
        rows[rid].append((r['ts'],r['event_type'],r['payload']))
# show two unclamped small trips and one clamped in full
shown=0
for t in sorted(A6,key=lambda t:t['entry_notional']):
    if t['clamp'] or shown>=2: continue
    rid=int(t['sigs'][0]['run_id']); print('\n### UNCLAMPED',t['symbol'],t['dir'],'notional',round(t['entry_notional'],1),'t0',t['t0'],'run',rid, 'cfg max_bet?')
    for ts,et,p in rows[rid]:
        if -200<=(T(ts)-T(t['t0'])).total_seconds()<=5: print(' ',ts,et,p[:900])
    shown+=1
# aggregate: for every trip, the decision event closest before t0: size_scale, conviction, confidence, decided_by; order_params keys
agg=[]
for t in A6:
    rid=int(t['sigs'][0]['run_id']); best=None; op=None
    for ts,et,p in rows[rid]:
        d=(T(ts)-T(t['t0'])).total_seconds()
        if -200<=d<=5:
            if et=='decision': best=json.loads(p)
            if et=='order_params': op=json.loads(p)
    agg.append((t,best,op))
print('\norder_params keys sample:',list((agg[0][2] or {}).keys())[:40])
print('order_params sample:',json.dumps(agg[0][2])[:1200])
def grp(key,f):
    c=collections.defaultdict(list)
    for t,d,o in agg:
        c[f(t,d,o)].append(t)
    print(f'\nby {key}:')
    for k in sorted(c,key=lambda k:str(k)):
        tr=c[k]; print(f"  {str(k):30s} n={len(tr):3d} medNotl={st.median(t['entry_notional'] for t in tr):6.1f} net={sum(t['net'] for t in tr):7.2f} gross={sum(t['gross'] for t in tr):7.2f} fees={sum(t['fees'] for t in tr):5.2f} clamped={sum(1 for t in tr if t['clamp'])}")
grp('decision.size_scale',lambda t,d,o:(d or {}).get('size_scale'))
grp('decision.decided_by',lambda t,d,o:(d or {}).get('decided_by'))
grp('clamped x size_scale',lambda t,d,o:(bool(t['clamp']),(d or {}).get('size_scale')))
# config max_bet_usd per run from runs.tsv config_snapshot_json
runs={r['id']:r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
mb=collections.Counter()
for t in A6:
    cfg=runs.get(t['sigs'][0]['run_id'],{}).get('config_snapshot_json','{}')
    try: c=json.loads(cfg)
    except Exception: c={}
    mb[(c.get('max_bet_usd'),c.get('budget_usd'),c.get('leverage'))]+=1
print('\nconfig (max_bet_usd,budget_usd,leverage) per trip:',mb.most_common(8))
