"""Full ranking with new continuous scoring system"""
import sys, os, json, requests, pandas as pd, numpy as np
from datetime import datetime, timezone
sys.path.insert(0, 'quant_factors')
from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single
from continuous_scores import continuous_score_all

profs = {}
for f in sorted(os.listdir('profiles_v2')):
    if f.endswith('.json'):
        try: profs[f.replace('.json','')] = json.load(open('profiles_v2/'+f, encoding='utf-8'))
        except: pass

rids = set(CAP_REGISTRY.keys())
def mc(pid, rids):
    if pid in rids: return pid
    parts = pid.split('_')
    if len(parts)>=2 and parts[0]=='cap' and parts[1].isdigit():
        p = 'cap_'+parts[1]; m = [c for c in rids if c.startswith(p+'_')]
        return m[0] if m else None
    return None

inst = requests.get('https://www.okx.com/api/v5/public/instruments?instType=SWAP',
    headers={'User-Agent':'Mozilla/5.0'}, timeout=10).json()
lev = {}
for i in inst.get('data',[]):
    if i['instId'].endswith('-USDT-SWAP'):
        base = i['instId'].replace('-USDT-SWAP','')
        l = i.get('lever','')
        if l: lev[base] = max(int(x) for x in l.split(','))

coins = ['BTC','ETH','SOL','XRP','DOGE','ADA','LINK','DOT','UNI','AAVE','LTC','BCH',
         'ORDI','ALLO','APE','ZEC','HYPE','LIT','EDGE','PI','POR','OP','WLD','SUI','NEAR']
results = []

for base in coins:
    try:
        d = requests.get('https://www.okx.com/api/v5/market/candles?instId='+base+'-USDT&bar=1D&limit=200',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10).json()
        raw = d.get('data',[]); raw.reverse()
        if not raw: continue
        cdl = []
        for x in raw:
            ts = int(x[0])/1000; dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            cdl.append({'date':dt.strftime('%Y-%m-%d'),'open':float(x[1]),'high':float(x[2]),
                        'low':float(x[3]),'close':float(x[4]),'volume':float(x[5])})
        df = pd.DataFrame(cdl); df['date'] = pd.to_datetime(df['date']); df = df.set_index('date').sort_index()
        feats = build_features_single(df); lat = feats.iloc[-1]
        cur = float(lat['close'])

        sigs = []
        for h, p in profs.items():
            tw, ws = 0.0, 0.0
            for cap in (p.get('capabilities_used',[]) or []):
                rid = cap.get('id',''); w = float(cap.get('weight',0))
                mid = mc(rid, rids)
                if mid:
                    s = continuous_score_all(mid, lat, feats)
                    if s != 0: ws += w*s; tw += abs(w)
            if tw > 0: sig = ws/tw
            else:
                b = p.get('bias_default','neutral')
                sig = 0.15 if b=='long_tilted' else (-0.15 if b=='short_tilted' else 0.0)
            sigs.append(sig)

        arr = np.array(sigs)
        ln = int(np.sum(arr>0.03)); sn = int(np.sum(arr<-0.03)); nn = len(arr)-ln-sn
        av = float(np.mean(arr)); fl = lev.get(base, 10)

        if av > 0.02: dire = 'BUY'; tp1 = cur*(1+1.0/fl)
        elif av < -0.02: dire = 'SELL'; tp1 = cur*(1-1.0/fl)
        else: continue

        results.append({'base':base, 'dir':dire, 'entry':cur, 'tp1':tp1, 'lev':fl,
            'kol_bull':ln, 'kol_bear':sn, 'kol_neu':nn, 'signal':round(av,4),
            'rsi':round(float(lat['rsi14']),1)})
        print(f'  {base:<6s} {dire:5s} {ln:>2d}/{sn:<2d} sig={av:+.4f}')
    except Exception as e:
        print(f'  {base}: skip - {str(e)[:30]}')

results.sort(key=lambda x: abs(x['signal']), reverse=True)
print()
print('='*110)
print('TOP 10 - CONTINUOUS SCORING SYSTEM')
print('='*110)
h = '  #  Dir   Coin     Entry       TP1(翻倍)     Lev  KOL L/S   Signal   RSI'
print(h); print('-'*90)

for i, r in enumerate(results[:10], 1):
    es = '{:.2f}'.format(r['entry']) if r['entry']>10 else '{:.4f}'.format(r['entry'])
    ts = '{:.2f}'.format(r['tp1']) if r['entry']>10 else '{:.4f}'.format(r['tp1'])
    print('  {:2d}  {:<5s} {:<6s} ${:<10s} ${:<10s} {:>4d}x {:>3d}/{:>3d} {:>+8.4f} {:>5.1f}'.format(
        i, r['dir'], r['base'], es, ts, r['lev'], r['kol_bull'], r['kol_bear'], r['signal'], r['rsi']))

out_path = os.path.join('quant_factors', 'continuous_ranking.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f'\nSaved: {out_path}')
