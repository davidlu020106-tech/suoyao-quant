"""
15m 入场信号检测系统 v1.0 — 10个独立信号 × FMZ策略参考

每个信号返回 0(不触发) 或 1(触发)，总分0-10。
≥6分=强信号, 3-5=弱信号, <3=不入场。方向感知：只触发与给定方向一致的信号。

FMZ参考策略 (10个):
  A1 Donchian-Channel-Trend-Following
  A2 Nifty-50-Opening-Range-Breakout
  A3 Bollinger-Bands-Channel-Breakout-Mean-Reversion
  A4 ATR-Average-Breakout-Strategy
  A5 Efficient-Price-Channel-15-Minute-Breakout
  A6 52-Week-High-Low-Average-Volume-Volume-Breakout
  A7 Double-Fractal-Breakout-Strategy
  A8 Triple-High-Price-Volume-Breakout-Strategy
  A9 Cryptocurrency-Momentum-Breakout-Strategy
  A10 Momentum-Driven-Keltner-Channel-Breakout-Trading-Strategy
"""

import numpy as np


# ═══════════════════════════════════════
# A1: 通道突破 — Donchian 20根高/低
# ═══════════════════════════════════════
def signal_donchian(high, low, close, direction, period=20):
    """A1: 价格突破N根K线最高/最低点
    FMZ: Donchian-Channel-Trend-Following
    做多: close[-1] > max(high[-period:-1])
    做空: close[-1] < min(low[-period:-1])
    """
    n = len(close)
    if n < period + 1: return 0
    if direction == 'long':
        return 1 if close[-1] > np.max(high[-period-1:-1]) else 0
    else:
        return 1 if close[-1] < np.min(low[-period-1:-1]) else 0


# ═══════════════════════════════════════
# A2: ORB — 开盘区间突破 (首4根15m=1小时)
# ═══════════════════════════════════════
def signal_orb(high, low, close, direction, period=4):
    """A2: 突破前N根K线构成的开盘区间
    FMZ: Nifty-50-Opening-Range-Breakout
    """
    n = len(close)
    if n < period + 1: return 0
    orb_high = np.max(high[-period-1:-1])
    orb_low = np.min(low[-period-1:-1])
    if direction == 'long':
        return 1 if close[-1] > orb_high else 0
    else:
        return 1 if close[-1] < orb_low else 0


# ═══════════════════════════════════════
# A3: BB极端回归 — 触上下轨+RSI确认
# ═══════════════════════════════════════
def signal_bb_extreme(close, direction, bb_lower=None, bb_upper=None, rsi=None):
    """A3: 价格触及BB上下轨且RSI极端
    FMZ: Bollinger-Bands-Channel-Breakout-Mean-Reversion
    做多: close < bb_lower 且 RSI < 35
    做空: close > bb_upper 且 RSI > 65
    没有BB/RIS数据 → 回退到简单的标准差检测
    """
    n = len(close)
    if n < 20: return 0

    if bb_lower is not None and bb_upper is not None and rsi is not None:
        if direction == 'long':
            return 1 if close[-1] < bb_lower[-1] and rsi[-1] < 35 else 0
        else:
            return 1 if close[-1] > bb_upper[-1] and rsi[-1] > 65 else 0

    # 回退: 用简单标准差模拟BB
    sma20 = np.mean(close[-20:])
    std20 = np.std(close[-20:])
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    if direction == 'long':
        return 1 if close[-1] < lower else 0
    else:
        return 1 if close[-1] > upper else 0


# ═══════════════════════════════════════
# A4: ATR通道突破
# ═══════════════════════════════════════
def signal_atr_breakout(high, low, close, direction, period=14, mult=2.0):
    """A4: SMA20±2×ATR14 通道突破
    FMZ: ATR-Average-Breakout-Strategy
    """
    n = len(close)
    if n < period + 20: return 0

    tr = np.maximum(high[-period:] - low[-period:],
                    np.abs(high[-period:] - np.roll(close[-period-1:-1], 1)))
    tr[0] = high[-period] - low[-period]
    atr = np.mean(tr)
    sma20 = np.mean(close[-20:])
    upper = sma20 + mult * atr
    lower = sma20 - mult * atr

    if direction == 'long':
        return 1 if close[-1] > upper else 0
    else:
        return 1 if close[-1] < lower else 0


