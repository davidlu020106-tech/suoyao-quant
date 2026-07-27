"""Show individual KOL votes per coin"""
import sys, os, json, requests, pandas as pd, numpy as np
from datetime import datetime, timezone
from collections import defaultdict
sys.path.insert(0,'quant_factors')
from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single

profs={}
for f in sorted(os.listdir('profiles_v2')):
    if f.endswith('.json'):
        try: profs[f.replace('.json','')]=json.load(open('profiles_v2/'+f,encoding='utf-8'))
        except: pass

def sc(cid,row):
    c=float(row['close']); m50=float(row.get('ma50',c)); m200=float(row.get('ma200',c))
    if cid=='cap_044_regime_trending_up': return 0.6 if c>m50 else -0.4
    if cid=='cap_045_regime_trending_down': return 0.6 if c<m50 else -0.4
    if cid=='cap_069_moving_average_reclaim': return 0.6 if c>m200 else -0.6
    if cid in ['emg_008_w50ema_bull_bear_divider','emg_014_horizontal_reclaim']: return 0.4 if c>m50 else -0.4
    if cid in ['cap_037_halving_cycle','cap_038_4year_cycle']: return -0.30
    return 0.0

def mc(pid,rids):
    if pid in rids: return pid
    parts=pid.split('_')
    if len(parts)>=2 and parts[0]=='cap' and parts[1].isdigit():
        p='cap_'+parts[1]; m=[c for c in rids if c.startswith(p+'_')]
        return m[0] if m else None
    return None

rids=set(CAP_REGISTRY.keys())
coins=['BTC','ETH','EDGE','ORDI','XRP','DOGE','POR']

for base in coins:
    d=requests.get('https://www.okx.com/api/v5/market/candles?instId='+base+'-USDT&bar=1D&limit=200',
        headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
    raw=d.get('data',[]); raw.reverse()
    if not raw: continue
    cdl=[]
    for x in raw:
        ts=int(x[0])/1000; dt=datetime.fromtimestamp(ts,tz=timezone.utc)
        cdl.append({'date':dt.strftime('%Y-%m-%d'),'open':float(x[1]),'high':float(x[2]),
                    'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
    df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date']); df=df.set_index('date').sort_index()
    feats=build_features_single(df); lat=feats.iloc[-1]; cur=float(lat['close'])

    votes={}
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
        votes[h]={'sig':round(sig,4),'school':p.get('school_primary','?')}
    
    bulls={k:v for k,v in votes.items() if v['sig']>0.03}
    bears={k:v for k,v in votes.items() if v['sig']<-0.03}
    neus={k:v for k,v in votes.items() if abs(v['sig'])<=0.03}
    
    print()
    print('='*95)
    print('  '+base+' | $'+str(round(cur,4))+' | Bull:'+str(len(bulls))+' Bear:'+str(len(bears))+' Neu:'+str(len(neus)))
    print('='*95)
    
    # 看多的人
    if bulls:
        print('  BULL ('+str(len(bulls))+'):')
        for h in sorted(bulls,key=lambda x:-bulls[x]['sig'])[:5]:
            v=bulls[h]
            print('    +'+str(v['sig'])+'  @'+h.ljust(22)+' ['+v['school']+']')
    
    # 看空的人
    if bears:
        print('  BEAR ('+str(len(bears))+'):')
        for h in sorted(bears,key=lambda x:bears[x]['sig'])[:5]:
            v=bears[h]
            print('    '+str(v['sig'])+'  @'+h.ljust(22)+' ['+v['school']+']')
