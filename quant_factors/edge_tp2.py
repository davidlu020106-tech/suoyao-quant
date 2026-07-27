"""Find TP2 for EDGE short"""
import sys, json, urllib.request, pandas as pd
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, 'quant_factors')

def api_get(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

d=api_get('/api/v5/market/candles?instId=EDGE-USDT&bar=1D&limit=200')
raw=d.get('data',[])
raw.reverse()
lows=[float(x[3]) for x in raw]
highs=[float(x[2]) for x in raw]
closes=[float(x[4]) for x in raw]

entry=0.4362

# Find support clusters below entry
bins=Counter()
for l in lows:
    if l < entry:
        bins[round(l/0.02)*0.02]+=1

print('EDGE short TP2 levels:')
print()
print('  Price    Hits  Type')
for level, cnt in sorted(bins.most_common(8)):
    if cnt>=2:
        dist=(entry-level)/entry*100
        label='Strong support' if cnt>=5 else 'Moderate support'
        print(f'  ${level:.4f}  {cnt}x   {label}  (-${entry-level:.4f}, -{dist:.1f}%)')

print()
print('Suggested TP2:')
print(f'  TP2 = $0.395 (round number + dense support)')
print(f'       From entry ${entry} → ${format(0.395,".4f")} = {(entry-0.395)/entry*100:.1f}% drop')
print(f'       With 20x: remaining 50% profit = {(entry-0.395)/entry*100*20*0.5:.1f}%')
