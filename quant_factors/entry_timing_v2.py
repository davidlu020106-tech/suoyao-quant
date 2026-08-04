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


# ═══════════════════════════════════════
# 第四批: ICT/SMC结构 (D1~D10)
# ═══════════════════════════════════════

def signal_fvg(high, low, close, direction):
    """D1: FVG缺口 — 3K形成的未回补缺口被回踩
    FMZ: FVG-Momentum-Scalping
    看涨FVG: candle1低点 > candle3高点 → 价格回到gap区做多"""
    n = len(close)
    if n < 4: return 0
    h1,h2,h3 = high[-3],high[-2],high[-1]
    l1,l2,l3 = low[-3],low[-2],low[-1]
    if direction == 'long':
        gap = l1 > h3  # 上涨缺口
        if gap and close[-1] <= l1 * 1.002 and close[-1] >= h3:
            return 1
    else:
        gap = h1 < l3  # 下跌缺口
        if gap and close[-1] >= h1 * 0.998 and close[-1] <= l3:
            return 1
    return 0


def signal_order_block(open_p, high, low, close, direction):
    """D2: 订单块 — 最后反向K被回踩
    FMZ: Order-Block-Finder
    看涨OB: 前下跌浪的最后阴线 → 价格回踩该K范围做多"""
    n = len(close)
    if n < 5: return 0
    if direction == 'long':
        # 找最后一次下跌的最后阴线
        for i in range(n-2, 1, -1):
            if close[i] < open_p[i] and close[i-1] > open_p[i-1]:
                ob_high, ob_low = max(open_p[i], close[i]), min(open_p[i], close[i])
                return 1 if ob_low <= close[-1] <= ob_high else 0
    else:
        for i in range(n-2, 1, -1):
            if close[i] > open_p[i] and close[i-1] < open_p[i-1]:
                ob_high, ob_low = max(open_p[i], close[i]), min(open_p[i], close[i])
                return 1 if ob_low <= close[-1] <= ob_high else 0
    return 0


def signal_bos(high, low, close, direction):
    """D3: Break of Structure — 突破前swing点
    FMZ: SMC-EMA
    看涨BOS: 突破最近swing高点 → 趋势延续"""
    n = len(close)
    if n < 6: return 0
    if direction == 'long':
        # 找最近swing高
        for i in range(n-3, 2, -1):
            if high[i] > high[i-1] and high[i] > high[i+1] and high[i] > high[i-2]:
                return 1 if close[-1] > high[i] else 0
    else:
        for i in range(n-3, 2, -1):
            if low[i] < low[i-1] and low[i] < low[i+1] and low[i] < low[i-2]:
                return 1 if close[-1] < low[i] else 0
    return 0


def signal_fvg_volume(high, low, close, volume, direction):
    """D4: FVG+放量确认
    FMZ: Dynamic-FVG-Intraday"""
    n = len(close)
    if n < 4: return 0
    vr = volume[-1] / np.mean(volume[-10:]) if np.mean(volume[-10:]) > 0 else 1
    if vr < 1.15: return 0
    return signal_fvg(high, low, close, direction)


def signal_liquidity_sweep(high, low, close, direction):
    """D5: 流动性扫荡 — 扫前高/低后反转
    FMZ: SMC-Market-HL-Breakout
    看涨: 价格跌破前低又快速收回 → 扫多流动性后做多"""
    n = len(close)
    if n < 5: return 0
    if direction == 'long':
        sweep_low = min(low[-5:-2])
        swept = low[-2] < sweep_low or low[-1] < sweep_low
        recovery = close[-1] > sweep_low
        return 1 if swept and recovery else 0
    else:
        sweep_high = max(high[-5:-2])
        swept = high[-2] > sweep_high or high[-1] > sweep_high
        recovery = close[-1] < sweep_high
        return 1 if swept and recovery else 0


def signal_structure_confirm(high, low, close, direction, htf_direction=None):
    """D6: 15m+1H结构一致
    FMZ: TrendSync-Pro-SMC
    如果提供了htf_direction, 只有15m BOS和HTF方向一致才触发"""
    bos = signal_bos(high, low, close, direction)
    if not bos: return 0
    if htf_direction is not None:
        return 1 if direction == htf_direction else 0
    return 1


def signal_fvg_atr(high, low, close, direction):
    """D7: ATR过滤微缺口
    FMZ: Adaptive-FVG-Detection"""
    n = len(close)
    if n < 4: return 0
    tr = np.maximum(high[-14:]-low[-14:], np.abs(high[-14:]-np.roll(close[-14:],1)))
    atr = np.mean(tr)
    h1,h3,l1,l3 = high[-3],high[-1],low[-3],low[-1]
    if direction == 'long':
        gap_size = (l1 - h3) / atr if atr > 0 else 0
        return 1 if gap_size > 0.3 and close[-1] >= h3 and close[-1] <= l1 else 0
    else:
        gap_size = (l3 - h1) / atr if atr > 0 else 0
        return 1 if gap_size > 0.3 and close[-1] >= h1 and close[-1] <= l3 else 0


