"""
精准入场规划器 — 对综合推荐 Top 3 计算入场方案

输入: 推荐币信息 + OHLC数据 → 输出: 第一入场价/第二入场价/强平价/TP1

算法:
  第一入场 (快速成交): 市价 + 小偏移 (0.1~0.3%)
  第二入场 (补仓):     ICT OTE + 海龟回撤 综合定价
                      在第一入场和强平价之间，距强平≥2%安全垫
"""

import numpy as np
import pandas as pd


def calc_ote_levels(df: pd.DataFrame, length: int = 20) -> dict:
    """
    ICT OTE (Optimal Trade Entry) 斐波那契入场位

    找近 length 根K线的摆动高/低点，计算 0.618~0.705 区间

    Returns:
        {'swing_high': float, 'swing_low': float,
         'fib_618': float, 'fib_705': float, 'ote_zone': (float, float)}
    """
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values

    n = min(length, len(df) - 1)
    swing_high = np.max(high[-n:])
    swing_low = np.min(low[-n:])
    diff = swing_high - swing_low

    fib_618 = swing_high - diff * 0.618
    fib_705 = swing_high - diff * 0.705

    return {
        'swing_high': swing_high,
        'swing_low': swing_low,
        'fib_618': round(fib_618, 8),
        'fib_705': round(fib_705, 8),
        'ote_zone': (round(min(fib_618, fib_705), 8),
                     round(max(fib_618, fib_705), 8)),
    }


def calc_turtle_pullback(df: pd.DataFrame, direction: str,
                         pullback_pct: float = 1.0) -> float:
    """
    海龟回撤入场位

    做空: 突破20日高后回撤 pullback_pct%
    做多: 突破20日低后回撤 pullback_pct%

    Returns: 回撤入场价
    """
    high = df['high'].values
    low = df['low'].values
    n = min(20, len(df))

    if direction == 'short':
        # 做空: 20日高 → 价格反弹回撤到该价下方
        high_20 = np.max(high[-n:])
        return round(high_20 * (1 + pullback_pct / 100), 8)
    else:
        low_20 = np.min(low[-n:])
        return round(low_20 * (1 - pullback_pct / 100), 8)


def calc_ema_reentry(df: pd.DataFrame, direction: str,
                     ema_length: int = 200) -> float:
    """
    动量均线回踩入场位

    做空: 价格反弹回踩 EMA 时入场
    做多: 价格回落到 EMA 时入场
    """
    close = df['close'].values
    if len(close) < ema_length:
        return None

    # 计算 EMA
    alpha = 2.0 / (ema_length + 1)
    ema = np.full_like(close, np.nan)
    ema[0] = close[0]
    for i in range(1, len(close)):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i-1]

    current_ema = ema[-1]
    if np.isnan(current_ema):
        return None

    return round(current_ema, 8)


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """计算EMA"""
    alpha = 2.0 / (period + 1)
    result = np.full_like(values, np.nan)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i-1]
    return result


def check_false_breakout(df: pd.DataFrame, direction: str) -> dict:
    """
    假突破检测

    价格突破20日高/低后立刻回头 = 假突破 → 反向信号
    结合ATR确认突破力度

    Returns:
        {'detected': bool, 'score': -1~+1, 'detail': str}
    """
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = min(20, len(df) - 1)

    # ATR
    tr = np.maximum(high[1:] - low[1:],
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1]))
    atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)

    high_20 = np.max(high[-n-1:-1])  # 前20日高（不含当前K线）
    low_20 = np.min(low[-n-1:-1])    # 前20日低
    cur_close = close[-1]
    cur_high = high[-1]
    cur_low = low[-1]

    if direction == 'short':
        # 做空: 价格突破20日高后立刻跌回 = 假突破向上 → 做空信号更强
        if cur_high > high_20 and cur_close < high_20:
            strength = (cur_high - high_20) / atr  # 突破力度
            score = min(0.8, 0.3 + strength * 0.2)
            return {'detected': True, 'score': round(score, 3),
                    'detail': f'假突破向上(超{strength:.1f}ATR)'}
        # 价格在20日高下方正常 → 无假突破
        return {'detected': False, 'score': 0.0, 'detail': '无假突破'}
    else:
        # 做多: 价格跌破20日低后立刻涨回 = 假突破向下 → 做多信号更强
        if cur_low < low_20 and cur_close > low_20:
            strength = (low_20 - cur_low) / atr
            score = min(0.8, 0.3 + strength * 0.2)
            return {'detected': True, 'score': round(score, 3),
                    'detail': f'假突破向下(超{strength:.1f}ATR)'}
        return {'detected': False, 'score': 0.0, 'detail': '无假突破'}


