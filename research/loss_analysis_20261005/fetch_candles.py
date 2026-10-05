import json,urllib.request,time,pickle,calendar
trips,*_=pickle.load(open('trips.pkl','rb'))
syms=sorted(set(t['symbol'] for t in trips if t['agent']=='6'))
def post(body):
    for a in range(4):
        try:
            r=urllib.request.Request('https://api.hyperliquid.xyz/info',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            return json.loads(urllib.request.urlopen(r,timeout=30).read())
        except Exception as e:
            time.sleep(1.5*(a+1)); err=e
    raise err
start=calendar.timegm(time.strptime('2026-09-04','%Y-%m-%d'))*1000
end=int(time.time()*1000)
out={}
for s in syms:
    base=s[:-4] if s.endswith('USDT') else s
    got=None
    for coin in (base,'k'+base):
        try:
            d=post({"type":"candleSnapshot","req":{"coin":coin,"interval":"15m","startTime":start,"endTime":end}})
        except Exception as e: d=[]
        if d: got=(coin,d); break
    if not got: print('MISSING',s); continue
    out[s]=dict(coin=got[0],c=[(x['t'],float(x['o']),float(x['h']),float(x['l']),float(x['c'])) for x in got[1]])
    time.sleep(0.25)
pickle.dump(out,open('candles15.pkl','wb'))
print(len(out),'symbols', min(len(v['c']) for v in out.values()), max(len(v['c']) for v in out.values()))
