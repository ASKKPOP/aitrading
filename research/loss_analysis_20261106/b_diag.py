import pickle, csv, collections, datetime as dt
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0='2026-10-05T15:49:00'
trips=[t for t in pickle.load(open('trips1.pkl','rb')) if 'net' in t and t['t0']>=WIN0]
ev=pickle.load(open('b_events.pkl','rb'))
byrun=collections.defaultdict(list)
for e in ev: byrun[e[1]].append(e)
sig=list(csv.DictReader(open('d/signals.tsv'),delimiter='\t'))
sigbyid={s['id']:s for s in sig}
# which signal legs belong to each trip: re-derive by agent+symbol+time range
legs=collections.defaultdict(list)
for s in sig: legs[(s['agent_id'],s['symbol'])].append(s)
for t in trips:
    L=[s for s in legs[(t['agent'],t['symbol'])] if t['t0']<=s['created_at']<=t['t1']]
    t['sigs']=L
    t['runs']=sorted({s['run_id'] for s in L})
multi=[t for t in trips if len(t['runs'])>1]
print('trips',len(trips),'multi-run trips',len(multi))
for t in multi[:10]: print(' ',t['symbol'],t['dir'],t['runs'],[ (s['side'],s['run_id'],s['client_order_id']) for s in t['sigs']])
# exit coid kinds per trip (all exit legs)
kinds=collections.Counter()
for t in trips:
    ex=[s for s in t['sigs'] if s['side'] in ('sell','cover')]
    kinds[tuple(sorted({('flatten' if 'flatten' in (s['client_order_id'] or '') else 'arm' if ':arm:' in (s['client_order_id'] or '') else 'cyc' if ':cyc:' in (s['client_order_id'] or '') else 'NULL' if s['client_order_id'] in ('NULL','',None) else s['client_order_id']) for s in ex}))]+=1
print(kinds.most_common())
# 'other' exits: show events in the run around t1
oth=[t for t in trips if t.get('exit_kind')=='other' and t['agent']=='6']
print('\nOTHER (NULL coid) trips',len(oth),round(sum(t['net'] for t in oth),2))
for t in oth[:8]:
    ex=[s for s in t['sigs'] if s['side'] in ('sell','cover')][-1]
    print('\n--',t['symbol'],t['dir'],'net',round(t['net'],2),'hold',round(t['hold_min']),'runs',t['runs'],'exit sig',ex['id'],ex['created_at'],'coid',repr(ex['client_order_id']),'run_id',ex['run_id'])
    t1=T(t['t1'])
    for rid in t['runs']:
        if rid=='NULL': continue
        for e in byrun[int(rid)]:
            if abs((T(e[4])-t1).total_seconds())<=400 and e[3] not in ('equity','recall','order_params','outlook','decision'):
                print('   ',e[4],e[3],str(e[5])[:200])
