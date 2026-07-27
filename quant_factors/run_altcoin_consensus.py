#!/usr/bin/env python3
"""Unified Altcoin Consensus & Resistance Analyzer.

整合两大能力:
  1. crypto-kol-quant"锁妖塔" — 99位加密KOL的87个量化因子共识
  2. OKX 山寨币实时数据 + 枢轴点/斐波那契阻力位分析

Usage:
    python run_altcoin_consensus.py                      # 默认：前30币种
    python run_altcoin_consensus.py --top 50              # 前50币种
    python run_altcoin_consensus.py --coins SOL,XRP,DOGE  # 指定币种
    python run_altcoin_consensus.py --quick               # 快速模式(仅阻力位，不跑KOL因子)
"""
import sys, os, json, argparse, time
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────
QF_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(QF_DIR)
sys.path.insert(0, QF_DIR)

from local_config import BASE as CONFIG_BASE, OKX_API_KEY
# Override BASE for feature_engine compatibility
os.environ['CRYPTO_KOL_BASE'] = BASE

# ──────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────
from okx_data_adapter import (
    fetch_altcoin_list, fetch_ohlc, fetch_all_altcoins_ohlc,
    build_features_single, build_altcoin_panel
)


# ══════════════════════════════════════════════
# 1. RESISTANCE ANALYSIS (Standalone)
# ══════════════════════════════════════════════
def compute_resistance_levels(feats):
    """Compute comprehensive resistance/support levels from features.

    Args:
        feats: pd.DataFrame (output of build_features_single)

    Returns:
        dict of latest resistance/support values
    """
    if feats is None or len(feats) < 2:
        return {}

    latest = feats.iloc[-1]
    prev = feats.iloc[-2]

    close = latest['close']
    pivot = latest.get('pivot', (latest['high'] + latest['low'] + close) / 3)
    high = latest['high']
    low = latest['low']

    # -- Pivot Point Standard --
    r1_pivot = latest.get('r1', 2 * pivot - low)
    r2_pivot = latest.get('r2', pivot + (high - low))
    s1_pivot = latest.get('s1', 2 * pivot - high)
    s2_pivot = latest.get('s2', pivot - (high - low))

    # -- Fibonacci levels --
    fib_382 = latest.get('fib_382', 0)
    fib_618 = latest.get('fib_618', 0)
    fib_500 = latest.get('fib_500', (fib_382 + fib_618) / 2) if (fib_382 and fib_618) else 0

    # -- Moving average levels --
    ma7 = latest.get('ma7', 0)
    ma20 = latest.get('ma20', 0)
    ma50 = latest.get('ma50', 0)
    ma200 = latest.get('ma200', 0)

    # -- Range extremes (20-day) --
    high_20d = latest.get('high_20d', feats['high'].rolling(20).max().iloc[-1])
    low_20d = latest.get('low_20d', feats['low'].rolling(20).min().iloc[-1])

    # -- RSI --
    rsi14 = latest.get('rsi14', 50)

    # -- Volume status --
    vol_avg = feats['volume'].rolling(20).mean().iloc[-1] if 'volume' in feats else 0
    vol_current = latest.get('volume', 0)
    vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1.0

    return {
        'close': close,
        'pivot': pivot,
        'r1': r1_pivot,
        'r2': r2_pivot,
        's1': s1_pivot,
        's2': s2_pivot,
        'fib_382': fib_382,
        'fib_500': fib_500,
        'fib_618': fib_618,
        'ma7': ma7,
        'ma20': ma20,
        'ma50': ma50,
        'ma200': ma200,
        'high_20d': high_20d,
        'low_20d': low_20d,
        'rsi14': rsi14,
        'vol_ratio': vol_ratio,
        'price_above_ma50': bool(latest.get('price_above_ma50', 0)),
        'price_above_ma200': bool(latest.get('price_above_ma200', 0)),
        'is_green': bool(latest.get('is_green', 0)),
    }


