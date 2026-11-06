# Agent A: (1) stop level behind the SL/TP-watcher closes — desk's own stop_pct vs the platform cap; (2) the three run_id-NULL closes.
import pickle,collections,json,re,datetime as dt
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
D=pickle.load(open('a_events.pkl','rb')); ev=D['ev']; sig=D['sig']; runs=D['runs']
out=pickle.load(open('a_exits.pkl','rb'))
byrun=collections.defaultdict(list)
for e in ev: byrun[e['run']].append(e)
sigs6=[s for s in sig if s['agent_id']=='6']
print('=== (1) watcher closes: stop geometry at entry')
w=[t for t in out if t['exit_kind']=='other' and t['auth'].startswith('no run event')]
tot_stop_dist=[]
for t in sorted(w,key=lambda t:t['net']):
    R=byrun.get(t['run'],[])
    ent=[s for s in sigs6 if s['symbol']==t['symbol'] and s['created_at']==t['t0']][0]
    c=re.search(r':cyc:(\d+)$',ent['client_order_id'] or ''); c=int(c.group(1)) if c else None
    op=[e for e in R if e['et']=='order_params' and e['p'].get('cycle')==c]; sc=[e for e in R if e['et']=='stop_cap' and e['p'].get('cycle')==c]
    br=[e for e in R if e['et']=='bracket_reanchor' and e['p'].get('cycle')==c]; tc=[e for e in R if e['et']=='target_cap' and e['p'].get('cycle')==c]
    params=(op[-1]['p'].get('params') or {}) if op else {}
    stop=None
    if br: stop=br[-1]['p'].get('stop_after'); fill=br[-1]['p'].get('fill_price')
    dist=(abs(stop-fill)/fill*100) if stop and fill else None
    if dist: tot_stop_dist.append(dist)
    # exit price vs stop
    last=[s for s in sigs6 if s['symbol']==t['symbol'] and s['created_at']==t['t1']][0]
    xp=float(last['exit_price'])
    print(f" {t['t1'][:16]} {t['symbol']:9s} {t['dir']:5s} net={t['net']:+5.2f} hold={t['hold_min']:4.0f}m | desk stop_pct={params.get('stop_pct')} target_pct={params.get('target_pct')} params_state={'absent' if not params else 'parsed'} | stop_cap={json.dumps(sc[-1]['p']) if sc else None} | bracket stop={stop} dist={dist and round(dist,2)}% exit={xp} ({'at/through stop' if stop and ((t['dir']=='short' and xp>=stop*0.999) or (t['dir']=='long' and xp<=stop*1.001)) else 'NOT at stop'})")
print('median stop distance %',round(sorted(tot_stop_dist)[len(tot_stop_dist)//2],2),'n',len(tot_stop_dist))
print('\n=== (2) run_id NULL closes')
for t in [t for t in out if t['run']=='NULL']:
    print(f"\n-- {t['symbol']} {t['dir']} t0={t['t0']} t1={t['t1']} net={t['net']:+.2f} legs={t['legs']}")
    legs=[s for s in sigs6 if s['symbol']==t['symbol'] and t['t0']<=s['created_at']<=t['t1']]
    for s in legs: print('   leg',s['id'],s['created_at'],s['side'],s['quantity'],s['entry_price'],s['exit_price'],'pnl',s['pnl'],'run',s['run_id'],'coid',s['client_order_id'])
    rids=set(s['run_id'] for s in legs if s['run_id']!='NULL')
    for rid in rids:
        r=runs[rid]; print('   run',rid,'status',r['status'],'reason',r['status_reason'],'started',r['started_at'],'stopped',r['stopped_at'],'stop_flatten',r['stop_flatten'])
        rs=[e for e in byrun[rid] if e['et'] in('run_status','adapt','alert','stop_mechanism') and e['ts']>=legs[0]['created_at']]
        for e in rs[-8:]: print('     ',e['ts'],e['et'],json.dumps(e['p'])[:160])
    # runs for this symbol created around t1
    near=[r for r in runs.values() if r['agent_id']=='6' and r['symbol']==t['symbol'] and r['created_at'][:16]<=t['t1'][:16]<= (r['started_at'] or r['created_at'])[:16] or (r['agent_id']=='6' and r['symbol']==t['symbol'] and abs((T(r['created_at'])-T(t['t1'])).total_seconds())<3600)]
    for r in near: print('   run created near close:',r['id'],r['created_at'],r['started_at'],r['status'],r['status_reason'],r['created_via'])
    # events of any agent-6 run of that symbol within 10 min of close
    E=[e for e in ev if e['agent']=='6' and runs.get(e['run'],{}).get('symbol')==t['symbol'] and abs((T(e['ts'])-T(t['t1'])).total_seconds())<=600 and e['et'] not in('equity',)]
    for e in E[:12]: print('     ',e['ts'],e['run'],e['et'],json.dumps(e['p'])[:150])
