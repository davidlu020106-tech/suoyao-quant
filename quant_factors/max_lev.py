"""MAX LEVERAGE based on OKX perp limits"""
import json, urllib.request

def api_get(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

print('Fetching OKX perp leverage limits...')
inst=api_get('/api/v5/public/instruments?instType=SWAP')
lev={}
for i in inst.get('data',[]):
    if i['instId'].endswith('-USDT-SWAP'):
        base=i['instId'].replace('-USDT-SWAP','')
        l=i.get('lever','')
        if l: lev[base]=max(int(x) for x in l.split(','))
print('Got '+str(len(lev))+' contracts')

defaults={'BTC':125,'ETH':125,'SOL':75,'XRP':50,'DOGE':50,'ADA':50,'DOT':50,
    'LINK':50,'UNI':50,'AAVE':50,'LTC':50,'BCH':50,'ATOM':50,'OP':50,'ARB':50}

with open('quant_factors/full_scan_results.json','r',encoding='utf-8') as f:
    data=json.load(f)

def fmt(p,cur):
    if cur>100: return '{:.2f}'.format(p)
    if cur>10: return '{:.2f}'.format(p)
    if cur>1: return '{:.4f}'.format(p)
    return '{:.6f}'.format(p)

def risk_label(pct):
    if pct<3: return 'HIGH'
    if pct<8: return 'MID'
    return 'LOW'

print()
print('='*125)
print('  MAX LEVERAGE (OKX Perp Limits) - TP1=本金翻倍平50%, TP2不限利跑')
print('='*125)

for direction, items in [('LONG',data['longs'][:10]), ('SHORT',data['shorts'][:10])]:
    print()
    print('  TOP 10 '+direction)
    print('  '+'-'*115)
    print('  #  Coin      Entry       TP1(2x)      Stop/Liq     Lev    KOL L/S   RSI  风险  24h方向')
    print('  '+'-'*115)
    
    for i,r in enumerate(items,1):
        cur=r['entry']; base=r['base']
        okx_max=lev.get(base,defaults.get(base,10))
        final_lev=okx_max
        
        if direction=='LONG':
            tp1=cur*(1+1.0/final_lev)
            stop=cur*(1-1.0/final_lev)
        else:
            tp1=cur*(1-1.0/final_lev)
            stop=cur*(1+1.0/final_lev)
        
        risk=100.0/final_lev
        es=fmt(cur,cur); ts=fmt(tp1,cur); ss=fmt(stop,cur)
        
        print('  {:3d} {:<8s} ${:<10s} ${:<10s} ${:<10s} {:>4d}x {:>3d}/{:>3d} {:>5.1f} {:<6s} {}'.format(
            i,base,es,ts,ss,final_lev,r['kol_long'],r['kol_short'],r['rsi'],
            risk_label(risk),r['prediction']))

print()
print('  TOP 5 DETAIL')
print('  '+'-'*60)
for r in data['longs'][:3]+data['shorts'][:2]:
    cur=r['entry']; base=r['base']
    okx_max=lev.get(base,defaults.get(base,10))
    fl=okx_max
    direction='LONG'
    tp1=cur*(1+1.0/fl); stop=cur*(1-1.0/fl)
    
    print('  ['+direction+'] '+base+' | OKX Max: '+str(fl)+'x')
    print('    Entry: ${:.4f}'.format(cur))
    print('    TP1(本金翻倍): ${:.4f} (+{:.1f}%) -> 平50%'.format(tp1,100.0/fl))
    print('    Liq/Stop:     ${:.4f} (-{:.1f}%)'.format(stop,100.0/fl))
    print('    KOL: L='+str(r['kol_long'])+' S='+str(r['kol_short'])+' bias={:+.4f}'.format(r['kol_avg']))
    print('    RSI: {:.1f} | 24h: {}'.format(r['rsi'],r['prediction']))
    print()
