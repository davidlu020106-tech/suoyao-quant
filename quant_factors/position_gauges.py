"""
20 维位置共识系统 (百分制) — 多维度判断币种相对位置

5 种参照系 × 多种时间窗口, 裁尾均值 + 偏向计数 + 分级。

每个判断器接受 feats DataFrame, 返回 0-100 百分制位置:
  0-25: 极低/超卖/深度价值区
  25-40: 偏低
  40-60: 中性
  60-75: 偏高
  75-100: 极高/超买/泡沫区

参考 FMZ 策略广场对应策略的核心算法。

用法:
    from position_gauges import evaluate_all_positions
    result = evaluate_all_positions(feats, 'long')
    # result['score'] = 裁尾均值 0-100
    # result['lean'] = +6 (6个维度偏高) 或 -4 (4个偏低)
    # result['grade'] = 'A'~'F'
"""

import numpy as np


def _safe_pct(close, lower, upper):
    """安全计算区间百分比位置, 输出 0-100"""
    if upper <= lower:
        return 50.0
    return float(np.clip((close - lower) / (upper - lower) * 100.0, 0.0, 100.0))


def _dev_to_pct(close, base, max_dev):
    """偏离度转百分制: (close/base - 1) / max_dev → [0,100]"""
    if base <= 0:
        return 50.0
    dev = close / base - 1.0
    return float(np.clip((dev + max_dev) / (2.0 * max_dev) * 100.0, 0.0, 100.0))


def _atr(feats, period):
    """从原始OHLC计算ATR (okx_data_adapter可能没有ATR7)"""
    close = feats['close'].values
    high = feats['high'].values
    low = feats['low'].values
    tr = np.maximum(high[1:] - low[1:],
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1]))
    # EMA-style ATR
    alpha = 2.0 / (period + 1)
    atr_vals = np.zeros(len(tr))
    atr_vals[0] = tr[0]
    for i in range(1, len(tr)):
        atr_vals[i] = alpha * tr[i] + (1 - alpha) * atr_vals[i-1]
    return atr_vals


# ═══════════════════════════════════════
# 20 个位置判断器 (每个返回 0-100)
# ═══════════════════════════════════════

# ── 波动率通道 (3个) ──

def gauge_keltner(feats):
    """Keltner通道 (EMA20 ± 2×ATR10)"""
    c = float(feats['close'].iloc[-1])
    ku = float(feats['kc_upper'].iloc[-1])
    kl = float(feats['kc_lower'].iloc[-1])
    return _safe_pct(c, kl, ku)


def gauge_bollinger(feats):
    """Bollinger %B (SMA20 ± 2σ)
    参考 FMZ: Bollinger-Bands-Mean-Reversion w/ Dynamic-Support
    """
    c = float(feats['close'].iloc[-1])
    bu = float(feats['bb_upper'].iloc[-1])
    bl = float(feats['bb_lower'].iloc[-1])
    return _safe_pct(c, bl, bu)


def gauge_atr14_channel(feats):
    """ATR通道14: (close - SMA20) / (2×ATR14) → [0,100]
    参考 FMZ: AlphaTrend-Adaptive-ATR-Channel
    """
    c = float(feats['close'].iloc[-1])
    sma20 = float(feats['ma20'].iloc[-1])
    atr14 = float(feats['atr14'].iloc[-1])
    if atr14 <= 0:
        return 50.0
    dev = (c - sma20) / (2.0 * atr14)
    return float(np.clip((dev + 1.5) / 3.0 * 100.0, 0.0, 100.0))


# ── 极值区间 (5个, 不同时间窗口) ──

def gauge_5d_range(feats):
    """5周期高低区间
    参考 FMZ: 5-day High-Low Breakout Price Channel
    """
    c = float(feats['close'].iloc[-1])
    h5 = float(feats['high'].iloc[-5:].max())
    l5 = float(feats['low'].iloc[-5:].min())
    return _safe_pct(c, l5, h5)


def gauge_10d_range(feats):
    """10周期高低区间"""
    c = float(feats['close'].iloc[-1])
    h10 = float(feats['high'].iloc[-10:].max())
    l10 = float(feats['low'].iloc[-10:].min())
    return _safe_pct(c, l10, h10)


def gauge_20d_range(feats):
    """20周期高低区间 (Donchian)
    参考 FMZ: Donchian-Channel-Trend-Following
    """
    c = float(feats['close'].iloc[-1])
    h20 = float(feats['high_20d'].iloc[-1])
    l20 = float(feats['low_20d'].iloc[-1])
    return _safe_pct(c, l20, h20)


def gauge_50d_range(feats):
    """50周期高低区间
    参考 FMZ: Historical-High-Breakthrough
    """
    c = float(feats['close'].iloc[-1])
    h50 = float(feats['high_50d'].iloc[-1])
    l50 = float(feats['low_50d'].iloc[-1])
    return _safe_pct(c, l50, h50)


