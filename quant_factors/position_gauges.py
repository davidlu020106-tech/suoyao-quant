"""
8 维位置共识系统 — 多维度判断币种相对位置

每个判断器接受 feats DataFrame + direction('long'/'short')，返回:
  position_01: [0,1] 归一化位置 (0=极低/支撑, 1=极高/阻力)
  bias_score:  [-1,1] 方向对齐评分 (正=位置支持当前方向, 负=位置反对)

参考 FMZ 策略广场对应策略的核心算法。

用法:
    from position_gauges import evaluate_all_positions, GAUGE_NAMES
    
    result = evaluate_all_positions(feats, 'long')
    # result['consensus'] = 8个维度的中位数位置
    # result['high_count'] = 偏高(>0.7)的维度数
    # result['bias_mean'] = 位置是否支持当前方向
"""

import numpy as np


def _pos_to_bias(pos_01, direction):
    """将归一化位置转为方向对齐评分。
    long: 低位置(0)→正面(+1), 高位置(1)→负面(-1)
    short: 高位置(1)→正面(+1), 低位置(0)→负面(-1)
    """
    if direction == 'long':
        return float(1.0 - 2.0 * pos_01)
    else:
        return float(2.0 * pos_01 - 1.0)


def _safe_pos(close, lower, upper):
    """安全计算区间位置, 防止除零"""
    if upper <= lower:
        return 0.5
    return float(np.clip((close - lower) / (upper - lower), 0.0, 1.0))


# ═══════════════════════════════════════
# 8 个位置判断器
# ═══════════════════════════════════════

def gauge_keltner(feats, direction):
    """Keltner通道位置 (EMA20 ± 2×ATR10)
    参考: 已有实现, 基准维度
    """
    c = float(feats['close'].iloc[-1])
    ku = float(feats['kc_upper'].iloc[-1])
    kl = float(feats['kc_lower'].iloc[-1])
    pos = _safe_pos(c, kl, ku)
    return pos, _pos_to_bias(pos, direction)


def gauge_bollinger(feats, direction):
    """Bollinger %B (SMA20 ± 2σ)
    参考 FMZ: Bollinger-Bands-Mean-Reversion w/ Dynamic-Support
    公式: %B = (close - lower) / (upper - lower)
    对极端波动比 Keltner 更敏感 (标准差 vs ATR)
    """
    c = float(feats['close'].iloc[-1])
    bu = float(feats['bb_upper'].iloc[-1])
    bl = float(feats['bb_lower'].iloc[-1])
    pos = _safe_pos(c, bl, bu)
    return pos, _pos_to_bias(pos, direction)


def gauge_ma50(feats, direction):
    """MA50偏离度
    参考 FMZ: Dual-MA-Deviation + ATR Trend-Following
    价格离中期均线多远, 偏离>20%视为极端
    """
    c = float(feats['close'].iloc[-1])
    ma50 = float(feats['ma50'].iloc[-1])
    if ma50 <= 0:
        return 0.5, 0.0
    dev = (c / ma50 - 1.0)
    # 归一化: ±20% → [0,1], 超出裁切
    pos = float(np.clip((dev + 0.20) / 0.40, 0.0, 1.0))
    return pos, _pos_to_bias(pos, direction)


def gauge_ma200(feats, direction):
    """MA200偏离度
    参考 FMZ: 200-EMA-VWAP-MFI Trend-Following
    山寨币专用: 低于MA200=长期价值区, 高于MA200=泡沫区
    归一化范围扩大到 ±50%
    """
    c = float(feats['close'].iloc[-1])
    ma200 = float(feats.get('ma200', feats['ma100']).iloc[-1])
    if ma200 <= 0:
        return 0.5, 0.0
    dev = (c / ma200 - 1.0)
    pos = float(np.clip((dev + 0.50) / 1.00, 0.0, 1.0))
    return pos, _pos_to_bias(pos, direction)


