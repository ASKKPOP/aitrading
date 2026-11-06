# Agent A: who authored each entry (agents 6, 60) in the window; PREREG H2 counts per ISO week.
import pickle,collections,json,datetime as dt,re,sys
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
D=pickle.load(open('a_events.pkl','rb')); ev=D['ev']; sig=D['sig']; runs=D['runs']
trips=pickle.load(open('trips1.pkl','rb'))
WIN0='2026-10-05T15:49'
byrun=collections.defaultdict(list)
for e in ev: byrun[e['run']].append(e)
for k in byrun: byrun[k].sort(key=lambda e:(e['ts'],e['id']))
def cyc_of(coid):
    m=re.search(r':cyc:(\d+)$',coid or ''); return int(m.group(1)) if m else None
rows=[]
for s in sig:
    if s['agent_id'] not in('6','60') or s['created_at']<WIN0 or s['side'] not in('buy','short'): continue
    R=byrun.get(s['run_id'],[]); tts=T(s['created_at']); cyc=cyc_of(s['client_order_id'])
    dec=[e for e in R if e['et']=='decision' and e['p'].get('cycle')==cyc] if cyc is not None else []
    dec=dec[-1] if dec else None
    # order_discussion: last one in run within 15 min before the trade
    od=[e for e in R if e['et']=='order_discussion' and 0<=(tts-T(e['ts'])).total_seconds()<=900]
    od=od[-1] if od else None
    oi=[e for e in R if e['et']=='order_intent' and e['p'].get('cycle')==cyc]; oi=oi[-1] if oi else None
    sc=[e for e in R if e['et']=='size_clamp' and e['p'].get('cycle')==cyc]
    nv=[e for e in R if e['et'] in('no_verdict','verdict_salvaged') and 0<=(tts-T(e['ts'])).total_seconds()<=900]
    p=dec['p'] if dec else {}
    ch=p.get('chair'); chs='none' if ch is None else (ch if isinstance(ch,str) else 'amended:'+','.join(ch.get('amended',[])))
    rows.append(dict(sid=int(s['id']),agent=s['agent_id'],run=s['run_id'],sym=s['symbol'],side=s['side'],ts=s['created_at'],wk=T(s['created_at']).isocalendar()[1],
        coid=s['client_order_id'],cyc=cyc,has_dec=dec is not None,decided_by=p.get('decided_by'),src=(p.get('llm') or {}).get('source'),model=(p.get('llm') or {}).get('model'),
        action=p.get('action'),fallback=p.get('fallback_reason'),chair=chs,disc='discussion' in p,route=(p.get('route') or {}).get('route'),
        od=od['p'] if od else None,od_proposed=(od['p'].get('proposed') or {}).get('action') if od else None,od_final=(od['p'].get('final') or {}).get('action') if od else None,
        veto=(od['p'].get('veto_overridden') if od else None),panel=(od['p'].get('panel_verdict') if od else None),entry_held=(od['p'].get('entry_held') if od else None),
        reviewed_by=(od['p'].get('reviewed_by') if od else None),intent=(oi['p'].get('intent') if oi else None),clamp=[c['p'].get('stage') for c in sc],
        nv=[e['et']+':'+str(e['p'].get('kind')) for e in nv],report=p.get('report','')[:200],conf=p.get('confidence'),conviction=p.get('conviction')))
pickle.dump(rows,open('a_entries.pkl','wb'))
for ag in ('6','60'):
    r=[x for x in rows if x['agent']==ag]
    print(f"\n===== agent {ag}: entry legs n={len(r)}  (buy {sum(1 for x in r if x['side']=='buy')}, short {sum(1 for x in r if x['side']=='short')})")
    print(' has decision:',collections.Counter(x['has_dec'] for x in r))
    print(' coid kinds:',collections.Counter((x['coid'] or 'NULL').split(':')[2] if x['coid'] and x['coid'].count(':')>=2 else (x['coid'] or 'NULL') for x in r))
    print(' decided_by:',collections.Counter(x['decided_by'] for x in r))
    print(' llm.source:',collections.Counter(x['src'] for x in r)); print(' model:',collections.Counter(x['model'] for x in r))
    print(' decision.action:',collections.Counter(x['action'] for x in r))
    print(' fallback_reason:',collections.Counter(x['fallback'] for x in r))
    print(' chair:',collections.Counter(x['chair'] for x in r))
    print(' has discussion key:',collections.Counter(x['disc'] for x in r))
    print(' order_discussion found:',collections.Counter(x['od'] is not None for x in r))
    print(' od proposed->final:',collections.Counter((x['od_proposed'],x['od_final']) for x in r))
    print(' veto_overridden:',collections.Counter(x['veto'] for x in r),' panel_verdict:',collections.Counter(x['panel'] for x in r),' entry_held:',collections.Counter(x['entry_held'] for x in r),' reviewed_by:',collections.Counter(x['reviewed_by'] for x in r))
    print(' order_intent:',collections.Counter(x['intent'] for x in r))
    print(' size_clamp stages:',collections.Counter(tuple(x['clamp']) for x in r))
    print(' no_verdict/salvaged within 15m before entry:',collections.Counter(tuple(x['nv']) for x in r).most_common(6))
    print(' route:',collections.Counter(x['route'] for x in r))
    wk=collections.defaultdict(list)
    for x in r: wk[x['wk']].append(x)
    for k in sorted(wk):
        w=wk[k]; print(f"  ISO wk {k}: n={len(w):3d} decided_by={dict(collections.Counter(x['decided_by'] for x in w))} chair_amended_action={sum(1 for x in w if 'amended:action' in x['chair'])} veto_overridden={sum(1 for x in w if x['veto'])} rule_fallback_entries={sum(1 for x in w if x['decided_by']=='rule')} shorts={sum(1 for x in w if x['side']=='short')}")
    # decided_by rule entries: show
    rb=[x for x in r if x['decided_by']!='ai']
    print(' NON-ai-decided entries:',len(rb))
    for x in rb[:12]: print('   ',x['ts'],x['sym'],x['side'],x['decided_by'],x['action'],x['fallback'],x['chair'],x['report'][:100])
    # the veto_overridden entries
    vo=[x for x in r if x['veto']]
    print(' veto_overridden entries:',len(vo))
    for x in vo: print('   ',x['ts'],x['sym'],x['side'],x['decided_by'],x['chair'],json.dumps(x['od'])[:250])
