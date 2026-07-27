"""重算排名 — 正确交易纪律版"""
import json, urllib.request

def g(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

print('Fetching OKX perp leverage...')
inst=g('/api/v5/public/instruments?instType=SWAP')
lev={}
for i in inst.get('data',[]):
    if i['instId'].endswith('-USDT-SWAP'):
        base=i['instId'].replace('-USDT-SWAP','')
        l=i.get('lever','')
        if l: lev[base]=max(int(x) for x in l.split(','))
print('  '+str(len(lev))+' contracts')

with open('quant_factors/full_scan_results.json','r',encoding='utf-8') as f:
    data=json.load(f)

def fmt(p,cur):
    if cur>100: return '{:.1f}'.format(p)
    if cur>10: return '{:.2f}'.format(p)
    if cur>1: return '{:.4f}'.format(p)
    return '{:.6f}'.format(p)

print()
print('='*130)
print('  FINAL RANKING — 正确交易纪律')
print('  阶段1: 入场 → 硬扛到TP1(利润=本金), 无止损!')
print('  阶段2: 到TP1平50%收回本金 → 剩余半仓成本=0')
print('='*130)
print()

for direction, label in [('longs','LONG BUY'),('shorts','SHORT SELL')]:
    items=data[direction]
    print()
    print('  TOP 10 '+label)
    print('  '+'-'*120)
    h='  #  Coin      Entry       TP1(利润=本金) 需涨跌   杠杆   KOL L/S   RSI  风险说明'
    print(h)
    print('  '+'-'*120)
    
    for i,r in enumerate(items[:10],1):
        cur=r['entry']; base=r['base']
        fl=lev.get(base,10)
        
        if direction=='longs':
            tp1=cur*(1+1.0/fl)
            need='+{:.1f}%'.format(100.0/fl)
            risk_note='无止损,硬扛到+{:.1f}%'.format(100.0/fl)
        else:
            tp1=cur*(1-1.0/fl)
            need='-{:.1f}%'.format(100.0/fl)
            risk_note='无止损,硬扛到-{:.1f}%'.format(100.0/fl)
        
        es=fmt(cur,cur); ts=fmt(tp1,cur)
        
        print('  {:3d} {:<8s} ${:<12s} ${:<12s} {:>8s} {:>4d}x {:>3d}/{:>3d} {:>5.1f} {}'.format(
            i,base,es,ts,need,fl,r['kol_long'],r['kol_short'],r['rsi'],risk_note))
    
    print()

print('  ================================================================================')
print('  到TP1后: 平50%,收回本金 → 剩余50%仓位成本=0')
print('  然后回来找我,咱重新看局势决定剩余仓位的止损/止盈')
print('  ================================================================================')
