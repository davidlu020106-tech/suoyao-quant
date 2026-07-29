"""
12 维位置共识系统 (滚动百分位 + 速度)

不再用绝对位置——牛市长期偏高、熊市长期偏低，绝对值没意义。
改用滚动百分位: 当前值在近100根K线中排第几？排50=正常，排90=真极端。

每个维度输出:
  percentile: 0-100 百分位 (50=历史中位)
  speed:      当前百分位 - 20根K线前的百分位 (正=恶化, 负=改善)

用法:
    from position_gauges import evaluate_all_positions
    result = evaluate_all_positions(feats, direction)
    # result['score'] = 裁尾均值百分位
    # result['speed'] = 平均速度
    # result['grade'] = A~F
"""

import numpy as np


# ═══════════════════════════════════════
# 12 个原始值提取器 (各返回全序列以便算百分位)
# ═══════════════════════════════════════

def _safe_ratio(close, lower, upper):
    """安全比例, 除零时返回 0.5"""
    d = upper - lower
    if d <= 0:
        return np.full_like(close, 0.5)
    return np.clip((np.array(close, dtype=float) - np.array(lower, dtype=float)) / d, 0.0, 1.0)


def _dev_to_ratio(close, base, max_dev):
    """偏离度转比例: (close/base-1)/max_dev → [0,1]"""
    valid = base > 0
    ratio = np.full_like(np.array(close, dtype=float), 0.5)
    if np.any(valid):
        dev = (np.array(close, dtype=float)[valid] / np.array(base, dtype=float)[valid] - 1.0) / max_dev
        ratio[valid] = np.clip((dev + 1.0) / 2.0, 0.0, 1.0)
    return ratio


GAUGE_RAW = {}  # {name: fn(feats) -> raw_array}

# ── 波动率通道 ──

def _gauge_keltner(feats):
    c = feats['close'].values
    ku = feats['kc_upper'].values
    kl = feats['kc_lower'].values
    return _safe_ratio(c, kl, ku)
GAUGE_RAW['Keltner'] = _gauge_keltner

def _gauge_bollinger(feats):
    c = feats['close'].values
    bu = feats['bb_upper'].values
    bl = feats['bb_lower'].values
    return _safe_ratio(c, bl, bu)
GAUGE_RAW['Bollinger'] = _gauge_bollinger

def _gauge_atr(feats):
    c = feats['close'].values
    sma20 = feats['ma20'].values
    atr14 = feats['atr14'].values
    valid = atr14 > 0
    ratio = np.full_like(c, 0.5)
    dev = (c[valid] - sma20[valid]) / (2.0 * atr14[valid])
    ratio[valid] = np.clip((dev + 1.5) / 3.0, 0.0, 1.0)
    return ratio
GAUGE_RAW['ATR通道'] = _gauge_atr

# ── 极值区间 ──

def _make_range_gauge(period):
    def fn(feats):
        c = feats['close'].values
        h = feats['high'].values
        l = feats['low'].values
        n = len(c)
        out = np.full(n, 0.5)
        for i in range(period - 1, n):
            hh = np.max(h[i - period + 1:i + 1])
            ll = np.min(l[i - period + 1:i + 1])
            if hh > ll:
                out[i] = np.clip((c[i] - ll) / (hh - ll), 0.0, 1.0)
        return out
    return fn

GAUGE_RAW['10日区间'] = _make_range_gauge(10)
GAUGE_RAW['20日区间'] = _make_range_gauge(20)
GAUGE_RAW['50日区间'] = _make_range_gauge(50)

# ── 均线偏离 ──

def _gauge_sma10(feats):
    c = feats['close'].values
    sma10 = np.convolve(c, np.ones(10)/10, mode='same')
    sma10[:9] = c[:9]
    return _dev_to_ratio(c, sma10, 0.15)
GAUGE_RAW['SMA10偏离'] = _gauge_sma10

def _gauge_ma50(feats):
    return _dev_to_ratio(feats['close'].values, feats['ma50'].values, 0.20)
GAUGE_RAW['MA50偏离'] = _gauge_ma50

def _gauge_ma200(feats):
    ma200 = feats.get('ma200', feats['ma100']).values
    return _dev_to_ratio(feats['close'].values, ma200, 0.50)
GAUGE_RAW['MA200偏离'] = _gauge_ma200

# ── 动量 ──

def _gauge_rsi(feats):
    return feats['rsi14'].values / 100.0  # RSI天然0-100
GAUGE_RAW['RSI'] = _gauge_rsi

