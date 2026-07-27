#!/usr/bin/env python3
"""ETH 6小时预测 — 99位KOL交易员全量参与投票。

每位交易员的所有能力都获得连续评分(不是等事件触发)，
然后按个人权重聚合，输出最终共识。

用法:
    python eth_6h_kol_forecast.py
"""
import sys, os, json, urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import Counter, defaultdict

QF = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QF)
sys.path.insert(0, os.path.dirname(QF))

from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single
from local_config import OKX_API_KEY

# ──────────────────────────────────────────────
# 1. 拉取 ETH 1H K线
# ──────────────────────────────────────────────
def api_get(path):
    url = f'https://www.okx.com{path}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())

print('Fetching ETH/USDT 1H candles...')
data = api_get('/api/v5/market/candles?instId=ETH-USDT&bar=1H&limit=200')
raw = data.get('data', [])
raw.reverse()
candles = []
for c in raw:
    ts = int(c[0]) / 1000
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    candles.append({
        'date': dt.strftime('%Y-%m-%d %H:%M'), 'open': float(c[1]),
        'high': float(c[2]), 'low': float(c[3]),
        'close': float(c[4]), 'volume': float(c[5]),
    })

df = pd.DataFrame(candles)
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date').sort_index()
feats = build_features_single(df)
latest = feats.iloc[-1]

cur_price = float(latest['close'])
print(f'Current: ${cur_price:.2f} ({feats.index[-1]})\n')