def check_supply_demand_zone(df: pd.DataFrame, entry_price: float,
                              direction: str) -> dict:
    """
    供需区检测

    入场价是否在历史供需区内？
    在区内 = 反转概率高

    Returns:
        {'in_zone': bool, 'score': -1~+1, 'detail': str}
    """
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = min(30, len(df))

    # 找近30根K线的支撑/阻力密集区 = 供需区
    # 支撑区: 多次触及的低点区域
    # 阻力区: 多次触及的高点区域
    recent_high = np.max(high[-n:])
    recent_low = np.min(low[-n:])
    mid = (recent_high + recent_low) / 2

    # 用25%/75%分位作为供需区边界
    p25 = recent_low + (mid - recent_low) * 0.5
    p75 = mid + (recent_high - mid) * 0.5

    if direction == 'short':
        # 做空: 入场价在阻力区(p75以上) = 好的做空位
        if entry_price >= p75:
            score = min(0.6, 0.3 + (entry_price - p75) / (recent_high - p75) * 0.3)
            return {'in_zone': True, 'score': round(score, 3),
                    'detail': f'阻力区{p75:.4f}~{recent_high:.4f}'}
        return {'in_zone': False, 'score': 0.0, 'detail': '不在供需区'}
    else:
        # 做多: 入场价在支撑区(p25以下) = 好的做多位
        if entry_price <= p25:
            score = min(0.6, 0.3 + (p25 - entry_price) / (p25 - recent_low) * 0.3)
            return {'in_zone': True, 'score': round(score, 3),
                    'detail': f'支撑区{recent_low:.4f}~{p25:.4f}'}
        return {'in_zone': False, 'score': 0.0, 'detail': '不在供需区'}


def check_breakout_trap(df: pd.DataFrame, direction: str) -> dict:
    """
    突破陷阱检测

    价格突破关键位后，成交量先放大后缩小 = 陷阱

    Returns:
        {'trapped': bool, 'score': -1~+1, 'detail': str}
    """
    close = df['close'].values
    volume = df['volume'].values if 'volume' in df.columns else None
    n = min(20, len(df))

    if volume is None or len(volume) < 20:
        return {'trapped': False, 'score': 0.0, 'detail': '无成交量数据'}

    recent_vol = volume[-5:]  # 最近5根成交量
    prev_vol = volume[-10:-5]  # 前5根成交量
    avg_vol = np.mean(volume[-20:])  # 20日均量

    vol_spike = np.mean(recent_vol) > avg_vol * 1.5
    vol_shrink = np.mean(recent_vol[-2:]) < np.mean(recent_vol[:3]) * 0.7

    # 趋势方向
    ema7 = _ema(close, 7)
    ema20 = _ema(close, 20)
    trend_up = ema7[-1] > ema20[-1] if not np.isnan(ema7[-1]) else False

    if direction == 'short':
        # 做空: 价格涨但缩量 = 多头陷阱
        if trend_up and vol_spike and vol_shrink:
            return {'trapped': True, 'score': 0.5,
                    'detail': '多头陷阱(放量冲高后缩量)'}
        return {'trapped': False, 'score': 0.0, 'detail': '无陷阱'}
    else:
        # 做多: 价格跌但缩量 = 空头陷阱
        if not trend_up and vol_spike and vol_shrink:
            return {'trapped': True, 'score': 0.5,
                    'detail': '空头陷阱(放量砸盘后缩量)'}
        return {'trapped': False, 'score': 0.0, 'detail': '无陷阱'}


