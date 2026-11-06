# Agent B: enrich trips with the algorithm events that ended them; write b_trips.pkl and print section tables.
import pickle, csv, collections, datetime as dt, statistics as st, json, bisect
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
WIN0='2026-10-05T15:49:00'; WIN1='2026-11-06T20:30:00'
trips=[t for t in pickle.load(open('trips1.pkl','rb')) if 'net' in t and t['t0']>=WIN0]
ev=pickle.load(open('b_events.pkl','rb'))
byrun=collections.defaultdict(list)
for e in ev: byrun[e[1]].append(e)
runs={r['id']:r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
sig=list(csv.DictReader(open('d/signals.tsv'),delimiter='\t'))
legs=collections.defaultdict(list)
for s in sig: legs[(s['agent_id'],s['symbol'])].append(s)
def kind(coid):
    if coid in (None,'','NULL'): return 'NULL'
    if 'flatten' in coid: return 'flatten'
    if ':arm:' in coid: return 'arm'
    if ':cyc:' in coid: return 'cyc'
    if 'reclaim' in coid: return 'reclaim'
    return 'other:'+coid
def sec(a,b): return (T(a)-T(b)).total_seconds()
for t in trips:
    L=[s for s in legs[(t['agent'],t['symbol'])] if t['t0']<=s['created_at']<=t['t1']]
    L.sort(key=lambda s:int(s['id']))
    t['sigs']=L
    for s in L:
        q=float(s['quantity']); px=float(s['entry_price'] if s['side'] in('buy','short') else (s['exit_price'] if s['exit_price']!='NULL' else s['entry_price']))
        s['_notional']=q*px; s['_fee']=float(s['fee_usd'] or 0); s['_kind']=kind(s['client_order_id']); s['_isexit']=s['side'] in('sell','cover')
    t['leg_notional']=sum(s['_notional'] for s in L)
    t['entry_notional']=sum(s['_notional'] for s in L if not s['_isexit'])
    t['exit_notional']=sum(s['_notional'] for s in L if s['_isexit'])
    t['fees']=t['entry_fee']+t['exit_fee']
    t['n_entry_legs']=sum(1 for s in L if not s['_isexit']); t['n_exit_legs']=sum(1 for s in L if s['_isexit'])
    fin=[s for s in L if s['_isexit']][-1]
    t['final_kind']=fin['_kind']; t['final_run']=fin['run_id']
    rid=int(fin['run_id']) if fin['run_id']!='NULL' else None
    t['mech']='?'; t['sm']=None; t['rs_reason']=None
    if rid:
        E=byrun[rid]
        near=[e for e in E if -300<=sec(e[4],t['t1'])<=60]
        sm=[e for e in near if e[3]=='stop_mechanism']
        rs=[e for e in near if e[3]=='run_status' and e[5].get('to')=='stopping']
        if sm: t['sm']=sm[-1][5]
        if rs: t['rs_reason']=rs[-1][5].get('reason')
        routed=[e for e in E if e[3]=='gate_skip' and 'routed stop hit' in str(e[5].get('reason')) and -900<=sec(e[4],t['t1'])<=5]
        t['routed_stop_note']=len(routed)
        if t['final_kind']=='flatten':
            r=t['rs_reason'] or ''
            if r=='stop_event:trailing_lock': t['mech']='ratchet' if t['sm'] else 'legacy_trail'
            elif r.startswith('stop_event:'): t['mech']=r.split(':',1)[1]
            elif r: t['mech']=r
            else:
                # flatten without a stopping transition nearby: look wider
                rs2=[e for e in E if e[3]=='run_status' and e[5].get('to')=='stopping' and -3600<=sec(e[4],t['t1'])<=600]
                t['mech']='flatten:'+(rs2[-1][5].get('reason') if rs2 else 'no_run_status')
        elif t['final_kind']=='arm': t['mech']='armed_exit(AI level)'
        elif t['final_kind']=='cyc': t['mech']='desk_cycle_close(AI)'
        elif t['final_kind']=='NULL': t['mech']='sltp_watcher_failsafe'
        else: t['mech']=t['final_kind']
        # equity path during the trip (run-scoped)
        eq=[(e[4],e[5]) for e in E if e[3]=='equity' and t['t0']<=e[4]<=t['t1']]
        if eq:
            base=eq[0][1]['realized']  # realized just after entry (includes entry fee)
            tot=[x[1]['total'] for x in eq]
            t['eq_n']=len(eq); t['eq_base']=base; t['eq_peak']=max(tot)-base; t['eq_trough']=min(tot)-base
            t['eq_last']=tot[-1]-base
        else: t['eq_n']=0
        # size clamp at entry
        sc=[e for e in E if e[3]=='size_clamp' and -120<=sec(e[4],t['t0'])<=5]
        t['clamp']=sc[-1][5] if sc else None
        # armed exits & adapt during trip
        t['armed']=[e[5] for e in E if e[3]=='armed_exit' and t['t0']<=e[4]<=t['t1']]
        t['adapts']=[(e[4],e[5].get('trigger'),e[5].get('realized')) for e in E if e[3]=='adapt' and t['t0']<=e[4]<=t['t1']]
        rr=runs.get(str(rid)) or {}
        t['run_status_reason']=rr.get('status_reason'); t['peak_pnl_usd']=rr.get('peak_pnl_usd'); t['peak_realized_usd']=rr.get('peak_realized_usd')
        t['stop_cond']=rr.get('stop_conditions_json')
    else:
        t['mech']='orphan_close(run_id NULL)'; t['eq_n']=0; t['clamp']=None; t['armed']=[]; t['adapts']=[]
pickle.dump(trips,open('b_trips.pkl','wb'))

def summ(name,tr,extra=''):
    if not tr: print(f"{name:42s} n=0"); return
    n=len(tr); net=sum(t['net'] for t in tr); gross=sum(t['gross'] for t in tr); fees=sum(t['fees'] for t in tr)
    big=min(tr,key=lambda t:abs(t['net']) if False else -abs(t['net']))
    ex=[t for t in tr if t is not big]
    exnet=sum(t['net'] for t in ex); exgross=sum(t['gross'] for t in ex)
    w=sum(1 for t in tr if t['net']>0)
    bp=[t['gross']/t['entry_notional']*1e4 for t in tr if t['entry_notional']>0]
    print(f"{name:42s} n={n:4d} net={net:8.2f} gross={gross:8.2f} fees={fees:6.2f} WR={w/n*100:5.1f}% medHold={st.median(t['hold_min'] for t in tr):7.1f}m medNotl={st.median(t['entry_notional'] for t in tr):6.1f} meanGrossBp={st.mean(bp):6.1f} medGrossBp={st.median(bp):6.1f} | ex-largest({big['symbol']} {big['net']:+.2f}): net={exnet:8.2f} gross={exgross:8.2f} {extra}")
for ag in ('6','60'):
    tr=[t for t in trips if t['agent']==ag]
    print(f"\n===== agent {ag}: n={len(tr)} net={sum(t['net'] for t in tr):.2f} gross={sum(t['gross'] for t in tr):.2f} fees={sum(t['fees'] for t in tr):.2f}")
    c=collections.Counter(t['mech'] for t in tr)
    for m,_ in c.most_common(): summ('  '+m,[t for t in tr if t['mech']==m])
    print('  final exit kind:',collections.Counter(t['final_kind'] for t in tr).most_common())
    print('  routed-stop note present on NULL exits:',collections.Counter((t['mech'],t.get('routed_stop_note',0)>0) for t in tr if t['final_kind']=='NULL'))