# ──────────────────────────────────────────────
# 2. 对 87 个因子做连续评分
# ──────────────────────────────────────────────
def continuous_score(cid, row):
    """Continuous score in [-1, +1] for a capability, no trigger event needed."""
    c = float(row['close'])
    h = float(row['high'])
    l = float(row['low'])
    o = float(row['open'])
    ma7 = float(row.get('ma7', c))
    ma20 = float(row.get('ma20', c))
    ma50 = float(row.get('ma50', c))
    ma200 = float(row.get('ma200', c))
    rsi = float(row.get('rsi14', 50))
    r1 = float(row.get('r1', c))
    r2 = float(row.get('r2', c))
    s1 = float(row.get('s1', c))
    s2 = float(row.get('s2', c))
    pivot = float(row.get('pivot', c))
    fib_618 = float(row.get('fib_618', c))
    bb_width = float(row.get('bb_width', 0))

    # Regime
    if cid == 'cap_044_regime_trending_up':
        return 0.6 if c > ma50 else -0.4
    if cid == 'cap_045_regime_trending_down':
        return 0.6 if c < ma50 else -0.4
    if cid == 'cap_046_regime_ranging':
        return 0.5 if (h-l)/c < 0.02 else 0.0
    if cid == 'cap_047_regime_volatile':
        return 0.6 if (h-l)/c > 0.03 else 0.0
    if cid == 'cap_070_parabolic_exhaustion':
        ret = float(row.get('ret_5d', 0))
        return 0.5 if abs(ret) > 0.05 else 0.0

    # Indicators
    if cid == 'cap_015_rsi_bullish_divergence':
        return 0.3 if rsi > 50 and c > ma50 else -0.1
    if cid == 'cap_016_rsi_bearish_divergence':
        return -0.3 if rsi < 50 and c < ma50 else 0.1
    if cid == 'cap_017_rsi_oversold_bounce':
        return 0.5 if rsi < 35 else (0.2 if rsi < 45 else 0.0)
    if cid == 'cap_018_ma_golden_cross':
        return 0.5 if ma50 > ma200 else -0.5
    if cid == 'cap_019_ma_death_cross':
        return -0.5 if ma50 < ma200 else 0.5
    if cid == 'cap_020_macd_histogram_cross':
        hist = float(row.get('macd_hist', 0))
        return 0.4 if hist > 0 else -0.4
    if cid == 'cap_021_bb_squeeze_breakout':
        return 0.4 if bb_width < 0.015 else (-0.2 if bb_width > 0.03 else 0.0)
    if cid == 'cap_022_fib_618_support':
        dist = abs(c - fib_618) / c
        return 0.7 if dist < 0.02 else (0.3 if dist < 0.05 else 0.0)
    if cid == 'cap_069_moving_average_reclaim':
        return 0.6 if c > ma200 else -0.6
    if cid in ['emg_008_w50ema_bull_bear_divider', 'emg_014_horizontal_reclaim']:
        return 0.4 if c > ma50 else -0.4
    if cid == 'emg_022_200w_mechanical_buy':
        return 0.5 if c < ma200 * 0.9 else -0.2
    if cid == 'emg_029_200w_value_zone':
        return 0.5 if c < ma200 * 0.85 else -0.1
    if cid == 'emg_028_20w_200w_double_reclaim':
        return 0.4 if c > ma200 and c > ma50 else -0.3
    if cid == 'emg_001_quarterly_vwap':
        return 0.3 if c > pivot else -0.3

    # Cycle
    if cid == 'cap_037_halving_cycle':
        return -0.30
    if cid == 'cap_038_4year_cycle':
        return -0.40
    if cid == 'emg_005_4year_same_day_compare':
        return -0.25
    if cid == 'emg_006_days_in_tight_range':
        return 0.1
    if cid == 'emg_023_monthly_seasonality':
        return 0.1 if datetime.now().month in [10,11,12,1,2,3] else -0.1

    # Structural
    if cid in ['cap_023_elliott_wave_3','cap_024_wyckoff_accumulation_spring',
               'cap_026_smc_order_block_retest','cap_048_ict_breaker_block',
               'cap_hh_defense','emg_007_htf_reclaim_retest',
               'emg_027_ohlc_anchor_framework','emg_030_htf_close_anchor']:
        return 0.3 if c > ma50 else -0.3
    if cid in ['cap_025_wyckoff_distribution_upthrust','cap_049_ict_fair_value_gap']:
        return -0.3 if c < ma50 else 0.3
    if cid == 'cap_065_btc_dominance_shift':
        return 0.0

    # Patterns (bullish setups)
    if cid in ['cap_001_falling_wedge_breakout','cap_003_bull_flag',
               'cap_006_inverse_head_shoulders','cap_008_double_bottom',
               'cap_009_cup_and_handle','cap_010_ascending_triangle']:
        return 0.35 if c > ma50 else -0.2
    # Patterns (bearish setups)
    if cid in ['cap_002_rising_wedge_breakdown','cap_004_bear_flag',
               'cap_005_head_shoulders_top','cap_007_double_top',
               'cap_011_descending_triangle']:
        return -0.35 if c < ma50 else 0.2
    # Patterns (neutral/directional)
    if cid in ['cap_012_sfp','cap_013_range_fade','cap_014_trend_pullback',
               'cap_050_three_drives','cap_051_quasimodo','cap_052_liquidity_grab',
               'cap_057_fake_breakout','cap_058_triple_bottom',
               'emg_010_broadening_wedge','emg_013_box_breakout',
               'emg_017_break_target_projection']:
        return 0.3 if c > ma20 else -0.3

    # Candlestick
    if cid == 'cap_053_doji':
        body = abs(c-o)
        rng = h-l
        return 0.3 if rng > 0 and body/rng < 0.1 else 0.0
    if cid == 'cap_054_engulfing':
        return 0.3 if c > o else 0.0
    if cid == 'cap_055_pin_bar':
        uw = h - max(c,o)
        lw = min(c,o) - l
        rng = h-l
        if rng > 0 and min(uw,lw)/rng < 0.1 and max(uw,lw)/rng > 0.5:
            return 0.4 if lw > uw else -0.4
        return 0.0
    if cid == 'cap_056_double_needle_bottom':
        return 0.3 if rsi < 40 else 0.0

    # Macro (proxy with technical)
    if cid in ['cap_027_dxy_inverse_btc','cap_028_spx_risk_on',
               'cap_029_yields_liquidity','cap_030_gold_safe_haven',
               'cap_062_m2_growth','cap_063_ism_pmi','cap_064_credit_spreads']:
        return 0.1 if c > ma50 else -0.1
    if cid == 'cap_040_etf_flows_proxy':
        return 0.2 if c > ma50 else -0.2

    # Risk
    if cid == 'cap_041_dont_catch_falling_knives':
        return -0.5 if rsi < 30 else 0.0
    if cid == 'cap_043_cut_losses_early':
        return -0.3 if c < s1 else 0.0
    if cid == 'emg_009_range_middle_filter':
        pos = (c - s1) / max(r1 - s1, 0.01)
        return 0.0 if 0.3 < pos < 0.7 else (0.3 if pos < 0.3 else -0.3)

    # Everything else (derivatives/onchain/events = neutral)
    return 0.0