def score_entry_signal(levels):
    """Generate entry signal score (0-10) and recommendation.

    评分维度:
      - 价格相对支撑位的距离 (weight: 3)
      - RSI 位置 (weight: 2)
      - 趋势方向 (MA关系) (weight: 2)
      - 成交量确认 (weight: 1.5)
      - 阻力位空间 (weight: 1.5)

    Returns:
        dict with score, signal, entry_zone, take_profit
    """
    if not levels:
        return {'score': 0, 'signal': 'NEUTRAL', 'reason': 'No data'}

    c = levels['close']
    r1 = levels['r1']
    r2 = levels['r2']
    s1 = levels['s1']
    s2 = levels['s2']
    rsi = levels['rsi14']
    above_ma50 = levels['price_above_ma50']
    above_ma200 = levels['price_above_ma200']
    vol_ratio = levels['vol_ratio']
    ma50 = levels['ma50']
    ma200 = levels['ma200']

    score = 0.0
    reasons = []

    # 1. Distance from support (0-3 points)
    dist_to_s1 = (c - s1) / c if c > 0 else 0
    dist_to_s2 = (c - s2) / c if c > 0 else 0
    if 0 < dist_to_s1 < 0.03:
        score += 3.0
        reasons.append('near S1 support')
    elif 0 < dist_to_s2 < 0.05:
        score += 2.5
        reasons.append('near S2 support')
    elif c < ma50 and c > s1:
        score += 1.5
        reasons.append('below MA50, above S1')
    else:
        score += 0.5
        reasons.append('above near support')

    # 2. RSI position (0-2 points)
    if rsi < 30:
        score += 2.0
        reasons.append('RSI oversold')
    elif rsi < 40:
        score += 1.5
        reasons.append('RSI near oversold')
    elif rsi < 50:
        score += 1.0
        reasons.append('RSI neutral-low')
    elif rsi > 70:
        score -= 1.0  # overbought = not good for entry
        reasons.append('RSI overbought')
    else:
        score += 0.5
        reasons.append('RSI neutral')

    # 3. Trend direction (0-2 points)
    if above_ma200 and above_ma50:
        score += 2.0
        reasons.append('uptrend (above MA50/200)')
    elif above_ma50:
        score += 1.0
        reasons.append('short-term uptrend')
    elif above_ma200:
        score += 0.5
        reasons.append('long-term uptrend')
    else:
        score -= 0.5
        reasons.append('downtrend (below MA200)')

    # 4. Volume confirmation (0-1.5 points)
    if vol_ratio > 1.5:
        score += 1.5
        reasons.append('high volume')
    elif vol_ratio > 1.0:
        score += 1.0
        reasons.append('normal-above volume')
    elif vol_ratio > 0.5:
        score += 0.5
        reasons.append('below avg volume')
    else:
        score += 0.0
        reasons.append('low volume')

    # 5. Resistance headroom (0-1.5 points)
    headroom_to_r1 = (r1 - c) / c if r1 > c > 0 else 0
    headroom_to_r2 = (r2 - c) / c if r2 > c > 0 else 0
    if headroom_to_r2 > 0.08:
        score += 1.5
        reasons.append(f'R2 headroom {headroom_to_r2*100:.1f}%')
    elif headroom_to_r1 > 0.03:
        score += 1.0
        reasons.append(f'R1 headroom {headroom_to_r1*100:.1f}%')
    else:
        score += 0.3
        reasons.append('limited headroom')

    # Clamp to 0-10
    score = max(0, min(10, score))

    # Signal classification
    if score >= 7:
        signal = 'STRONG BUY'
    elif score >= 5:
        signal = 'BUY'
    elif score >= 3:
        signal = 'WATCH'
    else:
        signal = 'PASS'

    # Entry zone
    if levels.get('s1', 0) > 0 and levels.get('s2', 0) > 0:
        entry_zone = f'${levels["s2"]:.4f} - ${levels["s1"]:.4f}'
    else:
        entry_zone = f'${c*0.95:.4f} - ${c*0.98:.4f}'

    # Take profit
    tp1 = r1
    tp2 = r2
    tp3 = r2 + (r2 - c) if r2 > c else c * 1.1

    return {
        'score': round(score, 1),
        'signal': signal,
        'reason': '; '.join(reasons),
        'entry_zone': entry_zone,
        'take_profit_1': tp1,
        'take_profit_2': tp2,
        'take_profit_3': tp3,
        'stop_loss': s2,
    }