def gauge_20d_range(feats, direction):
    """20周期高低区间位置
    参考 FMZ: 5-day High-Low Breakout Price Channel
    公式: (close - low_20d) / (high_20d - low_20d)
    最直接的价格位置, 无均线平滑
    """
    c = float(feats['close'].iloc[-1])
    h20 = float(feats['high_20d'].iloc[-1])
    l20 = float(feats['low_20d'].iloc[-1])
    pos = _safe_pos(c, l20, h20)
    return pos, _pos_to_bias(pos, direction)


def gauge_pivot(feats, direction):
    """Pivot支撑阻力区间位置
    参考 FMZ: Dynamic-Support-and-Resistance-Adaptive-Pivot
    公式: (close - S1) / (R1 - S1)
    基于前一日高/低/收的推演支撑阻力
    """
    c = float(feats['close'].iloc[-1])
    r1 = float(feats['r1'].iloc[-1])
    s1 = float(feats['s1'].iloc[-1])
    pos = _safe_pos(c, s1, r1)
    return pos, _pos_to_bias(pos, direction)


def gauge_rsi(feats, direction):
    """RSI动量位置 (非价格位置)
    参考 FMZ: RSI-Overbought-Oversold-Crossover w/ BB Dynamic-Stop
    公式: (RSI - 30) / (70 - 30)
    动量过热/过冷代理, 极端值预示反转
    """
    rsi = float(feats['rsi14'].iloc[-1])
    pos = float(np.clip((rsi - 30.0) / 40.0, 0.0, 1.0))
    return pos, _pos_to_bias(pos, direction)


def gauge_fib(feats, direction):
    """Fibonacci回撤位置
    参考 FMZ: RSI + Fibonacci-Retracement Strategy
    基于最近摆动高/低点的相对位置
    对应 0.382/0.5/0.618 关键回撤位
    """
    high = feats['high'].values
    low = feats['low'].values
    c = float(feats['close'].iloc[-1])

    # 找最近的摆动高低点 (50根K线内)
    n = min(50, len(high))
    swing_high = float(np.max(high[-n:]))
    swing_low = float(np.min(low[-n:]))
    pos = _safe_pos(c, swing_low, swing_high)
    return pos, _pos_to_bias(pos, direction)


# ═══════════════════════════════════════
# 聚合
# ═══════════════════════════════════════

GAUGES = {
    'Keltner': gauge_keltner,
    'Bollinger': gauge_bollinger,
    'MA50偏离': gauge_ma50,
    'MA200偏离': gauge_ma200,
    '20日区间': gauge_20d_range,
    'Pivot区间': gauge_pivot,
    'RSI位置': gauge_rsi,
    'Fib回撤': gauge_fib,
}

GAUGE_NAMES = list(GAUGES.keys())


def evaluate_all_positions(feats, direction):
    """运行全部 8 个位置判断器, 返回共识结果

    Args:
        feats: build_features_single 输出的 DataFrame
        direction: 'long' 或 'short'

    Returns:
        {
            'gauges': {name: {'position': float, 'bias': float}},
            'consensus': float,        # 8维中位数 [0,1]
            'high_count': int,         # 偏高维度数 (>0.7)
            'low_count': int,          # 偏低维度数 (<0.3)
            'bias_mean': float,        # 平均方向对齐评分 [-1,1]
            'bias_agree': int,         # 支持当前方向的维度数
        }
    """
    positions = []
    biases = []
    details = {}

    for name, gauge_fn in GAUGES.items():
        try:
            pos, bias = gauge_fn(feats, direction)
        except Exception:
            pos, bias = 0.5, 0.0
        positions.append(pos)
        biases.append(bias)
        details[name] = {'position': round(pos, 4), 'bias': round(bias, 4)}

    pos_arr = np.array(positions)
    bias_arr = np.array(biases)

    return {
        'gauges': details,
        'consensus': round(float(np.median(pos_arr)), 4),
        'high_count': int(np.sum(pos_arr > 0.7)),
        'low_count': int(np.sum(pos_arr < 0.3)),
        'bias_mean': round(float(np.mean(bias_arr)), 4),
        'bias_agree': int(np.sum(bias_arr > 0)) if direction == 'long' else int(np.sum(bias_arr < 0)),
    }
