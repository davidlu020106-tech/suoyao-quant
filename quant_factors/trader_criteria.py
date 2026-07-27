"""Show each trader's full judgment criteria for BCH"""
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
    cdl.append({'date':dt.strftime('%Y-%m-%d'),'open':float(x[1]),'high':float(x[2]),'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date']); df=df.set_index('date').sort_index()
feats=build_features_single(df); lat=feats.iloc[-1]

# Pre-compute all factor scores
fcache={}
for cid in CAP_REGISTRY:
    fcache[cid]=continuous_score_all(cid,lat,feats)

all_traders=[]
for h,p in profs.items():
    school=p.get('school_primary','?')
    bias=p.get('bias_default','?')
    time_p=p.get('time_preference','?')
    caps=p.get('capabilities_used',[]) or []
    
    total_w=0; total_ws=0
    cap_details=[]
    for cap in caps:
        rid=cap.get('id',''); w=float(cap.get('weight',0))
        mid=mc(rid,rids)
        if mid and mid in fcache:
            s=fcache[mid]
            if s!=0:
                total_ws+=w*s
                total_w+=abs(w)
                cap_details.append({'id':rid,'name':rid.replace('cap_','').replace('_',' ')[:25],'w':w,'s':s})
    
    if total_w>0: sig=total_ws/total_w
    else:
        sig=0.15 if bias=='long_tilted' else (-0.15 if bias=='short_tilted' else 0.0)
        cap_details=[{'id':'default','name':'default bias','w':1,'s':sig}]
    
    vote='BULL' if sig>0.03 else 'BEAR' if sig<-0.03 else 'NEUT'
    cap_details.sort(key=lambda x:-abs(x['s']))
    all_traders.append({'h':h,'sig':sig,'vote':vote,'school':school,'bias':bias,'time':time_p,'caps':cap_details})

all_traders.sort(key=lambda x:x['sig'])

print('EACH TRADERS FULL JUDGMENT CRITERIA FOR BCH')
print('='*130)
for t in all_traders:
    h=t['h']; sig=round(t['sig'],4); vote=t['vote']; sch=t['school']; bias=t['bias']; tm=t['time']
    caps=t['caps']
    active=[c for c in caps if abs(c['s'])>0.05]
    
    if active:
        reasons=[]
        for c in active[:4]:
            dir_str='LONG(+)' if c['s']>0 else 'SHORT(-)'
            w_str='{:.2f}'.format(c['w'])
            reasons.append('{} {:.2f} (w={})'.format(dir_str,c['s'],c['w']))
        reason_str=' | '.join(reasons)
    else:
        reason_str='default bias={:.2f} (no active factors)'.format(sig)
    
    print('{:.4f} {:5s} @{:<20s} [{}] bias={} time={} -> {}'.format(
        sig,vote,h,sch,bias,tm,reason_str))

bulls=[t for t in all_traders if t['vote']=='BULL']
bears=[t for t in all_traders if t['vote']=='BEAR']
print()
print('BULL={} BEAR={}'.format(len(bulls),len(bears)))
