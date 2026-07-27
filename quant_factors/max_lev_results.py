"""Recalculate with MAXIMUM leverage based on S2/R2"""
import json, urllib.request

with open('quant_factors/full_scan_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def api_get(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

# Get OKX max leverage per coin from instruments
print('Fetching max leverage limits...')
inst=api_get('/api/v5/public/instruments?instType=SPOT')
lev_map={}
for i in inst.get('data',[]):
    base=i['baseCcy']; l=i.get('lever','')
    if l and l!='': lev_map[base]=max(1,int(l.split(',')[0]))
print('  Got '+str(len(lev_map))+' coin limits')

def fmt(p, cur):
    if cur>100: return '{:.2f}'.format(p)
    if cur>10: return '{:.2f}'.format(p)
    if cur>1: return '{:.4f}'.format(p)
    return '{:.6f}'.format(p)

print()
print('=' * 120)
print('  MAX LEVERAGE RESULTS - TP1=本金翻倍 | 爆仓=S2(多)/R2(空)')
print('=' * 120)

for direction, label in [('longs','LONG'), ('shorts','SHORT')]:
    print()
    print('  TOP 10 '+label)
    print('  ' + '-' * 105)
    h = '  #  Coin      Entry       TP1(2x本金)   TP2(不限)    Liq/Stop     MaxLev  OKX限  R1/R2%  KOL L/S'
    print(h)
    print('  ' + '-' * 105)
    
    items = data[direction][:10]
    for i, r in enumerate(items, 1):
        cur = r['entry']
        if direction == 'longs':
            # Max leverage based on S2
            s2 = r.get('s2', 0)
            if s2 <= 0 or cur <= s2:
                # Fallback: use 50% as S2 proxy
                s2 = cur * 0.5
            max_lev = int(min(125, cur / (cur - s2))) if cur > s2 else 1
            if max_lev < 1: max_lev = 1
            tp1 = cur * (1 + 1.0/max_lev)
            tp2 = r.get('r2', cur * 1.5)
            liq = s2
            okx_lim = lev_map.get(r['base'], 10)
            final_lev = min(max_lev, okx_lim)
        else:
            r2 = r.get('r2', 0)
            if r2 <= cur: r2 = cur * 2
            max_lev = int(min(125, cur / (r2 - cur))) if r2 > cur else 1
            if max_lev < 1: max_lev = 1
            tp1 = cur * (1 - 1.0/max_lev)
            tp2 = r.get('s2', cur * 0.5)
            liq = r2
            okx_lim = lev_map.get(r['base'], 10)
            final_lev = min(max_lev, okx_lim)
        
        if final_lev < 1: final_lev = 1
        
        es = fmt(cur, cur)
        ts = fmt(tp1, cur)
        t2s = fmt(tp2, cur)
        ls = fmt(liq, cur)
        
        print('  {:3d} {:<8s} ${:<10s} ${:<10s} ${:<10s} ${:<10s} {:>4d}x {:>4d}x  {:>+5.1f}%  {:>3d}/{:>3d}'.format(
            i, r['base'], es, ts, t2s, ls, final_lev, okx_lim, 
            (abs(cur-tp1)/cur*100) if direction=='longs' else (abs(cur-tp1)/cur*100),
            r['kol_long'], r['kol_short']))

print()
print('  TOP 3 DETAIL - MAX LEVERAGE')
print('  ' + '-' * 60)
for direction, items in [('LONG', data['longs'][:3]), ('SHORT', data['shorts'][:2])]:
    for r in items:
        cur = r['entry']
        if direction == 'LONG':
            s2 = r.get('s2', cur*0.5)
            if s2 <= 0: s2 = cur*0.5
            ml = int(min(125, cur/(cur-s2))) if cur>s2 else 1
            tp1 = cur*(1+1.0/ml)
            liq = s2
        else:
            r2 = r.get('r2', cur*2)
            if r2 <= cur: r2 = cur*2
            ml = int(min(125, cur/(r2-cur))) if r2>cur else 1
            tp1 = cur*(1-1.0/ml)
            liq = r2
        okx_lim = lev_map.get(r['base'], 10)
        final_lev = min(ml, okx_lim)
        
        print('  ['+direction+'] '+r['base'])
        print('    Entry: ${:.4f} | Limit: ${:.4f} ({})'.format(cur, r['limit'], r['reason']))
        print('    TP1(本金翻倍): ${:.4f} (+{:.1f}%)  → 平50%'.format(tp1, 100/final_lev))
        print('    Liq/Stop: ${:.4f} | Leverage: {}x (OKX max: {}x)'.format(liq, final_lev, okx_lim))
        print('    KOL: L={} S={} bias={:+.4f} | RSI: {:.1f}'.format(r['kol_long'],r['kol_short'],r['kol_avg'],r['rsi']))
        print('    24h: {} | ${:.4f} ~ ${:.4f}'.format(r['prediction'],r['24h_low'],r['24h_high']))
        print()