# ══════════════════════════════════════════════
# 2. KOL CONSENSUS (from kol-quant engine)
# ══════════════════════════════════════════════
def load_kol_components():
    """Load KOL factor registry and trader profiles.

    Returns:
        CAP_REGISTRY: dict of 87 factor evaluators
        profiles: dict of 99 trader profiles
        factor_cols: list of factor column names
    """
    try:
        from capabilities import CAP_REGISTRY
        print(f'  [KOL] Loaded {len(CAP_REGISTRY)} factors')
    except ImportError as e:
        print(f'  [KOL] Error loading capabilities: {e}')
        CAP_REGISTRY = {}

    # Load trader profiles
    profiles = {}
    prof_dir = os.path.join(BASE, 'profiles_v2')
    if os.path.isdir(prof_dir):
        for f in sorted(os.listdir(prof_dir)):
            if f.endswith('.json'):
                try:
                    p = json.load(open(os.path.join(prof_dir, f), encoding='utf-8'))
                    profiles[f.replace('.json', '')] = p
                except:
                    pass

    factor_cols = list(CAP_REGISTRY.keys())
    return CAP_REGISTRY, profiles, factor_cols


def evaluate_factors_on_coin(feats, cap_registry, factor_cols):
    """Evaluate all 87 KOL factors on a single coin's feature DataFrame.

    Args:
        feats: pd.DataFrame of features
        cap_registry: dict of factor evaluators
        factor_cols: list of factor IDs

    Returns:
        dict: {factor_id: latest_score, ...}
        firing: list of factors that are "firing" now
    """
    if feats is None or len(feats) < 10 or not cap_registry:
        return {}, []

    latest = feats.iloc[-1:]
    factor_scores = {}

    for cid, meta in cap_registry.items():
        try:
            fn = meta['fn']
            result = fn(latest)
            if hasattr(result, 'score'):
                score = result.score
                score_val = float(score.iloc[-1]) if hasattr(score, '__len__') else float(score)
            elif isinstance(result, dict):
                score_val = float(result.get('score', 0))
            else:
                score_val = float(result)
            factor_scores[cid] = score_val
        except:
            factor_scores[cid] = 0.0

    # Determine firing factors (score magnitude > 0.1 active, > 0.05 borderline)
    firing = [
        {'id': cid, 'score': s}
        for cid, s in factor_scores.items()
        if abs(s) > 0.1
    ]
    firing.sort(key=lambda x: -abs(x['score']))

    return factor_scores, firing


def aggregate_consensus(factor_scores, profiles, factor_cols):
    """Aggregate all factor scores into a simple trader-like consensus.

    Simplified version that doesn't require the full trader_composite pipeline.
    """
    if not factor_scores:
        return {'long': 0, 'short': 0, 'neutral': 0, 'bias': 0}

    # Count factor directions
    long_count = sum(1 for v in factor_scores.values() if v > 0.05)
    short_count = sum(1 for v in factor_scores.values() if v < -0.05)
    neutral_count = sum(1 for v in factor_scores.values() if abs(v) <= 0.05)

    # Weighted average bias (weighted by absolute score magnitude)
    total_weight = sum(abs(v) for v in factor_scores.values())
    weighted_bias = sum(v for v in factor_scores.values()) / total_weight if total_weight > 0 else 0

    return {
        'long': long_count,
        'short': short_count,
        'neutral': neutral_count,
        'total': long_count + short_count + neutral_count,
        'bias': round(weighted_bias, 4),
    }