def check_reversal_vector(df: pd.DataFrame, entry_price: float,
                           direction: str) -> dict:
    """
    反转向量综合检测

    整合假突破 + 供需区 + 突破陷阱三个检测器

    Returns:
        {'score': float, 'grade': str, 'details': [str]}
    """
    # 1. 假突破
    fb = check_false_breakout(df, direction)
    # 2. 供需区
    sd = check_supply_demand_zone(df, entry_price, direction)
    # 3. 突破陷阱
    bt = check_breakout_trap(df, direction)

    details = []
    total_score = 0.0

    if fb['detected']:
        total_score += fb['score']
        details.append(fb['detail'])
    if sd['in_zone']:
        total_score += sd['score']
        details.append(sd['detail'])
    if bt['trapped']:
        total_score += bt['score']
        details.append(bt['detail'])

    # 评级
    if total_score >= 0.8:
        grade = '强反转信号'
    elif total_score >= 0.4:
        grade = '反转信号'
    elif total_score >= 0.1:
        grade = '弱反转信号'
    else:
        grade = '无明确反转'

    if not details:
        details.append('无反转向量')

    return {
        'score': round(total_score, 3),
        'grade': grade,
        'details': details,
        'false_breakout': fb,
        'supply_demand': sd,
        'breakout_trap': bt,
    }


def check_trend_strength(df: pd.DataFrame, direction: str) -> dict:
    """
    趋势强度检测 — TP1先于强平到达的核心指标

    公式: trendStrength = (ema7 - ema90) / (atr / close)
    值越大 → 趋势越强 → TP1先到的概率越高

    Returns:
        {'strength': float, 'grade': str, 'tp1_candles': float, 'liq_candles': float}
    """
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    n = len(close)

    # EMA7 和 EMA90
    ema7 = _ema(close, 7)
    ema90 = _ema(close, 90)

    if np.isnan(ema7[-1]) or np.isnan(ema90[-1]) or n < 100:
        return {'strength': 0, 'grade': '数据不足',
                'tp1_candles': 0, 'liq_candles': 0}

    # ATR
    tr = np.maximum(high[1:] - low[1:],
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1]))
    atr = np.mean(tr[-14:]) if len(tr) >= 14 else 1
    atr_pct = atr / close[-1] if close[-1] != 0 else 0.01

    # 趋势强度 = (ema7 - ema90) / (atr / close) = (快慢均线差) / (波动率%)
    # ★ 修复: 保留raw_strength(原始方向), aligned_strength按方向对齐(正=顺势)
    diff_pct = (ema7[-1] - ema90[-1]) / ema90[-1]
    raw_strength = diff_pct / atr_pct if atr_pct > 0 else 0

    if direction == 'long':
        aligned = raw_strength    # 正值=ema7>ema90=多头趋势
    else:
        aligned = -raw_strength   # 正值=ema7<ema90=空头趋势

    # TP1和强平需要多少根K线
    lev_pct = 0.02  # 50x杠杆约2%（标准参考值）
    tp1_candles = lev_pct / atr_pct if atr_pct > 0 else 99
    liq_candles = (lev_pct * 0.7) / atr_pct if atr_pct > 0 else 99

    # 评级 (基于aligned方向对齐值)
    if aligned > 2.0:
        grade = '趋势极强'
    elif aligned > 1.0:
        grade = '趋势强'
    elif aligned > 0.5:
        grade = '趋势中'
    elif aligned > 0.2:
        grade = '趋势弱'
    else:
        grade = '逆势'

    return {
        'strength': round(aligned, 3),           # ★ 方向对齐: 正=顺势
        'raw_strength': round(raw_strength, 3),  # ★ 新增: 原始方向(负=空头)
        'grade': grade,
        'atr_pct': round(atr_pct * 100, 2),
        'tp1_candles': round(tp1_candles, 1),
        'liq_candles': round(liq_candles, 1),
    }


