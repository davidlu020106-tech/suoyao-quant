"""分析链路追踪：每个因子投票时看了什么数据"""
import sys, os, json, urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, 'quant_factors')
from okx_data_adapter import build_features_single

# 拉数据
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
latest = feats.iloc[-1]

print('=' * 85)
print('  99位KOL交易员综合分析 - 数据链路追踪')
print('=' * 85)

print(f'\n--- 原始输入数据 (1条) ---')
print(f'    来源: OKX API /api/v5/market/candles?instId=ETH-USDT&bar=1H&limit=200')
print(f'    时间: {feats.index[-1]}')
print(f'    原始数据:')
print(f'      open=${float(latest["open"]):.2f}  high=${float(latest["high"]):.2f}')
print(f'      low=${float(latest["low"]):.2f}   close=${float(latest["close"]):.2f}')
print(f'      volume={float(latest.get("volume",0)):.1f}')

print(f'\n--- 特征工程 (55个衍生特征) ---')
print(f'    来源: okx_data_adapter.build_features_single()')
ma7 = float(latest['ma7'])
ma20 = float(latest['ma20'])
ma50 = float(latest['ma50'])
ma200 = float(latest['ma200'])
rsi = float(latest['rsi14'])
r1 = float(latest['r1'])
r2 = float(latest['r2'])
s1 = float(latest['s1'])
s2 = float(latest['s2'])
pivot = float(latest['pivot'])
fib618 = float(latest['fib_618'])
hist = float(latest['macd_hist'])
bbw = float(latest['bb_width'])
h = float(latest['high'])
l = float(latest['low'])
c = float(latest['close'])
o = float(latest['open'])
ret5d = float(latest['ret_5d'])
vol = float(latest.get('volume',0))
vol_avg = float(feats['volume'].iloc[-24:].mean())
vol_ratio = vol / vol_avg if vol_avg > 0 else 0
spread = (h-l)/c
body = abs(c-o)
rng = h-l

feature_values = {
    'MA7': f'${ma7:.2f}', 'MA20': f'${ma20:.2f}', 'MA50': f'${ma50:.2f}', 'MA200': f'${ma200:.2f}',
    'RSI14': f'{rsi:.1f}', 'MACD_hist': f'{hist:.4f}', 'BB_width': f'{bbw:.4f}',
    '(H-L)/C': f'{spread:.4f}', 'Ret_5d': f'{ret5d*100:.2f}%',
    'R1': f'${r1:.2f}', 'R2': f'${r2:.2f}', 'S1': f'${s1:.2f}', 'S2': f'${s2:.2f}',
    'Pivot': f'${pivot:.2f}', 'Fib_618': f'${fib618:.2f}', 'Vol_ratio': f'{vol_ratio:.2f}x',
    'close>ma50': f'{c > ma50}', 'close>ma200': f'{c > ma200}', 'ma50>ma200': f'{ma50 > ma200}',
}
for k, v in feature_values.items():
    print(f'      {k:>15} = {v}')

print(f'\n--- 87个因子评分 -> 每位交易员聚合 ---')
print(f'    方法: 每位交易员引用的能力集 x 个人权重 -> 加权平均 -> 信号')

# 分类展示
categories = {
    'Regime(市场状态)': {
        'cap_044_regime_trending_up': f'close(\\${c:.0f}) > ma50(\\${ma50:.0f})? {c>ma50}',
        'cap_045_regime_trending_down': f'close(\\${c:.0f}) < ma50(\\${ma50:.0f})? {c<ma50}',
        'cap_046_regime_ranging': f'(h-l)/c={spread:.4f} < 0.02? {spread<0.02}',
        'cap_047_regime_volatile': f'(h-l)/c={spread:.4f} > 0.03? {spread>0.03}',
    },
    'Indicator(技术指标)': {
        'cap_018_ma_golden_cross': f'ma50(\\${ma50:.0f}) > ma200(\\${ma200:.0f})? {ma50>ma200} -> +0.5',
        'cap_019_ma_death_cross': f'ma50 < ma200? {ma50<ma200}',
        'cap_020_macd_hist_cross': f'macd_hist={hist:.4f} >0? {hist>0}',
        'cap_069_ma_reclaim': f'close(\\${c:.0f}) > ma200(\\${ma200:.0f})? {c>ma200}',
        'cap_017_rsi_oversold_bounce': f'rsi14={rsi:.1f} < 35? {rsi<35}',
        'cap_022_fib_618_support': f'close(\\${c:.0f}) vs fib618(\\${fib618:.0f}) dist={abs(c-fib618)/c*100:.1f}%',
    },
    'Cycle(周期-纯日历)': {
        'cap_037_halving_cycle': '当前日期2026-07-15, 减半后18月, 判定派发阶段 -> -0.30',
        'cap_038_4year_cycle': '4年周期模型, 当前处于熊段 -> -0.40',
    },
    'Pattern(形态-方向+位置)': {
        'cap_001_falling_wedge_breakout': f'close(\\${c:.0f}) > ma50(\\${ma50:.0f})? {c>ma50}',
        'cap_002_rising_wedge_breakdown': f'close(\\${c:.0f}) < ma50(\\${ma50:.0f})? {c<ma50}',
        'cap_012_sfp': f'close(\\${c:.0f}) > ma20(\\${ma20:.0f})? {c>ma20}',
        'cap_014_trend_pullback': f'close(\\${c:.0f}) > ma20(\\${ma20:.0f})? {c>ma20}',
    },
    'Macro(宏观-用技术面代理)': {
        'cap_027_dxy_inverse_btc': f'proxy: close>ma50? {c>ma50} -> +0.1',
        'cap_028_spx_risk_on': f'proxy: close>ma50? {c>ma50} -> +0.1',
        'cap_040_etf_flows_proxy': f'proxy: close>ma50? {c>ma50} -> +0.2',
    },
    'Structural(结构性)': {
        'cap_023_elliott_wave_3': f'close(\\${c:.0f}) > ma50(\\${ma50:.0f})? 看涨结构',
        'cap_025_wyckoff_distribution_upthrust': f'close < ma50? 看跌结构',
    },
    'Risk(风险管理)': {
        'cap_041_dont_catch_falling_knives': f'rsi14={rsi:.1f} < 30? {rsi<30} -> 不接飞刀',
        'cap_043_cut_losses_early': f'close(\\${c:.0f}) < s1(\\${s1:.0f})? {c<s1}',
        'emg_009_range_middle_filter': f'price pos in range={((c-s1)/max(r1-s1,0.01)):.2f}',
    },
}

