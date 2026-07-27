"""Backtest the altcoin ranking results"""
import json, urllib.request
from datetime import datetime, timezone

with open('quant_factors/altcoin_5m_kol_ranking.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

def api_get(path):
    url='https://www.okx.com'+path
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

tickers=api_get('/api/v5/market/tickers?instType=SPOT')
price_map={}
for t in tickers.get('data',[]):
    inst=t['instId']
    if inst.endswith('-USDT'):
        base=inst.replace('-USDT','')
        price_map[base]=float(t.get('last','0') or 0)

now=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
print()
print('  Backtest - 6 High Vol Coins')
print(f'  {now}')
print('='*95)

total_pnl=0; total_win=0; total_lose=0

for r in results:
    base=r['base']; entry=r['entry']; tp1=r['r1']; tp2=r['r2']
    liq=r['s2']; lev=r['max_lev']; score=r['score']
    cur=price_map.get(base,0)
    if cur==0: continue
    
    change=(cur-entry)/entry*100
    hit=''; pnl=0
    if cur >= tp2:
        hit='TP2'
        pnl=((tp1-entry)/entry*0.5 + (tp2-entry)/entry*0.5)*lev*100
    elif cur >= tp1:
        hit='TP1'
        pnl=((tp1-entry)/entry*0.5)*lev*100
    elif cur <= liq:
        hit='LIQ'; pnl=-100
    else:
        hit='HOLD'
        pnl=change*lev
    
    total_pnl+=pnl
    if pnl>0: total_win+=1
    elif pnl<0: total_lose+=1
    
    m=''; m2=''
    if 'TP' in hit: m='(TP HIT)'
    elif hit=='LIQ': m='(LIQUIDATED)'
    if pnl>50: m2=' <<< WIN'
    elif pnl<=-100: m2=' <<< LOSS'
    
    print(f'  {base:<6s} entry=${entry:<8.4f} now=${cur:<8.4f} {change:>+6.2f}% {hit:<6s} PnL={pnl:>+7.1f}%{m}{m2}')
    print(f'         TP1=${tp1:<8.4f} TP2=${tp2:<8.4f} Liq=${liq:<8.4f} Lev={lev:.0f}x Score={score}/10')

print('='*95)
total=total_win+total_lose
print(f'  Total PnL: {total_pnl:+.1f}%  |  Win:{total_win} Lose:{total_lose}')
if total>0:
    print(f'  Win rate: {total_win/total*100:.0f}%')