def plan_entry(base: str, direction: str, market_price: float,
               max_lev: int, df: pd.DataFrame) -> dict:
    """
    对单个推荐币规划精准入场方案

    Args:
        base: 币种名
        direction: 'long' / 'short'
        market_price: 当前市价
        max_lev: OKX最大杠杆
        df: 15m OHLC DataFrame

    Returns:
        {
            'base', 'direction', 'max_lev',
            'entry1_price': 第一入场价,
            'entry2_price': 第二入场价,
            'liq_price': 强平价,
            'tp1_price': 止盈价,
            'entry1_amount': 20,
            'entry2_amount': 30,
            'safe': bool,     # 风控是否通过
            'detail': str,    # 说明
        }
    """
    # ── 1. 强平价 & TP1 ──
    # 实际强平只有理论差幅的70%（维持保证金占用）
    # 理论差幅 = 1/lev，实际差幅 = 1/lev * 0.7
    lev_pct = 1.0 / max_lev
    actual_pct = lev_pct * 0.7  # 实际强平幅度只有理论的70%

    liq_price = market_price * (1 + actual_pct) if direction == 'short' else \
                market_price * (1 - actual_pct)
    tp1_price = market_price * (1 - lev_pct) if direction == 'short' else \
                market_price * (1 + lev_pct)

    detail_parts = []

    # ── 2. 第一入场价 (ICT OTE 限价单) ──
    ote = calc_ote_levels(df)
    ote_low, ote_high = ote['ote_zone']

    if direction == 'short':
        entry1 = ote_high
    else:
        entry1 = ote_low

    dev1 = abs(entry1 - market_price) / market_price * 100
    if dev1 > 5:
        offset = 0.003
        entry1 = market_price * (1 + offset) if direction == 'short' else \
                 market_price * (1 - offset)
        detail_parts.append(f"OTE偏离{dev1:.1f}%, 改用市价+-0.3%")
    else:
        detail_parts.append(f"ICT OTE={ote_high if direction=='short' else ote_low}")
    entry1 = round(entry1, 8)

    # ── 3. 第二入场价 (补仓) ──
    turtle = calc_turtle_pullback(df, direction, pullback_pct=1.0)

    if direction == 'short':
        # 做空: 第二入场在 entry1 和 liq_price 之间（价格反弹补仓）
        ote_entry = ote['fib_618']
        candidate = max(ote_entry, turtle) if ote_entry else turtle
        lower = entry1 * 1.001
        upper = liq_price * 0.99  # 与风控阈值一致
        if lower < upper:
            entry2 = np.clip(candidate, lower, upper)
        else:
            entry2 = (entry1 + liq_price) / 2  # 空间不够时取中点
        entry2 = round(entry2, 8)
        if abs(entry2 - ote_entry) < abs(entry2 - turtle):
            detail_parts.append(f"ICT OTE={ote_entry}")
        else:
            detail_parts.append(f"海龟回撤={turtle}")

    else:
        # 做多: 第二入场在 liq_price 和 entry1 之间（价格回落补仓）
        ote_entry = ote['fib_705']
        candidate = min(ote_entry, turtle) if ote_entry else turtle
        lower = liq_price * 1.01  # 与风控阈值一致
        upper = entry1 * 0.999
        if lower < upper:
            entry2 = np.clip(candidate, lower, upper)
        else:
            entry2 = (liq_price + entry1) / 2  # 空间不够时取中点
        entry2 = round(entry2, 8)

        if abs(entry2 - ote_entry) < abs(entry2 - turtle):
            detail_parts.append(f"ICT OTE={ote_entry}")
        else:
            detail_parts.append(f"海龟回撤={turtle}")

    # ── 4. 风控检查 ──
    if direction == 'short':
        safe = entry2 < liq_price * 0.99
        safe_dist = (liq_price - entry2) / liq_price * 100
    else:
        safe = entry2 > liq_price * 1.01
        safe_dist = (entry2 - liq_price) / liq_price * 100

    if safe:
        detail_parts.append(f"距强平{safe_dist:.2f}% OK")
    else:
        detail_parts.append(f"距强平{safe_dist:.2f}% RISK 风险!")

    # ── 5. 反转向量检测 ──
    rv = check_reversal_vector(df, entry1, direction)
    if rv['score'] > 0:
        detail_parts.append(f"反转向量:{rv['grade']}(+{rv['score']})")
    detail_parts.extend(rv['details'])

    # ── 6. 趋势强度检测 ──
    ts = check_trend_strength(df, direction)
    if ts['grade'] != '数据不足':
        detail_parts.append(f"趋强:{ts['grade']}({ts['strength']})")
        detail_parts.append(f"波动:{ts['atr_pct']}%|TP1需{ts['tp1_candles']}K|强平需{ts['liq_candles']}K")

    # ── 7. 综合评级 ──
    rv_score = rv.get('score', 0)
    ts_score = ts.get('strength', 0)
    # ★ 修复: ts_score 正=顺势, 负=逆势; max(0,...)确保逆势不贡献分
    composite = rv_score * 0.3 + max(0, ts_score / 4) * 0.4 + (min(safe_dist, 5) / 5) * 0.3
    if composite >= 0.6:
        rating = '推荐入场'
    elif composite >= 0.3:
        rating = '谨慎入场'
    else:
        rating = '不建议入场'

    return {
        'base': base,
        'direction': direction,
        'max_lev': max_lev,
        'market_price': market_price,
        'entry1_price': entry1,
        'entry2_price': entry2,
        'liq_price': round(liq_price, 8),
        'tp1_price': round(tp1_price, 8),
        'entry1_amount': 20,
        'entry2_amount': 30,
        'safe': safe,
        'rating': rating,
        'detail': ' | '.join(detail_parts),
        'ote': ote,
        'reversal_vector': rv,
        'trend_strength': ts,
    }


