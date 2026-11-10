"""ratchet_arm_replay.py — counterfactual of the breakeven-ratchet arm multiple (read-only).

Added by the 2026-11-10 daily sweep. Replays every run whose exit was a
`stop_mechanism: breakeven_ratchet` fire, from its entry, on Hyperliquid 1m
candles, under arm = k x the arm the run actually used (k = 1 must reproduce
the real exits: CHECK THE CALIBRATION LINE before reading any delta), with the
desk's own bracket (bracket_reanchor stop/tp), the desk's trail
(order_plan.trail) and RATCHET_LOCK_FRAC 0.5. k=None = no ratchet.

Hyperliquid keeps only ~5000 1m candles (~3.5 days): run it on the sweep's own
day, every day, and append the k-table to the day's note. Older windows need
interval 15m and calibrate far worse (Oct: sim -3.69 vs actual 13.40).

Usage (prod, read-only, inside the worker):
  cat research/ratchet_arm_replay.py | ssh ... "docker exec -i -w /app/service/server \
      sooppiy-worker python - 2026-11-09T17:28:00Z 2026-11-10T17:28:00Z 6"
"""
import os,json,time,sys,urllib.request
from datetime import datetime,timezone
from sqlalchemy import create_engine, text
e=create_engine(os.environ['DATABASE_URL'])
A,B=sys.argv[1],sys.argv[2]; AG=int(sys.argv[3]) if len(sys.argv)>3 else 6
def ms(s): return int(datetime.strptime(s,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()*1000)
def candles(coin,a,b):
    req=json.dumps({"type":"candleSnapshot","req":{"coin":coin,"interval":"1m","startTime":a,"endTime":b}}).encode()
    for att in range(6):
        try:
            r=urllib.request.urlopen(urllib.request.Request("https://api.hyperliquid.xyz/info",data=req,headers={"Content-Type":"application/json"}),timeout=20); return json.loads(r.read())
        except Exception: time.sleep(3*(att+1))
    return None
now=int(time.time()*1000); KS=[1,2,3,5,10,None]
res=[]; skipped=0
with e.connect() as c:
    rids=[r[0] for r in c.execute(text("select distinct e.run_id from run_events e join trading_runs t on t.id=e.run_id where t.agent_id=:g and t.market='crypto' and e.event_type='stop_mechanism' and e.payload like '%breakeven_ratchet%' and e.ts>=:a and e.ts<:b"),dict(a=A,b=B,g=AG))]
    for rid in rids:
        sym=c.execute(text("select symbol from trading_runs where id=:r"),dict(r=rid)).scalar()
        ev=c.execute(text("select ts,event_type,payload from run_events where run_id=:r and event_type in ('trade','bracket_reanchor','order_plan','stop_mechanism') order by seq"),dict(r=rid)).fetchall()
        tr=[(ts,json.loads(p)) for ts,t,p in ev if t=='trade']
        br=[json.loads(p) for ts,t,p in ev if t=='bracket_reanchor']; pl=[json.loads(p) for ts,t,p in ev if t=='order_plan']
        sm=[json.loads(p) for ts,t,p in ev if t=='stop_mechanism']
        if len(tr)!=2 or not br or not sm: skipped+=1; continue
        (t0,o),(t1,x)=tr; sg=-1 if o['side']=='short' else (1 if o['side']=='buy' else 0)
        if not sg: skipped+=1; continue
        q=float(o['quantity']); ep=float(o['price']); f_in=float(o['fee_usd']); f_out=float(x['fee_usd'])
        actual=sg*(float(x['price'])-ep)*q-f_in-f_out
        arm1=float(sm[-1].get('arm') or 0)
        stop=br[-1].get('stop_after'); tp=br[-1].get('tp_after')
        trail=(pl[-1].get('trail') if pl else None) or {}
        act=float(trail.get('activate_usd') or 0); give=float(trail.get('giveback_frac') or 0)
        hz=pl[-1].get('horizon_until') if pl else None
        end=min(now, ms(hz) if hz else now, ms(t0)+48*3600*1000)
        cs=candles(sym.replace('USDT',''), ms(t0)+60000, end)
        if not cs: skipped+=1; continue
        row={'rid':rid,'sym':sym,'actual':actual,'notional':q*ep}
        for k in KS:
            arm = None if k is None else arm1*k
            peak=-1e9; out=None
            for kk in cs:
                h,l,cl=float(kk['h']),float(kk['l']),float(kk['c'])
                if stop and ((sg<0 and h>=stop) or (sg>0 and l<=stop)): out=sg*(stop-ep)*q-f_in-f_out; break
                if tp and ((sg<0 and l<=tp) or (sg>0 and h>=tp)): out=sg*(tp-ep)*q-f_in-f_out; break
                g=sg*(cl-ep)*q   # gross position pnl
                peak=max(peak,g); rt=f_in+f_out
                if arm is not None and peak>=arm and g<=rt+0.5*max(0.0,peak-rt): out=g-rt; break
                if act>0 and 0<give<1 and peak-f_in>=act and g-f_in<=(peak-f_in)*(1-give)+f_out: out=g-rt; break
            if out is None: out=sg*(float(cs[-1]['c'])-ep)*q-f_in-f_out
            row[k]=out
        res.append(row); time.sleep(0.7)
print('window',A,B,'agent',AG,'n',len(res),'skipped',skipped)
if res:
    tot={k:sum(r[k] for r in res) for k in KS}; act=sum(r['actual'] for r in res)
    print('actual',round(act,2), {str(k):round(v,2) for k,v in tot.items()})
    for k in KS:
        d=sorted([r[k]-r['actual'] for r in res],key=abs)
        print(' k',k,'delta',round(tot[k]-act,2),'ex_largest',round(tot[k]-act-d[-1],2),'wins',sum(1 for r in res if r[k]>0),'/',len(res), 'avg_notional',round(sum(r['notional'] for r in res)/len(res),1))
    cal=[abs(r[1]-r['actual']) for r in res]; print('calibration k=1 |sim-actual| median',round(sorted(cal)[len(cal)//2],4),'max',round(max(cal),3), 'sum sim',round(tot[1],2),'vs actual',round(act,2))