def signal_fvg_ma(high, low, close, direction):
    """D8: FVG+MA交叉区
    FMZ: SMA-FVG-Comprehensive"""
    n = len(close)
    if n < 20: return 0
    sma20 = np.mean(close[-20:])
    if direction == 'long':
        near_ma = abs(close[-1] - sma20) / sma20 < 0.01
        return 1 if near_ma and signal_fvg(high, low, close, direction) else 0
    else:
        near_ma = abs(close[-1] - sma20) / sma20 < 0.01
        return 1 if near_ma and signal_fvg(high, low, close, direction) else 0


def signal_fvg_deep(high, low, close, direction):
    """D9: FVG深度>ATR×0.3 — 只取有效缺口
    FMZ: Advanced-FVG-Risk"""
    n = len(close)
    if n < 4: return 0
    tr = np.maximum(high[-14:]-low[-14:], np.abs(high[-14:]-np.roll(close[-14:],1)))
    atr = np.mean(tr)
    if atr <= 0: return 0
    if direction == 'long':
        gap = low[-3] - high[-1]
        if gap < atr * 0.3: return 0
        return 1 if high[-1] <= close[-1] <= low[-3] else 0
    else:
        gap = low[-1] - high[-3]
        if gap < atr * 0.3: return 0
        return 1 if high[-3] <= close[-1] <= low[-1] else 0


def signal_ob_macd(open_p, high, low, close, direction):
    """D10: 订单块+MACD同向确认
    FMZ: MACD-SMC-EMA"""
    n = len(close)
    if n < 30: return 0
    ob = signal_order_block(open_p, high, low, close, direction)
    if not ob: return 0
    ema12 = np.mean(close[-12:]); ema26 = np.mean(close[-26:])
    if direction == 'long':
        return 1 if ema12 > ema26 else 0
    return 1 if ema12 < ema26 else 0


# ═══════════════════════════════════════
# 综合评分 v4 (40信号 A+B+C+D, 0-40分)
# ═══════════════════════════════════════

def score_entry_signals_v4(high, low, close, volume, open_p, direction,
                           bb_lower=None, bb_upper=None, rsi=None,
                           htf_direction=None):
    """40个信号综合评分, 总分0-40: >=24强/12-23弱/<12无"""
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
    d={
        'D1_FVG缺口':    signal_fvg(high,low,close,direction),
        'D2_订单块OB':   signal_order_block(open_p,high,low,close,direction),
        'D3_BOS结构':    signal_bos(high,low,close,direction),
        'D4_FVG量确认':  signal_fvg_volume(high,low,close,volume,direction),
        'D5_流动性扫荡': signal_liquidity_sweep(high,low,close,direction),
        'D6_结构一致':   signal_structure_confirm(high,low,close,direction,htf_direction),
        'D7_FVG_ATR':   signal_fvg_atr(high,low,close,direction),
        'D8_FVG_MA':    signal_fvg_ma(high,low,close,direction),
        'D9_FVG深度':    signal_fvg_deep(high,low,close,direction),
        'D10_OB_MACD':  signal_ob_macd(open_p,high,low,close,direction),
    }
    all_s={**a,**b,**c,**d}
    total=sum(all_s.values())
    trig=[k for k,v in all_s.items() if v]
    level='强' if total>=24 else ('弱' if total>=12 else '无')
    return {'total':total,'level':level,'signals':all_s,'details':trig,
            'breakout':sum(a.values()),'pullback':sum(b.values()),
            'candle':sum(c.values()),'smc':sum(d.values())}


# ═══════════════════════════════════════
# 第五批: 多指标共振 (E1~E10)
# 每组至少3个独立指标同时指向同一方向才触发
# ═══════════════════════════════════════

def signal_bb_rsi_adx(close, high, low, direction, rsi=None, adx=None):
    """E1: BB+RSI+ADX三指标共振
    FMZ: BB-RSI-ADX-Entry-Points
    做多: close<BB下轨+RSI<40+ADX>20"""
    n = len(close)
    if n < 20: return 0
    sma = np.mean(close[-20:]); std = np.std(close[-20:])
    lower = sma - 2*std; upper = sma + 2*std
    rsi_v = float(rsi[-1]) if rsi is not None else 50
    adx_v = adx if adx is not None else 20
    if direction == 'long':
        bb = close[-1] < lower; rs = rsi_v < 40; ad = adx_v > 20
        return 1 if bb and rs and ad else 0
    else:
        bb = close[-1] > upper; rs = rsi_v > 60; ad = adx_v > 20
        return 1 if bb and rs and ad else 0


