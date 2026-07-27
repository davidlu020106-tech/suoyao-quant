"""Show ALL 99 trader votes with reasons for BCH"""
import sys, os, json, requests, pandas as pd, numpy as np
from datetime import datetime, timezone
sys.path.insert(0,'quant_factors')
from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single
from continuous_scores import continuous_score_all

profs={}
for f in sorted(os.listdir('profiles_v2')):
    if f.endswith('.json'):
        try: profs[f.replace('.json','')]=json.load(open('profiles_v2/'+f,encoding='utf-8'))
        except: pass
rids=set(CAP_REGISTRY.keys())
def mc(pid,rids):
    if pid in rids: return pid
    parts=pid.split('_')
    if len(parts)>=2 and parts[0]=='cap' and parts[1].isdigit():
        p='cap_'+parts[1]; m=[c for c in rids if c.startswith(p+'_')]
        return m[0] if m else None
    return None

d=requests.get('https://www.okx.com/api/v5/market/candles?instId=BCH-USDT&bar=1D&limit=200',
    headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
raw=d.get('data',[]); raw.reverse()
cdl=[]
for x in raw:
    ts=int(x[0])/1000; dt=datetime.fromtimestamp(ts,tz=timezone.utc)
    cdl.append({'date':dt.strftime('%Y-%m-%d'),'open':float(x[1]),'high':float(x[2]),
                'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date']); df=df.set_index('date').sort_index()
feats=build_features_single(df); lat=feats.iloc[-1]
cur=float(lat['close']); ma50=float(lat['ma50']); ma200=float(lat['ma200'])

print('BCH $'+str(round(cur,2))+' | MA50 $'+str(round(ma50))+' | MA200 $'+str(round(ma200)))
print()

# Pre-compute ALL factor scores
factor_cache={}
for cid in CAP_REGISTRY:
    factor_cache[cid]=continuous_score_all(cid,lat,feats)

# For each trader
all_traders=[]
for h,p in profs.items():
    tw,ws=0.0,0.0
    caps_detail=[]
    for cap in (p.get('capabilities_used',[]) or []):
        rid=cap.get('id',''); w=float(cap.get('weight',0))
        mid=mc(rid,rids)
        if mid:
            s=factor_cache.get(mid,0)
            if s!=0:
                ws+=w*s; tw+=abs(w)
                caps_detail.append((rid[:35],s,w))
    
    if tw>0: sig=ws/tw
    else:
        b=p.get('bias_default','neutral')
        sig=0.15 if b=='long_tilted' else (-0.15 if b=='short_tilted' else 0.0)
        caps_detail=[('default_bias',sig,1.0)]
    
    vote='BULL' if sig>0.03 else 'BEAR' if sig<-0.03 else 'NEUT'
    all_traders.append({'h':h,'sig':sig,'vote':vote,'school':p.get('school_primary','?'),
                        'bias':p.get('bias_default','?'),'caps':caps_detail})

all_traders.sort(key=lambda x:-x['sig'])

print('ALL 99 TRADERS - BCH')
print('='*130)

for t in all_traders:
    sig=t['sig']; vote=t['vote']; h=t['h']; sch=t['school']; bias=t['bias']
    caps=t['caps']; caps.sort(key=lambda x:-abs(x[1]))
    top=caps[:2]
    
    scores=' | '.join(['{:.2f}'.format(x[1]) for x in top])
    names=' | '.join([x[0].replace('cap_','').replace('_',' ')[:22] for x in top])
    
    # Determine reason
    reasons=[]
    for cid,s,w in top:
        r=''
        cname=cid.replace('cap_','').replace('_',' ')[:22]
        if 'regime_trending_up' in cid:
            r='price ${:.0f} > MA50 ${:.0f}? {}'.format(cur,ma50,cur>ma50)
        elif 'regime_trending_down' in cid:
            r='price ${:.0f} < MA50 ${:.0f}? {}'.format(cur,ma50,cur<ma50)
        elif 'golden' in cid or 'death' in cid or 'w50ema' in cid or 'horizontal' in cid:
            r='price ${:.0f} vs MA50 ${:.0f}: {}'.format(cur,ma50,'above' if cur>ma50 else 'below')
        elif 'reclaim' in cid:
            r='price ${:.0f} vs MA200 ${:.0f}: {}'.format(cur,ma200,'above' if cur>ma200 else 'below')
        elif '4year' in cid or 'halving' in cid:
            r='calendar: bear phase (fixed)'
        elif 'mechanical' in cid or 'value_zone' in cid:
            r='price ${:.0f} < MA200 ${:.0f}? {}'.format(cur,ma200,cur<ma200)
        elif 'macd' in cid:
            hist=float(lat.get('macd_hist',0))
            r='MACD hist: {:.4f} (>0? {})'.format(hist,hist>0)
        elif 'default_bias' in cid:
            r='no data, used bias='+bias
        else:
            r='price vs MAs'
        reasons.append(r)
    
    reason=' | '.join(reasons)
    
    print('  {:5s} {:+.4f} @{:<22s} [{:<12s}] -> {}'.format(vote,sig,h,sch,reason))

bulls=[t for t in all_traders if t['vote']=='BULL']
bears=[t for t in all_traders if t['vote']=='BEAR']
neus=[t for t in all_traders if t['vote']=='NEUT']
print()
print('Summary: BULL='+str(len(bulls))+' BEAR='+str(len(bears))+' NEUT='+str(len(neus)))
avg_sig=np.mean([t['sig'] for t in all_traders])
print('Avg Signal: {:.4f}'.format(avg_sig))
