"""Generate 4H KOL predictions for backtesting tomorrow"""
import sys, os, json, hmac, base64, hashlib
from datetime import datetime, timezone
sys.path.insert(0, 'quant_factors')
from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single
import requests, pandas as pd, numpy as np

# Load profiles
profs={}
for f in sorted(os.listdir('profiles_v2')):
    if f.endswith('.json'):
        try: profs[f.replace('.json','')]=json.load(open('profiles_v2/'+f,encoding='utf-8'))
        except: pass

def sc(cid,row):
    c=float(row['close']); m50=float(row.get('ma50',c)); m200=float(row.get('ma200',c))
    ma20=float(row.get('ma20',c)); rsi=float(row.get('rsi14',50))
    if cid=='cap_044_regime_trending_up': return 0.6 if c>m50 else -0.4
    if cid=='cap_045_regime_trending_down': return 0.6 if c<m50 else -0.4
    if cid=='cap_018_ma_golden_cross': return 0.5 if m50>m200 else -0.5
    if cid=='cap_019_ma_death_cross': return -0.5 if m50<m200 else 0.5
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

# Coins to analyze
coins=['BTC','ETH','SOL','XRP','DOGE','ADA','LINK','DOT','UNI','AAVE','LTC','BCH',
       'ORDI','ALLO','APE','ZEC','HYPE','LIT','EDGE','PI','POR','OP','WLD','SUI','NEAR']

results={}
ts=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
print('Generating 4H KOL predictions...')
print(f'Timestamp: {ts}')
print()

for base in coins:
    try:
        d=requests.get('https://www.okx.com/api/v5/market/candles?instId='+base+'-USDT&bar=4H&limit=200',
            headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
        raw=d.get('data',[]); raw.reverse()
        if not raw: continue
        cdl=[]
        for x in raw:
            ts2=int(x[0])/1000; dt=datetime.fromtimestamp(ts2,tz=timezone.utc)
            cdl.append({'date':dt.strftime('%Y-%m-%d %H:%M'),'open':float(x[1]),'high':float(x[2]),
                        'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
        df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date']); df=df.set_index('date').sort_index()
        feats=build_features_single(df); lat=feats.iloc[-1]
        cur=float(lat['close'])
        
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
        
        r1=float(lat['r1']); s1=float(lat['s1'])
        rsi=float(lat['rsi14']); ma50=float(lat['ma50']); ma200=float(lat['ma200'])
        
        results[base]={
            'price':round(cur,6),'r1':round(r1,6),'s1':round(s1,6),
            'ma50':round(ma50,6),'ma200':round(ma200,6),'rsi':round(rsi,1),
            'kol_bull':ln,'kol_bear':sn,'kol_neu':nn,'kol_signal':round(av,4),
            'direction':'BULL' if av>0.02 else 'BEAR' if av<-0.02 else 'NEUT',
            'above_ma50':bool(cur>ma50),'above_ma200':bool(cur>ma200),
        }
        
        arrow='🟢' if av>0.02 else '🔴' if av<-0.02 else '⚪'
        print(f'{arrow} {base:<6s} ${cur:<10.4f} {arrow} Ln={ln} Sn={sn} sig={av:+.4f}')
    except Exception as e:
        print(f'  {base}: skip ({str(e)[:30]})')

# Save
out={'timestamp':ts,'predictions':results}
op=os.path.join('quant_factors','4h_predictions.json')
json.dump(out,open(op,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(f'\nSaved: {op}')
print(f'Total: {len(results)} coins')