def fmt_price(p: float) -> str:
    """格式化价格显示"""
    if p > 1000:
        return f'${p:.2f}'
    elif p > 10:
        return f'${p:.4f}'
    elif p > 1:
        return f'${p:.6f}'
    elif p > 0.001:
        return f'${p:.8f}'
    else:
        return f'${p:.10f}'


def print_entry_plan(plan: dict):
    """打印精准入场方案"""
    d = plan['direction']
    dir_cn = '做空' if d == 'short' else '做多'
    safe_tag = '[OK]' if plan['safe'] else '[RISK]'
    rating = plan.get('rating', '')

    print(f'  [{dir_cn}] {plan["base"]} ({plan["max_lev"]}x) 评级:{rating}')
    print(f'    杠杆: {plan["max_lev"]}x (OKX最大)')
    liq_dir = '涨爆' if d == 'short' else '跌爆'
    print(f'    强平价: {fmt_price(plan["liq_price"])} ({1/plan["max_lev"]*100*0.7:.1f}% {liq_dir})')
    tp_dir = '跌' if d == 'short' else '涨'
    print(f'    TP1:   {fmt_price(plan["tp1_price"])} ({1/plan["max_lev"]*100:.1f}% {tp_dir} = 利润=本金)')
    print(f'    {"-" * 40}')
    print(f'    第一入场: {fmt_price(plan["entry1_price"])} -> 限价{plan["entry1_amount"]}U')
    print(f'    第二入场: {fmt_price(plan["entry2_price"])} -> 限价{plan["entry2_amount"]}U {safe_tag}')
    print(f'    OTE区间: {fmt_price(plan["ote"]["ote_zone"][0])} ~ {fmt_price(plan["ote"]["ote_zone"][1])}')

    # 反转向量
    rv = plan.get('reversal_vector', {})
    if rv:
        rv_details = ' '.join(rv.get('details', []))
        grade = rv.get('grade', '')
        print(f'    反转向量: {grade} ({rv_details})')

    # 趋势强度
    ts = plan.get('trend_strength', {})
    if ts and ts.get('grade'):
        ts_grade = ts.get('grade', '')
        ts_str = ts.get('strength', 0)
        atr = ts.get('atr_pct', 0)
        tp1k = ts.get('tp1_candles', 0)
        liqk = ts.get('liq_candles', 0)
        print(f'    趋势强度: {ts_grade}({ts_str}) '
              f'ATR={atr:.1f}% TP1需{tp1k}K线 强平需{liqk}K线')

    print(f'    {"-" * 40}')
    print(f'    {plan["detail"]}')
    print()