def gauge_15d_donchian(feats):
    """Donchian15: 15周期布尔突破通道
    参考 FMZ: Donchian-Breakout-Strategy
    """
    c = float(feats['close'].iloc[-1])
    h15 = float(feats['high'].iloc[-15:].max())
    l15 = float(feats['low'].iloc[-15:].min())
    return _safe_pct(c, l15, h15)


# ── 均线偏离 (4个, 不同周期) ──

def gauge_sma10(feats):
    """SMA10偏离度: (close/sma10-1)/15% → [0,100]
    参考 FMZ: EMA-Percentage-Channel
    """
    c = float(feats['close'].iloc[-1])
    sma10 = float(feats['close'].iloc[-10:].mean())
    return _dev_to_pct(c, sma10, 0.15)


def gauge_ma50(feats):
    """MA50偏离度 (±20%)"""
    c = float(feats['close'].iloc[-1])
    ma50 = float(feats['ma50'].iloc[-1])
    return _dev_to_pct(c, ma50, 0.20)


def gauge_ema20(feats):
    """EMA20偏离度 (±12%)
    参考 FMZ: Dynamic-Envelope-Moving-Average
    """
    c = float(feats['close'].iloc[-1])
    ema = float(feats['ema20'].iloc[-1])
    return _dev_to_pct(c, ema, 0.12)


def gauge_ma200(feats):
    """MA200偏离度 (±50%), 山寨币价值区判断"""
    c = float(feats['close'].iloc[-1])
    ma200 = float(feats.get('ma200', feats['ma100']).iloc[-1])
    return _dev_to_pct(c, ma200, 0.50)


# ── 动量/波动率 (3个) ──

def gauge_rsi(feats):
    """RSI动量位置: RSI本身[0,100]就是天然百分制
    参考 FMZ: RSI-Overbought-Oversold Crossover
    """
    return float(feats['rsi14'].iloc[-1])


def gauge_atr7_channel(feats):
    """ATR通道7: (close-SMA10)/(2×ATR7) → [0,100]
    短期ATR比14更敏感
    """
    c = float(feats['close'].iloc[-1])
    sma10 = float(feats['close'].iloc[-10:].mean())
    atr7_arr = _atr(feats, 7)
    atr7 = float(atr7_arr[-1])
    if atr7 <= 0:
        return 50.0
    dev = (c - sma10) / (2.0 * atr7)
    return float(np.clip((dev + 1.5) / 3.0 * 100.0, 0.0, 100.0))


def gauge_stoch_rsi(feats):
    """StochRSI: 比RSI更敏感, [0,100]天然百分制
    参考 FMZ: Momentum-based-ZigZag
    """
    s = feats.get('stoch_rsi', feats['rsi14'])
    val = float(s.iloc[-1])
    if hasattr(val, '__float__'):
        return float(np.clip(float(val) * 100.0, 0.0, 100.0))
    return 50.0


# ── 结构/支撑阻力 (5个) ──

def gauge_pivot(feats):
    """Pivot区间: (close-S1)/(R1-S1) ×100
    参考 FMZ: Dynamic-Support/Resistance-Adaptive-Pivot
    """
    c = float(feats['close'].iloc[-1])
    r1 = float(feats['r1'].iloc[-1])
    s1 = float(feats['s1'].iloc[-1])
    return _safe_pct(c, s1, r1)


def gauge_fib(feats):
    """Fibonacci回撤位置 (50日摆动)
    参考 FMZ: RSI+Fibonacci-Retracement
    """
    c = float(feats['close'].iloc[-1])
    high = feats['high'].values
    low = feats['low'].values
    n = min(50, len(high))
    sh = float(np.max(high[-n:]))
    sl = float(np.min(low[-n:]))
    return _safe_pct(c, sl, sh)


def gauge_fib_short(feats):
    """Fibonacci回撤位置 (20日摆动, 更敏感)"""
    c = float(feats['close'].iloc[-1])
    high = feats['high'].values
    low = feats['low'].values
    n = min(20, len(high))
    sh = float(np.max(high[-n:]))
    sl = float(np.min(low[-n:]))
    return _safe_pct(c, sl, sh)


def gauge_vwap(feats):
    """VWAP偏离: (close-vwap)/vwap → [0,100]
    参考 FMZ: VWAP-Deviation-and-OBV-RSI
    """
    c = float(feats['close'].iloc[-1])
    vol = feats['volume'].values
    close_arr = feats['close'].values
    n = min(200, len(close_arr))
    vwap = float(np.sum(close_arr[-n:] * vol[-n:]) / np.sum(vol[-n:]))
    return _dev_to_pct(c, vwap, 0.08)


