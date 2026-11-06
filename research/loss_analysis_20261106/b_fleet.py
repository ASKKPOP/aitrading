# Section 4: what the fleet did with its slots — gate_skip, run_status, flat vs holding, churn.
import pickle, csv, json, collections, statistics as st, datetime as dt
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0='2026-10-05T15:49:00'; WIN1='2026-11-06T20:30:00'; W0=T(WIN0); W1=T(WIN1); WH=(W1-W0).total_seconds()/3600
ev=[e for e in pickle.load(open('b_events.pkl','rb')) if WIN0<=e[4]<=WIN1]
trips=pickle.load(open('b_trips.pkl','rb'))
runs=list(csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE))
print(f"window hours={WH:.1f}")
for ag in ('6','60'):
    E=[e for e in ev if e[0]==ag]
    gs=[e for e in E if e[3]=='gate_skip']
    print(f"\n=== agent {ag}: gate_skip n={len(gs)}")
    print('  by stage:',collections.Counter(e[5]['stage'] for e in gs).most_common())
    def norm(r):
        r=str(r)
        if r.startswith('confidence'): return 'confidence below threshold'
        if r.startswith('add_limit: position underwater'): return 'add_limit: position underwater'
        return r[:70]
    print('  by reason:',collections.Counter(norm(e[5]['reason']) for e in gs).most_common(14))
    rs=[e for e in E if e[3]=='run_status']
    print(f"  run_status n={len(rs)}; stopping reasons:",collections.Counter(e[5]['reason'] for e in rs if e[5].get('to')=='stopping').most_common())
    print('  paused reasons:',collections.Counter(e[5]['reason'] for e in rs if e[5].get('to')=='paused').most_common())
    # runs of the fleet alive in window
    fl='44' if ag=='6' else '43'
    R=[r for r in runs if r['agent_id']==ag and r['fleet_id']==fl and r['started_at']!='NULL' and r['started_at']<=WIN1 and (r['stopped_at']=='NULL' or r['stopped_at']>=WIN0)]
    print(f"  fleet {fl} runs alive in window: {len(R)}; status now:",collections.Counter(r['status'] for r in R).most_common(),'; stopped reasons:',collections.Counter(r['status_reason'] for r in R).most_common(12))
    # slot-hours: run alive time clipped to window; holding time from trips (agent-level: union of trip intervals per run)
    tot_h=0; 
    for r in R:
        a=max(W0,T(r['started_at'])); b=min(W1,T(r['stopped_at']) if r['stopped_at']!='NULL' else W1)
        tot_h+=max(0,(b-a).total_seconds()/3600)
    tr=[t for t in trips if t['agent']==ag]
    hold_h=sum(min(T(t['t1']),W1).timestamp()-max(T(t['t0']),W0).timestamp() for t in tr)/3600
    print(f"  slot-hours alive={tot_h:.0f} of 8x{WH:.0f}={8*WH:.0f} possible ({tot_h/(8*WH)*100:.0f}% occupancy); holding a position {hold_h:.0f}h = {hold_h/tot_h*100:.1f}% of alive slot-hours, {hold_h/(8*WH)*100:.1f}% of 8 slots; flat {tot_h-hold_h:.0f}h")
    # churn: runs that never traded and how they ended; run lifetimes
    traded={t['final_run'] for t in tr}|{s['run_id'] for t in tr for s in t['sigs']}
    nt=[r for r in R if r['id'] not in traded and r['status']=='stopped']
    print(f"  runs that never traded & stopped: {len(nt)}; reasons:",collections.Counter(r['status_reason'] for r in nt).most_common(8))
    life=[(T(r['stopped_at'])-T(r['started_at'])).total_seconds()/60 for r in R if r['stopped_at']!='NULL']
    print(f"  run lifetime median={st.median(life):.0f}m mean={st.mean(life):.0f}m; runs/day={len(R)/(WH/24):.1f}")
    # fee of churn: fees on runs ended by idle_retired/no_prospect/desk_retired that did trade
    for reason in ('idle_retired','no_prospect_switched','desk_retired','adapt_retired','positions_held','eval_failed','stop_eval_failed'):
        rr=[r for r in R if r['status_reason']==reason]
        tt=[t for t in tr if t['final_run'] in {r['id'] for r in rr}]
        print(f"    {reason:22s} runs={len(rr):4d} trips={len(tt):3d} net={sum(t['net'] for t in tt):7.2f} fees={sum(t['fees'] for t in tt):5.2f}")
    # decisions: hold share & no-llm share
    dec=[e for e in E if e[3]=='decision']
    print(f"  decisions n={len(dec)}; action:",collections.Counter(d[5].get('action') for d in dec).most_common(6),'; decided_by:',collections.Counter(d[5].get('decided_by') for d in dec).most_common(),'; fallback:',collections.Counter(d[5].get('fallback_reason') for d in dec).most_common(4))
    nv=[e for e in E if e[3]=='no_verdict']; print('  no_verdict n=',len(nv),collections.Counter(e[5].get('kind') for e in nv).most_common(5))
# fleet 43 replenishing: run count over time (count running runs at each run_status transition)
print('\n=== fleet 43 (agent 60) running-slot count over the window')
R43=[r for r in runs if r['fleet_id']=='43' and r['started_at']!='NULL']
pts=[]
for r in R43:
    pts.append((r['started_at'],1)); pts.append((r['stopped_at'] if r['stopped_at']!='NULL' else '2026-11-06T21:08:00Z',-1))
pts.sort(); cur=0; hist=collections.Counter(); last=None
for ts,d in pts:
    if last and ts>=WIN0: hist[cur]+= (T(min(ts,WIN1))-T(max(last,WIN0))).total_seconds()/3600 if min(ts,WIN1)>max(last,WIN0) else 0
    cur+=d; last=ts
print('  hours at each running-run count:',{k:round(v,1) for k,v in sorted(hist.items())}, 'mean slots',round(sum(k*v for k,v in hist.items())/sum(hist.values()),2))
R44=[r for r in runs if r['fleet_id']=='44' and r['started_at']!='NULL']
pts=[]
for r in R44:
    pts.append((r['started_at'],1)); pts.append((r['stopped_at'] if r['stopped_at']!='NULL' else '2026-11-06T21:08:00Z',-1))
pts.sort(); cur=0; hist=collections.Counter(); last=None
for ts,d in pts:
    if last and ts>=WIN0: hist[cur]+= (T(min(ts,WIN1))-T(max(last,WIN0))).total_seconds()/3600 if min(ts,WIN1)>max(last,WIN0) else 0
    cur+=d; last=ts
print('=== fleet 44 hours at each running-run count:',{k:round(v,1) for k,v in sorted(hist.items())}, 'mean slots',round(sum(k*v for k,v in hist.items())/sum(hist.values()),2))
