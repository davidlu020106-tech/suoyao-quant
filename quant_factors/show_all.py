import json
with open('quant_factors/continuous_ranking.json','r',encoding='utf-8') as f:
    data=json.load(f)
print('='*130)
print('  FULL RANKING ('+str(len(data))+' coins) - 2026-07-25')
print('='*130)
print('  #  Dir  Coin     Entry       TP1          Lev  KOL     Signal   RSI  TP1h')
print('-'*130)
for i,r in enumerate(data,1):
    es='{:.4f}'.format(r['entry']) if r['entry']<10 else '{:.2f}'.format(r['entry'])
    ts='{:.4f}'.format(r['tp1']) if r['entry']<10 else '{:.2f}'.format(r['tp1'])
    kol=str(r['kol_bull'])+'/'+str(r['kol_bear'])
    h=r.get('tp1_hit',0); t=r.get('tp1_total',0)
    print('  {:2d}  {:<4s} {:<6s} ${:<10s} ${:<10s} {:>4d}x {:>6s} {:>+8.4f} {:>5.1f} {:>2d}/{:>2d}'.format(
        i,r['dir'],r['base'],es,ts,r['lev'],kol,r['signal'],r['rsi'],h,t))