def signal_ema_macd_supertrend(close, high, low, direction):
    """E2: EMA金叉+MACD>0+价格在SuperTrend上方
    FMZ: EMA-MACD-SuperTrend-Combo"""
    n = len(close)
    if n < 30: return 0
    ema12 = np.mean(close[-12:]); ema26 = np.mean(close[-26:])
    macd = ema12 - ema26
    prev12 = np.mean(close[-13:-1]); prev26 = np.mean(close[-27:-1])
    prev_macd = prev12 - prev26
    st = (high[-1]+low[-1])/2
    if direction == 'long':
        return 1 if ema12>ema26 and macd>prev_macd and close[-1]>st else 0
    return 1 if ema12<ema26 and macd<prev_macd and close[-1]<st else 0


def signal_rsi_stoch_kc(close, high, low, direction, rsi=None):
    """E3: RSI+Stoch+KC三振荡器
    FMZ: CCI-RSI-KC-Trend-Filter"""
    n = len(close)
    if n < 20: return 0
    # Stoch %K simple
    hh14 = np.max(high[-14:]); ll14 = np.min(low[-14:])
    stoch = (close[-1]-ll14)/(hh14-ll14)*100 if hh14>ll14 else 50
    # KC position
    ema20 = np.mean(close[-20:])
    tr = np.maximum(high[-14:]-low[-14:], np.abs(high[-14:]-np.roll(close[-14:],1)))
    atr = np.mean(tr)
    rsi_v = float(rsi[-1]) if rsi is not None else 50
    if direction == 'long':
        return 1 if rsi_v<40 and stoch<30 and close[-1]<(ema20-atr*1.5) else 0
    return 1 if rsi_v>60 and stoch>70 and close[-1]>(ema20+atr*1.5) else 0


def signal_adx_rsi_sma(close, direction, rsi=None, adx=None):
    """E4: ADX+RSI+SMA趋势确认
    FMZ: ADXRSISMA-Multi-Indicator"""
    sma20 = np.mean(close[-20:]); sma50 = np.mean(close[-50:]) if len(close)>=50 else sma20
    rsi_v = float(rsi[-1]) if rsi is not None else 50
    adx_v = adx if adx is not None else 20
    if direction == 'long':
        return 1 if sma20>sma50 and rsi_v>50 and adx_v>25 else 0
    return 1 if sma20<sma50 and rsi_v<50 and adx_v>25 else 0


def signal_ema_rsi_ta(close, direction, rsi=None):
    """E5: EMA交叉+RSI+价格趋势
    FMZ: EMA-RSI-TA-Multi-Indicator"""
    n = len(close)
    if n < 20: return 0
    ema9 = np.mean(close[-9:]); ema21 = np.mean(close[-21:]) if n>=21 else ema9
    rsi_v = float(rsi[-1]) if rsi is not None else 50
    if direction == 'long':
        return 1 if ema9>ema21 and rsi_v>50 and close[-1]>ema9 else 0
    return 1 if ema9<ema21 and rsi_v<50 and close[-1]<ema9 else 0


def signal_ma_macd_bb(close, direction):
    """E6: MA金叉+MACD+BB中轨突破
    FMZ: MA-MACD-BB-Combo"""
    n = len(close)
    if n < 26: return 0
    ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:])
    ema12 = np.mean(close[-12:]); ema26 = np.mean(close[-26:])
    bb_mid = np.mean(close[-20:])
    if direction == 'long':
        return 1 if ma10>ma20 and ema12>ema26 and close[-1]>bb_mid else 0
    return 1 if ma10<ma20 and ema12<ema26 and close[-1]<bb_mid else 0


def signal_supertrend_adx_atr(high, low, close, direction, adx=None):
    """E7: SuperTrend+ADX+ATR
    FMZ: SuperTrend-ADX-ATR-Combo"""
    n = len(close)
    if n < 14: return 0
    atr = np.mean(np.maximum(high[-14:]-low[-14:], np.abs(high[-14:]-np.roll(close[-14:],1))))
    st_upper = (high[-1]+low[-1])/2 + 2*atr
    st_lower = (high[-1]+low[-1])/2 - 2*atr
    adx_v = adx if adx is not None else 20
    if direction == 'long':
        return 1 if close[-1]>st_upper and adx_v>25 else 0
    return 1 if close[-1]<st_lower and adx_v>25 else 0


