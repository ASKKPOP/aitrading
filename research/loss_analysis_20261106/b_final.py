import pickle, csv, collections, statistics as st, datetime as dt, json
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
trips=pickle.load(open('b_trips.pkl','rb')); A6=[t for t in trips if t['agent']=='6']
ev=pickle.load(open('b_events.pkl','rb')); byrun=collections.defaultdict(list)
for e in ev: byrun[e[1]].append(e)
# (i) no-size bucket
ns=[t for t in A6 if t['clamp']]; sz=[t for t in A6 if not t['clamp']]
def S(tr): return (len(tr),round(sum(t['net'] for t in tr),2),round(sum(t['gross'] for t in tr),2),round(sum(t['fees'] for t in tr),2))
w=min(ns,key=lambda t:t['net']); b=max(ns,key=lambda t:t['net'])
print('(i) clamp-sized (desk gave no size):',S(ns),'ex-worst',w['symbol'],round(w['net'],2),S([t for t in ns if t is not w]),'ex-best',b['symbol'],round(b['net'],2),S([t for t in ns if t is not b]))
print('    desk-sized:',S(sz),'medNotl',round(st.median(t['entry_notional'] for t in sz),1))
k=18.7/93.75
print(f"    if clamp-sized trips had been sized at the desk's own median $18.7 (x{k:.3f}): net={sum(t['net']*k for t in ns):.2f} (vs {sum(t['net'] for t in ns):.2f}) -> +{sum(t['net'] for t in ns)*(k-1)*-1:.2f} on this tape; ex-worst +{sum(t['net'] for t in ns if t is not w)*(k-1)*-1:.2f}")
print(f"    if clamp-sized trips had NOT been taken: +{-sum(t['net'] for t in ns):.2f}; ex-best trip +{-sum(t['net'] for t in ns if t is not b):.2f}; fees alone {sum(t['fees'] for t in ns):.2f}")
# (ii) MCD
for t in trips:
    if t['agent']=='60' and t['symbol']=='MCD' and t['mech']=='ratchet':
        print('(ii) MCD',round(t['net'],2),'hold',round(t['hold_min']),'sm',t['sm'],'peak_realized',t['peak_realized_usd'],'legs',[(s['side'],s['_kind'],round(s['_notional'],1),s['pnl']) for s in t['sigs']],'adapts',t['adapts'])
# (iii) watcher split
W=[t for t in A6 if t['mech']=='sltp_watcher_failsafe']; tp=[t for t in W if t['gross']>0]; sl=[t for t in W if t['gross']<=0]
print('(iii) watcher TP closes',S(tp),[t['symbol'] for t in tp],'; watcher SL closes',S(sl),'median lossBp',round(st.median(t['gross']/t['entry_notional']*1e4 for t in sl)),'median hold',round(st.median(t['hold_min'] for t in sl)),'ex-worst',S([t for t in sl if t is not min(sl,key=lambda t:t['net'])]))
# big-loser table ex-worst for the 25
big=[t for t in A6 if t['net']<-1]; print('    25 big losers ex-worst (SUI -3.25):',round(sum(t['net'] for t in big)+3.25,2))
# (iv) conviction_collapse agent 6: convictions in the last 3 decisions before exit
cc=[t for t in A6 if t['mech']=='conviction_collapse']
for t in cc:
    rid=int(t['final_run']); d=[e[5] for e in byrun[rid] if e[3]=='decision' and t['t0']<=e[4]<=t['t1']]
    print(f"(iv) {t['symbol']:9s} net={t['net']:6.2f} hold={t['hold_min']:5.0f}m lossBp={t['gross']/t['entry_notional']*1e4:5.0f} convictions while holding={[x.get('conviction') for x in d][-4:]} actions={[x.get('action') for x in d][-4:]}")
# ratchet per-trip $: median net, mean net
rat=[t for t in A6 if t['mech']=='ratchet']; print('ratchet median net $%.3f mean $%.3f; trips needed to pay one -$1.40 stop-out: %.0f'%(st.median(t['net'] for t in rat),st.mean(t['net'] for t in rat),1.40/st.mean(t['net'] for t in rat)))
# short vs long by mech
print('dir split:',collections.Counter((t['dir'],t['mech']) for t in A6).most_common(8))
# weekly net by mech for drift check (largest week)
wk=collections.defaultdict(float)
for t in A6: wk[(T(t['t0']).isocalendar()[1])]+=t['net']
print('net by ISO week:',{k:round(v,2) for k,v in sorted(wk.items())})
