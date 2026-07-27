"""Scored ranking with vol filter"""
import json,requests
with open('quant_factors/continuous_ranking.json','r',encoding='utf-8') as f:data=json.load(f)
t=requests.get('https://www.okx.com/api/v5/market/tickers?instType=SPOT',headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
vol={x['instId'].replace('-USDT',''):float(x.get('volCcy24h','0')or 0) for x in t['data'] if x['instId'].endswith('-USDT')}
for r in data:
    v=vol.get(r['base'],0);vs=min(30,v/1e6*5)
    h=r.get('tp1_hit',0);tv=r.get('tp1_total',1);ts=min(20,h/max(tv,1)*20)
    r['sc']=abs(r['signal'])*50+vs+ts
data.sort(key=lambda x:x['sc'],reverse=True)
print('='*120)
print('  RANKING (vol>=500K) - Latest Data')
print('='*120)
print('  #  Dir Coin    Vol     Entry      TP1        Lev KOL     Scor RSI TP1h')
print('-'*120)
for i,r in enumerate(data,1):
    v=vol.get(r['base'],0)
    if v<500000: continue
    es='{:.4f}'.format(r['entry']) if r['entry']<10 else '{:.0f}'.format(r['entry'])
    ts='{:.4f}'.format(r['tp1']) if r['entry']<10 else '{:.0f}'.format(r['tp1'])
    h=r.get('tp1_hit',0);tv=r.get('tp1_total',0)
    print('  {:2d}  {:<4s} {:<6s} \${:<6.0f}K ${:<10s} ${:<10s} {:>4d}x {:>6s} {:>5.1f} {:>5.1f} {:>2d}/{:>2d}'.format(
        i,r['dir'],r['base'],v/1000,es,ts,r['lev'],str(r['kol_bull'])+'/'+str(r['kol_bear']),r['sc'],r['rsi'],h,tv))
