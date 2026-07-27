#!/usr/bin/env python3
"""MTF Signal — 多时间框架综合信号报告。

一条命令输出：锁妖塔KOL方向 + 1H趋势确认 + SMC结构 + ATR止损

用法:
    python quant_factors/mtf_signal.py KAITO
    python quant_factors/mtf_signal.py KAITO --htf 4H
    python quant_factors/mtf_signal.py ALLO --htf 1H
    python quant_factors/mtf_signal.py             # 扫描全部
"""
import sys, os, json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_data_adapter import fetch_ohlc, check_mtf_trend
from smc_entry_signal import check_entry_signal, calc_rsi
from capabilities import CAP_REGISTRY


def check_orb_range(closes, highs, lows, window=12):
    """ORB dynamic range: highest high / lowest low over last N bars.

    Returns dict with: orb_high, orb_low, break_above, break_below
    """
    if len(closes) < window + 1:
        return {'orb_high': 0, 'orb_low': 0, 'break_above': False, 'break_below': False, 'pct': 0}

    orb_high = max(highs[-window:-1])  # highest high in range (excl current)
    orb_low = min(lows[-window:-1])    # lowest low in range
    cur_c = closes[-1]
    prev_c = closes[-2]

    break_above = prev_c <= orb_high <= cur_c  # price breaks above ORB high
    break_below = prev_c >= orb_low >= cur_c   # price breaks below ORB low

    range_pct = (orb_high - orb_low) / orb_low * 100 if orb_low > 0 else 0

    return {
        'orb_high': round(orb_high, 6),
        'orb_low': round(orb_low, 6),
        'break_above': break_above,
        'break_below': break_below,
        'range_pct': round(range_pct, 2),
    }


def get_kol_consensus_5m(symbol, lookback=200):
    """Simplified KOL consensus for a coin using 5m data.

    Returns dict with bull/bear/neutral counts and avg signal.
    """
    candles = fetch_ohlc(symbol, '5m', lookback)
    if not candles or len(candles) < 100:
        return None

    closes = np.array([c['close'] for c in candles])
    highs = np.array([c['high'] for c in candles])
    lows = np.array([c['low'] for c in candles])
    volumes = np.array([c.get('volume', 0) for c in candles])

    # Build features for the last bar
    c = closes[-1]
    ma50 = np.mean(closes[-50:]) if len(closes) >= 50 else c
    ma200 = np.mean(closes[-200:]) if len(closes) >= 200 else c
    rsi = calc_rsi(closes)[-1]
    vol_avg = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

    # Simplified KOL scoring for key factors
    rids = set(CAP_REGISTRY.keys())
    sigs = []

    # Regime factors
    if c > ma50:
        sigs.append(('cap_044_regime_trending_up', 0.6 if c > ma50 else -0.4))
    if c < ma50:
        sigs.append(('cap_045_regime_trending_down', 0.6 if c < ma50 else -0.4))
    if ma50 > ma200:
        sigs.append(('cap_018_ma_golden_cross', 0.5))
    if ma50 < ma200:
        sigs.append(('cap_019_ma_death_cross', -0.5))
    if c > ma200:
        sigs.append(('cap_069_moving_average_reclaim', 0.6))
    if c < ma200:
        sigs.append(('cap_069_moving_average_reclaim', -0.6))

    # Load trader profiles and vote
    prof_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'profiles_v2')
    ln, sn, nn = 0, 0, 0
    tsigs = []

    for f in sorted(os.listdir(prof_dir)):
        if not f.endswith('.json'):
            continue
        try:
            p = json.load(open(os.path.join(prof_dir, f), encoding='utf-8'))
        except:
            continue
        tw, ws = 0.0, 0.0
        for cap in (p.get('capabilities_used', []) or []):
            cid = cap.get('id', '')
            w = float(cap.get('weight', 0))
            matched = [s for s in sigs if s[0] == cid]
            if matched:
                ws += w * matched[0][1]
                tw += abs(w)
        sig = ws / tw if tw > 0 else 0.0
        tsigs.append(sig)
        if sig > 0.03:
            ln += 1
        elif sig < -0.03:
            sn += 1
        else:
            nn += 1

    avg_sig = np.mean(tsigs) if tsigs else 0
    return {'bull': ln, 'bear': sn, 'neu': nn, 'avg_sig': round(avg_sig, 4), 'total': ln+sn+nn}


