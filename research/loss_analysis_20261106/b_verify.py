import pickle, csv, collections, statistics as st, datetime as dt, json
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
trips=pickle.load(open('b_trips.pkl','rb')); A6=[t for t in trips if t['agent']=='6']
ev=pickle.load(open('b_events.pkl','rb')); byrun=collections.defaultdict(list)
for e in ev: byrun[e[1]].append(e)
# (a) watcher closes: overshoot vs last authored stop, and did a decision land within 200s before the close?
W=[t for t in A6 if t['mech']=='sltp_watcher_failsafe']
over=0; n_over=0; inwin=0; rows=[]
for t in W:
    rid=int(t['final_run']); fin=[s for s in t['sigs'] if s['_isexit']][-1]
    stop=None
    for e in byrun[rid]:
        if e[3] in ('bracket_reanchor','stop_cap') and t['t0']<=e[4]<=t['t1']: stop=e[5].get('stop_after')
    px=float(fin['exit_price']); q=float(fin['quantity']); sgn=-1 if t['dir']=='short' else 1
    if stop:
        o=sgn*(stop-px)*q  # positive = closed worse than the stop level
        over+=o; n_over+=o>0
        rows.append((t['symbol'],round(o,3),round((px/stop-1)*1e4*sgn*-1,0)))
    dec=[e for e in byrun[rid] if e[3]=='decision' and -200<=(T(e[4])-T(t['t1'])).total_seconds()<=0]
    inwin+=bool(dec)
print(f"(a) watcher closes n={len(W)}: closed worse than the authored stop on {n_over}/{len(rows)}; net overshoot vs stop = ${over:.2f}; decision landed within 200s before the close: {inwin}/{len(W)}")
print('    per trip (symbol, $ past stop, bp past stop):',rows)
# (b) clamp counterfactual: scale clamped trips by size_before/size_after (all legs scale)
g=sum(t['gross'] for t in A6); f=sum(t['fees'] for t in A6)
gf=0; ff=0
for t in A6:
    k=t['clamp']['size_before']/t['clamp']['size_after'] if t['clamp'] else 1.0
    gf+=t['gross']*k; ff+=t['fees']*k
print(f"(b) actual gross={g:.2f} fees={f:.2f} net={g-f:.2f}; without null_size_cap (clamped trips scaled by size_before/size_after): gross={gf:.2f} fees={ff:.2f} net={gf-ff:.2f}; book notional {sum(t['entry_notional'] for t in A6):.0f} -> {sum(t['entry_notional']*(t['clamp']['size_before']/t['clamp']['size_after'] if t['clamp'] else 1) for t in A6):.0f}")
# (e) legacy trail geometry: order_plan activate_usd / notional, giveback
L=[t for t in A6 if t['mech']=='legacy_trail']
geo=[]
for t in L:
    rid=int(t['final_run']); op=[e for e in byrun[rid] if e[3]=='order_plan' and -60<=(T(e[4])-T(t['t0'])).total_seconds()<=60]
    if op: geo.append((op[-1][5]['trail']['activate_usd']/t['entry_notional']*1e4, op[-1][5]['trail']['giveback_frac'], t['gross']/t['entry_notional']*1e4))
