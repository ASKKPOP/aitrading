# Agent A: exit authorship for agent-6 trips in window — cyc / arm / other(NULL coid) — with per-trip reasons.
import pickle,collections,json,datetime as dt,re,statistics as st
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
D=pickle.load(open('a_events.pkl','rb')); ev=D['ev']; sig=D['sig']; runs=D['runs']
trips=pickle.load(open('trips1.pkl','rb'))
WIN0=T('2026-10-05T15:49:00')
byrun=collections.defaultdict(list)
for e in ev: byrun[e['run']].append(e)
for k in byrun: byrun[k].sort(key=lambda e:(e['ts'],e['id']))
bysym=collections.defaultdict(list)
for e in ev:
    r=runs.get(e['run']); 
    if r: bysym[(e['agent'],r['symbol'])].append(e)
for k in bysym: bysym[k].sort(key=lambda e:(e['ts'],e['id']))
sigs6=[s for s in sig if s['agent_id']=='6']
def summ(name,tr):
    tr=[t for t in tr if 'net' in t]
    if not tr: print(f"{name:34s} n=0"); return
    n=len(tr); net=sum(t['net'] for t in tr); gross=sum(t['gross'] for t in tr); fees=sum(t['entry_fee']+t['exit_fee'] for t in tr)
    w=sorted(tr,key=lambda t:t['net']); big=w[0] if abs(w[0]['net'])>abs(w[-1]['net']) else w[-1]
    print(f"{name:34s} n={n:3d} net={net:7.2f} gross={gross:7.2f} fees={fees:5.2f} WR={sum(1 for t in tr if t['net']>0)/n*100:4.0f}% ex-largest({big['symbol']} {big['net']:+.2f}) net={net-big['net']:7.2f} gross={gross-big['gross']:7.2f}")
W=[t for t in trips if t['agent']=='6' and 'net' in t and T(t['t0'])>=WIN0]
out=[]
for t in W:
    legs=[s for s in sigs6 if s['symbol']==t['symbol'] and t['t0']<=s['created_at']<=t['t1'] and s['side'] in('sell','cover')]
    last=legs[-1]
    tts=T(last['created_at']); run=last['run_id']
    R=byrun.get(run,[]) if run!='NULL' else bysym.get(('6',t['symbol']),[])
    near=[e for e in R if abs((T(e['ts'])-tts).total_seconds())<=90 and e['et'] not in('equity','recall','outlook','hot_issue','order_params')]
    k=t.get('exit_kind'); auth='?'; why=''
    cyc=re.search(r':cyc:(\d+)$',last['client_order_id'] or '')
    if k=='cyc':
        dec=[e for e in R if e['et']=='decision' and e['p'].get('cycle')==int(cyc.group(1))]
        p=dec[-1]['p'] if dec else {}
        auth=f"desk cycle decided_by={p.get('decided_by')} chair={p.get('chair') if isinstance(p.get('chair'),str) else ('amended:'+','.join((p.get('chair') or {}).get('amended',[])))}"
        why=(p.get('report') or '')[:160]
        oi=[e for e in R if e['et']=='order_intent' and e['p'].get('cycle')==int(cyc.group(1))]
        if oi: why+=' | intent='+str(oi[-1]['p'].get('intent'))+' why='+str(oi[-1]['p'].get('why'))[:120]
        sm=[e for e in near if e['et']=='stop_mechanism']
        if sm: why+=' | stop_mech='+json.dumps(sm[-1]['p'])[:120]
    elif k=='arm':
        ae=[e for e in R if e['et']=='armed_exit' and abs((T(e['ts'])-tts).total_seconds())<=90]
        auth='armed exit (desk-authored level, executed by rail)'
        why=json.dumps(ae[-1]['p'])[:200] if ae else 'no armed_exit event within 90s'
        # who armed it: last order_intent with arm before
        oi=[e for e in R if e['et']=='order_intent' and e['p'].get('arm') and T(e['ts'])<tts]
        if oi: why+=' | armed by intent cyc '+str(oi[-1]['p'].get('cycle'))+' arm='+json.dumps(oi[-1]['p'].get('arm'))[:120]
    elif k=='other':
        kinds=collections.Counter(e['et'] for e in near)
        rs=[e for e in near if e['et']=='run_status']; ad=[e for e in near if e['et']=='adapt']; sm=[e for e in near if e['et']=='stop_mechanism']
        if run=='NULL': auth='run_id NULL: outside any run (start-run close / orphan)'
        elif sm: auth='stop_mechanism '+sm[-1]['p'].get('reason','')
        elif rs: auth='run_status '+rs[-1]['p'].get('reason','')+' '+str(rs[-1]['p'].get('detail'))
        elif ad: auth='adapt '+ad[-1]['p'].get('trigger','')
        else: auth='no run event within 90s -> SL/TP watcher (risk_engine, no coid)'
        why=' ; '.join(e['et']+':'+json.dumps(e['p'])[:110] for e in near[:5])
        # bracket at open: stop_loss/take_profit from order_params of entry cycle
        ecyc=re.search(r':cyc:(\d+)$',[s for s in sigs6 if s['symbol']==t['symbol'] and s['created_at']==t['t0']][0]['client_order_id'] or '')
        if ecyc and run!='NULL':
            op=[e for e in R if e['et']=='order_params' and e['p'].get('cycle')==int(ecyc.group(1))]
            if op: why+=' | entry params='+json.dumps((op[-1]['p'].get('params') or {}))[:140]
            br=[e for e in R if e['et']=='bracket_reanchor' and e['p'].get('cycle')==int(ecyc.group(1))]
            if br: why+=' | bracket='+json.dumps(br[-1]['p'])[:140]
    t['auth']=auth; t['why']=why; t['exit_legs']=len(legs); t['last_coid']=last['client_order_id']; t['run']=run
    out.append(t)
pickle.dump(out,open('a_exits.pkl','wb'))
print('==== agent 6 window trips by exit_kind')
for k in ('flatten','arm','cyc','other'): summ(k,[t for t in out if t['exit_kind']==k])
for k in ('cyc','arm','other'):
    print(f"\n######## {k}")
    tr=sorted([t for t in out if t['exit_kind']==k],key=lambda t:t['net'])
    print(' authors:',collections.Counter(t['auth'][:60] for t in tr))
    for t in tr:
        print(f"  {t['t1'][:16]} {t['symbol']:10s} {t['dir']:5s} net={t['net']:+6.2f} gross={t['gross']:+6.2f} hold={t['hold_min']:5.0f}m legs={t['legs']} run={t['run']} | {t['auth']}\n      {t['why'][:420]}")