def gauge_week_range(feats):
    """周级别区间: 近24×7=168根15mK线 或 近7根日线的高低区间
    以近48根15mK线作代理 (~1日级别)
    """
    c = float(feats['close'].iloc[-1])
    n = min(len(feats) // 4, 96)
    n = max(n, 20)
    h_week = float(feats['high'].iloc[-n:].max())
    l_week = float(feats['low'].iloc[-n:].min())
    return _safe_pct(c, l_week, h_week)


# ═══════════════════════════════════════
# 聚合
# ═══════════════════════════════════════

GAUGES = {
    # 波动率通道
    'Keltner通道': gauge_keltner,
    'Bollinger%B': gauge_bollinger,
    'ATR通道14': gauge_atr14_channel,
    'ATR通道7': gauge_atr7_channel,
    # 极值区间 (5/10/15/20/50日)
    '5日区间': gauge_5d_range,
    '10日区间': gauge_10d_range,
    '15日Donchian': gauge_15d_donchian,
    '20日区间': gauge_20d_range,
    '50日区间': gauge_50d_range,
    # 均线偏离
    'SMA10偏离': gauge_sma10,
    'EMA20偏离': gauge_ema20,
    'MA50偏离': gauge_ma50,
    'MA200偏离': gauge_ma200,
    # 动量/波动率
    'RSI': gauge_rsi,
    'StochRSI': gauge_stoch_rsi,
    # 结构
    'Pivot区间': gauge_pivot,
    'Fib50日': gauge_fib,
    'Fib20日': gauge_fib_short,
    'VWAP偏离': gauge_vwap,
    '周级别区间': gauge_week_range,
}

GAUGE_NAMES = list(GAUGES.keys())


def evaluate_all_positions(feats, direction):
    """运行全部 20 个位置判断器, 返回共识结果

    Args:
        feats: build_features_single 输出的 DataFrame
        direction: 'long' 或 'short'

    Returns:
        {
            'score': int,           # 裁尾均值 0-100 (去掉最高/最低各3个)
            'lean': int,            # (>55) - (<45) 偏向计数, +N偏高 -N偏低
            'grade': str,           # A(极佳)/B(良好)/C(中性)/D(不利)/F(危险)
            'high_count': int,      # 偏高(>60)的维度数
            'low_count': int,       # 偏低(<40)的维度数
            'bias_mean': float,     # 方向对齐评分 [-1,1]
        }
    """
    positions = []
    details = {}

    for name, gauge_fn in GAUGES.items():
        try:
            pos = gauge_fn(feats)
        except Exception:
            pos = 50.0
        pos = float(np.clip(pos, 0.0, 100.0))
        positions.append(pos)
        details[name] = round(pos, 1)

    pos_arr = np.array(positions)

    # 裁尾均值: 去掉最高3个和最低3个
    n = len(pos_arr)
    if n >= 8:
        sorted_pos = np.sort(pos_arr)
        trimmed = sorted_pos[3:n-3]
        score = float(np.mean(trimmed))
    else:
        score = float(np.median(pos_arr))

    # 偏向计数
    high_count = int(np.sum(pos_arr > 60))
    low_count = int(np.sum(pos_arr < 40))
    lean = high_count - low_count

    # 方向对齐评分
    # long: 低分好 (0→+1, 100→-1)
    # short: 高分好 (0→-1, 100→+1)
    if direction == 'long':
        biases = [(100.0 - p) / 50.0 - 1.0 for p in positions]  # 0→+1, 50→0, 100→-1
    else:
        biases = [p / 50.0 - 1.0 for p in positions]             # 0→-1, 50→0, 100→+1
    bias_mean = float(np.mean(biases))

    # 分级
    if direction == 'long':
        if score <= 25 and lean <= -5:
            grade = 'A'   # 极低 + 多数偏低 → 绝佳做多位
        elif score <= 35 and lean <= -2:
            grade = 'B'   # 偏低 → 良好做多位
        elif score >= 75 and lean >= 5:
            grade = 'F'   # 极高 + 多数偏高 → 危险做多位
        elif score >= 65 and lean >= 2:
            grade = 'D'   # 偏高 → 不建议做多
        else:
            grade = 'C'   # 中性
    else:
        if score >= 75 and lean >= 5:
            grade = 'A'   # 极高 + 多数偏高 → 绝佳做空位
        elif score >= 65 and lean >= 2:
            grade = 'B'   # 偏高 → 良好做空位
        elif score <= 25 and lean <= -5:
            grade = 'F'   # 极低 + 多数偏低 → 危险做空位
        elif score <= 35 and lean <= -2:
            grade = 'D'   # 偏低 → 不建议做空
        else:
            grade = 'C'   # 中性

    return {
        'gauges': details,
        'score': round(score),
        'lean': lean,
        'grade': grade,
        'high_count': high_count,
        'low_count': low_count,
        'bias_mean': round(bias_mean, 4),
    }
