"""综合排名: 做多+做空统一排行"""
import json, requests

with open('quant_factors/1d_predictions.json','r',encoding='utf-8') as f:
    data=json.load(f)

p=data['predictions']

# 获取杠杆
inst=requests.get('https://www.okx.com/api/v5/public/instruments?instType=SWAP',
    headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
lev={}
for i in inst.get('data',[]):
    if i['instId'].endswith('-USDT-SWAP'):
        base=i['instId'].replace('-USDT-SWAP','')
        l=i.get('lever','')
        if l: lev[base]=max(int(x) for x in l.split(','))

results=[]
for base,info in p.items():
    cur=info['price']; bl=info['kol_bull']; br=info['kol_bear']
    sig=info['kol_signal']; rsi=info['rsi']; ma=info['ma_status']
    fl=lev.get(base,10)
    
    if abs(sig)<0.02: continue
    
    if sig>0:
        dire='LONG'
        tp1=cur*(1+1.0/fl)
        kol_sc=bl/(bl+br)*50
        rsi_sc=10 if rsi<40 else (5 if rsi<50 else 0)
        ma_sc=10 if ma=='BOTH' else 5 if ma=='MA50' else 0
    else:
        dire='SHORT'
        tp1=cur*(1-1.0/fl)
        kol_sc=br/(bl+br)*50
        rsi_sc=10 if rsi>60 else (5 if rsi>50 else 0)
        ma_sc=0 if ma=='NONE' else 5
    
    total=kol_sc+min(20,fl)+rsi_sc+ma_sc
    results.append({'base':base,'dir':dire,'entry':cur,'tp1':tp1,
        'lev':fl,'kol':str(bl)+'/'+str(br),'sig':sig,'rsi':rsi,'ma':ma,'score':round(total,1)})

results.sort(key=lambda x:x['score'],reverse=True)

print('='*120)
print('  Top 20 Ranking - 2026-07-17')
print('='*120)
h='  #  Dir   Coin     Entry       TP1(翻倍)     Lev  KOL     Signal  RSI  MA    Score'
print(h)
print('-'*120)
for i,r in enumerate(results[:20],1):
    es='{:.4f}'.format(r['entry']); ts='{:.4f}'.format(r['tp1'])
    if r['entry']>10:
        es='{:.2f}'.format(r['entry']); ts='{:.2f}'.format(r['tp1'])
    d='BUY' if r['dir']=='LONG' else 'SELL'
    print('  {:2d}  {:<5s} {:<6s} ${:<10s} ${:<10s} {:>4d}x {:>6s} {:>+7.4f} {:>5.1f} {:>4s} {:>5.1f}'.format(
        i,d,r['base'],es,ts,r['lev'],r['kol'],r['sig'],r['rsi'],r['ma'],r['score']))
