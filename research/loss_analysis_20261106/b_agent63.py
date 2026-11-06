import csv, json, collections
csv.field_size_limit(10**9)
sig=[s for s in csv.DictReader(open('d/signals.tsv'),delimiter='\t') if s['agent_id']=='63']
print('agent 63 signals n=',len(sig))
for s in sig: print(' ',{k:s[k] for k in ('id','created_at','symbol','side','entry_price','exit_price','quantity','pnl','fee_usd','run_id','client_order_id')})
runs=[r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE) if r['agent_id']=='63']
print('agent 63 runs n=',len(runs))
for r in runs: print(' ',{k:r[k] for k in ('id','symbol','status','status_reason','started_at','stopped_at','realized_pnl_usd','created_via')})
import pickle
ev=[e for e in pickle.load(open('b_events.pkl','rb')) if e[0]=='63']
print('agent 63 events in pickle:',collections.Counter(e[3] for e in ev).most_common())
for e in ev[:30]:
    if e[3] in ('trade','run_status','adapt','stop_mechanism','alert'): print(' ',e[4],e[1],e[3],str(e[5])[:200])
cash=9933.76995028; start=10000
print('cash delta',round(cash-start,2),'; sum pnl of sells',sum(float(s['pnl']) for s in sig if s['pnl']!='NULL'),'; sum fees',sum(float(s['fee_usd']) for s in sig if s['fee_usd']!='NULL'))
