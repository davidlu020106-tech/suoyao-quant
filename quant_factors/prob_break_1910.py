"""ETH 突破 $1910 概率分析 - 99位KOL + 6项统计方法"""
import sys, json, urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, 'quant_factors')
from okx_data_adapter import build_features_single

# 1. 拉数据
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
target = 1910.0
dist_pct = (target - cur) / cur * 100
dist_abs = target - cur

atr_1h = float(feats['atr14'].iloc[-1])
atr_6h = atr_1h * np.sqrt(6)
bb_upper = float(feats['bb_upper'].iloc[-1])
bb_lower = float(feats['bb_lower'].iloc[-1])
r1 = float(feats['r1'].iloc[-1])
r2 = float(feats['r2'].iloc[-1])
ma50 = float(feats['ma50'].iloc[-1])
ma200 = float(feats['ma200'].iloc[-1])
rsi = float(feats['rsi14'].iloc[-1])

print('=' * 70)
print('  ETH突破$1,910概率分析 - 6小时窗口')
print('=' * 70)
print(f'  当前价格:     ${cur:.2f}')
print(f'  目标:         ${target:.0f}')
print(f'  需涨幅:       {dist_pct:+.2f}% (${dist_abs:.2f})')
print(f'  6h ATR推演:   ${atr_6h:.2f} ({atr_6h/cur*100:.2f}%)')
print(f'  BB上轨:       ${bb_upper:.2f}')
print(f'  R1/R2:        ${r1:.2f} / ${r2:.2f}')
print(f'  MA50/200:     ${ma50:.0f} / ${ma200:.0f}')
print(f'  RSI14:        {rsi:.1f}')

# 2. 统计概率
print('\n--- 1. 历史统计 (过去200h, 6h滑动窗口) ---')
closes = feats['close'].values
highs = feats['high'].values
six_h_highs = []
for i in range(6, len(closes)):
    start_px = closes[i-6]
    win_high = max(highs[i-5:i+1])
    six_h_highs.append((win_high - start_px) / start_px * 100)

total_w = len(six_h_highs)
c2 = sum(1 for r in six_h_highs if r >= 2.0)
c1_5 = sum(1 for r in six_h_highs if r >= 1.5)
c1 = sum(1 for r in six_h_highs if r >= 1.0)
c_needed = sum(1 for r in six_h_highs if r >= dist_pct)

print(f'  样本: {total_w}个6h窗口')
print(f'  涨>=2.0%: {c2}次 ({c2/total_w*100:.0f}%)')
print(f'  涨>=1.5%: {c1_5}次 ({c1_5/total_w*100:.0f}%)')
print(f'  涨>=1.0%: {c1}次 ({c1/total_w*100:.0f}%)')
hist_prob = c_needed / total_w * 100 if total_w > 0 else 25
print(f'  涨>={dist_pct:.1f}%: {c_needed}次 ({hist_prob:.0f}%)  <- 直接匹配')

# 3. ATR概率
print('\n--- 2. ATR波动率法 ---')
atr_ratio = dist_abs / atr_6h
# 价格在6h内移动超过1倍ATR的概率约32%, 2倍ATR约5%
if atr_ratio <= 0.5:
    atr_prob = 50
elif atr_ratio <= 1.0:
    atr_prob = 35 - (atr_ratio - 0.5) * 30
elif atr_ratio <= 1.5:
    atr_prob = 18 - (atr_ratio - 1.0) * 26
elif atr_ratio <= 2.0:
    atr_prob = 5 - (atr_ratio - 1.5) * 8
else:
    atr_prob = 3
atr_prob = max(1, min(60, atr_prob))
print(f'  需{atr_ratio:.1f}倍ATR -> 概率约{atr_prob:.0f}%')

# 4. BB突破概率
print('\n--- 3. 布林带法 ---')
bb_dist = (bb_upper - cur) / cur * 100
print(f'  价格距BB上轨: {bb_dist:.2f}% (${bb_upper-cur:.2f})')
print(f'  BB上轨= ${bb_upper:.2f}')
bb_prob = 5 if cur > bb_upper else (15 if abs(cur-bb_upper)/cur < 0.005 else 25)
print(f'  突破BB上轨概率: ~{bb_prob}%')