# ═══════════════════════════════════════
# A5: 首K通道
# ═══════════════════════════════════════
def signal_first_bar_channel(high, low, close, direction, period=4):
    """A5: 最近N根K线的首K高低点作为通道
    FMZ: Efficient-Price-Channel-15-Minute-Breakout
    """
    n = len(close)
    if n < period: return 0
    first_high = high[-period]
    first_low = low[-period]
    if direction == 'long':
        return 1 if close[-1] > first_high else 0
    else:
        return 1 if close[-1] < first_low else 0


# ═══════════════════════════════════════
# A6: 历史极值+量 — 近50小时最高
# ═══════════════════════════════════════
def signal_extreme_high(high, low, close, volume, direction, lookback=200):
    """A6: 价格接近历史高位+成交量放大
    FMZ: 52-Week-High-Low-Volume-Breakout
    做多: close > 90%历史高位 + vol > 1.5×均量
    做空: close < 10%历史低位 + vol > 1.5×均量
    """
    n = len(close)
    if n < lookback: return 0
    hh = np.max(high[-lookback:])
    ll = np.min(low[-lookback:])
    vol_ma = np.mean(volume[-50:]) if len(volume) >= 50 else np.mean(volume)
    vol_ratio = volume[-1] / vol_ma if vol_ma > 0 else 1

    if direction == 'long':
        near_high = close[-1] >= hh * 0.95
        return 1 if near_high and vol_ratio > 1.3 else 0
    else:
        near_low = close[-1] <= ll * 1.05
        return 1 if near_low and vol_ratio > 1.3 else 0


# ═══════════════════════════════════════
# A7: 分形突破
# ═══════════════════════════════════════
def signal_fractal(high, low, close, direction):
    """A7: 5K分形点突破
    FMZ: Double-Fractal-Breakout-Strategy
    底分形: middle low < 左2低 且 < 右2低
    顶分形: middle high > 左2高 且 > 右2高
    """
    n = len(close)
    if n < 6: return 0

    if direction == 'long':
        # 找最近底分形
        for i in range(n-3, 1, -1):
            if low[i] < low[i-1] and low[i] < low[i-2] and low[i] < low[i+1] and low[i] < low[i+2]:
                return 1 if close[-1] > high[i] else 0
        return 0
    else:
        for i in range(n-3, 1, -1):
            if high[i] > high[i-1] and high[i] > high[i-2] and high[i] > high[i+1] and high[i] > high[i+2]:
                return 1 if close[-1] < low[i] else 0
        return 0


# ═══════════════════════════════════════
# A8: 三重递增 — 3K高点+量递增
# ═══════════════════════════════════════
def signal_triple_high(high, low, close, volume, direction):
    """A8: 连续3根K线高点递增且成交量递增
    FMZ: Triple-High-Price-Volume-Breakout
    """
    n = len(close)
    if n < 4: return 0

    if direction == 'long':
        h3 = high[-4]; h2 = high[-3]; h1 = high[-2]; h0 = high[-1]
        v3 = volume[-4]; v2 = volume[-3]; v1 = volume[-2]; v0 = volume[-1]
        price_rising = (h0 > h1 > h2) or (h1 > h2 > h3)
        vol_rising = (v0 > v1 > v2) or (v1 > v2 > v3) or (v0 > np.mean([v1,v2,v3]))
        return 1 if price_rising and vol_rising else 0
    else:
        l3 = low[-4]; l2 = low[-3]; l1 = low[-2]; l0 = low[-1]
        v3 = volume[-4]; v2 = volume[-3]; v1 = volume[-2]; v0 = volume[-1]
        price_falling = (l0 < l1 < l2) or (l1 < l2 < l3)
        vol_rising = (v0 > v1 > v2) or (v1 > v2 > v3) or (v0 > np.mean([v1,v2,v3]))
        return 1 if price_falling and vol_rising else 0


