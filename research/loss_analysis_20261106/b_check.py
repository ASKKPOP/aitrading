# Second independent pass over every figure stated in agentB.md section 1 and the key claims.
import pickle, statistics as st, collections
trips=pickle.load(open('b_trips.pkl','rb')); A6=[t for t in trips if t['agent']=='6']; A60=[t for t in trips if t['agent']=='60']
S=lambda tr:(len(tr),round(sum(t['net'] for t in tr),2),round(sum(t['gross'] for t in tr),2),round(sum(t['fees'] for t in tr),2))
ALG={'ratchet','legacy_trail','sltp_watcher_failsafe','conviction_collapse','adapt_retired','orphan_close(run_id NULL)'}
alg=[t for t in A6 if t['mech'] in ALG]; ai=[t for t in A6 if t['mech'] not in ALG]
print('agent6 all',S(A6)); print('algorithm-closed',S(alg),'(report: 435,-6.27,17.66,23.95)'); print('AI-closed',S(ai),'(report: 33,-20.93,-19.13,1.80)')
assert S(alg)[0]+S(ai)[0]==468 and abs(S(alg)[1]+S(ai)[1]-S(A6)[1])<0.02
W=[t for t in A6 if t['mech']=='sltp_watcher_failsafe']; print('watcher stop side',S([t for t in W if t['gross']<=0]),'tp side',S([t for t in W if t['gross']>0]))
rat=[t for t in A6 if t['mech']=='ratchet']; tr=[t for t in A6 if t['mech']=='legacy_trail']
print('ratchet+trail',S(rat+tr),'(report +32.55 over 393)'); print('ratchet mean net',round(st.mean(t['net'] for t in rat),3),'median',round(st.median(t['net'] for t in rat),3))
print('ratchet gross<2xfee',S([t for t in rat if t['gross']<2*t['fees']]),'net<=0',S([t for t in rat if t['net']<=0]),'gross<=0',S([t for t in rat if t['gross']<=0]))
big=[t for t in A6 if t['net']<-1]; print('big losers',S(big),'ex-worst',round(sum(t['net'] for t in big)-min(t['net'] for t in big),2),'rest',S([t for t in A6 if t['net']>=-1]))
print('big by mech',collections.Counter(t['mech'] for t in big))
cl=[t for t in A6 if t['clamp']]; un=[t for t in A6 if not t['clamp']]; print('clamped',S(cl),'medNotl',round(st.median(t['entry_notional'] for t in cl),1),'unclamped',S(un),'medNotl',round(st.median(t['entry_notional'] for t in un),1))
print('clamp resize x0.199 ->',round(sum(t['net']*18.7/93.75 for t in cl),2),'delta',round(sum(t['net'] for t in cl)*(1-18.7/93.75)*-1,2))
zh=[t for t in trips if t['hold_min']<2]; print('zero-hold',S(zh))
print('agent60',S(A60),'ex-MCD',round(sum(t['net'] for t in A60)+2.0,2))
cc6=[t for t in A6 if t['mech']=='conviction_collapse']; print('cc agent6',S(cc6),'cc agent60',S([t for t in A60 if t['mech']=='conviction_collapse']))
print('notional sum',round(sum(t['entry_notional'] for t in A6)),'net bp/trip',round(sum(t['net'] for t in A6)/sum(t['entry_notional'] for t in A6)*1e4,1),'gross bp',round(sum(t['gross'] for t in A6)/sum(t['entry_notional'] for t in A6)*1e4,1))
print('shorts: ratchet',sum(1 for t in rat if t['dir']=='short'),'watcher',sum(1 for t in W if t['dir']=='short'))
