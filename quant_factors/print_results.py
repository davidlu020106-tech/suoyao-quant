"""Recalculate with ATR-based leverage"""
import json

with open('quant_factors/full_scan_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def fmt_price(p, cur):
    if cur > 100: return '{:.1f}'.format(p)
    if cur > 10: return '{:.2f}'.format(p)
    if cur > 1: return '{:.4f}'.format(p)
    return '{:.6f}'.format(p)

def fmt_range(lo, hi):
    if lo > 100: return '{:.0f}-{:.0f}'.format(lo, hi)
    if lo > 1: return '{:.2f}-{:.2f}'.format(lo, hi)
    return '{:.4f}-{:.4f}'.format(lo, hi)

print()
print('=' * 115)
print('  TOP 10 LONG - TP1=本金翻倍 | 止损=15% | 最大杠杆')
print('=' * 115)
h = '  #  Coin      Entry       Limit       TP1(2x)     Stop(15%)    Lev  KOL L/S  RSI  24h Range'
print(h)
print('  ' + '-' * 100)

for i, r in enumerate(data['longs'][:10], 1):
    cur = r['entry']
    stop_pct = 0.20 if r.get('rsi', 50) < 35 else 0.15
    lev = min(50, int(1.0 / stop_pct))
    tp1 = cur * (1 + 1.0/lev)
    stop = cur * (1 - stop_pct)
    
    es = fmt_price(cur, cur)
    ls = fmt_price(r['limit'], cur)
    ts = fmt_price(tp1, cur)
    ss = fmt_price(stop, cur)
    rs = fmt_range(r['24h_low'], r['24h_high'])
    
    print('  {:3d} {:<8s} ${:<10s} ${:<10s} ${:<10s} ${:<10s} {:>4.0f}x {:>3d}/{:<3d} {:>5.1f} {}'.format(
        i, r['base'], es, ls, ts, ss, lev, r['kol_long'], r['kol_short'], r['rsi'], rs))

print()
print('=' * 115)
print('  TOP 10 SHORT - TP1=本金翻倍 | 止损=15% | 最大杠杆')
print('=' * 115)
print(h)
print('  ' + '-' * 100)

for i, r in enumerate(data['shorts'][:10], 1):
    cur = r['entry']
    stop_pct = 0.20 if r.get('rsi', 50) > 65 else 0.15
    lev = min(50, int(1.0 / stop_pct))
    tp1 = cur * (1 - 1.0/lev)
    stop = cur * (1 + stop_pct)
    
    es = fmt_price(cur, cur)
    ls = fmt_price(r['limit'], cur)
    ts = fmt_price(tp1, cur)
    ss = fmt_price(stop, cur)
    rs = fmt_range(r['24h_low'], r['24h_high'])
    
    print('  {:3d} {:<8s} ${:<10s} ${:<10s} ${:<10s} ${:<10s} {:>4.0f}x {:>3d}/{:<3d} {:>5.1f} {}'.format(
        i, r['base'], es, ls, ts, ss, lev, r['kol_long'], r['kol_short'], r['rsi'], rs))

print()
print('TOP 3 DETAIL')
print('-' * 60)
for r in data['longs'][:3] + data['shorts'][:2]:
    cur = r['entry']
    sp = 0.20 if r.get('rsi', 50) < 35 else 0.15
    lev = min(50, int(1.0 / sp))
    if r['direction'] == 'LONG':
        tp1 = cur * (1 + 1.0/lev); stop = cur * (1 - sp)
    else:
        tp1 = cur * (1 - 1.0/lev); stop = cur * (1 + sp)
    
    print('  [' + r['direction'] + '] ' + r['base'])
    print('    Entry: ${:.4f} | Limit: ${:.4f} ({})'.format(cur, r['limit'], r['reason']))
    print('    TP1:   ${:.4f} (+{:.1f}%) | Stop: ${:.4f} | Lev: {}x'.format(tp1, 100/lev, stop, lev))
    print('    KOL: L={} S={} bias={:+.4f} | RSI: {:.1f}'.format(r['kol_long'], r['kol_short'], r['kol_avg'], r['rsi']))
    print('    24h: {} | Range: ${:.4f} ~ ${:.4f}'.format(r['prediction'], r['24h_low'], r['24h_high']))
    print()
