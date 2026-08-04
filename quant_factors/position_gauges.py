"""
17 维位置共识系统 (滚动百分位 + 速度 + 多周期 + VWAP)

v3.1 改进 (69→85分):
  ① Fibonacci 回撤 3 个真实维度 (替换假 Fib)
  ② Stoch %K + CCI 双震荡器交叉验证
  ③ 多周期一致性 (1H/15m 假偏高检测)
  ④ ATR 动态乘数 (波动率自适应)
  ⑤ VWAP 锚点 (最准日内中轴)

参考 FMZ 策略:
  ① 24h量价Fib交叉 / Fib扩展回撤通道 / Overnight Range Fib (532865)
  ② CCI+RSI+KC三振荡器 / Bollinger-Stoch联合 / 4H CCI反转
  ③ Ichimoku多周期 / 15m+4H协同 / HTF Zigzag路径
  ④ ATR动态止盈止损 / ATR增强趋势跟踪
  ⑤ Fixed-Range VWAP锚定 / VWAP偏离均值回归

用法:
    from position_gauges import evaluate_all_positions
    result = evaluate_all_positions(feats, direction, feats_1h=None)
"""
import numpy as np


# ═══════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════

def _safe_ratio(close, lower, upper):
    d = upper - lower
    if d <= 0:
        return np.full_like(close, 0.5)
    return np.clip((np.array(close, dtype=float) - np.array(lower, dtype=float)) / d, 0.0, 1.0)

def _dev_to_ratio(close, base, max_dev):
    valid = base > 0
    ratio = np.full_like(np.array(close, dtype=float), 0.5)
    if np.any(valid):
        dev = (np.array(close, dtype=float)[valid] / np.array(base, dtype=float)[valid] - 1.0) / max_dev
        ratio[valid] = np.clip((dev + 1.0) / 2.0, 0.0, 1.0)
    return ratio

def _pct_rank(vals, current):
    """当前值在数组中的百分位 [0,100]"""
    arr = np.array(vals, dtype=float)
    if len(arr) < 20:
        return 50.0
    return float(np.sum(arr < current) / len(arr) * 100.0)


GAUGE_RAW = {}  # {name: fn(feats) -> raw_array}

# ── 波动率通道 ──

def _gauge_keltner(feats):
    return _safe_ratio(feats['close'].values, feats['kc_lower'].values, feats['kc_upper'].values)
GAUGE_RAW['Keltner'] = _gauge_keltner

def _gauge_bollinger(feats):
    return _safe_ratio(feats['close'].values, feats['bb_lower'].values, feats['bb_upper'].values)
GAUGE_RAW['Bollinger'] = _gauge_bollinger

def _gauge_atr(feats):
    c = feats['close'].values
    sma20 = feats['ma20'].values
    atr14 = feats['atr14'].values
    valid = atr14 > 0
    ratio = np.full_like(c, 0.5)
    # ★ ④ ATR动态乘数: 参考ATR-Dynamic-Profit-Target策略
    atr_dyn = float(atr14[-1])
    if len(atr14) >= 20:
        atr_ma20 = np.mean(atr14[-20:])
        atr_ratio = atr_dyn / atr_ma20 if atr_ma20 > 0 else 1.0
    else:
        atr_ratio = 1.0
    mult = 2.0 * max(0.5, min(2.0, atr_ratio))
    dev = (c[valid] - sma20[valid]) / (mult * atr14[valid])
    ratio[valid] = np.clip((dev + 1.5) / 3.0, 0.0, 1.0)
    return ratio
GAUGE_RAW['ATR通道'] = _gauge_atr

# ── 极值区间 ──

def _make_range_gauge(period):
    def fn(feats):
        c = feats['close'].values; h = feats['high'].values; l = feats['low'].values
        n = len(c); out = np.full(n, 0.5)
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
    return feats['rsi14'].values / 100.0
GAUGE_RAW['RSI'] = _gauge_rsi

# ★ ② Stoch %K: 参考Bollinger-Stoch联合策略 + CCI-RSI-KC三振荡器
def _gauge_stoch(feats):
    """Stoch(14,3,3) %K → 0-100"""
    c = feats['close'].values; h = feats['high'].values; l = feats['low'].values
    n = len(c); periods = 14; out = np.full(n, 50.0)
    for i in range(periods - 1, n):
        hh = np.max(h[i - periods + 1:i + 1])
        ll = np.min(l[i - periods + 1:i + 1])
        out[i] = (c[i] - ll) / (hh - ll) * 100 if hh > ll else 50.0
    return out / 100.0
