"""Print saved 4H predictions"""
import json
with open('quant_factors/4h_predictions.json','r',encoding='utf-8') as f:
    data=json.load(f)

print('4H KOL Predictions - '+data['timestamp'])
print('='*95)
print('  #  Coin     Price      R1         S1         KOL L/S     Signal   Dir  RSI   MA')
print('-'*95)
items=sorted(data['predictions'].items())
for i,(base,p) in enumerate(items,1):
    d='BULL' if p['direction']=='BULL' else 'BEAR' if p['direction']=='BEAR' else 'NEUT'
    ma='BOTH' if p['above_ma50'] and p['above_ma200'] else 'MA50' if p['above_ma50'] else 'NONE'
    print('  {:3d} {:<6s} ${:<8.4f} ${:<8.4f} ${:<8.4f} {:>3d}/{:>3d}   {:>+7.4f} {:>5s} {:>5.1f} {:>4s}'.format(
        i,base,p['price'],p['r1'],p['s1'],p['kol_bull'],p['kol_bear'],p['kol_signal'],d,p['rsi'],ma))