# 5. RSI动能
print('\n--- 4. RSI动能法 ---')
print(f'  RSI14={rsi:.1f}')
if rsi > 70:
    rsi_prob = 5
    rsi_note = '超买,难继续涨'
elif rsi > 60:
    rsi_prob = 25
    rsi_note = '偏强,有动能'
elif rsi > 50:
    rsi_prob = 20
    rsi_note = '中性偏强'
elif rsi > 40:
    rsi_prob = 15
    rsi_note = '中性偏弱'
elif rsi > 30:
    rsi_prob = 10
    rsi_note = '弱'
else:
    rsi_prob = 5
    rsi_note = '超卖'
print(f'  RSI推断概率: {rsi_prob}% ({rsi_note})')

# 6. 阻力位突破概率
print('\n--- 5. 阻力位法 ---')
print(f'  到R1(${r1:.0f})距: ${r1-cur:.1f} ({(r1-cur)/cur*100:.2f}%)')
print(f'  到R2(${r2:.0f})距: ${r2-cur:.1f} ({(r2-cur)/cur*100:.2f}%)')
print(f'  到目标(${target:.0f})距: ${target-cur:.1f} ({(target-cur)/cur*100:.2f}%)')
# R2 is a strong resistance. Target is above R2.
if target <= r1:
    res_prob = 35
elif target <= r2:
    res_prob = 20
else:
    res_prob = 10
print(f'  阻力位推断: 目标在R2上方 -> {res_prob}%')

# 7. KOL共识
print('\n--- 6. KOL交易员共识法 ---')
kol_bull_pct = 73.0  # from earlier analysis
kol_bear_pct = 10.0
# 看多比例越高,向上突破概率越大
kol_prob = 15 + kol_bull_pct * 0.3
kol_prob = min(50, kol_prob)
print(f'  73%交易员看多 -> 向上概率加成 -> {kol_prob:.0f}%')

# 加权综合
print('\n' + '=' * 70)
print('  综合概率计算')
print('=' * 70)
weights = {
    '历史统计': (hist_prob, 0.25),
    'ATR波动率': (atr_prob, 0.20),
    '布林带': (bb_prob, 0.15),
    'RSI动能': (rsi_prob, 0.10),
    '阻力位': (res_prob, 0.15),
    'KOL共识': (kol_prob, 0.15),
}

weighted_sum = 0
total_wt = 0
print(f'  {"方法":<12} {"概率":>6} {"权重":>6} {"加权":>8}')
print(f'  {"-"*12} {"-"*6} {"-"*6} {"-"*8}')
for name, (prob, wt) in weights.items():
    contrib = prob * wt
    weighted_sum += contrib
    total_wt += wt
    print(f'  {name:<12} {prob:>5.0f}% {wt:>5.1f}  {contrib:>6.1f}%')

final_prob = weighted_sum / total_wt if total_wt > 0 else 25
print(f'  {"综合":<12} {final_prob:>5.0f}%')
print()

print(f'--- 最终结论 ---')
print(f'  未来6小时ETH突破$1,910的概率: {final_prob:.0f}%')
print(f'')
if final_prob < 15:
    print(f'  判断: 小概率事件,不建议做多突破')
elif final_prob < 30:
    print(f'  判断: 低概率,突破难度大,倾向于震荡')
elif final_prob < 45:
    print(f'  判断: 中等偏低,需要放量配合')
elif final_prob < 60:
    print(f'  判断: 中等概率,有可能但不确定')
else:
    print(f'  判断: 高概率,突破是大概率事件')
print(f'')
print(f'  {final_prob:.0f}% - 综合6个维度(历史+波动率+布林带+RSI+阻力位+KOL共识)')
print(f'  主要阻力: BB上轨${bb_upper:.0f}和R2${r2:.0f}之间需放量突破')
print(f'  关键观察: 若1H收盘站上${r2:.0f}+放量,概率升至60%+')