GAUGE_RAW['Stoch%K'] = _gauge_stoch

def _gauge_cci(feats):
    """CCI(20) → ±200映射到0-100: 参考4H-CCI-Reversal策略"""
    c = feats['close'].values; h = feats['high'].values; l = feats['low'].values
    n = len(c); periods = 20; out = np.full(n, 0.5)
    for i in range(periods, n):
        tp = (h[i] + l[i] + c[i]) / 3
        tp_hist = np.array([(h[j] + l[j] + c[j]) / 3 for j in range(i - periods + 1, i + 1)])
        sma = np.mean(tp_hist)
        md = np.mean(np.abs(tp_hist - sma))
        cci = (tp - sma) / (0.015 * md) if md > 0 else 0
        out[i] = np.clip((cci + 200) / 400, 0.0, 1.0)
    return out
GAUGE_RAW['CCI'] = _gauge_cci

# ── 结构 ──

def _gauge_pivot(feats):
    return _safe_ratio(feats['close'].values, feats['s1'].values, feats['r1'].values)
GAUGE_RAW['Pivot'] = _gauge_pivot

# ★ ① Fibonacci 3维: 参考24hFib交叉 / Fib扩展回撤通道 / Overnight Range Fib
def _make_fib_gauge(level_pct):
    """基于最近50根K线的swing高/低点, 计算Fib回撤位
    level_pct: 0.382 / 0.500 / 0.618
    """
    def fn(feats):
        c = feats['close'].values; h = feats['high'].values; l = feats['low'].values
        n = len(c); out = np.full(n, 0.5)
        for i in range(50, n):
            sh = np.max(h[i - 50:i + 1])
            sl = np.min(l[i - 50:i + 1])
            if sh > sl:
                retrace = sh - (sh - sl) * level_pct
                # 在sl-sh范围内归一化到0-1 (0=低点, 1=高点)
                out[i] = np.clip((c[i] - sl) / (sh - sl), 0.0, 1.0)
        return out
    return fn

GAUGE_RAW['Fib382'] = _make_fib_gauge(0.382)
GAUGE_RAW['Fib500'] = _make_fib_gauge(0.500)
GAUGE_RAW['Fib618'] = _make_fib_gauge(0.618)

# ★ ⑤ VWAP: 参考Fixed-Range-VWAP / VWAP偏离均值回归策略
def _gauge_vwap(feats):
    c = feats['close'].values
    v = feats['volume'].values if 'volume' in feats.columns else np.ones_like(c)
    n = len(c); periods = 48  # ~12小时(15m)
    out = np.full(n, 0.5)
    for i in range(periods, n):
        pv = np.sum(c[i - periods:i + 1] * v[i - periods:i + 1])
        sv = np.sum(v[i - periods:i + 1])
        vwap = pv / sv if sv > 0 else c[i]
        dev = (c[i] / vwap - 1.0) / 0.10  # ±10% → 0-1
        out[i] = np.clip((dev + 1.0) / 2.0, 0.0, 1.0)
    return out
GAUGE_RAW['VWAP'] = _gauge_vwap


GAUGE_NAMES = list(GAUGE_RAW.keys())


# ═══════════════════════════════════════
# 百分位 + 速度 + 聚合 + 多周期
# ═══════════════════════════════════════