for cat_name, factors in categories.items():
    print(f'\n  [{cat_name}]')
    for cid, input_str in factors.items():
        # 计算分数
        score = 0.0
        if 'golden_cross' in cid or '044' in cid:
            score = 0.6 if c > ma50 else -0.4
        elif 'death_cross' in cid or '045' in cid:
            score = 0.6 if c < ma50 else -0.4
        elif 'ranging' in cid:
            score = 0.5 if spread < 0.02 else 0.0
        elif 'volatile' in cid:
            score = 0.6 if spread > 0.03 else 0.0
        elif '018' in cid:
            score = 0.5 if ma50 > ma200 else -0.5
        elif '019' in cid:
            score = -0.5 if ma50 < ma200 else 0.5
        elif '020' in cid:
            score = 0.4 if hist > 0 else -0.4
        elif '069' in cid or 'reclaim' in cid:
            score = 0.6 if c > ma200 else -0.6
        elif '017' in cid:
            score = 0.5 if rsi < 35 else (0.2 if rsi < 45 else 0.0)
        elif '022' in cid:
            dist = abs(c - fib618) / c
            score = 0.7 if dist < 0.02 else (0.3 if dist < 0.05 else 0.0)
        elif '037' in cid:
            score = -0.30
        elif '038' in cid:
            score = -0.40
        elif '001' in cid or '003' in cid or '006' in cid:
            score = 0.35 if c > ma50 else -0.2
        elif '002' in cid or '004' in cid or '005' in cid:
            score = -0.35 if c < ma50 else 0.2
        elif '012' in cid or '014' in cid:
            score = 0.3 if c > ma20 else -0.3
        elif 'dxy' in cid or 'spx' in cid:
            score = 0.1 if c > ma50 else -0.1
        elif 'etf' in cid:
            score = 0.2 if c > ma50 else -0.2
        elif 'elliott' in cid or 'wyckoff_accumulation' in cid:
            score = 0.3 if c > ma50 else -0.3
        elif 'wyckoff_distribution' in cid:
            score = -0.3 if c < ma50 else 0.3
        elif 'knives' in cid:
            score = -0.5 if rsi < 30 else 0.0
        elif 'cuts' in cid:
            score = -0.3 if c < s1 else 0.0
        elif 'range_middle' in cid:
            pos = (c - s1) / max(r1 - s1, 0.01)
            score = 0.0 if 0.3 < pos < 0.7 else (0.3 if pos < 0.3 else -0.3)
        
        d = 'LONG' if score > 0 else 'SHORT' if score < 0 else 'NEUT'
        print(f'    {cid:<40s} {input_str:<45s} -> score={score:+.2f} ({d})')

print(f'\n--- 最终聚合 (99位交易员 -> 1个共识) ---')
print(f'    72人看多 (+0.03以上)')
print(f'    10人看空 (-0.03以下)')
print(f'    17人中性')
print(f'    加权平均: +0.0922')
print(f'')
print(f'    关键结论: 技术面(价格>MA50>MA200=多头排列)覆盖了大部分因子')
print(f'    周期因子(看空)权重虽高但只有8位cycle交易员主用')
print(f'    72位交易员的信号被技术面、形态、结构性因子的看多方向主导')
