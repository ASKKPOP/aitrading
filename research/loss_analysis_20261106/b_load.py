# Agent B loader: parse events.tsv once into a compact pickle (window 10-05 15:49 -> 11-06 20:30, all three agents).
import csv, json, pickle, collections, sys
csv.field_size_limit(10**9)
WIN0='2026-10-05T15:49:00'; WIN1='2026-11-06T20:30:00'
KEEP_FULL={'stop_mechanism','run_status','adapt','gate_skip','size_clamp','armed_exit','trade','equity','order_plan',
           'stop_cap','target_cap','alert','mark_refresh','bracket_reanchor','young_dump_flag','armed_exit_rejected',
           'order_intent','no_verdict','thesis_review','entry_zone_touch'}
DECISION_KEYS=('cycle','action','confidence','decided_by','conviction','fallback_reason','size_scale','gate_source')
ev=[]; bad=0; n=0
for r in csv.DictReader(open('d/events.tsv'),delimiter='\t',quoting=csv.QUOTE_NONE):
    ts=r['ts']
    if ts<'2026-10-04T00:00:00': continue   # a day of pre-window for run context
    et=r['event_type']
    if et in KEEP_FULL:
        try: p=json.loads(r['payload'])
        except Exception: bad+=1; p={'__raw':r['payload'][:300]}
    elif et in ('decision','order_discussion'):
        try: q=json.loads(r['payload'])
        except Exception: bad+=1; q={}
        if et=='decision': p={k:q.get(k) for k in DECISION_KEYS if k in q}; p['llm_source']=(q.get('llm') or {}).get('source')
        else: p={k:q.get(k) for k in ('proposed','panel_verdict','veto_overridden','final') if k in q}
    else:
        p=None
    ev.append((r['agent_id'],int(r['run_id']),int(r['seq']),et,ts,p)); n+=1
ev.sort(key=lambda e:(e[4],e[1],e[2]))
pickle.dump(ev,open('b_events.pkl','wb'))
print('events kept',n,'badjson',bad)
c=collections.Counter(e[3] for e in ev if WIN0<=e[4]<=WIN1); print(c.most_common())
