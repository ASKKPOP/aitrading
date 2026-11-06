# Agent A loader: parse d/events.tsv (agents 6,60 from 2026-10-01) into a_events.pkl; signals + runs too.
import csv,json,pickle,sys,datetime as dt
csv.field_size_limit(10**9)
def T(s): return dt.datetime.strptime(s[:19],'%Y-%m-%dT%H:%M:%S')
ev=[]
bad=0
with open('d/events.tsv') as f:
    r=csv.reader(f,delimiter='\t',quoting=csv.QUOTE_NONE); next(r)
    for row in r:
        if row[1] not in ('6','60') or row[5]<'2026-10-01': continue
        try: p=json.loads(row[6]) if row[6]!='NULL' else {}
        except Exception: bad+=1; p={'_raw':row[6]}
        ev.append(dict(id=int(row[0]),agent=row[1],run=row[2],seq=int(row[3]) if row[3]!='NULL' else None,et=row[4],ts=row[5],p=p))
print('events',len(ev),'bad json',bad)
sig=[s for s in csv.DictReader(open('d/signals.tsv'),delimiter='\t')]
runs={r['id']:r for r in csv.DictReader(open('d/runs.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE)}
pickle.dump(dict(ev=ev,sig=sig,runs=runs),open('a_events.pkl','wb'))
print('signals',len(sig),'runs',len(runs))
