#!/usr/bin/env python3
"""full scan - all altcoins + KOL consensus + max leverage + 24h prediction"""
import sys, os, json, urllib.request, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone

QF = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(QF)
sys.path.insert(0, QF); sys.path.insert(0, BASE)
from local_config import OKX_API_KEY
from okx_data_adapter import build_features_single

STABLE={'USDT','USDC','DAI','TUSD','BUSD','FDUSD','USDP','EUR','GBP','AUD',
        'SGD','AED','CNY','JPY','KRW','USDG','TRY','BRL','CAD','CHF','HKD','MXN'}

def api_get(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

def cscore(cid,row):
    c=float(row['close']); h=float(row['high']); l=float(row['low']); o=float(row['open'])
    ma50=float(row.get('ma50',c)); ma200=float(row.get('ma200',c))
    rsi=float(row.get('rsi14',50)); fib=float(row.get('fib_618',c))
    bbw=float(row.get('bb_width',0)); hist=float(row.get('macd_hist',0))
    rng=h-l
    if cid=='cap_044_regime_trending_up': return 0.6 if c>ma50 else -0.4
    if cid=='cap_045_regime_trending_down': return 0.6 if c<ma50 else -0.4
    if cid=='cap_018_ma_golden_cross': return 0.5 if ma50>ma200 else -0.5
    if cid=='cap_019_ma_death_cross': return -0.5 if ma50<ma200 else 0.5
    if cid=='cap_020_macd_histogram_cross': return 0.4 if hist>0 else -0.4
    if cid=='cap_069_moving_average_reclaim': return 0.6 if c>ma200 else -0.6
    if cid=='cap_022_fib_618_support':
        d=abs(c-fib)/c if c>0 else 1; return 0.7 if d<0.02 else 0.3 if d<0.05 else 0.0
    if cid=='cap_037_halving_cycle': return -0.30
    if cid=='cap_038_4year_cycle': return -0.40
    if cid=='cap_001_falling_wedge_breakout': return 0.35 if c>ma50 else -0.2
    if cid=='cap_002_rising_wedge_breakdown': return -0.35 if c<ma50 else 0.2
    if cid=='cap_012_sfp': return 0.3 if c>float(row.get('ma20',c)) else -0.3
    if cid in ['cap_027_dxy_inverse_btc','cap_028_spx_risk_on']: return 0.1 if c>ma50 else -0.1
    if cid=='cap_041_dont_catch_falling_knives': return -0.5 if rsi<30 else 0.0
    if cid in ['cap_023_elliott_wave_3','cap_024_wyckoff_accumulation_spring']: return 0.3 if c>ma50 else -0.3
    return 0.0

def match_cap(pid,rids):
    if pid in rids: return pid
    parts=pid.split('_')
    if len(parts)>=2 and parts[0]=='cap' and parts[1].isdigit():
        p='cap_'+parts[1]; m=[c for c in rids if c.startswith(p+'_')]
        return m[0] if m else None
    return None

print('Loading KOL...')
from capabilities import CAP_REGISTRY
reg=CAP_REGISTRY; rids=set(reg.keys())
profs={}
pd_=os.path.join(BASE,'profiles_v2')
for f in sorted(os.listdir(pd_)):
    if f.endswith('.json'):
        try:
            p=json.load(open(os.path.join(pd_,f),encoding='utf-8'))
            profs[f.replace('.json','')]=p
        except: pass
print('  '+str(len(reg))+' factors, '+str(len(profs))+' traders')

print('Fetching tickers...')
t=api_get('/api/v5/market/tickers?instType=SPOT')
coins=[]
for x in t.get('data',[]):
    inst=x['instId']
    if not inst.endswith('-USDT'): continue
    b=inst.replace('-USDT','')
    if b in STABLE: continue
    v=float(x.get('volCcy24h','0') or 0)
    if v>=500000: coins.append({'base':b,'symbol':inst,'vol':v})
coins.sort(key=lambda x:x['vol'],reverse=True)
print('  '+str(len(coins))+' coins')

results=[]
for i,coin in enumerate(coins):
    base=coin['base']; sym=coin['symbol']
    try:
        d=api_get('/api/v5/market/candles?instId='+sym+'&bar=1D&limit=200')
        raw=d.get('data',[])
        if not raw: continue
        raw.reverse()
        cdl=[]
        for x in raw:
            ts=int(x[0])/1000; dt=datetime.fromtimestamp(ts,tz=timezone.utc)
            cdl.append({'date':dt.strftime('%Y-%m-%d'),'open':float(x[1]),
                        'high':float(x[2]),'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
        if len(cdl)<20: continue
        df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date'])
        df=df.set_index('date').sort_index()
        feats=build_features_single(df)
    except: continue

    lat=feats.iloc[-1]; cur=float(lat['close'])
    hh=float(feats['high'].max()); ll=float(feats['low'].min())
    pv=(hh+ll+cur)/3; r1=2*pv-ll; r2=pv+(hh-ll); s1=2*pv-hh; s2=pv-(hh-ll)
    rsi=float(lat.get('rsi14',50))
    
    fs={}
    for cid,meta in reg.items():
        try: fs[cid]=cscore(cid,lat)
        except: fs[cid]=0.0
    
    tsigs=[]
    for h,p in profs.items():
        tw,ws=0.0,0.0
        for cap in (p.get('capabilities_used',[]) or []):
            rid=cap.get('id',''); w=float(cap.get('weight',0))
            mid=match_cap(rid,rids)
            if mid:
                s=fs.get(mid,0)
                if s!=0: ws+=w*s; tw+=abs(w)
        if tw>0: sig=ws/tw
        else:
            b=p.get('bias_default','neutral')
            sig=0.15 if b=='long_tilted' else (-0.15 if b=='short_tilted' else 0.0)
        tsigs.append(sig)
    
    arr=np.array(tsigs)
    ln=int(np.sum(arr>0.03)); sn=int(np.sum(arr<-0.03)); av=float(np.mean(arr))
    
    if av>0.01:
        direction='LONG'
        max_lev=min(125, cur/(cur-s2)) if cur>s2 else 1
        tp1=cur*(1+1/max_lev)
        tp2=r2; liq=s2
        if rsi<40: limit=cur*0.98; reason='rsi oversold - buy dip'
        else: limit=cur; reason='market entry'
    elif av<-0.01:
        direction='SHORT'
        max_lev=min(125, cur/(r2-cur)) if r2>cur else 1
        tp1=cur*(1-1/max_lev)
        tp2=s2; liq=r2
        if rsi>60: limit=cur*1.02; reason='rsi high - sell rally'
        else: limit=cur; reason='market entry'
    else: continue
    
    upside=abs(cur-tp1)/cur*100
    if upside<0.5: continue

    # 24h atr
    try:
        d2=api_get('/api/v5/market/candles?instId='+sym+'&bar=1D&limit=30')
        r2d=d2.get('data',[])
        if r2d:
            r2d.reverse(); tr=[]
            for j in range(1,len(r2d)):
                hx=float(r2d[j][2]); lx=float(r2d[j][3]); pc=float(r2d[j-1][4])
                tr.append(max(hx-lx,abs(hx-pc),abs(lx-pc)))
            atr_1d=sum(tr[-14:])/14 if len(tr)>=14 else cur*0.03
        else: atr_1d=cur*0.03
    except: atr_1d=cur*0.03
    
    if direction=='LONG':
        lo24=cur-atr_1d*1.5; hi24=cur+atr_1d*2.0+(atr_1d*0.5 if av>0.05 else 0)
        pred='bullish' if av>0.02 else 'slight bull'
    else:
        lo24=cur-atr_1d*2.0-(atr_1d*0.5 if av<-0.05 else 0); hi24=cur+atr_1d*1.5
        pred='bearish' if av<-0.02 else 'slight bear'
    
    results.append({
        'base':base,'direction':direction,'entry':cur,'limit':limit,
        'tp1':tp1,'tp2':tp2,'liq':liq,'lev':max_lev,
        'kol_long':ln,'kol_short':sn,'kol_avg':av,'rsi':rsi,
        'upside':upside,'reason':reason,'prediction':pred,
        '24h_low':lo24,'24h_high':hi24,
    })
    if (i+1)%20==0: print('  '+str(i+1)+'/'+str(len(coins))+' = '+str(len(results))+' candidates')

longs=[r for r in results if r['direction']=='LONG']
shorts=[r for r in results if r['direction']=='SHORT']
for r in longs: r['rank']=max(0,r['kol_avg'])*30+r['upside']*0.3
for r in shorts: r['rank']=max(0,-r['kol_avg'])*30+r['upside']*0.3
longs.sort(key=lambda x:x['rank'],reverse=True)
shorts.sort(key=lambda x:x['rank'],reverse=True)

print()
print('='*110)
print('  TOP 10 LONG (Buy)')
print('='*110)
h='  #  Coin      Entry       Limit       TP1(2x)     Liq       Lev  KOL L/S  RSI  24h Range'
print(h); print('  '+'-'*90)
for i,r in enumerate(longs[:10],1):
    e='{:.4f}'.format(r['entry']); l='{:.4f}'.format(r['limit'])
    t='{:.4f}'.format(r['tp1']); lq='{:.4f}'.format(r['liq'])
    if r['entry']>10:
        e='{:.2f}'.format(r['entry']); l='{:.2f}'.format(r['limit'])
        t='{:.2f}'.format(r['tp1']); lq='{:.2f}'.format(r['liq'])
    r24='{:.1f}-{:.1f}'.format(r['24h_low'],r['24h_high']) if r['24h_low']<100 else '{:.0f}-{:.0f}'.format(r['24h_low'],r['24h_high'])
    print('  {:3d} {:<8s} ${:<10s} ${:<10s} ${:<10s} ${:<10s} {:>4.0f}x {:>3d}/{:<3d} {:>5.1f} {}'.format(
        i,r['base'],e,l,t,lq,r['lev'],r['kol_long'],r['kol_short'],r['rsi'],r24))

print()
print('='*110)
print('  TOP 10 SHORT (Sell)')
print('='*110)
print(h); print('  '+'-'*90)
for i,r in enumerate(shorts[:10],1):
    e='{:.4f}'.format(r['entry']); l='{:.4f}'.format(r['limit'])
    t='{:.4f}'.format(r['tp1']); lq='{:.4f}'.format(r['liq'])
    if r['entry']>10:
        e='{:.2f}'.format(r['entry']); l='{:.2f}'.format(r['limit'])
        t='{:.2f}'.format(r['tp1']); lq='{:.2f}'.format(r['liq'])
    r24='{:.1f}-{:.1f}'.format(r['24h_low'],r['24h_high']) if r['24h_low']<100 else '{:.0f}-{:.0f}'.format(r['24h_low'],r['24h_high'])
    print('  {:3d} {:<8s} ${:<10s} ${:<10s} ${:<10s} ${:<10s} {:>4.0f}x {:>3d}/{:<3d} {:>5.1f} {}'.format(
        i,r['base'],e,l,t,lq,r['lev'],r['kol_long'],r['kol_short'],r['rsi'],r24))

print(); print('TOP 3 DETAIL')
for r in longs[:3]+shorts[:2]:
    print('  ['+r['direction']+'] '+r['base'])
    print('    Entry: ${:.4f} | Limit: ${:.4f} ({})'.format(r['entry'],r['limit'],r['reason']))
    print('    TP1:   ${:.4f} (+{:.1f}%) | TP2: ${:.4f} | Liq: ${:.4f} | Lev: {:.0f}x'.format(r['tp1'],r['upside'],r['tp2'],r['liq'],r['lev']))
    print('    KOL: L={} S={} bias={:+.4f} | RSI: {:.1f} | 24h: {} (${:.1f}-${:.1f})'.format(r['kol_long'],r['kol_short'],r['kol_avg'],r['rsi'],r['prediction'],r['24h_low'],r['24h_high']))
    print()

op=os.path.join(QF,'full_scan_results.json')
json.dump({'longs':longs[:20],'shorts':shorts[:20]},open(op,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('Saved: '+op)
print('Total: '+str(len(results))+' candidates ('+str(len(longs))+' long, '+str(len(shorts))+' short)')
