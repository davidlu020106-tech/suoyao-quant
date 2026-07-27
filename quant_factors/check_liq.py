"""检查爆仓情况"""
import requests, json

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
        price[b]={'h24':float(x.get('high24h',0)or 0),'l24':float(x.get('low24h',0)or 0)}

print('爆仓检查(24h内)')
print('='*90)
print('  Dir  Coin     Entry    LiqPrice  Worst%    WorstVal  Liquidated')
print('-'*90)
for base,entry,tp1,dir_,lev in coins:
    p=price.get(base,{})
    h24=p.get('h24',0); l24=p.get('l24',0)
    if h24==0: continue
    
    if dir_=='SELL':
        liq=entry*(1+1/lev)
        worst=h24
        chg=(h24-entry)/entry*100
        boom=worst>=liq
    else:
        liq=entry*(1-1/lev)
        worst=l24
        chg=(l24-entry)/entry*100
        boom=worst<=liq
    
    print('  {:4s} {:<6s} ${:<8.3f} ${:<8.3f} {:>+7.2f}% ${:<8.3f} {}'.format(
        dir_,base,entry,liq,chg,worst,'YES!!' if boom else 'no'))