# ──────────────────────────────────────────────
# 3. 加载 99 位交易员，计算每人投票
# ──────────────────────────────────────────────
profiles = {}
prof_dir = os.path.join(os.path.dirname(QF), 'profiles_v2')
for f in sorted(os.listdir(prof_dir)):
    if f.endswith('.json'):
        try:
            p = json.load(open(os.path.join(prof_dir, f), encoding='utf-8'))
            profiles[f.replace('.json', '')] = p
        except:
            pass

print(f'Loaded {len(profiles)} trader profiles')

def match_cap(pid, reg_ids):
    if pid in reg_ids:
        return pid
    parts = pid.split('_')
    if len(parts) >= 2 and parts[0] == 'cap' and parts[1].isdigit():
        pref = 'cap_' + parts[1]
        matches = [c for c in reg_ids if c.startswith(pref + '_')]
        return matches[0] if matches else None
    return None

registry_ids = set(CAP_REGISTRY.keys())

trader_votes = []
for handle, p in profiles.items():
    tw = 0.0
    ws = 0.0
    mc = 0
    for c in (p.get('capabilities_used', []) or []):
        raw_id = c.get('id', '')
        w = float(c.get('weight', 0))
        mid = match_cap(raw_id, registry_ids)
        if mid:
            s = continuous_score(mid, latest)
            if s != 0:
                ws += w * s
                tw += abs(w)
                mc += 1
    if tw > 0:
        signal = ws / tw
    else:
        bias = p.get('bias_default', 'neutral')
        if bias == 'long_tilted':
            signal = 0.15
        elif bias == 'short_tilted':
            signal = -0.15
        else:
            signal = 0.0

    trader_votes.append({
        'handle': handle,
        'school': p.get('school_primary', '?'),
        'bias': p.get('bias_default', '?'),
        'signal': round(signal, 4),
        'matched': mc,
    })

# ──────────────────────────────────────────────
# 4. 波动区间预测
# ──────────────────────────────────────────────
atr_1h = float(feats['atr14'].iloc[-1])
atr_6h = atr_1h * np.sqrt(6)
bb_upper = float(feats['bb_upper'].iloc[-1])
bb_lower = float(feats['bb_lower'].iloc[-1])
bb_range = (bb_upper - bb_lower) / 2
projected_range = (atr_6h + bb_range) / 2

consensus_signals = [v['signal'] for v in trader_votes]
avg_signal = float(np.mean(consensus_signals))
signal_std = float(np.std(consensus_signals))
long_n = sum(1 for s in consensus_signals if s > 0.03)
short_n = sum(1 for s in consensus_signals if s < -0.03)
neutral_n = len(consensus_signals) - long_n - short_n
long_pct = long_n / len(consensus_signals) * 100
short_pct = short_n / len(consensus_signals) * 100
neutral_pct = neutral_n / len(consensus_signals) * 100

bias_offset = avg_signal * projected_range * 0.3
range_low = cur_price - projected_range + bias_offset
range_high = cur_price + projected_range + bias_offset

r1 = float(feats['r1'].iloc[-1])
r2 = float(feats['r2'].iloc[-1])
s1 = float(feats['s1'].iloc[-1])
s2 = float(feats['s2'].iloc[-1])
pivot_mid = (r1 + s1) / 2

final_low = max(min(range_low, s1, s2), min(s2, s1) * 0.98)
final_high = min(max(range_high, r1, r2), max(r1, r2) * 1.02)
final_low = min(final_low, cur_price * 0.97)
final_high = max(final_high, cur_price * 1.03)

# School stats
school_stats = defaultdict(lambda: {'sig': [], 'n': 0})
for v in trader_votes:
    s = v['school']
    school_stats[s]['sig'].append(v['signal'])
    school_stats[s]['n'] += 1

top_bull = sorted(trader_votes, key=lambda x: -x['signal'])[:5]
top_bear = sorted(trader_votes, key=lambda x: x['signal'])[:5]

# ──────────────────────────────────────────────
# 5. 输出
# ──────────────────────────────────────────────
print('')
print('=' * 78)
print('  ETH/USDT 6-Hour Forecast -- 99 KOL Trader Full Consensus')
print('=' * 78)

cur_ts = feats.index[-1].strftime('%H:%M UTC')

print(f'\n  Current: ${cur_price:.2f}  ({cur_ts})')
print(f'  MA50=${float(feats["ma50"].iloc[-1]):.2f}  MA200=${float(feats["ma200"].iloc[-1]):.2f}  RSI={float(feats["rsi14"].iloc[-1]):.1f}')
print(f'  ATR(14h)=${atr_1h:.2f}  >6h proj=${atr_6h:.2f}  BB=${bb_lower:.2f}~${bb_upper:.2f}')

