"""Unified ranking - Long + Short combined"""
import json, urllib.request

def api_get(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

print('Fetching leverage...')
inst=api_get('/api/v5/public/instruments?instType=SWAP')
lev={}
for i in inst.get('data',[]):
    if i['instId'].endswith('-USDT-SWAP'):
        base=i['instId'].replace('-USDT-SWAP','')
        l=i.get('lever','')
        if l: lev[base]=max(int(x) for x in l.split(','))
defaults={'BTC':125,'ETH':125,'SOL':75,'XRP':50,'DOGE':50,'ADA':50,'LINK':50,'UNI':50,'AAVE':50,'LTC':50,'BCH':50}

with open('quant_factors/full_scan_results.json','r',encoding='utf-8') as f:
    data=json.load(f)

def risk_label(pct):
    if pct<3: return 'HIGH'
    if pct<8: return 'MID'
    return 'LOW'

# Build unified list
unified=[]
for r in data['longs'][:15]:
    cur=r['entry']; base=r['base']
    fl=lev.get(base,defaults.get(base,10))
    tp1=cur*(1+1.0/fl); stop=cur*(1-1.0/fl)
    risk=100.0/fl
    # Score: KOL agreement + leverage attractiveness + RSI favorable
    kol_score=(r['kol_long']/99)*50  # max 50 for full agreement
    lev_score=min(20,fl)  # max 20 for leverage
    rsi_score=0
    if r['rsi']<35: rsi_score=15  # oversold = good for longs
    elif r['rsi']<50: rsi_score=10
    total=kol_score+lev_score+rsi_score
    unified.append({'base':base,'dir':'LONG','entry':cur,'tp1':tp1,'stop':stop,'lev':fl,
        'kol_l':r['kol_long'],'kol_s':r['kol_short'],'rsi':r['rsi'],'risk':risk,
        'risk_l':risk_label(risk),'score':total,'pred':r['prediction']})

for r in data['shorts'][:15]:
    cur=r['entry']; base=r['base']
    fl=lev.get(base,defaults.get(base,10))
    tp1=cur*(1-1.0/fl); stop=cur*(1+1.0/fl)
    risk=100.0/fl
    kol_score=(r['kol_short']/99)*50
    lev_score=min(20,fl)
    rsi_score=0
    if r['rsi']>65: rsi_score=15  # overbought = good for shorts
    elif r['rsi']>50: rsi_score=10
    total=kol_score+lev_score+rsi_score
    unified.append({'base':base,'dir':'SHORT','entry':cur,'tp1':tp1,'stop':stop,'lev':fl,
        'kol_l':r['kol_long'],'kol_s':r['kol_short'],'rsi':r['rsi'],'risk':risk,
        'risk_l':risk_label(risk),'score':total,'pred':r['prediction']})

unified.sort(key=lambda x:x['score'],reverse=True)

def fmt(p,cur):
    if cur>100: return '{:.2f}'.format(p)
    if cur>10: return '{:.2f}'.format(p)
    if cur>1: return '{:.4f}'.format(p)
    return '{:.6f}'.format(p)

print()
print('='*130)
print('  UNIFIED RANKING - ALL COINS | 86 Coins x 87 Factors x 99 Traders')
print('='*130)
h='  Rank Dir  Coin      Entry       TP1(2x本金)   Stop/Liq     Lev   KOL L/S    RSI  Risk  Score'
print(h)
print('  '+'-'*115)

for i,r in enumerate(unified[:20],1):
    es=fmt(r['entry'],r['entry'])
    ts=fmt(r['tp1'],r['entry'])
    ss=fmt(r['stop'],r['entry'])
    arrow='BUY' if r['dir']=='LONG' else 'SELL'
    print('  {:4d} {:<5s} {:<8s} ${:<10s} ${:<10s} ${:<10s} {:>4d}x {:>3d}/{:>3d} {:>5.1f} {:<6s} {:>5.1f}'.format(
        i,arrow,r['base'],es,ts,ss,r['lev'],r['kol_l'],r['kol_s'],r['rsi'],r['risk_l'],r['score']))

print()
print('  TOP 3 DETAIL')
print('  '+'-'*60)
for r in unified[:3]:
    print('  ['+r['dir']+'] '+r['base']+' | Score: '+str(round(r['score'],1)))
    print('    Entry: ${:.4f} | TP1: ${:.4f} (+{:.1f}%) | Stop: ${:.4f} | Lev: {}x'.format(
        r['entry'],r['tp1'],100.0/r['lev'],r['stop'],r['lev']))
    print('    KOL: L={} S={} | RSI: {:.1f} | Risk: {} | 24h: {}'.format(
        r['kol_l'],r['kol_s'],r['rsi'],r['risk_l'],r['pred']))
    print()