def analyze_coin(symbol, htf='1H'):
    """Complete multi-timeframe analysis for one coin.

    Combines: 5m KOL consensus + HTF trend + SMC structure + ATR stop-loss
    """
    print(f'\n{"="*60}')
    print(f'  综合信号报告: {symbol}')
    print(f'{"="*60}')

    # 1. MTF Trend
    mtf = check_mtf_trend(symbol, htf, 20)
    mtf_dir = '看多' if mtf['direction'] == 'BULL' else ('看空' if mtf['direction'] == 'BEAR' else '中性')
    print(f'\n  1) 大趋势 ({htf} EMA20):')
    print(f'     {mtf_dir} (价{mtf["distance_pct"]:+.2f}%偏离EMA, EMA={mtf["ema"]:.4f})')

    # 2. 5m KOL Consensus
    kol = get_kol_consensus_5m(symbol)
    if kol:
        kol_dir = '做多' if kol['avg_sig'] > 0.03 else ('做空' if kol['avg_sig'] < -0.03 else '中性')
        print(f'\n  2) 锁妖塔 (5m KOL投票):')
        print(f'     多 {kol["bull"]} / 空 {kol["bear"]} / 中 {kol["neu"]}  (偏度={kol["avg_sig"]:+.4f})')
        print(f'     方向: {kol_dir}')
    else:
        print(f'\n  2) 锁妖塔 (5m): 数据不足')
        kol_dir = '未知'

    # 3. SMC Structure
    candles = fetch_ohlc(symbol, '5m', 200)
    if candles and len(candles) >= 30:
        closes = np.array([c['close'] for c in candles])
        highs = np.array([c['high'] for c in candles])
        lows = np.array([c['low'] for c in candles])
        volumes = np.array([c.get('volume', 0) for c in candles])
        rsi_v = calc_rsi(closes)
        smc_sig = check_entry_signal(closes, highs, lows, volumes, rsi_v)

        smc_dir = smc_sig['direction']
        smc_signal = smc_sig['signal']
        sh = smc_sig['swing_high']
        sl = smc_sig['swing_low']
        atr = smc_sig['atr']
        sl_price = smc_sig['stop_loss']
        tp_price = smc_sig['take_profit']

        print(f'\n  3) SMC 结构 ({smc_signal}):')
        if sh:
            print(f'     前高: ${sh:.4f}')
        if sl:
            print(f'     前低: ${sl:.4f}')
        print(f'     建议: {smc_dir} | ATR={atr:.6f}')
        print(f'     止损(ATRx2): ${sl_price:.4f} | 止盈(ATRx3): ${tp_price:.4f}')

        # ORB dynamic range check
        orb = check_orb_range(closes, highs, lows)
        print(f'\n     ORB区间 (最近12根K线): {orb["range_pct"]:.1f}%')
        print(f'     区间上沿: ${orb["orb_high"]:.4f} | 区间下沿: ${orb["orb_low"]:.4f}')
        if orb['break_above']:
            print(f'     >>> 价格突破区间上沿')
        elif orb['break_below']:
            print(f'     >>> 价格跌破区间下沿')
        else:
            print(f'     价格在区间内')

        # FVG check
        fvg_active = smc_sig.get('fvg_active', False)
        if fvg_active:
            fvg_type = '向上缺口' if smc_sig.get('fvg_bull') else '向下缺口'
            print(f'     FVG: {fvg_type} 活跃')
    else:
        print(f'\n  3) SMC 结构: 数据不足')
        smc_dir = '未知'

    # 4. Signal alignment
    print(f'\n  4) 综合判断:')
    mtf_bull = mtf['direction'] == 'BULL'
    mtf_bear = mtf['direction'] == 'BEAR'
    kol_bull = kol_dir == '做多'
    kol_bear = kol_dir == '做空'
    smc_bull = smc_dir == 'LONG'
    smc_bear = smc_dir == 'SHORT'

    # Count alignments
    bullish_count = sum([mtf_bull, kol_bull, smc_bull])
    bearish_count = sum([mtf_bear, kol_bear, smc_bear])

    print(f'     HTF: {mtf_dir} | KOL: {kol_dir} | SMC: {smc_dir}')
    if bullish_count >= 2:
        print(f'     >>> 综合: 偏多 ({bullish_count}/3)')
        print(f'     建议: HTF看多 + KOL看多 = 方向一致, 等SMC结构突破入场')
    elif bearish_count >= 2:
        print(f'     >>> 综合: 偏空 ({bearish_count}/3)')
        print(f'     建议: HTF看空 + KOL看空 = 方向一致, 等SMC结构突破入场')
    else:
        print(f'     >>> 综合: 方向不统一, 建议等待')
        print(f'     建议: 三个维度不一致, 进场风险大, 等信号统一')

    # 5. Key price levels
    print(f'\n  5) 关键价位:')
    if candles and len(candles) >= 30:
        cur_c = closes[-1]
        print(f'     当前价: ${cur_c:.4f}')
        if mtf['ema'] > 0:
            print(f'     {htf} EMA20: ${mtf["ema"]:.4f}')
        if sh:
            print(f'     Swing High: ${sh:.4f}')
        if sl:
            print(f'     Swing Low: ${sl:.4f}')

    # 6. One-line conclusion
    print(f'\n  >>> 一句话结论:')
    if bearish_count >= 2:
        target = f'做空 {symbol.replace("-USDT","")}'
        entry_price = cur_c if candles and len(candles) >= 30 else 0
        stop = smc_sig.get('stop_loss_initial', 0) if candles and len(candles) >= 30 else 0
        tp = smc_sig.get('take_profit', 0) if candles and len(candles) >= 30 else 0
        print(f'     {target}  入场${entry_price:.4f}  止损${stop:.4f}  TP1${tp:.4f}')
        print(f'     理由: {mtf_dir}趋势 + KOL看空 + SMC{smc_signal} = {bearish_count}/3一致')
    elif bullish_count >= 2:
        target = f'做多 {symbol.replace("-USDT","")}'
        entry_price = cur_c if candles and len(candles) >= 30 else 0
        stop = smc_sig.get('stop_loss_initial', 0) if candles and len(candles) >= 30 else 0
        tp = smc_sig.get('take_profit', 0) if candles and len(candles) >= 30 else 0
        print(f'     {target}  入场${entry_price:.4f}  止损${stop:.4f}  TP1${tp:.4f}')
        print(f'     理由: {mtf_dir}趋势 + KOL看多 + SMC{smc_signal} = {bullish_count}/3一致')
    else:
        print(f'     方向不统一, 建议等待')

    return {
        'htf_dir': mtf['direction'],
        'kol_bull': kol['bull'] if kol else 0,
        'kol_bear': kol['bear'] if kol else 0,
        'smc_signal': smc_sig['signal'] if candles and len(candles) >= 30 else 'NODATA',
    }


