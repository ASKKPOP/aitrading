# Section A: the 25 trips net < -$1 (agent 6) — what ended each, peak, drawdown, stop geometry.
import pickle, collections, statistics as st, json, datetime as dt
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
trips=pickle.load(open('b_trips.pkl','rb')); ev=pickle.load(open('b_events.pkl','rb'))
byrun=collections.defaultdict(list)
for e in ev: byrun[e[1]].append(e)
A6=[t for t in trips if t['agent']=='6']
big=sorted([t for t in A6 if t['net']<-1],key=lambda t:t['net']); rest=[t for t in A6 if t['net']>=-1]
print(f"big n={len(big)} net={sum(t['net'] for t in big):.2f} gross={sum(t['gross'] for t in big):.2f} fees={sum(t['fees'] for t in big):.2f} | rest n={len(rest)} net={sum(t['net'] for t in rest):.2f} gross={sum(t['gross'] for t in rest):.2f} fees={sum(t['fees'] for t in rest):.2f}")
print('big by mech:',{m:(sum(1 for t in big if t['mech']==m),round(sum(t['net'] for t in big if t['mech']==m),2)) for m in set(t['mech'] for t in big)})
print('\nsym dir  net   gross  notl  hold  mech                  eqN  peak$  trough$  peakBp lossBp  stop(last stop_after vs entry)  armed?(peak>=arm_est) adds exits  rs_reason')
rows=[]
for t in big:
    rid=int(t['final_run']) if t['final_run']!='NULL' else None
    # last stop level before exit from bracket_reanchor/stop_cap
    stop_px=None; entry_px=t.get('entry_px')
    if rid:
        for e in byrun[rid]:
            if e[3] in ('bracket_reanchor','stop_cap') and t['t0']<=e[4]<=t['t1']: stop_px=e[5].get('stop_after')
    avg_entry=t['entry_notional']/sum(float(s['quantity']) for s in t['sigs'] if not s['_isexit'])
    sgn=-1 if t['dir']=='short' else 1
    stop_bp=None if not stop_px else sgn*(stop_px/avg_entry-1)*1e4
    loss_bp=t['gross']/t['entry_notional']*1e4
    peak=t.get('eq_peak'); arm_est=t['entry_notional']*0.00045*2*1.78
    pk_bp=None if peak is None else (peak+t['entry_fee'])/t['entry_notional']*1e4  # add back entry fee: equity base already includes it
    rows.append((t['symbol'],t['dir'],t['net'],t['gross'],t['entry_notional'],t['hold_min'],t['mech'],t.get('eq_n',0),peak,t.get('eq_trough'),pk_bp,loss_bp,stop_bp,(None if peak is None else peak+t['entry_fee']>=arm_est),t['adds'],t['n_exit_legs'],t.get('rs_reason')))
    print(f"{t['symbol'][:8]:8s} {t['dir'][:5]:5s} {t['net']:6.2f} {t['gross']:6.2f} {t['entry_notional']:6.1f} {t['hold_min']:6.0f} {t['mech'][:22]:22s} {t.get('eq_n',0):4d} {('%.2f'%peak) if peak is not None else '  na':>6s} {('%.2f'%t.get('eq_trough',0)) if peak is not None else '  na':>7s} {('%.0f'%pk_bp) if pk_bp is not None else 'na':>6s} {loss_bp:6.0f}  {('%.0f'%stop_bp) if stop_bp is not None else 'na':>6s}bp  {str(None if peak is None else peak+t['entry_fee']>=arm_est):5s} {t['adds']:3d} {t['n_exit_legs']:3d} {t.get('rs_reason')}")
# summary stats
pk=[r[10] for r in rows if r[10] is not None]; lb=[r[11] for r in rows]; sb=[r[12] for r in rows if r[12] is not None]
print(f"\nbig losers: median loss {st.median(lb):.0f}bp (mean {st.mean(lb):.0f}); median peak excursion {st.median(pk):.0f}bp (n={len(pk)}); peaks>=arm_est: {sum(1 for r in rows if r[13])}/{len(rows)}; median authored stop distance {st.median(sb):.0f}bp (n={len(sb)})")
print('watcher-failsafe losers: loss bp vs stop bp:',[(r[0],round(r[11]),None if r[12] is None else round(r[12])) for r in rows if r[6]=='sltp_watcher_failsafe'])
# how many big losers had positive peak but were not banked by the ratchet
pos_peak=[r for r in rows if r[10] is not None and r[10]>0]
print('big losers with a positive equity peak:',len(pos_peak),'of',len(pk),'; peaks bp:',[round(r[10]) for r in pos_peak])
# the ratchet's own 377 fires: realized vs peak; fires below 2x RT fee
rat=[t for t in A6 if t['mech']=='ratchet']
below2=[t for t in rat if t['gross']<2*t['fees']]
print(f"\nratchet fires n={len(rat)} net={sum(t['net'] for t in rat):.2f}; gross<2xRTfee: n={len(below2)} net={sum(t['net'] for t in below2):.2f} gross={sum(t['gross'] for t in below2):.2f}; gross<=0: n={sum(1 for t in rat if t['gross']<=0)} net={sum(t['net'] for t in rat if t['gross']<=0):.2f}; net<=0: n={sum(1 for t in rat if t['net']<=0)} sum={sum(t['net'] for t in rat if t['net']<=0):.2f}")
arm_fee=[(t['sm']['arm'],t['sm']['exit_fee'],t['fees'],t['gross'],t['sm']['peak'],t['sm']['total'],t['peak_realized_usd']) for t in rat if t['sm']]
print('arm/exit_fee ratio distinct:',collections.Counter(round(a/b,3) for a,b,*_ in arm_fee if b).most_common(5))
print('arm vs actual RT fee (entry+exit) ratio median:',round(st.median(a/f for a,b,f,*_ in arm_fee if f),3),'; arm<RTfee count',sum(1 for a,b,f,*_ in arm_fee if a<f))
# excursion at fire vs arm: peak - peak_realized
exc=[]
for a,b,f,g,pk_,tot,pr in arm_fee:
    try: pr=float(pr)
    except: continue
    exc.append(((pk_-pr)/a, (tot-pr)/a, g))
print('peak excursion / arm: median %.2f, <1.0: %d, >=2: %d of %d'%(st.median(x[0] for x in exc),sum(1 for x in exc if x[0]<1),sum(1 for x in exc if x[0]>=2),len(exc)))
print('give-back (peak - exit gross)/peak median: %.2f'%st.median((x[0]-x[1])/x[0] for x in exc if x[0]>0))
print('ratchet gross/entry_notional bp: median %.1f mean %.1f; hold median %.1fm'%(st.median(t['gross']/t['entry_notional']*1e4 for t in rat),st.mean(t['gross']/t['entry_notional']*1e4 for t in rat),st.median(t['hold_min'] for t in rat)))
# zero-hold trips
zh=[t for t in trips if t['hold_min']<2]
print('\nzero-hold (<2min) trips:',[(t['agent'],t['symbol'],t['mech'],round(t['hold_min'],2),round(t['net'],3)) for t in zh])
print('zero-hold total net',round(sum(t['net'] for t in zh),2),'n',len(zh))
