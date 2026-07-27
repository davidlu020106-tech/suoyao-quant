"""回测TOP 10预测结果"""
import requests, json
from datetime import datetime, timezone

now=datetime.now(timezone.utc)
print('当前:', now.strftime('%m-%d %H:%M UTC'))
print('预测: 07-17 13:13 UTC')
print('过去: '+str(round((now.timestamp()-datetime(2026,7,17,13,13,tzinfo=timezone.utc).timestamp())/3600,1))+'小时')
print()

coins=[
    ('POR',0.101,0.091,'SELL',10),
    ('EDGE',0.408,0.388,'SELL',20),
    ('BCH',223.7,219.2,'SELL',50),
    ('ADA',0.160,0.157,'SELL',50),
    ('PI',0.078,0.074,'SELL',20),
    ('ALLO',0.401,0.441,'BUY',10),
    ('LIT',2.280,2.326,'BUY',50),
    ('ZEC',530.7,567.9,'BUY',20),
    ('HYPE',62.47,65.59,'BUY',20),
    ('APE',0.147,0.154,'BUY',20),
]

t=requests.get('https://www.okx.com/api/v5/market/tickers?instType=SPOT',
    headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
price={}
for x in t.get('data',[]):
    if x['instId'].endswith('-USDT'):
        b=x['instId'].replace('-USDT','')
        price[b]={'last':float(x.get('last',0)or 0),'high24':float(x.get('high24h',0)or 0),'low24':float(x.get('low24h',0)or 0)}

print('回测: 13:13预测 -> 现在')
print('='*110)
print('  Dir  Coin     Entry    TP1      Now     Chg%    Max%    Min%    HitTP1')
print('-'*110)

hit=0
for base,entry,tp1,dir_,lev in coins:
    p=price.get(base,{})
    cur=p.get('last',0)
    h24=p.get('high24',0)
    l24=p.get('low24',0)
    if cur==0: continue
    
    chg=(cur-entry)/entry*100
    if dir_=='SELL':
        hit_tp1=l24<=tp1
        max_chg=(l24-entry)/entry*100
    else:
        hit_tp1=h24>=tp1
        max_chg=(h24-entry)/entry*100
    
    h_str='YES' if hit_tp1 else 'no'
    if hit_tp1: hit+=1
    
    print('  {:4s} {:<6s} ${:<7.3f} ${:<7.3f} ${:<7.3f} {:>+6.2f}% {:>+7.2f}% {:>7.2f}% {:>5s}'.format(
        dir_,base,entry,tp1,cur,chg,max_chg,(h24-entry)/entry*100 if dir_=='SELL' else (l24-entry)/entry*100,h_str))

print('-'*110)
print('到TP1: '+str(hit)+'/'+str(len(coins)))