# ══════════════════════════════════════════════
# 3. FORMATTED OUTPUT
# ══════════════════════════════════════════════
def print_analysis_table(results, show_all=True):
    """Print formatted analysis table (FMZ bot style)."""
    if not results:
        print('\n  No results to display.')
        return

    # Sort by signal score descending
    results.sort(key=lambda r: r['entry']['score'], reverse=True)

    print('\n' + '=' * 120)
    print(f'  山寨币多维度分析报告 — {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}')
    print('=' * 120)

    print(f'\n{"#":>3} {"币种":<10} {"价格":>10} {"信号":<12} {"评分":>5} {"R1":>10} {"R2":>10} {"S1":>10} {"S2":>10} '
          f'{"MA50":>10} {"MA200":>10} {"RSI":>5} {"24hVol":>10}')
    print('-' * 120)

    for i, r in enumerate(results, 1):
        lv = r['levels']
        ev = r['entry']
        signal = ev['signal']
        score = ev['score']
        close = lv['close']
        r1 = lv['r1']
        r2 = lv['r2']
        s1 = lv['s1']
        s2 = lv['s2']
        ma50 = lv['ma50']
        ma200 = lv['ma200']
        rsi = lv['rsi14']
        vol = lv.get('vol_ratio', 0)

        # Color coding for signal
        signal_display = signal
        if signal == 'STRONG BUY':
            signal_display = f'[BUY!]{signal}'
        elif signal == 'BUY':
            signal_display = f'[BUY]{signal}'
        elif signal == 'WATCH':
            signal_display = f'[WATCH]{signal}'
        else:
            signal_display = f'[PASS]{signal}'

        coin_name = r['base']

        print(f'{i:3d} {coin_name:<10} {close:>10.4f} {signal_display:<12} {score:>5.1f} '
              f'{r1:>10.4f} {r2:>10.4f} {s1:>10.4f} {s2:>10.4f} '
              f'{ma50:>10.2f} {ma200:>10.2f} {rsi:>5.1f} {vol:>9.1f}x')

    print('-' * 120)
    print(f'  [BUY!] STRONG BUY >=7  [BUY] BUY 5-7  [WATCH] WATCH 3-5  [PASS] PASS <3')
    print()

    # Show top picks detail
    print('\n' + '=' * 120)
    print('  *** 最佳入场候选 (Top 5) ***')
    print('=' * 120)

    for r in results[:5]:
        ev = r['entry']
        lv = r['levels']
        print(f'\n  {r["base"]:12s} [{ev["signal"]}] 评分: {ev["score"]}/10')
        print(f'  {"":12s} 当前: ${lv["close"]:.4f}  |  Pivot: ${lv["pivot"]:.4f}')
        print(f'  {"":12s} 第一阻力 R1: ${lv["r1"]:.4f} (TP1)')
        print(f'  {"":12s} 第二阻力 R2: ${lv["r2"]:.4f} (TP2)')
        print(f'  {"":12s} 第一支撑 S1: ${lv["s1"]:.4f}')
        print(f'  {"":12s} 第二支撑 S2: ${lv["s2"]:.4f}')
        print(f'  {"":12s} 入场区: {ev["entry_zone"]}')
        print(f'  {"":12s} 止盈: TP1=${ev["take_profit_1"]:.4f} | TP2=${ev["take_profit_2"]:.4f} | TP3=${ev["take_profit_3"]:.4f}')
        print(f'  {"":12s} 止损: ${ev["stop_loss"]:.4f}  |  RSI: {lv["rsi14"]:.1f}')
        print(f'  {"":12s} 依据: {ev["reason"]}')

        # KOL factors
        kons = r.get('consensus', {})
        if kons.get('total', 0) > 0:
            print(f'  {"":12s} KOL因子: 多={kons["long"]} 空={kons["short"]} 中性={kons["neutral"]}  偏={kons["bias"]:+.4f}')

    print()