def scan_all(htf='1H'):
    """Batch scan all coins showing alignment status."""
    coins = ['BTC','ETH','SOL','XRP','DOGE','ADA','LINK','DOT','LTC','BCH',
             'ALLO','KAITO','ZEC','LIT','EDGE','PI','WLD','SUI','NEAR','ONDO']
    print(f'\nMTF 批量扫描 (5m KOL + {htf} 趋势)')
    print('=' * 65)
    print(f'{"币种":<8s} {"HTF趋势":<10s} {"KOL多空":<12s} {"SMC":<10s} {"综合":<8s} {"建议":<10s}')
    print('-' * 65)
    for base in coins:
        symbol = f'{base}-USDT'
        try:
            mtf = check_mtf_trend(symbol, htf, 20)
            kol = get_kol_consensus_5m(symbol)

            candles = fetch_ohlc(symbol, '5m', 200)
            smc_signal = 'NODATA'
            if candles and len(candles) >= 30:
                closes = np.array([c['close'] for c in candles])
                highs = np.array([c['high'] for c in candles])
                lows = np.array([c['low'] for c in candles])
                volumes = np.array([c.get('volume', 0) for c in candles])
                rsi_v = calc_rsi(closes)
                smc_sig = check_entry_signal(closes, highs, lows, volumes, rsi_v)
                smc_signal = smc_sig['signal']

            htf_disp = mtf['direction'][:4] if mtf['direction'] else 'N/A'
            kol_disp = f"{kol['bull']}/{kol['bear']}" if kol else 'N/A'
            smc_disp = smc_signal[:6] if smc_signal else 'N/A'

            # Alignment check
            mtf_bull = mtf['direction'] == 'BULL'
            mtf_bear = mtf['direction'] == 'BEAR'
            kol_bull = kol['avg_sig'] > 0.03 if kol else False
            kol_bear = kol['avg_sig'] < -0.03 if kol else False
            smc_bull = smc_sig['direction'] == 'LONG' if candles and len(candles) >= 30 else False
            smc_bear = smc_sig['direction'] == 'SHORT' if candles and len(candles) >= 30 else False

            bull = sum([mtf_bull, kol_bull, smc_bull])
            bear = sum([mtf_bear, kol_bear, smc_bear])

            if bull >= 2:
                verdict = '看多'
                advice = '关注多'
            elif bear >= 2:
                verdict = '看空'
                advice = '关注空'
            else:
                verdict = '观望'
                advice = '等信号'

            print(f'{base:<8s} {htf_disp:<10s} {kol_disp:<12s} {smc_disp:<10s} {verdict:<8s} {advice:<10s}')
        except Exception as e:
            print(f'{base:<8s} ERR')
    print()
    print('综合>=2: 三个维度中至少两个方向一致时可进场')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='MTF 多时间框架综合信号报告')
    parser.add_argument('coin', nargs='?', default=None, help='币种名,如 KAITO')
    parser.add_argument('--htf', default='1H', help='高时间框架: 1H, 4H, 1D (默认1H)')
    args = parser.parse_args()

    if args.coin:
        symbol = f'{args.coin.upper()}-USDT'
        analyze_coin(symbol, args.htf)
    else:
        scan_all(args.htf)


if __name__ == '__main__':
    main()