def signal_cci_dmi_macd(high, low, close, direction):
    """E8: CCI+DMI+MACD三重方向
    FMZ: CCI-DMI-MACD-Hybrid"""
    n = len(close)
    if n < 26: return 0
    tp = (high[-1]+low[-1]+close[-1])/3
    tp_hist = np.array([(high[i]+low[i]+close[i])/3 for i in range(-20, 0)])
    cci = (tp - np.mean(tp_hist)) / (0.015 * np.mean(np.abs(tp_hist-np.mean(tp_hist)))) if np.mean(np.abs(tp_hist-np.mean(tp_hist)))>0 else 0
    ema12 = np.mean(close[-12:]); ema26 = np.mean(close[-26:])
    if direction == 'long':
        return 1 if cci>100 and ema12>ema26 and high[-1]>high[-2] else 0
    return 1 if cci<-100 and ema12<ema26 and low[-1]<low[-2] else 0


def signal_confluence_3plus(high, low, close, open_p, volume, direction):
    """E9: 任意3+指标同时指向同一方向
    FMZ: Kuberan-Confluence-Approach
    统计A+B+C+D四批共40个信号, 取同一方向触发数>=5"""
    # 快速聚合前4批中不需要rsl/adx外部参数的核心信号
    count = 0
    count += signal_donchian(high, low, close, direction)
    count += signal_orb(high, low, close, direction)
    count += signal_atr_breakout(high, low, close, direction)
    count += signal_fractal(high, low, close, direction)
    count += signal_ema_pullback(close, direction)
    count += signal_bb_mean_revert(close, direction)
    count += signal_ma_zone(close, direction)
    count += signal_dual_ma_retrace(close, direction)
    count += signal_engulf_atr(open_p, high, low, close, direction)
    count += signal_bos(high, low, close, direction)
    return 1 if count >= 5 else 0


def signal_trend_align_3tf(high, low, close, direction):
    """E10: 三重趋势对齐 — MA短中长排列
    FMZ: Multi-Indicator-Combo-Trend
    做多: MA10>MA20>MA50 全部多头"""
    n = len(close)
    if n < 50: return 0
    ma10 = np.mean(close[-10:]); ma20 = np.mean(close[-20:]); ma50 = np.mean(close[-50:])
    if direction == 'long':
        return 1 if ma10 > ma20 > ma50 else 0
    return 1 if ma10 < ma20 < ma50 else 0


# ═══════════════════════════════════════
# 综合评分 v5 (50信号 A+B+C+D+E, 0-50分)
# ═══════════════════════════════════════

def score_entry_signals_v5(high, low, close, volume, open_p, direction,
                           bb_lower=None, bb_upper=None, rsi=None, adx=None,
                           htf_direction=None):
    """50个信号综合评分, 总分0-50: >=30强/15-29弱/<15无"""
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
    }; b={
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
    }; c={
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
    }; d={
        'D1_FVG缺口':    signal_fvg(high,low,close,direction),
        'D2_订单块OB':   signal_order_block(open_p,high,low,close,direction),
        'D3_BOS结构':    signal_bos(high,low,close,direction),
        'D4_FVG量确认':  signal_fvg_volume(high,low,close,volume,direction),
        'D5_流动性扫荡': signal_liquidity_sweep(high,low,close,direction),
        'D6_结构一致':   signal_structure_confirm(high,low,close,direction,htf_direction),
        'D7_FVG_ATR':   signal_fvg_atr(high,low,close,direction),
        'D8_FVG_MA':    signal_fvg_ma(high,low,close,direction),
        'D9_FVG深度':    signal_fvg_deep(high,low,close,direction),
        'D10_OB_MACD':  signal_ob_macd(open_p,high,low,close,direction),
    }; e={
        'E1_BB_RSI_ADX':    signal_bb_rsi_adx(close,high,low,direction,rsi,adx),
        'E2_EMA_MACD_ST':   signal_ema_macd_supertrend(close,high,low,direction),
        'E3_RSI_Stoch_KC':  signal_rsi_stoch_kc(close,high,low,direction,rsi),
        'E4_ADX_RSI_SMA':   signal_adx_rsi_sma(close,direction,rsi,adx),
        'E5_EMA_RSI_TA':    signal_ema_rsi_ta(close,direction,rsi),
        'E6_MA_MACD_BB':    signal_ma_macd_bb(close,direction),
        'E7_ST_ADX_ATR':    signal_supertrend_adx_atr(high,low,close,direction,adx),
        'E8_CCI_DMI_MACD':  signal_cci_dmi_macd(high,low,close,direction),
        'E9_3+指标共振':    signal_confluence_3plus(high,low,close,open_p,volume,direction),
        'E10_三MA排列':     signal_trend_align_3tf(high,low,close,direction),
    }
    all_s={**a,**b,**c,**d,**e}
    total=sum(all_s.values())
    trig=[k for k,v in all_s.items() if v]
    level='强' if total>=30 else ('弱' if total>=15 else '无')
    return {'total':total,'level':level,'signals':all_s,'details':trig,
            'breakout':sum(a.values()),'pullback':sum(b.values()),
            'candle':sum(c.values()),'smc':sum(d.values()),'combo':sum(e.values())}
