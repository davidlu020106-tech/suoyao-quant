#!/usr/bin/env python3
"""Consensus snapshot: given current BTC state, pull each trader's
composite signal, weight by their historical IC, bucket by school."""
import os, json
import numpy as np
import pandas as pd
from collections import defaultdict

BASE = os.path.expanduser('~/shared/materials/crypto_traders_distill')
factors = pd.read_parquet(f'{BASE}/quant_factors/factors.parquet')
features = pd.read_parquet(f'{BASE}/quant_factors/features.parquet')
signals = pd.read_parquet(f'{BASE}/quant_factors/trader_signals_btc.parquet')
ic_df = pd.read_csv(f'{BASE}/quant_factors/trader_composite_ic.csv').set_index('handle')

# Latest BTC state
btc_factors = factors[factors['symbol'] == 'BTCUSDT'].sort_index()
btc_features = features.loc['BTCUSDT'].sort_index()
latest_date = btc_features.index[-1]
latest = btc_features.iloc[-1]  # has price/indicator columns
latest_fac = btc_factors.iloc[-1]  # has factor columns
print(f'=== BTC Snapshot: {latest_date.date()} ===')
print(f'close: ${latest["close"]:,.0f}')
print(f'MA50:  ${latest["ma50"]:,.0f}  price_above_MA50: {bool(latest["price_above_ma50"])}')
print(f'MA200: ${latest["ma200"]:,.0f}  price_above_MA200: {bool(latest["price_above_ma200"])}')
print(f'RSI14: {latest["rsi14"]:.1f}')
print(f'ADX14: {latest["adx14"]:.1f}')
print(f'RV30:  {latest["rv30"]:.3f} ({latest["rv30_pctile"]*100:.0f} pctile)')
print(f'ret_30d: {latest["ret_30d"]*100:+.1f}%')
print(f'pct_from_ATH(200d): {latest["pct_from_high_200d"]*100:+.1f}%')
print()

# Which factors are firing right now?
factor_cols = [c for c in factors.columns if c.startswith('cap_') or c.startswith('emg_')]
latest_factors = latest_fac[factor_cols]
firing = latest_factors[latest_factors.abs() > 0.05].sort_values()

print(f'=== Firing factors today ({len(firing)}) ===')
for fc, v in firing.items():
    label = 'LONG' if v > 0 else 'SHORT'
    print(f'  {label:5s} {v:+.2f}  {fc}')
print()

# Each trader's latest composite signal
latest_signals = signals.iloc[-1].dropna()
print(f'=== Trader signals: {len(latest_signals)} traders ===')

# Join with IC trust
df = pd.DataFrame({'signal': latest_signals})
df = df.join(ic_df[['ic_30d','school','bias_default']], how='left')

def classify_signal(s):
    if s > 0.03: return 'long'
    if s < -0.03: return 'short'
    return 'neutral'

df['stance'] = df['signal'].apply(classify_signal)
df['weight'] = df['ic_30d'].abs().clip(lower=0.01)  # Absolute IC as trust weight; reverse-sign low-IC later

# Equal-weight consensus
eq_long = (df['stance'] == 'long').sum()
eq_short = (df['stance'] == 'short').sum()
eq_neutral = (df['stance'] == 'neutral').sum()
eq_mean = df['signal'].mean()

# IC-weighted consensus (positive IC = follow; negative IC = reverse)
# For reverse-indicator traders, flip their signal before averaging
df['ic_aligned_signal'] = np.where(df['ic_30d'] >= 0, df['signal'], -df['signal'])
df['weight_positive'] = df['ic_30d'].clip(lower=0)  # only positive-IC traders get weight
positive_weight_sum = df['weight_positive'].sum()
if positive_weight_sum > 0:
    weighted_bias = (df['signal'] * df['weight_positive']).sum() / positive_weight_sum
else:
    weighted_bias = 0

# IC-weighted bias including reversal of negative-IC traders
df['abs_weight'] = df['ic_30d'].abs().fillna(0)
abs_weight_sum = df['abs_weight'].sum()
if abs_weight_sum > 0:
    adjusted_bias = (df['ic_aligned_signal'] * df['abs_weight']).sum() / abs_weight_sum
else:
    adjusted_bias = 0

