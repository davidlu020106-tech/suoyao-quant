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
    liq_price = market_price * (1 + 1/max_lev) if direction == 'short' else \
                market_price * (1 - 1/max_lev)
    tp1_price = market_price * (1 - 1/max_lev) if direction == 'short' else \
                market_price * (1 + 1/max_lev)

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
        # 做空: 第二入场在 entry1 和 liq_price 之间
        # ICT OTE: fib_618 ~ fib_705 (价格反弹到这个区间)
        ote_entry = ote['fib_618']

        # 取 ICT OTE 和海龟回撤中较低者（更安全）
        candidate = min(ote_entry, turtle) if ote_entry else turtle

        # 硬约束: 必须在 [entry1 + 0.1%, liq_price * 0.98] 之间
        lower = entry1 * 1.001
        upper = liq_price * 0.98
        entry2 = np.clip(candidate, lower, upper)
        entry2 = round(entry2, 8)

        # 检测用了哪个策略
        if abs(entry2 - ote_entry) < abs(entry2 - turtle):
            detail_parts.append(f"ICT OTE={ote_entry}")
        else:
            detail_parts.append(f"海龟回撤={turtle}")

    else:
        # 做多: 第二入场在 liq_price 和 entry1 之间
        ote_entry = ote['fib_705']

        candidate = max(ote_entry, turtle) if ote_entry else turtle

        lower = liq_price * 1.02
        upper = entry1 * 0.999
        entry2 = np.clip(candidate, lower, upper)
        entry2 = round(entry2, 8)

        if abs(entry2 - ote_entry) < abs(entry2 - turtle):
            detail_parts.append(f"ICT OTE={ote_entry}")
        else:
            detail_parts.append(f"海龟回撤={turtle}")

    # ── 4. 风控检查 ──
    if direction == 'short':
        safe = entry2 < liq_price * 0.98
        safe_dist = (liq_price - entry2) / liq_price * 100
    else:
        safe = entry2 > liq_price * 1.02
        safe_dist = (entry2 - liq_price) / liq_price * 100

    if safe:
        detail_parts.append(f"距强平{safe_dist:.2f}% OK")
    else:
        detail_parts.append(f"距强平{safe_dist:.2f}% RISK 风险!")

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
        'detail': ' | '.join(detail_parts),
        'ote': ote,
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

    print(f'  [{dir_cn}] {plan["base"]} ({plan["max_lev"]}x)')
    print(f'    杠杆: {plan["max_lev"]}x (OKX最大)')
    print(f'    强平价: {fmt_price(plan["liq_price"])} ({1/plan["max_lev"]*100:.1f}% {"涨" if d=="short" else "跌"}爆)')
    print(f'    TP1:   {fmt_price(plan["tp1_price"])} ({1/plan["max_lev"]*100:.1f}% {"跌" if d=="short" else "涨"} = 利润=本金)')
    print(f'    {"─" * 40}')
    print(f'    第一入场: {fmt_price(plan["entry1_price"])} → 挂限价{plan["entry1_amount"]}U (市价+0.2%)')
    print(f'    第二入场: {fmt_price(plan["entry2_price"])} → 挂限价{plan["entry2_amount"]}U {safe_tag}')
    print(f'    OTE区间: {fmt_price(plan["ote"]["ote_zone"][0])} ~ {fmt_price(plan["ote"]["ote_zone"][1])}')
    print(f'    {"─" * 40}')
    print(f'    {plan["detail"]}')
    print()