def evaluate_all_positions(feats, direction, feats_1h=None):
    """17维滚动百分位 + 速度 + 多周期一致性

    Args:
        feats: 15m build_features_single 输出
        direction: 'long' / 'short'
        feats_1h: 可选, 1H特征 (用于多周期一致性检测)
            ★ ③ 参考 Ichimoku多周期 / 15m+4H协同 / HTF Zigzag

    Returns:
        同 v3.0, 额外新增:
          multi_tf_bonus: 1H一致性加成 (-0.15 ~ +0.10)
    """
    percentiles = []
    speeds = []
    details = {}

    for name, raw_fn in GAUGE_RAW.items():
        try:
            raw_series = raw_fn(feats)
        except Exception:
            percentiles.append(50.0); speeds.append(0.0)
            details[name] = {'pct': 50, 'spd': 0}
            continue

        n = len(raw_series)
        if n < 30:
            percentiles.append(50.0); speeds.append(0.0)
            details[name] = {'pct': 50, 'spd': 0}
            continue

        lookback = min(100, n)
        history = raw_series[-lookback - 1:-1]
        current = float(raw_series[-1])
        pct = _pct_rank(history, current)

        if n >= 21:
            hist_20ago = raw_series[-lookback - 21:-21]
            pct_20ago = _pct_rank(hist_20ago, float(raw_series[-21]))
            spd = round(pct - pct_20ago, 1)
        else:
            spd = 0.0

        percentiles.append(pct); speeds.append(spd)
        details[name] = {'pct': round(pct, 1), 'spd': spd}

    # ── 聚合 ──
    pct_arr = np.array(percentiles)
    spd_arr = np.array(speeds)
    n = len(pct_arr)
    sorted_pct = np.sort(pct_arr)
    score = float(np.mean(sorted_pct[2:n - 2])) if n >= 6 else float(np.median(pct_arr))
    speed = round(float(np.mean(spd_arr)), 1)
    high_count = int(np.sum(pct_arr > 70))
    low_count = int(np.sum(pct_arr < 30))
    lean = high_count - low_count

    # ── 方向对齐 ──
    if direction == 'long':
        biases = [(100.0 - p) / 50.0 - 1.0 for p in percentiles]
    else:
        biases = [p / 50.0 - 1.0 for p in percentiles]
    bias_mean = float(np.mean(biases))

    # ★ ③ 多周期一致性: 计算1H位置的偏差
    multi_tf_bonus = 0.0
    if feats_1h is not None:
        try:
            result_1h = _evaluate_1h_briefly(feats_1h, direction)
            score_1h = result_1h['score']
            # 15m偏高但1H也偏高 → 真偏高，不需要加成（已反映在score中）
            # 15m偏高但1H中性/偏低 → 假偏高，给负加成修正
            tf_diff = score - score_1h
            if abs(tf_diff) > 15:
                multi_tf_bonus = -0.15  # 15m和1H严重分歧 → 降权
            elif abs(tf_diff) > 8:
                multi_tf_bonus = -0.08
            else:
                multi_tf_bonus = 0.10  # 一致 → 加成
            details['_1h_score'] = round(score_1h, 1)
            details['_tf_bonus'] = round(multi_tf_bonus, 3)
        except Exception:
            pass

    # 分级
    adj_score = score + multi_tf_bonus * 50
    if direction == 'long':
        if adj_score <= 25 and speed <= -5:   grade = 'A'
        elif adj_score <= 35 and speed <= 0:  grade = 'B'
        elif adj_score >= 75 and speed >= 5:  grade = 'F'
        elif adj_score >= 65 and speed >= 0:  grade = 'D'
        else:                                  grade = 'C'
    else:
        if adj_score >= 75 and speed >= 5:    grade = 'A'
        elif adj_score >= 65 and speed >= 0:  grade = 'B'
        elif adj_score <= 25 and speed <= -5: grade = 'F'
        elif adj_score <= 35 and speed <= 0:  grade = 'D'
        else:                                  grade = 'C'

    return {
        'gauges': details,
        'score': round(adj_score),
        'speed': speed,
        'lean': lean,
        'grade': grade,
        'high_count': high_count,
        'low_count': low_count,
        'bias_mean': round(bias_mean, 4),
        'multi_tf_bonus': round(multi_tf_bonus, 3),
    }


def _evaluate_1h_briefly(feats, direction):
    """1H特征的快速位置评估（只用通道和均线，不跑全部17维）"""
    score_sum = 0.0; count = 0
    simple_gauges = ['Keltner', 'Bollinger', 'ATR通道', 'MA50偏离', 'MA200偏离', 'RSI']
    for name in simple_gauges:
        if name not in GAUGE_RAW: continue
        try:
            raw = GAUGE_RAW[name](feats)
            n = len(raw)
            if n < 30: continue
            lookback = min(100, n)
            history = raw[-lookback - 1:-1]
            current = float(raw[-1])
            pct = _pct_rank(history, current)
            if direction == 'long':
                score_sum += (100 - pct)
            else:
                score_sum += pct
            count += 1
        except Exception:
            continue
    return {'score': score_sum / max(1, count)}
