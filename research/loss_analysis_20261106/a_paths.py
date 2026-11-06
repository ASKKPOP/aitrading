# Agent A: entry path x trip outcome; report keyword tally; AI-up vs AI-down days; rule-fallback decisions never trade check; agent 60 reasons.
import pickle,collections,re,datetime as dt,statistics as st,json
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
rows=pickle.load(open('a_entries.pkl','rb')); trips=pickle.load(open('trips1.pkl','rb')); D=pickle.load(open('a_events.pkl','rb')); ev=D['ev']
WIN0=T('2026-10-05T15:49:00')
ent={(r['agent'],r['sym'],r['ts']):r for r in rows}
W=[t for t in trips if t['agent'] in('6','60') and 'net' in t and T(t['t0'])>=WIN0]
for t in W:
    r=ent.get((t['agent'],t['symbol'],t['t0'])); t['e']=r
print('trips with entry row:',sum(1 for t in W if t['e']),'/',len(W))
def summ(name,tr):
    if not tr: print(f"{name:52s} n=0"); return
    n=len(tr); net=sum(t['net'] for t in tr); gross=sum(t['gross'] for t in tr); fees=sum(t['entry_fee']+t['exit_fee'] for t in tr)
    big=max(tr,key=lambda t:abs(t['net']))
    print(f"{name:52s} n={n:3d} net={net:7.2f} gross={gross:7.2f} fees={fees:5.2f} WR={sum(1 for t in tr if t['net']>0)/n*100:3.0f}% medHold={st.median(t['hold_min'] for t in tr):5.0f}m ex-largest({big['symbol']} {big['net']:+.2f}) net={net-big['net']:7.2f} gross={gross-big['gross']:7.2f}")
for ag in ('6','60'):
    A=[t for t in W if t['agent']==ag and t['e']]
    print(f"\n===== agent {ag} trips by ENTRY PATH")
    summ('all',A)
    def path(t):
        e=t['e']
        if e['veto']: return 'panel hold OVERRIDDEN (pre-fix 10-05)'
        if e['od_proposed'] is None: return 'no order_discussion found (full route?)'
        if e['od_proposed']!=e['od_final']: return f"panel REVERSED light proposal {e['od_proposed']}->{e['od_final']}"
        return f"panel confirmed light proposal {e['od_proposed']}"
    for k,g in sorted(collections.defaultdict(list,{p:[t for t in A if path(t)==p] for p in set(path(t) for t in A)}).items()): summ('  '+k,g)
    print(' -- by chair action on the final decision')
    for k in sorted(set(t['e']['chair'] for t in A)): summ('  chair='+k,[t for t in A if t['e']['chair']==k])
    print(' -- by route of the decision');
    for k in sorted(set(str(t['e']['route']) for t in A)): summ('  route='+k,[t for t in A if str(t['e']['route'])==k])
    print(' -- by null_size_cap clamp');
    for k in (True,False): summ(f'  clamped={k}',[t for t in A if (len(t['e']['clamp'])>0)==k])
    print(' -- by direction'); 
    for k in ('short','long'): summ('  '+k,[t for t in A if t['dir']==k])
    print(' -- by confidence bucket of final decision')
    for lo,hi in ((0,0.55),(0.55,0.6),(0.6,0.65),(0.65,0.7),(0.7,1.01)): summ(f'  conf [{lo},{hi})',[t for t in A if t['e']['conf'] is not None and lo<=t['e']['conf']<hi])