# ── 结构 ──

def _gauge_pivot(feats):
    c = feats['close'].values
    r1 = feats['r1'].values
    s1 = feats['s1'].values
    return _safe_ratio(c, s1, r1)
GAUGE_RAW['Pivot'] = _gauge_pivot

def _gauge_fib(feats):
    c = feats['close'].values
    h = feats['high'].values
    l = feats['low'].values
    n = len(c)
    out = np.full(n, 0.5)
    for i in range(50, n):
        sh = np.max(h[i - 50:i + 1])
        sl = np.min(l[i - 50:i + 1])
        if sh > sl:
            out[i] = np.clip((c[i] - sl) / (sh - sl), 0.0, 1.0)
    return out
GAUGE_RAW['Fib'] = _gauge_fib

GAUGE_NAMES = list(GAUGE_RAW.keys())


# ═══════════════════════════════════════
# 百分位 + 速度 + 聚合
# ═══════════════════════════════════════

def _percentile(current_val, history_vals):
    """当前值在历史序列中的百分位 [0, 100]"""
    if len(history_vals) < 20:
        return 50.0
    return float(np.sum(history_vals < current_val) / len(history_vals) * 100.0)


def evaluate_all_positions(feats, direction):
    """12维滚动百分位 + 速度

    Returns:
        score: 裁尾均值百分位 0-100
        speed: 平均速度 (正=恶化, 负=改善)
        lean:  偏高维度数 - 偏低维度数
        grade: A~F
        high_count, low_count
        bias_mean: 方向对齐评分
    """
    percentiles = []
    speeds = []
    details = {}

    for name, raw_fn in GAUGE_RAW.items():
        try:
            raw_series = raw_fn(feats)
        except Exception:
            percentiles.append(50.0)
            speeds.append(0.0)
            details[name] = {'pct': 50, 'spd': 0}
            continue

        n = len(raw_series)
        if n < 30:
            percentiles.append(50.0)
            speeds.append(0.0)
            details[name] = {'pct': 50, 'spd': 0}
            continue

        # 滚动百分位(近100根)
        lookback = min(100, n)
        history = raw_series[-lookback - 1:-1]  # 不含当前
        current = float(raw_series[-1])
        pct = _percentile(current, history)

        # 速度: 当前百分位 vs 20根前
        if n >= 21:
            history_20ago = raw_series[-lookback - 21:-21]
            pct_20ago = _percentile(float(raw_series[-21]), history_20ago)
            spd = round(pct - pct_20ago, 1)
        else:
            spd = 0.0

        percentiles.append(pct)
        speeds.append(spd)
        details[name] = {'pct': round(pct, 1), 'spd': spd}

    # 聚合
    pct_arr = np.array(percentiles)
    spd_arr = np.array(speeds)

    # 裁尾均值 (去最高最低各2个)
    n = len(pct_arr)
    if n >= 6:
        sorted_pct = np.sort(pct_arr)
        score = float(np.mean(sorted_pct[2:n - 2]))
    else:
        score = float(np.median(pct_arr))

    speed = round(float(np.mean(spd_arr)), 1)
    high_count = int(np.sum(pct_arr > 70))
    low_count = int(np.sum(pct_arr < 30))
    lean = high_count - low_count

    # 方向对齐
    if direction == 'long':
        biases = [(100.0 - p) / 50.0 - 1.0 for p in percentiles]
    else:
        biases = [p / 50.0 - 1.0 for p in percentiles]
    bias_mean = float(np.mean(biases))

    # 分级 (结合百分位和速度)
    if direction == 'long':
        if score <= 25 and speed <= -5:
            grade = 'A'  # 极低+改善中
        elif score <= 35 and speed <= 0:
            grade = 'B'
        elif score >= 75 and speed >= 5:
            grade = 'F'  # 极高+恶化中
        elif score >= 65 and speed >= 0:
            grade = 'D'
        else:
            grade = 'C'
    else:
        if score >= 75 and speed >= 5:
            grade = 'A'
        elif score >= 65 and speed >= 0:
            grade = 'B'
        elif score <= 25 and speed <= -5:
            grade = 'F'
        elif score <= 35 and speed <= 0:
            grade = 'D'
        else:
            grade = 'C'

    return {
        'gauges': details,
        'score': round(score),
        'speed': speed,
        'lean': lean,
        'grade': grade,
        'high_count': high_count,
        'low_count': low_count,
        'bias_mean': round(bias_mean, 4),
    }