print(f'\n=== Implied 30d price range (from firing factors) ===')
# For each firing factor, look up its historical forward 30d distribution when triggered
# use the factors.parquet + fwd_30d column
for fc, v in firing.items():
    if abs(v) < 0.05: continue
    direction = 'long' if v > 0 else 'short'
    # Filter panel: rows where this factor had same sign
    same_sign = btc_factors[btc_factors[fc] * v > 0][['fwd_30d']].dropna()
    if len(same_sign) < 5:
        continue
    p25 = same_sign['fwd_30d'].quantile(0.25) * 100
    p50 = same_sign['fwd_30d'].quantile(0.5) * 100
    p75 = same_sign['fwd_30d'].quantile(0.75) * 100
    hit = ((same_sign['fwd_30d'] > 0) if direction == 'long' else (same_sign['fwd_30d'] < 0)).mean()
    implied_low = float(latest['close']) * (1 + p25/100)
    implied_high = float(latest['close']) * (1 + p75/100)
    print(f'  {direction:5s} {fc[:35]:35s} p25={p25:+.1f}% p50={p50:+.1f}% p75={p75:+.1f}%  → box ${implied_low:,.0f}-${implied_high:,.0f}  hit={hit:.2f} n={len(same_sign)}')

print(f'\n=== Consensus ===')
print(f'Equal weight:       long {eq_long:3d} | short {eq_short:3d} | neutral {eq_neutral:3d} | mean signal {eq_mean:+.3f}')
print(f'IC>=0 weighted bias:                                         {weighted_bias:+.3f}')
print(f'Trust-adjusted bias (reverse negatives):                     {adjusted_bias:+.3f}')

# School breakdown
print(f'\n=== By school ===')
for school, group in df.groupby('school'):
    n = len(group)
    mean_sig = group['signal'].mean()
    long_n = (group['stance'] == 'long').sum()
    short_n = (group['stance'] == 'short').sum()
    print(f'  {school or "?":15s} n={n:3d} mean={mean_sig:+.3f} L={long_n:2d} S={short_n:2d}')

# Top 10 most confident alignment (positive IC) traders' current calls
aligned = df[df['ic_30d'] > 0.05].sort_values('ic_30d', ascending=False)
print(f'\n=== Top 15 aligned traders (IC>0.05) — their calls RIGHT NOW ===')
for h, r in aligned.head(15).iterrows():
    sig = r['signal']
    arrow = '🟢' if sig > 0.1 else '🔴' if sig < -0.1 else '⚪'
    print(f"  {arrow} @{h[:22]:22s} IC={r['ic_30d']:+.2f}  signal={sig:+.3f}  school={r['school'] or '?'}")

# Bottom 10 reversed traders (negative IC) — reverse their signal for consensus
reversed_traders = df[df['ic_30d'] < -0.05].sort_values('ic_30d')
print(f'\n=== Top 10 reverse-indicator traders — flip their signal ===')
for h, r in reversed_traders.head(10).iterrows():
    sig = r['signal']
    flipped = -sig
    arrow = '🟢' if flipped > 0.1 else '🔴' if flipped < -0.1 else '⚪'
    print(f"  {arrow} @{h[:22]:22s} IC={r['ic_30d']:+.2f}  raw={sig:+.3f} flipped={flipped:+.3f}  school={r['school'] or '?'}")

# Save snapshot
snapshot = {
    'date': str(latest_date.date()),
    'btc_price': float(latest['close']),
    'btc_features': {
        'rsi14': float(latest['rsi14']),
        'adx14': float(latest['adx14']),
        'price_above_ma200': bool(latest['price_above_ma200']),
        'ma50_above_ma200': bool(latest['ma50_above_ma200']),
        'pct_from_ath': float(latest['pct_from_high_200d']),
        'ret_30d': float(latest['ret_30d']),
    },
    'firing_factors': [{'id': k, 'score': float(v)} for k, v in firing.items()],
    'consensus': {
        'equal_weight': {'long': int(eq_long), 'short': int(eq_short), 'neutral': int(eq_neutral), 'mean_signal': float(eq_mean)},
        'ic_positive_weighted': float(weighted_bias),
        'trust_adjusted': float(adjusted_bias),
    },
    'by_school': {
        (school or 'unknown'): {
            'count': len(group),
            'mean_signal': float(group['signal'].mean()),
            'long_count': int((group['stance']=='long').sum()),
            'short_count': int((group['stance']=='short').sum()),
            'neutral_count': int((group['stance']=='neutral').sum()),
        }
        for school, group in df.groupby('school')
    },
    'traders': [
        {
            'handle': h,
            'school': row['school'],
            'bias_default': row['bias_default'],
            'ic_30d': float(row['ic_30d']) if not pd.isna(row['ic_30d']) else None,
            'signal_now': float(row['signal']),
            'stance': row['stance'],
            'trust_adjusted_vote': (float(row['signal']) if row['ic_30d']>=0 else -float(row['signal'])) if not pd.isna(row['ic_30d']) else None,
        }
        for h, row in df.iterrows()
    ]
}
with open(f'{BASE}/quant_factors/consensus_snapshot.json','w') as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)
print(f'\nsaved consensus_snapshot.json')
