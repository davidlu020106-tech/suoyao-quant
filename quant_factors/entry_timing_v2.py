"""
15m 入场信号检测系统 v2.0 — 20个独立信号 × FMZ策略参考

每个信号返回 0(不触发) 或 1(触发)。
批次A: 价格突破 (A1-A10), 批次B: 回撤入场 (B1-B10)。
score_entry_signals_v2() 总分0-20: ≥12=强, 6-11=弱, <6=无。
方向感知：只触发与给定方向一致的信号。

FMZ参考策略:
  A1 Donchian-Channel-Trend-Following       B1 Fibonacci-Retracement-MA-Cross
  A2 Nifty-Opening-Range-Breakout           B2 EMA-Pullback (EMA33/165/365)
  A3 Bollinger-Bands-Mean-Reversion         B3 BB+AlphaTrend Mean-Reversion
  A4 ATR-Average-Breakout                   B4 Keltner-Channel-Pullback
  A5 Efficient-Price-Channel-15m            B5 RSI-Fibonacci-Retracement
  A6 52-Week-High-Low-Volume                B6 Multi-Zone MA100 Retracement
  A7 Double-Fractal-Breakout                B7 Donchian-Channel Retracement
  A8 Triple-High-Price-Volume               B8 MACD-Volume-Reversal
  A9 Cryptocurrency-Momentum-Breakout       B9 Bollinger-Bands-EMA-9
  A10 Momentum-Keltner-Channel              B10 Dual-MA Retracement
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


# ═══════════════════════════════════════
# 第二批: 回撤入场 (B1~B10)
# ═══════════════════════════════════════

def signal_fib_retrace(high, low, close, direction, lookback=50):
    """B1: 价格触及Fibonacci 0.5回撤位
    FMZ: Fibonacci-Retracement-MA-Cross"""
    n = len(close)
    if n < lookback: return 0
    rng = np.max(high[-lookback:]) - np.min(low[-lookback:])
    if rng <= 0: return 0
    rng = float(rng)
    fib50 = float(np.max(high[-lookback:])) - rng * 0.5
    return 1 if abs(float(close[-1]) - fib50) / rng < 0.03 else 0


def signal_ema_pullback(close, direction, short_p=33, long_p=165):
    """B2: 价格回踩短EMA且多头排列
    FMZ: EMA-Pullback"""
    n = len(close)
    if n < long_p: return 0
    def _ema(s, p):
        a = 2.0/(p+1); r = np.full_like(s, float(s[0]), dtype=float)
        for i in range(1,len(s)): r[i] = a*float(s[i]) + (1-a)*r[i-1]
        return r
    e_short = _ema(close[-long_p:], short_p)[-1]
    e_long = _ema(close[-long_p*2:], long_p)[-1]
    if direction == 'long':
        return 1 if close[-1] <= e_short * 1.01 and e_short > e_long else 0
    else:
        return 1 if close[-1] >= e_short * 0.99 and e_short < e_long else 0


def signal_bb_mean_revert(close, direction):
    """B3: BB下轨均值回归
    FMZ: BB Mean-Reversion"""
    n = len(close)
    if n < 20: return 0
    sma = np.mean(close[-20:]); std = np.std(close[-20:])
    if direction == 'long':
        return 1 if close[-1] < (sma - 2*std) * 1.01 else 0
    return 1 if close[-1] > (sma + 2*std) * 0.99 else 0


def signal_kc_pullback(high, low, close, direction):
    """B4: Keltner突破后回撤
    FMZ: Keltner-Channel-Pullback"""
    n = len(close)
    if n < 30: return 0
    ema20 = np.mean(close[-20:])
    tr = np.maximum(high[-14:]-low[-14:], np.abs(high[-14:]-np.roll(close[-14:],1)))
    atr = np.mean(tr)
    lower = ema20 - 1.5*atr; upper = ema20 + 1.5*atr
    if direction == 'long':
        return 1 if np.any(close[-10:-1] < lower) and close[-1] < lower else 0
    return 1 if np.any(close[-10:-1] > upper) and close[-1] > upper else 0


def signal_rsi_fib_deep(close, direction, rsi=None, lookback=50):
    """B5: RSI超卖+Fib 0.618深回撤
    FMZ: RSI-Fibonacci-Retracement"""
    n = len(close)
    if n < lookback: return 0
    hh = np.max(close[-lookback:]); ll = np.min(close[-lookback:])
    rng = hh - ll
    if rng <= 0: return 0
    fib = hh - rng * 0.618
    rsi_v = float(rsi[-1]) if rsi is not None else 50
    if direction == 'long':
        return 1 if abs(float(close[-1])-fib)/rng < 0.05 and rsi_v < 35 else 0
    fib2 = hh - rng * 0.382
    return 1 if abs(float(close[-1])-fib2)/rng < 0.05 and rsi_v > 65 else 0


def signal_ma_zone(close, direction):
    """B6: MA50-MA100区间
    FMZ: Multi-Zone MA100 Retracement"""
    n = len(close)
    if n < 100: return 0
    ma50 = np.mean(close[-50:]); ma100 = np.mean(close[-100:])
    if direction == 'long':
        return 1 if ma50 > close[-1] > ma100 else 0
    return 1 if ma50 < close[-1] < ma100 else 0


def signal_donchian_pullback(high, low, close, direction, period=20):
    """B7: Donchian下轨附近
    FMZ: Donchian Retracement"""
    n = len(close)
    if n < period: return 0
    d_high = np.max(high[-period:]); d_low = np.min(low[-period:])
    rng = d_high - d_low
    if rng <= 0: return 0
    if direction == 'long':
        return 1 if (close[-1] - d_low) / rng < 0.15 else 0
    return 1 if (d_high - close[-1]) / rng < 0.15 else 0


def signal_macd_volume_reversal(close, volume, direction):
    """B8: MACD反转+放量
    FMZ: MACD-Volume-Reversal"""
    n = len(close)
    if n < 30: return 0
    ema12 = np.mean(close[-12:]); ema26 = np.mean(close[-26:])
    prev12 = np.mean(close[-13:-1]); prev26 = np.mean(close[-27:-1])
    macd_now = ema12 - ema26; macd_prev = prev12 - prev26
    vol_r = volume[-1] / np.mean(volume[-20:]) if np.mean(volume[-20:])>0 else 1
    if direction == 'long':
        return 1 if macd_now > macd_prev and vol_r > 1.2 else 0
    return 1 if macd_now < macd_prev and vol_r > 1.2 else 0


def signal_bb_ema9_bounce(close, direction):
    """B9: EMA9下方+BB下轨上方
    FMZ: BB-EMA-9"""
    n = len(close)
    if n < 20: return 0
    ema9 = np.mean(close[-9:])
    sma = np.mean(close[-20:]); std = np.std(close[-20:])
    if direction == 'long':
        return 1 if close[-1] < ema9 and close[-1] > (sma-2*std) else 0
    return 1 if close[-1] > ema9 and close[-1] < (sma+2*std) else 0


def signal_dual_ma_retrace(close, direction):
    """B10: SMA20-SMA50之间
    FMZ: Dual-MA Retracement"""
    n = len(close)
    if n < 50: return 0
    s20 = np.mean(close[-20:]); s50 = np.mean(close[-50:])
    if direction == 'long':
        return 1 if s20 > close[-1] > s50 else 0
    return 1 if s20 < close[-1] < s50 else 0


# ═══════════════════════════════════════
# 综合评分 v2 (20个信号)
# ═══════════════════════════════════════

def score_entry_signals_v2(high, low, close, volume, direction,
                           bb_lower=None, bb_upper=None, rsi=None):
    """20个信号综合评分 A1-A10 + B1-B10, 总分0-20"""
    batch_a = {
        'A1_通道突破': signal_donchian(high, low, close, direction),
        'A2_ORB区间':  signal_orb(high, low, close, direction),
        'A3_BB极端':   signal_bb_extreme(close, direction, bb_lower, bb_upper, rsi),
        'A4_ATR突破':  signal_atr_breakout(high, low, close, direction),
        'A5_首K通道':  signal_first_bar_channel(high, low, close, direction),
        'A6_历史极值': signal_extreme_high(high, low, close, volume, direction),
        'A7_分形突破': signal_fractal(high, low, close, direction),
        'A8_三重递增': signal_triple_high(high, low, close, volume, direction),
        'A9_动量突破': signal_momentum_breakout(high, low, close, direction),
        'A10_KC动量':  signal_kc_momentum(high, low, close, direction),
    }
    batch_b = {
        'B1_Fib回撤':  signal_fib_retrace(high, low, close, direction),
        'B2_EMA回踩':  signal_ema_pullback(close, direction),
        'B3_BB回归':   signal_bb_mean_revert(close, direction),
        'B4_KC回撤':   signal_kc_pullback(high, low, close, direction),
        'B5_RSI深回撤': signal_rsi_fib_deep(close, direction, rsi),
        'B6_MA区间':   signal_ma_zone(close, direction),
        'B7_Donchian底': signal_donchian_pullback(high, low, close, direction),
        'B8_MACD反转': signal_macd_volume_reversal(close, volume, direction),
        'B9_BB弹跳':   signal_bb_ema9_bounce(close, direction),
        'B10_双MA回撤': signal_dual_ma_retrace(close, direction),
    }
    all_s = {**batch_a, **batch_b}
    total = sum(all_s.values())
    trig = [k for k,v in all_s.items() if v]
    level = '强' if total>=12 else ('弱' if total>=6 else '无')
    return {'total':total,'level':level,'signals':all_s,'details':trig,
            'breakout_score':sum(batch_a.values()),'pullback_score':sum(batch_b.values())}


# ═══════════════════════════════════════
# 第三批: K线反转形态 (C1~C10)
# ═══════════════════════════════════════

def signal_engulf_confirm(open_p, high, low, close, direction):
    """C1: 吞没形态+前反向吞没确认
    FMZ: 15m Engulfing Multi-Confirmation (胜率76%)"""
    n = len(close)
    if n < 4: return 0
    o0,c0,h0,l0=open_p[-1],close[-1],high[-1],low[-1]
    o1,c1=open_p[-2],close[-2]
    body0=abs(c0-o0); body1=abs(c1-o1)
    if direction=='long':
        if c0>o0 and c1<o1 and c0>o1 and o0<c1 and body0>0:
            for i in range(n-3,2,-1):
                if close[i]<open_p[i] and close[i-1]>open_p[i-1]:
                    return 1 if c0>high[i] else 0
            return 1
    else:
        if c0<o0 and c1>o1 and c0<o1 and o0>c1 and body0>0:
            for i in range(n-3,2,-1):
                if close[i]>open_p[i] and close[i-1]<open_p[i-1]:
                    return 1 if c0<low[i] else 0
            return 1
    return 0


def signal_engulf_atr(open_p, high, low, close, direction):
    """C2: 实体吞没+ATR确认
    FMZ: 4H Engulfing+动态止盈"""
    n=len(close)
    if n<3:return 0
    tr=np.maximum(high[-14:]-low[-14:],np.abs(high[-14:]-np.roll(close[-14:],1)))
    atr=np.mean(tr)
    body0=abs(close[-1]-open_p[-1])
    if body0<atr*0.5:return 0
    o0,c0,o1,c1=open_p[-1],close[-1],open_p[-2],close[-2]
    if direction=='long':
        return 1 if c0>o0 and c1<o1 and c0>o1 and o0<c1 else 0
    return 1 if c0<o0 and c1>o1 and c0<o1 and o0>c1 else 0


def signal_engulf_ratio(open_p, close, direction):
    """C3: 吞没比例>=3x
    FMZ: Bullish-Bearish-Engulfing"""
    n=len(close)
    if n<2:return 0
    b0=abs(close[-1]-open_p[-1]);b1=abs(close[-2]-open_p[-2])
    if b1<0.0001:return 0
    r=b0/b1
    if direction=='long':
        return 1 if close[-1]>open_p[-1] and close[-2]<open_p[-2] and close[-1]>open_p[-2] and r>3 else 0
    return 1 if close[-1]<open_p[-1] and close[-2]>open_p[-2] and close[-1]<open_p[-2] and r>3 else 0


def signal_hammer(open_p, high, low, close, direction):
    """C4: 锤子/Shooting Star
    FMZ: Inverted-Hammer"""
    n=len(close)
    if n<5:return 0
    c0,o0,h0,l0=close[-1],open_p[-1],high[-1],low[-1]
    body=abs(c0-o0)
    if body<0.0001:return 0
    uw=h0-max(c0,o0);lw=min(c0,o0)-l0
    if direction=='long':
        hammer=lw>body*2.5 and uw<body*0.5
        falling=close[-4]<close[-2] or close[-3]<close[-2]
        return 1 if hammer and falling else 0
    else:
        star=uw>body*2.5 and lw<body*0.5
        rising=close[-4]>close[-2] or close[-3]>close[-2]
        return 1 if star and rising else 0


def signal_doji(open_p, high, low, close, direction):
    """C5: 十字星反转
    FMZ: Doji Reversal"""
    n=len(close)
    if n<5:return 0
    c0,o0,h0,l0=close[-1],open_p[-1],high[-1],low[-1]
    rng=h0-l0
    if rng<0.0001:return 0
    if abs(c0-o0)/rng>0.1:return 0
    if direction=='long':
        return 1 if (close[-3]>close[-2] or close[-4]>close[-3]) and c0>l0+rng*0.3 else 0
    return 1 if (close[-3]<close[-2] or close[-4]<close[-3]) and c0<h0-rng*0.3 else 0


def signal_three_soldiers(open_p, close, direction):
    """C6: 三兵/三鸦
    FMZ: Three Soldiers/Crows"""
    n=len(close)
    if n<4:return 0
    b1=abs(close[-1]-open_p[-1]);b2=abs(close[-2]-open_p[-2]);b3=abs(close[-3]-open_p[-3])
    if direction=='long':
        return 1 if close[-1]>open_p[-1] and close[-2]>open_p[-2] and close[-3]>open_p[-3] and b1>b2>b3 else 0
    return 1 if close[-1]<open_p[-1] and close[-2]<open_p[-2] and close[-3]<open_p[-3] and b1>b2>b3 else 0


def signal_piercing_dark(open_p, close, direction):
    """C7: 刺穿线/乌云盖顶
    FMZ: Piercing/Dark Cloud"""
    n=len(close)
    if n<2:return 0
    mid=(open_p[-2]+close[-2])/2
    if direction=='long':
        return 1 if close[-2]<open_p[-2] and open_p[-1]<close[-2] and close[-1]>mid else 0
    return 1 if close[-2]>open_p[-2] and open_p[-1]>close[-2] and close[-1]<mid else 0


def signal_harami(open_p, close, direction):
    """C8: 孕线/Harami
    FMZ: Harami Reversal"""
    n=len(close)
    if n<2:return 0
    in_body=max(close[-1],open_p[-1])<max(close[-2],open_p[-2]) and min(close[-1],open_p[-1])>min(close[-2],open_p[-2])
    if not in_body:return 0
    if direction=='long':
        return 1 if close[-2]<open_p[-2] and close[-1]>open_p[-1] else 0
    return 1 if close[-2]>open_p[-2] and close[-1]<open_p[-1] else 0


def signal_candle_at_fib(open_p, high, low, close, direction, lookback=50):
    """C9: Fib位蜡烛反转
    FMZ: Fib Channel Candle"""
    n=len(close)
    if n<lookback:return 0
    hh=np.max(high[-lookback:]);ll=np.min(low[-lookback:])
    rng=hh-ll
    if rng<=0:return 0
    if abs(close[-1]-(hh-rng*0.5))/rng>0.04:return 0
    if direction=='long':
        return 1 if close[-1]>open_p[-1] and close[-2]<open_p[-2] else 0
    return 1 if close[-1]<open_p[-1] and close[-2]>open_p[-2] else 0


def signal_volume_candle(open_p, close, volume, direction):
    """C10: 量确认蜡烛+放量
    FMZ: Volume+Engulfing"""
    n=len(close)
    if n<3:return 0
    vr=volume[-1]/np.mean(volume[-10:]) if np.mean(volume[-10:])>0 else 1
    if vr<1.2:return 0
    if direction=='long':
        return 1 if close[-1]>open_p[-1] and close[-2]<open_p[-2] else 0
    return 1 if close[-1]<open_p[-1] and close[-2]>open_p[-2] else 0


# ═══════════════════════════════════════
# 综合评分 v3 (30信号 A+B+C, 0-30分)
# ═══════════════════════════════════════

def score_entry_signals_v3(high, low, close, volume, open_p, direction,
                           bb_lower=None, bb_upper=None, rsi=None):
    """30个信号综合评分, 总分0-30: >=18强/9-17弱/<9无"""
    a={
        'A1_通道突破': signal_donchian(high,low,close,direction),
        'A2_ORB区间':  signal_orb(high,low,close,direction),
        'A3_BB极端':   signal_bb_extreme(close,direction,bb_lower,bb_upper,rsi),
        'A4_ATR突破':  signal_atr_breakout(high,low,close,direction),
        'A5_首K通道':  signal_first_bar_channel(high,low,close,direction),
        'A6_历史极值': signal_extreme_high(high,low,close,volume,direction),
        'A7_分形突破': signal_fractal(high,low,close,direction),
        'A8_三重递增': signal_triple_high(high,low,close,volume,direction),
        'A9_动量突破': signal_momentum_breakout(high,low,close,direction),
        'A10_KC动量':  signal_kc_momentum(high,low,close,direction),
    }
    b={
        'B1_Fib回撤':  signal_fib_retrace(high,low,close,direction),
        'B2_EMA回踩':  signal_ema_pullback(close,direction),
        'B3_BB回归':   signal_bb_mean_revert(close,direction),
        'B4_KC回撤':   signal_kc_pullback(high,low,close,direction),
        'B5_RSI深回撤': signal_rsi_fib_deep(close,direction,rsi),
        'B6_MA区间':   signal_ma_zone(close,direction),
        'B7_Donchian底': signal_donchian_pullback(high,low,close,direction),
        'B8_MACD反转': signal_macd_volume_reversal(close,volume,direction),
        'B9_BB弹跳':   signal_bb_ema9_bounce(close,direction),
        'B10_双MA回撤': signal_dual_ma_retrace(close,direction),
    }
    c={
        'C1_吞没确认': signal_engulf_confirm(open_p,high,low,close,direction),
        'C2_吞没ATR':  signal_engulf_atr(open_p,high,low,close,direction),
        'C3_吞没比例': signal_engulf_ratio(open_p,close,direction),
        'C4_锤子':     signal_hammer(open_p,high,low,close,direction),
        'C5_十字星':   signal_doji(open_p,high,low,close,direction),
        'C6_三兵':     signal_three_soldiers(open_p,close,direction),
        'C7_刺穿线':   signal_piercing_dark(open_p,close,direction),
        'C8_孕线':     signal_harami(open_p,close,direction),
        'C9_Fib蜡烛':  signal_candle_at_fib(open_p,high,low,close,direction),
        'C10_量蜡烛':  signal_volume_candle(open_p,close,volume,direction),
    }
    all_s={**a,**b,**c}
    total=sum(all_s.values())
    trig=[k for k,v in all_s.items() if v]
    level='强' if total>=18 else ('弱' if total>=9 else '无')
    return {'total':total,'level':level,'signals':all_s,'details':trig,
            'breakout':sum(a.values()),'pullback':sum(b.values()),'candle':sum(c.values())}