if True:
    A=[t for t in W if t['agent']=='6' and t['e']]
    # AI-up vs AI-down days: define per day by share of decided_by ai among agent-6 decisions
    dec=[e for e in ev if e['agent']=='6' and e['et']=='decision' and e['ts']>='2026-10-05T15:49']
    day=collections.defaultdict(collections.Counter)
    for e in dec: day[e['ts'][:10]][e['p'].get('decided_by')]+=1
    up={d:(c['ai']/sum(c.values())) for d,c in day.items()}
    print('\n -- agent 6 by LLM availability of the entry day (share of decisions decided_by ai)')
    summ('  AI-up day (ai share>=0.5)',[t for t in A if up.get(t['t0'][:10],0)>=0.5]); summ('  AI-down day (ai share<0.5)',[t for t in A if up.get(t['t0'][:10],0)<0.5])
    print('  up-days:',sum(1 for v in up.values() if v>=0.5),'down-days:',sum(1 for v in up.values() if v<0.5))
    # keyword tally in final decision report, shorts vs longs
    kws=['fear','greed','fgi','rsi','overbought','oversold','resistance','support','downtrend','uptrend','below','above','bearish','bullish','long/short','crowded','squeeze','momentum','200','golden','death','breach','invalidat','pullback','liquidation','funding']
    print('\n -- keyword share in the FINAL decision report, agent-6 entries (short n=%d, long n=%d)'%(sum(1 for t in A if t['dir']=='short'),sum(1 for t in A if t['dir']=='long')))
    for k in kws:
        s=[t for t in A if t['dir']=='short']; l=[t for t in A if t['dir']=='long']
        fs=sum(1 for t in s if k in (t['e']['report'] or '').lower())/len(s); fl=sum(1 for t in l if k in (t['e']['report'] or '').lower())/len(l)
        print(f"   {k:12s} short {fs:4.2f}  long {fl:4.2f}")
    # sample short reports for 'panel REVERSED buy->sell'
    print('\n -- 8 sample reports where the panel turned a light BUY into a SELL (short):')
    for t in [t for t in A if t['e']['od_proposed']=='buy' and t['e']['od_final']=='sell'][:8]: print('   ',t['t0'][:16],t['symbol'],f"net={t['net']:+.2f}",'|',t['e']['report'][:200])
    print('\n -- 6 sample reports for confirmed sell->sell:')
    for t in [t for t in A if t['e']['od_proposed']=='sell' and t['e']['od_final']=='sell'][:6]: print('   ',t['t0'][:16],t['symbol'],f"net={t['net']:+.2f}",'|',t['e']['report'][:200])
    # F&G mentions: extract FGI numbers
    fg=[int(m.group(1)) for t in A for m in [re.search(r'(?:FGI|fear.greed(?: index)?)\D{0,12}(\d{2})',t['e']['report'] or '',re.I)] if m]
    print('\n F&G values quoted in entry reports: n=%d'%len(fg), 'median',st.median(fg) if fg else None, 'min',min(fg) if fg else None,'max',max(fg) if fg else None)
    # rule-fallback decisions: did ANY trade follow one within the same cycle?
    byrun=collections.defaultdict(list)
    for e in ev: byrun[e['run']].append(e)
    rule=[e for e in dec if e['p'].get('decided_by')=='rule']
    acts=collections.Counter(e['p'].get('action') for e in rule); ch=collections.Counter(str(e['p'].get('chair'))[:40] for e in rule)
    traded=0
    for e in rule:
        c=e['p'].get('cycle')
        if any(x['et']=='trade' and re.search(rf':cyc:{c}$',x['p'].get('client_order_id') or '') for x in byrun[e['run']]): traded+=1
    print('\n rule-fallback decisions (agent 6, window):',len(rule),'actions',dict(acts),'chair',dict(ch.most_common(5)),'-> trades in that cycle:',traded)
    # 'ai' decisions with chair amended action -> action distribution & trades
    aa=[e for e in dec if e['p'].get('decided_by')=='ai' and isinstance(e['p'].get('chair'),dict) and 'action' in e['p']['chair'].get('amended',[])]
    print(' ai decisions with chair-amended ACTION:',len(aa),'final actions',dict(collections.Counter(e['p'].get('action') for e in aa)))
    # agent 60 entry reasons
    print('\n -- agent 60: entry decision reports (all 30 chair-amended action):')
    B=[t for t in W if t['agent']=='60' and t['e']]
    for t in B[:30]: print('   ',t['t0'][:16],t['symbol'],f"net={t['net']:+.2f} hold={t['hold_min']:.0f}m exit={t.get('exit_kind')}",'|',t['e']['report'][:150])
