import pickle, collections, datetime as dt, statistics as st
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
trips=pickle.load(open('b_trips.pkl','rb')); ev=pickle.load(open('b_events.pkl','rb'))
byrun=collections.defaultdict(list)
for e in ev: byrun[e[1]].append(e)
W=[t for t in trips if t['mech']=='sltp_watcher_failsafe']
print('watcher fail-safe closes n=',len(W),'net',round(sum(t['net'] for t in W),2))
summary=collections.Counter(); gaps=[]
for t in W:
    rid=int(t['final_run']); E=byrun[rid]; t1=T(t['t1'])
    dec=[e for e in E if e[3]=='decision' and -1800<=(T(e[4])-t1).total_seconds()<=0]
    nv=[e for e in E if e[3]=='no_verdict' and -1800<=(T(e[4])-t1).total_seconds()<=0]
    last=dec[-1][5] if dec else None
    gap=None if not dec else (t1-T(dec[-1][4])).total_seconds()/60
    after=[e for e in E if e[3]=='decision' and 0<(T(e[4])-t1).total_seconds()<=600]
    rs_after=[e[5]['reason'] for e in E if e[3]=='run_status' and e[5].get('to')=='stopping' and 0<=(T(e[4])-t1).total_seconds()<=7200]
    key=(last.get('action') if last else 'no decision in 30m', last.get('decided_by') if last else None, last.get('fallback_reason') if last else None)
    summary[key]+=1; gaps.append(gap if gap is not None else 99)
    print(f" {t['symbol']:9s} net={t['net']:6.2f} hold={t['hold_min']:5.0f}m lossBp={t['gross']/t['entry_notional']*1e4:5.0f} last decision {gap and round(gap,1)}m before close: {key}; decisions in prior 30m={len(dec)} no_verdict={len(nv)}; next decision after close={[(a[5].get('action'),a[5].get('decided_by')) for a in after[:1]]}; run ended={rs_after[:1]} ({t['run_status_reason']})")
print('\nlast-decision state before watcher close:',summary.most_common())
print('minutes since last decision median',round(st.median(gaps),1))
