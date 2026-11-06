# Agent A: no_verdict / verdict_salvaged rates (agents 6, 60) and what the desk did on those cycles.
import pickle,collections,datetime as dt
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
D=pickle.load(open('a_events.pkl','rb')); ev=[e for e in D['ev'] if e['ts']>='2026-10-05T15:49']
byrun=collections.defaultdict(list)
for e in ev: byrun[e['run']].append(e)
for k in byrun: byrun[k].sort(key=lambda e:(e['ts'],e['id']))
for ag in ('6','60'):
    E=[e for e in ev if e['agent']==ag]
    dec=[e for e in E if e['et']=='decision']; nv=[e for e in E if e['et']=='no_verdict']; vs=[e for e in E if e['et']=='verdict_salvaged']
    print(f"\n===== agent {ag}: decisions={len(dec)} no_verdict={len(nv)} ({len(nv)/max(1,len(dec))*100:.1f}% of decisions) verdict_salvaged={len(vs)} ({len(vs)/max(1,len(dec))*100:.1f}%)")
    print(' decided_by:',collections.Counter(e['p'].get('decided_by') for e in dec))
    print(' route:',collections.Counter((e['p'].get('route') or {}).get('route') for e in dec))
    print(' no_verdict kinds:',collections.Counter(e['p'].get('kind') for e in nv)); print(' salvaged kinds:',collections.Counter(e['p'].get('kind') for e in vs))
    print(' fallback_reason:',collections.Counter(e['p'].get('fallback_reason') for e in dec).most_common(6))
    # per week
    wk=collections.defaultdict(lambda:collections.Counter())
    for e in dec: wk[T(e['ts']).isocalendar()[1]]['dec']+=1; wk[T(e['ts']).isocalendar()[1]]['ai' if e['p'].get('decided_by')=='ai' else e['p'].get('decided_by')]+=1
    for e in nv: wk[T(e['ts']).isocalendar()[1]]['no_verdict']+=1
    for e in vs: wk[T(e['ts']).isocalendar()[1]]['salvaged']+=1
    for k in sorted(wk): print(f"  ISO wk {k}: {dict(wk[k])}")
    # per day for agent 6
    if ag=='6':
        day=collections.defaultdict(lambda:collections.Counter())
        for e in dec: day[e['ts'][:10]]['dec']+=1; day[e['ts'][:10]][e['p'].get('decided_by')]+=1
        for e in nv: day[e['ts'][:10]]['nv']+=1
        tr=[e for e in E if e['et']=='trade']
        for e in tr: day[e['ts'][:10]]['trades']+=1
        for k in sorted(day): print(f"   {k}: {dict(day[k])}")
    # what followed a no_verdict: decision in same run within 120s after
    follow=collections.Counter(); traded=0; actions=collections.Counter()
    for e in nv:
        R=byrun[e['run']]; t=T(e['ts'])
        d=[x for x in R if x['et']=='decision' and 0<=(T(x['ts'])-t).total_seconds()<=180]
        if d:
            p=d[0]['p']; follow[(p.get('decided_by'),p.get('action'))]+=1
            tr=[x for x in R if x['et']=='trade' and 0<=(T(x['ts'])-t).total_seconds()<=240]
            if tr: traded+=1
        else: follow[('no decision within 180s',)]+=1
    print(' decision following a no_verdict (<=180s):',follow.most_common(8)); print(' trades within 240s after a no_verdict:',traded)
    # what the desk held when no_verdict: was there an open position in that run? use order_params/position via decision 'position_qty' in order_intent
    # verdict_salvaged -> trades
    st_=0
    for e in vs:
        R=byrun[e['run']]; t=T(e['ts'])
        tr=[x for x in R if x['et']=='trade' and 0<=(T(x['ts'])-t).total_seconds()<=240]
        if tr: st_+=1
    print(' trades within 240s after a verdict_salvaged:',st_)
    # scaffold decisions: when a position is held (light cycle no verdict with open position)
    sc=[e for e in dec if e['p'].get('decided_by')=='scaffold']
    print(' scaffold decisions:',len(sc),'actions:',collections.Counter(e['p'].get('action') for e in sc))
