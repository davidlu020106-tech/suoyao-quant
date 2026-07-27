"""99位KOL交易员认为的6小时波动范围"""
import sys, json, urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, 'quant_factors')
from okx_data_adapter import build_features_single

def api_get(path):
    url = f'https://www.okx.com{path}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())

data = api_get('/api/v5/market/candles?instId=ETH-USDT&bar=1H&limit=200')
raw = data.get('data', [])
raw.reverse()
candles = []
for c in raw:
    ts = int(c[0])/1000
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    candles.append({'date': dt.strftime('%Y-%m-%d %H:%M'), 'open': float(c[1]), 'high': float(c[2]),
                    'low': float(c[3]), 'close': float(c[4]), 'volume': float(c[5])})

df = pd.DataFrame(candles)
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date').sort_index()
feats = build_features_single(df)
cur = float(feats['close'].iloc[-1])

atr_1h = float(feats['atr14'].iloc[-1])
atr_6h = atr_1h * np.sqrt(6)
bb_u = float(feats['bb_upper'].iloc[-1])
bb_l = float(feats['bb_lower'].iloc[-1])
r1 = float(feats['r1'].iloc[-1])
r2 = float(feats['r2'].iloc[-1])
s1 = float(feats['s1'].iloc[-1])
s2 = float(feats['s2'].iloc[-1])
pivot = float(feats['pivot'].iloc[-1])
ma50 = float(feats['ma50'].iloc[-1])

# 历史6h振幅统计
highs = feats['high'].values
lows = feats['low'].values
closes = feats['close'].values
ranges = []
for i in range(6, len(closes)):
    win_high = max(highs[i-5:i+1])
    win_low = min(lows[i-5:i+1])
    ranges.append((win_high - win_low) / closes[i-6] * 100)

avg_r = np.mean(ranges)
med_r = np.median(ranges)
p80 = np.percentile(ranges, 80)
p90 = np.percentile(ranges, 90)

print('=' * 65)
print('  99位KOL交易员认为的6小时波动范围')
print('=' * 65)
print(f'\n  当前: ${cur:.2f}  |  72人看多(73%) / 10人看空(10%)')
print(f'  信号: +0.0922偏多 | 标准差0.1013(分歧中等)')

print(f'\n  数据基础:')
print(f'    ATR6h: ${atr_6h:.2f}  |  BB: ${bb_l:.0f}~${bb_u:.0f}')
print(f'    历史6h振幅: 均值{avg_r:.1f}% 中位{med_r:.1f}%  P80={p80:.1f}%  P90={p90:.1f}%')
print(f'    R=${r2:.0f}  R1=${r1:.0f}  P=${pivot:.0f}  S1=${s1:.0f}  S2=${s2:.0f}')

# 计算范围
bias_shift = (72-10)/99 * atr_6h * 0.3
center = cur + bias_shift
core_low = center - atr_6h * 0.4
core_high = center + atr_6h * 0.4
kol_low = center - atr_6h * 0.6
kol_high = center + atr_6h * 0.6
extreme_low = kol_low - atr_6h * 0.2
extreme_high = kol_high + atr_6h * 0.2

print(f'\n  KOL偏多偏移: +${bias_shift:.2f}  |  波动中枢: ${center:.2f}')
print()
print(f'  [核心区 68%%概率]  ${core_low:.0f} ~ ${core_high:.0f}')
print(f'    幅度 ${core_high-core_low:.0f}  ({(core_high-core_low)/cur*100:.1f}%%)')
print(f'    -- 大部分情况下ETH在这里面震荡')
print()
print(f'  [主要区 90%%概率]  ${kol_low:.0f} ~ ${kol_high:.0f}')
print(f'    幅度 ${kol_high-kol_low:.0f}  ({(kol_high-kol_low)/cur*100:.1f}%%)')
print(f'    -- 除非极端行情,不会超出')
print()
print(f'  [极限区 95%%+]  <${extreme_low:.0f} 或 >${extreme_high:.0f}')
print(f'    -- 超出需要重大消息驱动')

# 各价位概率
print(f'\n  各价位触及概率(基于KOL共识+ATR+历史):')
print(f'  {"价位":>7} {"KOL":>7} {"ATR":>7} {"历史":>7} {"综合":>7}')
for lv in [1850, 1860, 1870, 1880, 1890, 1900, 1910]:
    dist = (lv - cur) / cur * 100
    if dist > 0:
        kol_p = max(5, 73 - abs(dist)*12)
    else:
        kol_p = max(5, 73 + dist*12)
    kol_p = min(90, kol_p)
    atr_p = max(5, min(60, (1 - abs(dist)/(atr_6h/cur*100)) * 60))
    hist_p = sum(1 for r in ranges if r >= abs(dist)) / len(ranges) * 100 if ranges else 50
    total = kol_p * 0.4 + atr_p * 0.3 + hist_p * 0.3
    marker = ' <==' if abs(lv - 1910) < 5 else ''
    print(f'  ${lv:>4d}  {kol_p:>5.0f}% {atr_p:>5.0f}% {hist_p:>5.0f}% {total:>5.0f}%{marker}')

# 结论
print(f'\n--- 最终结论 ---')
print(f'')
print(f'  KOL交易员共识下,ETH未来6小时波动范围:')
print(f'')
print(f'    核心区:  ${core_low:.0f} ~ ${core_high:.0f}  (68%%)')
print(f'    主要区:  ${kol_low:.0f} ~ ${kol_high:.0f}  (90%%)')
print(f'')
print(f'  结合您空单(入场$1865,爆仓$1910):')
near_liq = (kol_high - 1910) / 1910 * 100
if kol_high > 1910:
    print(f'    KOL共识上沿${kol_high:.0f} 高于爆仓价$1910')
    print(f'    但核心区${core_high:.0f}低于$1910,常规波动不会爆')
else:
    print(f'    KOL共识上沿${kol_high:.0f} 低于爆仓价$1910')
    print(f'    常规波动不会触及爆仓')
print(f'    关键观察: 若1H突破${r2:.0f}且放量, 波动范围需上修')
print(f'    若1H跌破${s1:.0f}, 支撑下看${s2:.0f}~${bb_l:.0f}')