print(f'\n--- Predicted 6h Range ---')
print(f'  Low:  ${final_low:.2f}')
print(f'  High: ${final_high:.2f}')
print(f'  Pivot: ${pivot_mid:.2f}')
print(f'  Width: {(final_high-final_low)/cur_price*100:.1f}%')

print(f'\n  Key Levels:')
print(f'    R2=${r2:.2f}  R1=${r1:.2f}  P=${pivot_mid:.2f}  S1=${s1:.2f}  S2=${s2:.2f}')

print(f'\n--- 99 Traders Vote ---')
print(f'  Bullish (signal>+0.03): {long_n} traders ({long_pct:.0f}%)')
print(f'  Bearish (signal<-0.03): {short_n} traders ({short_pct:.0f}%)')
print(f'  Neutral:                  {neutral_n} traders ({neutral_pct:.0f}%)')
print(f'  Weighted avg signal:     {avg_signal:+.4f}')
print(f'  Signal std:              {signal_std:.4f}')
if avg_signal > 0.02:
    verdict = 'BULLISH -- buy on dip'
elif avg_signal < -0.02:
    verdict = 'BEARISH -- sell on rally'
else:
    verdict = 'NEUTRAL -- wait for direction'
print(f'  Verdict: {verdict}')

print(f'\n--- By School ---')
print(f'{"School":<20} {"N":>3} {"AvgSig":>10} {"Dir":>6}')
print('-' * 42)
for school, st in sorted(school_stats.items(), key=lambda x: np.mean(x[1]['sig'])):
    avg = float(np.mean(st['sig']))
    n = st['n']
    dir_label = 'BULL' if avg > 0.02 else 'BEAR' if avg < -0.02 else 'NEUT'
    print(f'{school:<20} {n:>3} {avg:>+10.4f} {dir_label:>6}')

print(f'\n--- Top 5 Bullish Traders ---')
for v in top_bull:
    print(f'  @{v["handle"]:<22s} sig={v["signal"]:+.4f}  {v["school"]:<12s} (bias={v["bias"]})')

print(f'\n--- Top 5 Bearish Traders ---')
for v in top_bear:
    print(f'  @{v["handle"]:<22s} sig={v["signal"]:+.4f}  {v["school"]:<12s} (bias={v["bias"]})')

print(f'\n--- 6h Strategy ---')
if avg_signal > 0.01:
    bias_str = 'Bullish'
elif avg_signal < -0.01:
    bias_str = 'Bearish'
else:
    bias_str = 'Neutral'
print(f'  Bias: {bias_str}  |  Range: ${final_low:.1f} ~ ${final_high:.1f}')
print(f'  Long:  dip to ${s2:.2f}-${s1:.2f} hold + KOL bullish --> target ${r1:.2f}-${r2:.2f}')
print(f'  Short: rally to ${r1:.2f}-${r2:.2f} reject + KOL bearish --> target ${s1:.2f}-${s2:.2f}')
print(f'  SL:    long below ${s2:.2f} | short above ${r2:.2f}')
if abs(avg_signal) > 0.02:
    print(f'  Size: normal (clear consensus)')
else:
    print(f'  Size: half (fuzzy consensus)')

# Save
output = {
    'timestamp': datetime.now().isoformat(),
    'symbol': 'ETH/USDT',
    'price': cur_price,
    '6h_forecast': {
        'low': round(final_low, 2), 'high': round(final_high, 2),
        'pivot': round(pivot_mid, 2),
        'r1': round(r1, 2), 'r2': round(r2, 2),
        's1': round(s1, 2), 's2': round(s2, 2),
    },
    'consensus': {
        'total': len(trader_votes),
        'bullish': long_n, 'bearish': short_n, 'neutral': neutral_n,
        'avg_signal': round(avg_signal, 4),
        'bias': 'bullish' if avg_signal > 0.02 else 'bearish' if avg_signal < -0.02 else 'neutral',
    },
    'technical': {
        'rsi14': round(float(feats['rsi14'].iloc[-1]), 1),
        'ma50': round(float(feats['ma50'].iloc[-1]), 2),
        'ma200': round(float(feats['ma200'].iloc[-1]), 2),
        'atr14': round(atr_1h, 2),
    }
}
out_path = os.path.join(QF, 'eth_6h_forecast.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'\n  Saved: {out_path}')