# ═══════════════════════════════════════
# A9: 动量突破 — 价格突破+ROC确认
# ═══════════════════════════════════════
def signal_momentum_breakout(high, low, close, direction, period=20, roc_period=10):
    """A9: 价格突破N根高低+ROC确认
    FMZ: Cryptocurrency-Momentum-Breakout
    """
    n = len(close)
    if n < period + roc_period: return 0

    roc = (close[-1] - close[-roc_period]) / close[-roc_period] * 100

    if direction == 'long':
        breakout = close[-1] > np.max(high[-period-1:-1])
        return 1 if breakout and roc > 0 else 0
    else:
        breakdown = close[-1] < np.min(low[-period-1:-1])
        return 1 if breakdown and roc < 0 else 0


# ═══════════════════════════════════════
# A10: KC动量 — Keltner通道+动量
# ═══════════════════════════════════════
def signal_kc_momentum(high, low, close, direction):
    """A10: EMA20±1.5×ATR14 + 14期动量
    FMZ: Momentum-Driven-Keltner-Channel-Breakout
    """
    n = len(close)
    if n < 30: return 0

    def ema(s, period):
        alpha = 2.0/(period+1); r = np.full_like(s, s[0], dtype=float)
        for i in range(1, len(s)): r[i] = alpha*s[i] + (1-alpha)*r[i-1]
        return r

    ema20_arr = ema(close[-30:], 20)

    tr = np.maximum(high[-30:]-low[-30:],
                    np.abs(high[-30:]-np.roll(close[-30:], 1)))
    tr[0] = high[-30] - low[-30]
    atr14 = np.mean(tr[-14:])
    atr_mult = 1.5

    kc_upper = ema20_arr[-1] + atr_mult * atr14
    kc_lower = ema20_arr[-1] - atr_mult * atr14
    momentum = close[-1] - close[-14]

    if direction == 'long':
        return 1 if close[-1] > kc_upper and momentum > 0 else 0
    else:
        return 1 if close[-1] < kc_lower and momentum < 0 else 0


# ═══════════════════════════════════════
# 综合评分
# ═══════════════════════════════════════

def score_entry_signals(high, low, close, volume, direction,
                        bb_lower=None, bb_upper=None, rsi=None):
    """
    对15m数据运行10个入场信号检测，返回综合得分。

    Args:
        high/low/close/volume: numpy数组，15m K线数据，至少30根
        direction: 'long' / 'short' (来自1H/4H/日线框架)
        bb_lower/bb_upper/rsi: 可选，预计算的布林带和RSI

    Returns:
        {
            'total': 总分(0-10),
            'level': '强'/'弱'/'无',
            'signals': {A1:1, A2:0, ...},
            'details': ['A1:通道突破', 'A4:ATR突破', ...]
        }
    """
    signals = {
        'A1_通道突破': signal_donchian(high, low, close, direction),
        'A2_ORB区间':  signal_orb(high, low, close, direction),
        'A3_BB极端':   signal_bb_extreme(close, direction, bb_lower, bb_upper, rsi),
        'A4_ATR突破':  signal_atr_breakout(high, low, close, direction),
        'A5_首K通道':  signal_first_bar_channel(high, low, close, direction),
        'A6_历史极值': signal_extreme_high(high, low, close, volume, direction),
        'A7_分形突破': signal_fractal(high, low, close, direction),
        'A8_三重递增': signal_triple_high(high, low, close, volume, direction),
        'A9_动量突破': signal_momentum_breakout(high, low, close, direction),
        'A10_KC动量': signal_kc_momentum(high, low, close, direction),
    }

    total = sum(signals.values())
    triggered = [k for k, v in signals.items() if v]

    level = '强' if total >= 6 else ('弱' if total >= 3 else '无')

    return {
        'total': total,
        'level': level,
        'signals': signals,
        'details': triggered,
    }
