"""APE resistance levels"""
import sys, requests, pandas as pd
from datetime import datetime, timezone
sys.path.insert(0,'quant_factors')
from okx_data_adapter import build_features_single

d=requests.get('https://www.okx.com/api/v5/market/candles?instId=APE-USDT&bar=1D&limit=200',
    headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
raw=d.get('data',[]); raw.reverse()
cdl=[]
for x in raw:
    ts=int(x[0])/1000; dt=datetime.fromtimestamp(ts,tz=timezone.utc)
    cdl.append({'date':dt.strftime('%Y-%m-%d'),'open':float(x[1]),'high':float(x[2]),
                'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date']); df=df.set_index('date').sort_index()
feats=build_features_single(df); lat=feats.iloc[-1]; cur=float(lat['close'])

r1=float(lat['r1']); r2=float(lat['r2']); s1=float(lat['s1']); s2=float(lat['s2'])
pivot=float(lat['pivot']); ma50=float(lat['ma50']); ma200=float(lat['ma200'])
bb_u=float(lat['bb_upper']); bb_l=float(lat['bb_lower']); fib618=float(lat['fib_618'])
rsi=float(lat['rsi14'])

print('APE Resistance Levels (1D)')
print('='*55)
print('Current: ${:.4f} | RSI: {:.1f}'.format(cur,rsi))
print()
print('UP (Resistance):')
print('  R1:     ${:.4f} (+{:.1f}%)  Target'.format(r1,(r1-cur)/cur*100))
print('  BB Up:  ${:.4f} (+{:.1f}%)  Bollinger'.format(bb_u,(bb_u-cur)/cur*100))
print('  R2:     ${:.4f} (+{:.1f}%)  Pivot R2'.format(r2,(r2-cur)/cur*100))
print('  MA200:  ${:.4f} (+{:.1f}%)  Long term MA'.format(ma200,(ma200-cur)/cur*100))
print()
print('DOWN (Support):')
print('  S1:     ${:.4f} ({:.1f}%)'.format(s1,(s1-cur)/cur*100))
print('  MA50:   ${:.4f} ({:.1f}%)'.format(ma50,(ma50-cur)/cur*100))
print('  BB Low: ${:.4f} ({:.1f}%)'.format(bb_l,(bb_l-cur)/cur*100))
print('  S2:     ${:.4f} ({:.1f}%)'.format(s2,(s2-cur)/cur*100))
print('  Fib618: ${:.4f} ({:.1f}%)'.format(fib618,(fib618-cur)/cur*100))
print()
tp1=cur*(1+1/20)
print('TP1(翻倍): ${:.4f} (+5.0%) @20x'.format(tp1))
