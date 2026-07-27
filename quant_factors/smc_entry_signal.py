#!/usr/bin/env python3
"""SMC Structure Break Entry Signal - 入场时机判断模块。

基于 FMZ/TradingView 的 SMC 策略，检测结构突破 + 成交量激增 + RSI 三重确认。
配合锁妖塔 KOL 方向使用：
  1. KOL 说方向（做空/做多）
  2. SMC 说时机（现在进 / 等回调 / 无信号）

用法:
    python quant_factors/smc_entry_signal.py KAITO          # 单个币种详细分析
    python quant_factors/smc_entry_signal.py                # 批量扫描排名
    python quant_factors/smc_entry_signal.py --bar 1h       # 指定时间框架
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_data_adapter import fetch_ohlc


def detect_swing_points(highs, lows, lookback=5):
    """Detect swing highs and lows."""
    n = len(highs)
    last_sh_price = None
    last_sl_price = None

    for i in range(lookback, n):
        right_limit = min(lookback, n - 1 - i)
        if right_limit < 1:
            continue
        if (all(highs[i] >= highs[i - j] for j in range(1, min(lookback, i) + 1)) and
            all(highs[i] >= highs[i + j] for j in range(1, right_limit + 1))):
            last_sh_price = highs[i]
        if (all(lows[i] <= lows[i - j] for j in range(1, min(lookback, i) + 1)) and
            all(lows[i] <= lows[i + j] for j in range(1, right_limit + 1))):
            last_sl_price = lows[i]

    return last_sh_price, last_sl_price


def calc_rsi(closes):
    """Calculate RSI values for entire series."""
    diff = np.diff(closes)
    gains = np.where(diff > 0, diff, 0)
    losses = np.where(diff < 0, -diff, 0)
    rsi_v = np.ones(len(closes)) * 50
    for i in range(14, len(closes)):
        g = np.mean(gains[i-14:i])
        l = np.mean(losses[i-14:i])
        if l > 0:
            rsi_v[i] = 100 - 100 / (1 + g/l)
    return rsi_v


def calc_adx(closes, highs, lows, period=14):
    """Calculate ADX (Average Directional Index) for trend strength.

    Returns:
        (adx_value, adx_rising) where adx_value is current ADX,
        adx_rising is True if ADX is increasing (trend strengthening)
    """
    n = len(closes)
    if n < period + 2:
        return 0, False

    tr_list = []
    dm_plus_list = []
    dm_minus_list = []

    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)

        dm_plus = max(highs[i] - highs[i-1], 0) if highs[i] - highs[i-1] > lows[i-1] - lows[i] else 0
        dm_minus = max(lows[i-1] - lows[i], 0) if lows[i-1] - lows[i] > highs[i] - highs[i-1] else 0
        dm_plus_list.append(dm_plus)
        dm_minus_list.append(dm_minus)

    # Wilder smoothing
    atr = [sum(tr_list[:period]) / period]
    s_dm_plus = [sum(dm_plus_list[:period]) / period]
    s_dm_minus = [sum(dm_minus_list[:period]) / period]

    for i in range(period, len(tr_list)):
        atr.append((atr[-1] * (period - 1) + tr_list[i]) / period)
        s_dm_plus.append((s_dm_plus[-1] * (period - 1) + dm_plus_list[i]) / period)
        s_dm_minus.append((s_dm_minus[-1] * (period - 1) + dm_minus_list[i]) / period)

    # DI and DX
    di_plus_list = [dp / a * 100 if a > 0 else 0 for dp, a in zip(s_dm_plus, atr)]
    di_minus_list = [dm / a * 100 if a > 0 else 0 for dm, a in zip(s_dm_minus, atr)]
    dx_list = [abs(dp - dm) / (dp + dm) * 100 if (dp + dm) > 0 else 0
               for dp, dm in zip(di_plus_list, di_minus_list)]

    # ADX = SMA of DX
    adx_values = []
    for i in range(period - 1, len(dx_list)):
        adx_values.append(np.mean(dx_list[i - period + 1:i + 1]))

    if not adx_values:
        return 0, False

    current_adx = adx_values[-1]
    prev_adx = adx_values[-2] if len(adx_values) >= 2 else current_adx
    adx_rising = current_adx > prev_adx

    return round(current_adx, 1), adx_rising


def check_entry_signal(closes, highs, lows, volumes, rsi_values, lookback=5, vol_mult=2.0):
    """Check for SMC structure break entry signal.

    Returns dict with: signal, direction, current_price, swing_high, swing_low,
                       vol_ratio, rsi, confidence, reason
    """
    n = len(closes)
    if n < 30:
        return {'signal': 'WAIT', 'direction': 'NONE', 'current_price': 0,
                'swing_high': None, 'swing_low': None, 'vol_ratio': 0,
                'rsi': 50, 'confidence': 0, 'reason': '数据不足'}

    sh_price, sl_price = detect_swing_points(highs, lows, lookback)
    cur_c = closes[-1]
    prev_c = closes[-2]
    cur_v = volumes[-1]
    cur_rsi = rsi_values[-1]

    vol_avg = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    vol_spike = cur_v > vol_avg * vol_mult if vol_avg > 0 else False
    vol_ratio = cur_v / vol_avg if vol_avg > 0 else 0

    result = {
        'signal': 'WAIT', 'direction': 'NONE',
        'swing_high': sh_price, 'swing_low': sl_price,
        'current_price': cur_c, 'vol_ratio': round(vol_ratio, 2),
        'rsi': round(cur_rsi, 1), 'confidence': 0, 'reason': '',
        'atr': 0, 'stop_loss': 0, 'take_profit': 0,
        'adx': 0, 'adx_rising': False,
    }

    # Calculate ATR for stop-loss suggestion
    atr_val = 0
    if len(closes) >= 15:
        trs = []
        for i in range(1, min(15, len(closes))):
            tr = max(highs[-i] - lows[-i], abs(highs[-i] - closes[-i-1]), abs(lows[-i] - closes[-i-1]))
            trs.append(tr)
        if trs:
            atr_val = np.mean(trs)
    result['atr'] = round(atr_val, 6)

    # ADX calculation for trend strength filter
    adx_val, adx_rising = calc_adx(closes, highs, lows, 14)
    result['adx'] = adx_val
    result['adx_rising'] = adx_rising

    # Two-stage ATR stop-loss (from YTPBTC1HATRSSADX strategy)
    # Stage 1 (initial): stop = entry +/- ATR*1.0 — wide, don't get shaken out
    # Stage 2 (trailing): after profit >= ATR*3.0, stop slides at ATR*9.0 distance
    init_sl_mult = 1.0   # initial stop distance
    trail_trig = 3.0      # profit needed to activate trailing (in ATR units)
    trail_sl_mult = 9.0   # trailing stop distance (very wide = let profits run)
    
    if result['direction'] == 'SHORT':
        result['stop_loss'] = round(cur_c + atr_val * init_sl_mult, 6)
        result['stop_loss_initial'] = round(cur_c + atr_val * init_sl_mult, 6)
        result['stop_loss_trail'] = round(cur_c + atr_val * trail_sl_mult, 6)
        result['take_profit'] = round(cur_c - atr_val * trail_trig, 6)
    elif result['direction'] == 'LONG':
        result['stop_loss'] = round(cur_c - atr_val * init_sl_mult, 6)
        result['stop_loss_initial'] = round(cur_c - atr_val * init_sl_mult, 6)
        result['stop_loss_trail'] = round(cur_c - atr_val * trail_sl_mult, 6)
        result['take_profit'] = round(cur_c + atr_val * trail_trig, 6)
    else:
        result['stop_loss'] = round(cur_c + atr_val * init_sl_mult, 6)
        result['stop_loss_initial'] = round(cur_c + atr_val * init_sl_mult, 6)
        result['stop_loss_trail'] = round(cur_c + atr_val * trail_sl_mult, 6)
        result['take_profit'] = round(cur_c - atr_val * trail_trig, 6)

    # FVG (Fair Value Gap) detection — 3-candle pattern
    # Bullish FVG: high of 2 bars ago < low of current bar (gap up)
    # Bearish FVG: low of 2 bars ago > high of current bar (gap down)
    fvg_bull = False
    fvg_bear = False
    if len(closes) >= 4:
        if highs[-3] < lows[-1]:
            fvg_bull = True
        if lows[-3] > highs[-1]:
            fvg_bear = True
    result['fvg_bull'] = fvg_bull
    result['fvg_bear'] = fvg_bear
    result['fvg_active'] = fvg_bull or fvg_bear

    # SHORT signal
    if sh_price is not None:
        if prev_c >= sh_price >= cur_c:
            if vol_spike and cur_rsi > 50:
                result['signal'] = 'ENTER NOW'
                result['direction'] = 'SHORT'
                result['confidence'] = 4
                result['reason'] = f'向下突破前高{sh_price:.4f}+放量{vol_ratio:.1f}x+RSI{cur_rsi:.0f}>50'
            elif vol_spike:
                result['signal'] = 'ENTER NOW'
                result['direction'] = 'SHORT'
                result['confidence'] = 3
                result['reason'] = f'向下突破前高{sh_price:.4f}+放量{vol_ratio:.1f}x,RSI={cur_rsi:.0f}未确认'
            else:
                result['signal'] = 'WATCH'
                result['direction'] = 'SHORT'
                result['confidence'] = 2
                result['reason'] = f'向下突破前高{sh_price:.4f}但无量'
        elif abs(cur_c - sh_price) / cur_c < 0.02:
            result['signal'] = 'WATCH'
            result['direction'] = 'SHORT'
            result['confidence'] = 1
            result['reason'] = f'接近前高{sh_price:.4f},关注是否放量跌破'

    # LONG signal
    if sl_price is not None:
        if prev_c <= sl_price <= cur_c:
            if vol_spike and cur_rsi < 50:
                result['signal'] = 'ENTER NOW'
                result['direction'] = 'LONG'
                result['confidence'] = 4
                result['reason'] = f'向上突破前低{sl_price:.4f}+放量{vol_ratio:.1f}x+RSI{cur_rsi:.0f}<50'
            elif vol_spike:
                result['signal'] = 'ENTER NOW'
                result['direction'] = 'LONG'
                result['confidence'] = 3
                result['reason'] = f'向上突破前低{sl_price:.4f}+放量{vol_ratio:.1f}x,RSI={cur_rsi:.0f}未确认'
            else:
                result['signal'] = 'WATCH'
                result['direction'] = 'LONG'
                result['confidence'] = 2
                result['reason'] = f'向上突破前低{sl_price:.4f}但无量'
        elif abs(cur_c - sl_price) / cur_c < 0.02:
            if result['signal'] == 'WAIT':
                result['signal'] = 'WATCH'
                result['direction'] = 'LONG'
                result['confidence'] = 1
                result['reason'] = f'接近前低{sl_price:.4f},关注是否放量突破'

    if result['signal'] == 'WAIT':
        if sh_price and sl_price:
            result['reason'] = f'在区间${sl_price:.4f}-${sh_price:.4f},无突破'
        else:
            result['reason'] = '无有效摆动点'

    return result


def analyze_coin(symbol, bar='5m', limit=200, lookback=5, vol_mult=2.0):
    """Full SMC analysis with detailed printout for a single coin."""
    candles = fetch_ohlc(symbol, bar, limit)
    if not candles or len(candles) < 30:
        print('  数据不足')
        return None

    closes = np.array([c['close'] for c in candles])
    highs = np.array([c['high'] for c in candles])
    lows = np.array([c['low'] for c in candles])
    volumes = np.array([c.get('volume', 0) for c in candles])
    rsi_values = calc_rsi(closes)

    signal = check_entry_signal(closes, highs, lows, volumes, rsi_values, lookback, vol_mult)
    sh = signal.get('swing_high')
    sl = signal.get('swing_low')
    cur = signal.get('current_price')

    print(f'\nSMC 分析: {symbol} ({bar})')
    print('=' * 55)
    print(f'  当前价:    ${cur:.4f}')
    if sh:
        print(f'  前高(SH):  ${sh:.4f}  (相距 {(cur-sh)/cur*100:+.2f}%)')
    if sl:
        print(f'  前低(SL):  ${sl:.4f}  (相距 {(cur-sl)/cur*100:+.2f}%)')
    print(f'  成交量比:  {signal["vol_ratio"]:.1f}x (均量)')
    print(f'  RSI(14):   {signal["rsi"]:.1f}')

    sig = signal['signal']
    direction = signal['direction']
    conf = signal['confidence']
    reason = signal['reason']

    if sig == 'ENTER NOW':
        flag = '!!' if conf >= 4 else '!'
        print(f'  信号: {flag} {sig} ({direction}) [信心 {conf}/5]')
    elif sig == 'WATCH':
        print(f'  信号: ? {sig} ({direction}) [信心 {conf}/5]')
    else:
        print(f'  信号: - {sig}')
    print(f'  理由: {reason}')
    print(f'  ATR(14): {signal["atr"]:.6f}')
    print(f'  初始止损(ATRx1): ${signal["stop_loss_initial"]:.4f} | 追踪止损(ATRx9): ${signal["stop_loss_trail"]:.4f}')
    print(f'  追踪激活: 盈利>=ATRx3 (${signal["take_profit"]:.4f})')
    adx_status = f'{signal["adx"]:.1f}'
    if signal['adx'] >= 25:
        adx_status += ' 强趋势'
    elif signal['adx'] >= 12:
        adx_status += ' 趋势中' + ('(增强)' if signal['adx_rising'] else '(减弱)')
    else:
        adx_status += ' 弱/震荡'
    print(f'  ADX(14): {adx_status}')
    if signal['fvg_active']:
        fvg_type = '向上缺口' if signal['fvg_bull'] else '向下缺口'
        print(f'  FVG: {fvg_type} 活跃')

    if sig == 'ENTER NOW':
        if direction == 'SHORT':
            print(f'  建议: 现价挂单做空, TP1=${cur*0.95:.4f}')
        else:
            print(f'  建议: 现价挂单做多, TP1=${cur*1.05:.4f}')

    return signal


def scan_all(bar='5m', lookback=5, vol_mult=2.0):
    """Batch scan: silent, only print ranking table."""
    scan_coins = ['BTC','ETH','SOL','XRP','DOGE','ADA','LINK','DOT','LTC','BCH',
                  'ALLO','KAITO','ZEC','LIT','EDGE','PI','WLD','SUI','NEAR','ONDO']
    print(f'SMC 批量扫描 ({bar})')
    print('=' * 65)
    print(f'{"币种":<8s} {"信号":<12s} {"方向":>4s} {"当前价":>10s} {"前低/前高":>14s} {"量":>4s} {"RSI":>5s}')
    print('-' * 65)
    for base in scan_coins:
        try:
            candles = fetch_ohlc(f'{base}-USDT', bar, 200)
            if not candles or len(candles) < 30:
                print(f'{base:<8s} NODATA')
                continue
            closes = np.array([c['close'] for c in candles])
            highs = np.array([c['high'] for c in candles])
            lows = np.array([c['low'] for c in candles])
            volumes = np.array([c.get('volume', 0) for c in candles])
            rsi_v = calc_rsi(closes)
            sig = check_entry_signal(closes, highs, lows, volumes, rsi_v, lookback, vol_mult)
            arrow = 'v' if sig['direction'] == 'SHORT' else ('^' if sig['direction'] == 'LONG' else '-')
            levels = ''
            if sig['swing_low'] and sig['swing_high']:
                levels = f'{sig["swing_low"]:.4f}-{sig["swing_high"]:.4f}'
            vol_f = '!!' if sig['vol_ratio'] >= 2.0 else ('!' if sig['vol_ratio'] >= 1.5 else '-')
            print(f'{base:<8s} {sig["signal"]:<12s} {arrow:>4s} ${sig["current_price"]:<8.4f} {levels:>14s} {vol_f:>4s} {sig["rsi"]:>5.1f}')
        except Exception as e:
            print(f'{base:<8s} ERR ({e})')
    print()
    print('量: !!>=2x !=1.5x -=正常 | 方向: v做空 ^做多 -观望')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC 结构突破入场信号')
    parser.add_argument('coin', nargs='?', default=None, help='币种名,如 KAITO')
    parser.add_argument('--bar', default='5m', help='时间框架: 5m, 15m, 1H, 4H, 1D (默认5m)')
    parser.add_argument('--lookback', type=int, default=5, help='Swing回看K线数 (默认5)')
    parser.add_argument('--vol-mult', type=float, default=2.0, help='放量倍数 (默认2.0)')
    args = parser.parse_args()

    if args.coin:
        symbol = f'{args.coin.upper()}-USDT'
        analyze_coin(symbol, args.bar, 200, args.lookback, args.vol_mult)
    else:
        scan_all(args.bar, args.lookback, args.vol_mult)


if __name__ == '__main__':
    main()