print(f"(e) legacy trail fires n={len(L)} net={sum(t['net'] for t in L):.2f}: activate bp median={st.median(x[0] for x in geo):.0f} (n={len(geo)}), giveback median={st.median(x[1] for x in geo):.2f}, realized gross bp median={st.median(x[2] for x in geo):.0f}")
# how many trips had a trail configured and reached +activate but were not banked by the trail? use run peak excursion
runs={r['id']:r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
reached=0; banked_by_other=collections.Counter()
for t in A6:
    r=runs.get(str(t['final_run']))
    if not r: continue
    try: pk=float(r['peak_pnl_usd'])-float(r['peak_realized_usd']); cond=json.loads(r['stop_conditions_json'] or '{}')
    except Exception: continue
    act=(cond.get('trail') or {}).get('activate_usd')
    if act and pk>=act: reached+=1; banked_by_other[t['mech']]+=1
print(f"    trips whose run peak excursion reached the trail activate: {reached}; ended by: {banked_by_other.most_common()}")
# (f) ratchet fill shortfall vs its own floor: floor = exit_fee + 0.5*(peak_exc - exit_fee); exit gross (position-scoped) = total - peak_realized? use trip gross vs floor
sf=[]
for t in A6:
    if t['mech']!='ratchet' or not t['sm']: continue
    sm=t['sm']
    try: pr=float(t['peak_realized_usd'])
    except: continue
    exc=sm['peak']-pr; floor=sm['exit_fee']+0.5*max(0,exc-sm['exit_fee'])
    # position-scoped gross at the fire per the engine: total - base; actual exit gross = trip gross (entry fee not included in gross? gross=pnl+exit_fee, i.e. before both fees?)
    sf.append((floor,(sm['total']-pr),t['gross'],exc))
print(f"(f) ratchet n={len(sf)}: floor median ${st.median(x[0] for x in sf):.3f}; engine total-at-fire minus base median ${st.median(x[1] for x in sf):.3f}; realized trip gross median ${st.median(x[2] for x in sf):.3f}; sum(floor - engine value at fire)=${sum(x[0]-x[1] for x in sf):.2f} (sampling gap below floor); sum(floor - realized gross)=${sum(x[0]-x[2] for x in sf):.2f}; peak exc sum ${sum(x[3] for x in sf):.2f} vs realized gross sum ${sum(x[2] for x in sf):.2f}")
# (h) independent second pass: straight from signals.tsv, agent 6 window exits by coid kind; and ledger cash check
sig=[s for s in csv.DictReader(open('d/signals.tsv'),delimiter='\t') if s['agent_id']=='6']
WIN0='2026-10-05T15:49:00'
allpnl=sum(float(s['pnl']) for s in sig if s['pnl']!='NULL'); allfee=sum(float(s['fee_usd']) for s in sig if s['fee_usd']!='NULL')
print(f"(h) agent6 ALL signals since 09-25: sum pnl={allpnl:.2f} sum fee={allfee:.2f} -> pnl - entry fees? ledger: cash-start={9891.71885956-10000:.2f}")
# pnl field is net of exit fee? check: trips gross=pnl+exit_fee per trips1 -> pnl is after exit fee. ledger = sum(pnl) - sum(entry fees)
ent=sum(float(s['fee_usd']) for s in sig if s['side'] in('buy','short'))
print(f"    sum(pnl) - sum(entry fees) = {allpnl-ent:.2f}  vs cash delta {9891.71885956-10000:.2f}; window trips net sum={sum(t['net'] for t in A6):.2f}; pre-window = {allpnl-ent-sum(t['net'] for t in A6):.2f} (prior report: -81.08)")
# by exit kind straight from signals (exit legs in window), compare with trip-level mechanism totals
k=collections.defaultdict(lambda:[0,0.0,0.0])
for s in sig:
    if s['side'] in('sell','cover') and s['created_at']>=WIN0:
        kind='flatten' if 'flatten' in (s['client_order_id'] or '') else 'arm' if ':arm:' in (s['client_order_id'] or '') else 'cyc' if ':cyc:' in (s['client_order_id'] or '') else 'NULL'
        k[kind][0]+=1; k[kind][1]+=float(s['pnl']); k[kind][2]+=float(s['fee_usd'])
print('    exit LEGS in window by coid kind (n, sum pnl after exit fee, exit fees):',{a:(b[0],round(b[1],2),round(b[2],2)) for a,b in k.items()})
print('    trips: mech totals sum',round(sum(t['net'] for t in A6),2),'; flatten trips',round(sum(t['net'] for t in A6 if t['final_kind']=='flatten'),2),'n',sum(1 for t in A6 if t['final_kind']=='flatten'))
