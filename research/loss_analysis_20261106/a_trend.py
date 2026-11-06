# Agent A: agent 63 (trend module) — reconcile the two 10-08 sells and cash 9933.77; what the module's own trail would have done.
import csv,json,bisect,pickle,calendar,time,statistics as st
csv.field_size_limit(10**9)
C=pickle.load(open('a_candles15.pkl','rb'))
sig=[s for s in csv.DictReader(open('d/signals.tsv'),delimiter='\t') if s['agent_id']=='63']
for s in sig: print('leg',s['id'],s['created_at'],s['symbol'],s['side'],'px',s['exit_price'],'qty',s['quantity'],'pnl',s['pnl'],'fee',s['fee_usd'],'run',s['run_id'],'coid',s['client_order_id'])
state=json.loads([r for r in csv.reader(open('d/settings.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE) if r[0]=='trend_module_state'][0][1])
ev=state['events']; co=[e for e in ev if e['event']=='closed_outside']
for e in co: print('closed_outside',e)
# implied entry price = exit + pnl/qty (pnl is net of exit fee -> gross = pnl + fee)
tot=0
for s in sig:
    q=float(s['quantity']); px=float(s['exit_price']); pnl=float(s['pnl']); fee=float(s['fee_usd'])
    gross=pnl+fee; entry=px-gross/q  # long: gross=(px-entry)*q
    stop=[e for e in co if e['symbol']==s['symbol']][0]['stop']
    print(f"{s['symbol']}: implied entry {entry:.4f}, exit {px}, initial_stop {stop}, stop dist {(entry-stop)/entry*100:.2f}% -> R=${(entry-stop)*q:.2f}; realised gross {gross:.2f} = {gross/((entry-stop)*q):.2f}R; exit fee {fee:.3f}; entry fee ~{entry*q*0.00045:.3f}")
    tot+=pnl
print('sum pnl (net of exit fee)',round(tot,2))
# cash reconciliation: cash now vs 10000 - all fees + all pnl needs full history; the window's cash delta:
print('cash now 9933.76995028; window realised (net of exit fee) =',round(tot,2),'; 10-05 report said agent 63: 1 closed loss -15.02 + 2 open longs')
print('implied cash at 10-05 = 9933.77 -',round(tot,2),'=',round(9933.76995028-tot,2),' -> 10000 - 15.02 - entry fees of the two opens =',round(10000-15.02-sum(((float(s['exit_price'])+ (float(s['pnl'])+float(s['fee_usd']))/float(s['quantity'])*-1)*0) for s in sig),2))
# trail per last trail_update, and when the price crossed the TRAIL vs the initial stop
ts=lambda s: calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))*1000
last={}
for e in ev:
    if e['event']=='trail_update': last[e['symbol']]=e
for sym,e in last.items():
    print(f"\n{sym}: last trail_update {e['ts']} trail={e['trail']:.4f} best_close={e['best_close']} close={e['close']}")
    c=C[sym]['c']; idx=[x[0] for x in c]
    i0=bisect.bisect_left(idx,ts('2026-10-07T00:00:00')); i1=bisect.bisect_right(idx,ts('2026-10-08T16:00:00'))
    stop=[x for x in co if x['symbol']==sym][0]['stop']; trail=e['trail']
    first_trail=None; first_stop=None
    for x in c[i0:i1]:
        t=time.strftime('%m-%dT%H:%M',time.gmtime(x[0]/1000))
        if first_trail is None and x[3]<trail: first_trail=(t,x[3])
        if first_stop is None and x[3]<stop: first_stop=(t,x[3])
    print(f"  first 15m low below trail {trail:.4f}: {first_trail}; first 15m low below initial stop {stop:.4f}: {first_stop}")
    # daily closes 10-05..10-08 UTC
    for day in ('2026-10-05','2026-10-06','2026-10-07','2026-10-08'):
        j=bisect.bisect_right(idx,ts(day+'T23:45:00'))-1
        if 0<=j<len(c): print(f"  daily close {day}: {c[j][4]}")
    # path 10-07 16:00 -> 10-08 16:00 hourly
    print('  hourly closes 10-07 16:00 -> 10-08 16:00:',[ (time.strftime('%dT%H',time.gmtime(x[0]/1000)),x[4]) for x in c[i0:i1] if (x[0]//60000)%60==0 and x[0]>=ts('2026-10-07T16:00:00')])
# count module ticks per day from trail_update events
import collections
days=collections.Counter(e['ts'][:10] for e in ev if e['event']=='trail_update')
print('\ntrail_update ticks per day:',dict(sorted(days.items())))
