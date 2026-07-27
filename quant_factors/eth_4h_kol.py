"""ETH 4H KOL Consensus Analysis"""
import sys, os, json, urllib.request, pandas as pd, numpy as np
from datetime import datetime, timezone
sys.path.insert(0, 'quant_factors')
from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single

def g(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

profs={}
for f in sorted(os.listdir('profiles_v2')):
    if f.endswith('.json'):
        try: profs[f.replace('.json','')]=json.load(open('profiles_v2/'+f,encoding='utf-8'))
        except: pass

d=g('/api/v5/market/candles?instId=ETH-USDT&bar=4H&limit=200')
raw=d.get('data',[]); raw.reverse()
cdl=[]
for x in raw:
    ts=int(x[0])/1000; dt=datetime.fromtimestamp(ts,tz=timezone.utc)
    cdl.append({'date':dt.strftime('%Y-%m-%d %H:%M'),'open':float(x[1]),'high':float(x[2]),
                'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date']); df=df.set_index('date').sort_index()
feats=build_features_single(df); lat=feats.iloc[-1]
cur=float(lat['close']); target=1917.18

def sc(cid,row):
    c=float(row['close']); m50=float(row.get('ma50',c)); m200=float(row.get('ma200',c))
    ma20=float(row.get('ma20',c)); rsi=float(row.get('rsi14',50))
    fib=float(row.get('fib_618',c)); bbw=float(row.get('bb_width',0)); hist=float(row.get('macd_hist',0))
    if cid=='cap_044_regime_trending_up': return 0.6 if c>m50 else -0.4
    if cid=='cap_045_regime_trending_down': return 0.6 if c<m50 else -0.4
    if cid=='cap_018_ma_golden_cross': return 0.5 if m50>m200 else -0.5
    if cid=='cap_019_ma_death_cross': return -0.5 if m50<m200 else 0.5
    if cid=='cap_069_moving_average_reclaim': return 0.6 if c>m200 else -0.6
    if cid=='cap_020_macd_histogram_cross': return 0.4 if hist>0 else -0.4
    if cid in ['emg_008_w50ema_bull_bear_divider','emg_014_horizontal_reclaim']: return 0.4 if c>m50 else -0.4
    if cid=='cap_022_fib_618_support':
        d2=abs(c-fib)/c if c>0 else 1; return 0.7 if d2<0.02 else (0.3 if d2<0.05 else 0.0)
    if cid=='cap_017_rsi_oversold_bounce': return 0.5 if rsi<35 else (0.2 if rsi<45 else 0)
    if cid=='cap_021_bb_squeeze_breakout': return 0.4 if bbw<0.02 else (-0.2 if bbw>0.06 else 0.0)
    if cid in ['cap_037_halving_cycle','cap_038_4year_cycle']: return -0.30
    if cid in ['cap_012_sfp','cap_014_trend_pullback']: return 0.3 if c>ma20 else -0.3
    if cid in ['cap_001_falling_wedge_breakout']: return 0.35 if c>m50 else -0.2
    if cid in ['cap_027_dxy_inverse_btc','cap_028_spx_risk_on']: return 0.1 if c>m50 else -0.1
    if cid=='cap_023_elliott_wave_3': return 0.3 if c>m50 else -0.3
    return 0.0

def mc(pid,rids):
    if pid in rids: return pid
    parts=pid.split('_')
    if len(parts)>=2 and parts[0]=='cap' and parts[1].isdigit():
        p='cap_'+parts[1]; m=[c for c in rids if c.startswith(p+'_')]
        return m[0] if m else None
    return None

rids=set(CAP_REGISTRY.keys())

sigs=[]
for h,p in profs.items():
    tw,ws=0.0,0.0
    for cap in (p.get('capabilities_used',[]) or []):
        rid=cap.get('id',''); w=float(cap.get('weight',0))
        mid=mc(rid,rids)
        if mid:
            s=sc(mid,lat)
            if s!=0: ws+=w*s; tw+=abs(w)
    if tw>0: sig=ws/tw
    else:
        b=p.get('bias_default','neutral')
        sig=0.15 if b=='long_tilted' else (-0.15 if b=='short_tilted' else 0.0)
    sigs.append(sig)

arr=np.array(sigs)
ln=int(np.sum(arr>0.03)); sn=int(np.sum(arr<-0.03)); nn=len(arr)-ln-sn; av=float(np.mean(arr))
dist=(target-cur)/cur*100
atr14=float(feats['atr14'].iloc[-1])

print()
print('='*60)
print('  ETH 4H KOL Consensus')
print('='*60)
print()
print('  Technical:')
print('    Current: ${:.2f}  |  Target: ${:.2f}'.format(cur, target))
print('    MA50: ${:.2f}  MA200: ${:.2f}'.format(float(lat['ma50']),float(lat['ma200'])))
print('    Price > MA50? {}  |  Price > MA200? {}'.format(cur>float(lat['ma50']),cur>float(lat['ma200'])))
print('    RSI14: {:.1f}  |  MACDh: {:.4f}'.format(float(lat['rsi14']),float(lat['macd_hist'])))
print('    R1: ${:.2f}  |  S1: ${:.2f}'.format(float(lat['r1']),float(lat['s1'])))
print()
print('  KOL Vote:')
print('    Bullish: {} traders ({}%)'.format(ln, round(ln/99*100)))
print('    Bearish: {} traders ({}%)'.format(sn, round(sn/99*100)))
print('    Neutral: {} traders ({}%)'.format(nn, round(nn/99*100)))
print('    Avg Signal: {:.4f}'.format(av))
if av>0.02: print('    Verdict: BULLISH')
elif av<-0.02: print('    Verdict: BEARISH')
else: print('    Verdict: NEUTRAL')
print()
print('  4H Target ${:.2f}:'.format(target))
print('    Distance: {:+.2f}%'.format(dist))
print('    ATR(14x4H): ${:.2f}'.format(atr14))
print('    ATR ratio: {:.2f}x'.format(abs(dist)/(atr14/cur*100) if atr14>0 else 0))
if dist>0:
    print('    UP probability: {} of {} active traders'.format(ln, ln+sn))
else:
    print('    DOWN probability: {} of {} active traders'.format(sn, ln+sn))
print()