# ══════════════════════════════════════════════
# 4. MAIN PIPELINE
# ══════════════════════════════════════════════
def run_pipeline(top_n=30, specific_coins=None, quick=False):
    """Run the full analysis pipeline.

    Args:
        top_n: number of altcoins to analyze (default 30)
        specific_coins: comma-separated coin symbols, e.g. 'SOL,XRP,DOGE'
        quick: if True, skip KOL factor evaluation

    Returns:
        list of result dicts
    """
    print(f'\n  +=== 山寨币 KOL 共识阻力位分析引擎 ===+')
    print(f'  |  山寨币 KOL 共识阻力位分析引擎        |')
    print(f'  |  OKX + 锁妖塔(99 KOL / 87 因子)         |')
    print(f'  +=========================================+')
    print(f'\n  时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} UTC')
    print(f'  Quick模式: {"Yes (仅阻力位)" if quick else "No (含KOL因子)"}')

    # ── Load KOL components (unless quick) ──
    cap_registry = {}
    profiles = {}
    factor_cols = []
    if not quick:
        print('\n[1/4] 加载 KOL 组件...')
        cap_registry, profiles, factor_cols = load_kol_components()
        print(f'  [KOL] {len(cap_registry)} factors, {len(profiles)} trader profiles loaded')
    else:
        print('\n[1/4] 跳过 KOL 因子加载 (quick模式)')

    # ── Fetch altcoin data ──
    print('\n[2/4] 获取 OKX 山寨币数据...')

    if specific_coins:
        # Use specific coin list
        coin_list = [c.strip().upper() for c in specific_coins.split(',')]
        from okx_data_adapter import fetch_ohlc
        import ccxt
        altcoins = [{'symbol': f'{c}/USDT', 'base': c, 'volume_24h': 0,
                     'last_price': 0, 'open_24h': 0, 'change_24h': '0'}
                    for c in coin_list]
        print(f'  指定币种: {coin_list}')
    else:
        altcoins = fetch_altcoin_list(top_n=top_n)

    if not altcoins:
        print('[ERROR] No altcoins to analyze!')
        return []

    # ── Fetch OHLC + Build features ──
    print(f'\n[3/4] 获取K线数据 & 构建特征...')
    ohlc_data = fetch_all_altcoins_ohlc(altcoins, bar='1D', limit=200)
    if not ohlc_data:
        print('[ERROR] No OHLC data!')
        return []

    # ── Analyze each coin ──
    print(f'\n[4/4] 分析 {len(ohlc_data)} 个币种...')

    results = []
    for sym_key, candles in ohlc_data.items():
        base = sym_key.replace('USDT', '')
        if len(candles) < 20:
            continue

        # Build features
        df = pd.DataFrame(candles)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        feats = build_features_single(df)

        # 4a. Resistance analysis
        levels = compute_resistance_levels(feats)
        entry = score_entry_signal(levels)

        # 4b. KOL consensus (if not quick)
        consensus = {}
        if not quick and cap_registry:
            factor_scores, firing = evaluate_factors_on_coin(feats, cap_registry, factor_cols)
            consensus = aggregate_consensus(factor_scores, profiles, factor_cols)
            consensus['firing_count'] = len(firing)
            consensus['top_firing'] = firing[:5]

        result = {
            'base': base,
            'symbol': sym_key,
            'levels': levels,
            'entry': entry,
            'consensus': consensus,
            'timestamp': datetime.now().isoformat(),
        }
        results.append(result)

    # Print analysis table
    print_analysis_table(results)

    # Save JSON
    output_path = os.path.join(QF_DIR, 'altcoin_analysis_result.json')
    serializable = []
    for r in results:
        sr = {
            'base': r['base'],
            'symbol': r['symbol'],
            'timestamp': r['timestamp'],
            'levels': {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in r['levels'].items()},
            'entry': {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in r['entry'].items()},
            'consensus': {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in r['consensus'].items()},
        }
        serializable.append(sr)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f'\n  结果已保存到: {output_path}')

    return results


# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Altcoin Consensus & Resistance Analyzer')
    parser.add_argument('--top', type=int, default=15, help='Number of altcoins (default: 15)')
    parser.add_argument('--coins', type=str, help='Comma-separated coin list, e.g. SOL,XRP,DOGE')
    parser.add_argument('--quick', action='store_true', help='Quick mode: resistance only, no KOL factors')
    args = parser.parse_args()

    run_pipeline(
        top_n=args.top,
        specific_coins=args.coins,
        quick=args.quick,
    )
