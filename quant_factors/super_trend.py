"""
20维超级趋势识别 — 百分制, 纯标签不影响任何判断

每维度0-5分, 判定当前是超级多头还是超级空头。
≥60分 → 超级做多/超级做空, <60 → 无超级趋势。

每个维度参考FMZ策略广场对应策略的核心算法。
"""

import numpy as np
import pandas as pd


def detect_super_trend(feats, daily_feats=None):
    """
    对单币运行20维超级趋势检测
    
    Args:
        feats: 15m build_features_single 输出
        daily_feats: 可选, 日线特征 (用于多周期一致检测)
    
    Returns:
        {'bull_score': int, 'bear_score': int, 
         'label': '🔥超级做多'/'🔥超级做空'/None,
         'details': {dim: '多'/'空'/'-'}}
    """
    c = feats['close'].values
    h = feats['high'].values
    l = feats['low'].values
    v = feats['volume'].values if 'volume' in feats.columns else np.ones_like(c)
    n = len(c)
    
    bull = 0
    bear = 0
    details = {}

    # ── 1. ADX强度 ──
    # FMZ: ADX-Trend-Breakout-Momentum-Trading-Strategy
    adx = float(feats['adx14'].iloc[-1]) if 'adx14' in feats.columns else 0
    if adx > 40:   bull += 5; bear += 5; details['ADX强度'] = f'{adx:.0f}(极强)'
    elif adx > 30: bull += 3; bear += 3; details['ADX强度'] = f'{adx:.0f}(强)'
    elif adx > 25: bull += 1; bear += 1; details['ADX强度'] = f'{adx:.0f}(有趋势)'
    else: details['ADX强度'] = f'{adx:.0f}(弱)'

    # ── 2. ADX方向 ──
    # FMZ: Dynamic-EMA-Crossover-Strategy-with-ADX-Trend-Strength-Filtering
    if n >= 5 and adx > 0:
        adx_prev = float(feats['adx14'].iloc[-5])
        if adx > adx_prev: 
            if c[-1] > c[-5]: bull += 3
            else: bear += 3
            details['ADX方向'] = '上升'
        else: details['ADX方向'] = '下降/平'
    else: details['ADX方向'] = '-'

    # ── 3. DI差值 ──
    # FMZ: ADXRSI-Momentum-Indicators-Strategy
    # 用ema7 vs ema50近似 +DI/-DI
    if n >= 50:
        ema7 = float(np.mean(c[-7:]))
        ema50 = float(np.mean(c[-50:]))
        if ema7 > ema50 * 1.02: bull += 3; details['DI方向'] = '多'
        elif ema7 < ema50 * 0.98: bear += 3; details['DI方向'] = '空'
        else: details['DI方向'] = '-'
    else: details['DI方向'] = '-'

    # ── 4. SuperTrend ──
    # FMZ: BEST-Supertrend-Strategy
    # ST = (H+L)/2 ± 3×ATR10
    if n >= 10:
        atr10 = float(feats['atr14'].iloc[-1] * 0.85) if 'atr14' in feats.columns else np.mean(h[-10:]-l[-10:])
        mid = (float(h[-1]) + float(l[-1])) / 2
        st_upper = mid + 3 * atr10
        st_lower = mid - 3 * atr10
        if c[-1] > st_upper: bull += 3; details['SuperTrend'] = '线上看多'
        elif c[-1] < st_lower: bear += 3; details['SuperTrend'] = '线下看空'
        else: details['SuperTrend'] = '区间内'
    else: details['SuperTrend'] = '-'

    # ── 5. Parabolic SAR ──
    # FMZ: EMA-and-Parabolic-SAR-Combination-Strategy
    # 简化: 连续2根K线高点上移=SAR上升
    if n >= 3:
        if h[-1] > h[-2] > h[-3] and l[-1] > l[-2] > l[-3]:
            bull += 2; details['SAR'] = '上升'
        elif h[-1] < h[-2] < h[-3] and l[-1] < l[-2] < l[-3]:
            bear += 2; details['SAR'] = '下降'
        else: details['SAR'] = '-'
    else: details['SAR'] = '-'

    # ── 6. CCI极端 ──
    # FMZ: CCI-Momentum-Divergence-Trend-Trading-Strategy
    # 简化: (close - SMA20) / (0.015 × MAD)
    if n >= 20:
        sma20 = float(np.mean(c[-20:]))
        mad = float(np.mean(np.abs(c[-20:] - sma20)))
        if mad > 0:
            cci = (float(c[-1]) - sma20) / (0.015 * mad)
            if cci > 150: bull += 2; details['CCI'] = f'{cci:.0f}(极高)'
            elif cci < -150: bear += 2; details['CCI'] = f'{cci:.0f}(极低)'
            else: details['CCI'] = f'{cci:.0f}'
        else: details['CCI'] = '-'
    else: details['CCI'] = '-'

    # ── 7. Aroon ──
    # FMZ: Aroon-Indicator-Based-Quantitative-Strategy
    if n >= 14:
        h14 = h[-14:]
        l14 = l[-14:]
        aroon_up = (13 - np.argmax(h14)) / 13 * 100 if len(h14) > 1 else 50
        aroon_down = (13 - np.argmin(l14)) / 13 * 100 if len(l14) > 1 else 50
        if aroon_up > 70 and aroon_down < 30: bull += 2; details['Aroon'] = f'Up={aroon_up:.0f}'
        elif aroon_down > 70 and aroon_up < 30: bear += 2; details['Aroon'] = f'Down={aroon_down:.0f}'
        else: details['Aroon'] = '-'
    else: details['Aroon'] = '-'

    # ── 8. Vortex ──
    # FMZ: Dual-Vortex-Indicator-with-Trend-Strength
    if n >= 14:
        vm_plus = np.sum(np.abs(h[1:] - l[:-1])) if n > 1 else 1
        vm_minus = np.sum(np.abs(l[1:] - h[:-1])) if n > 1 else 1
        tr_sum = np.sum(np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1]))))
        if tr_sum > 0:
            vi_plus = vm_plus / tr_sum
            vi_minus = vm_minus / tr_sum
            if vi_plus > vi_minus * 1.1: bull += 2; details['Vortex'] = 'VI+>VI-'
            elif vi_minus > vi_plus * 1.1: bear += 2; details['Vortex'] = 'VI+<VI-'
            else: details['Vortex'] = '-'
        else: details['Vortex'] = '-'
    else: details['Vortex'] = '-'

    # ── 9. 一目云 ──
    # FMZ: Ichimoku-Cloud-and-ATR-Strategy
    if n >= 52:
        turning9 = (np.max(h[-9:]) + np.min(l[-9:])) / 2
        turning26 = (np.max(h[-26:]) + np.min(l[-26:])) / 2
        cloud_top = max(turning9, turning26)
        cloud_bot = min(turning9, turning26)
        if c[-1] > cloud_top: bull += 3; details['一目云'] = '云上'
        elif c[-1] < cloud_bot: bear += 3; details['一目云'] = '云下'
        else: details['一目云'] = '云中'
    else: details['一目云'] = '-'

    # ── 10. Donchian ──
    # FMZ: Donchian-Channel-Trend-Following-Strategy
    if n >= 20:
        hh20 = float(np.max(h[-20:]))
        ll20 = float(np.min(l[-20:]))
        if c[-1] >= hh20 * 0.995: bull += 2; details['Donchian'] = '破20日高'
        elif c[-1] <= ll20 * 1.005: bear += 2; details['Donchian'] = '破20日低'
        else: details['Donchian'] = '-'
    else: details['Donchian'] = '-'

    # ── 11. MA排列 ──
    # FMZ: Multi-EMA-Trend-Following-Swing-Trading-with-ATR-Risk-Management
    if n >= 50:
        ma7 = float(np.mean(c[-7:]))
        ma25 = float(np.mean(c[-25:]))
        ma50 = float(np.mean(c[-50:]))
        if ma7 > ma25 > ma50: bull += 3; details['MA排列'] = '多头排列'
        elif ma7 < ma25 < ma50: bear += 3; details['MA排列'] = '空头排列'
        else: details['MA排列'] = '-'
    else: details['MA排列'] = '-'

    # ── 12. MACD柱 ──
    # FMZ: MACD-Momentum-Strategy
    if 'macd_hist' in feats.columns and n >= 5:
        hist = float(feats['macd_hist'].iloc[-1])
        hist_prev = float(feats['macd_hist'].iloc[-5])
        if hist > 0 and hist > hist_prev: bull += 2; details['MACD柱'] = '扩张'
        elif hist < 0 and hist < hist_prev: bear += 2; details['MACD柱'] = '扩张'
        else: details['MACD柱'] = '-'
    else: details['MACD柱'] = '-'

    # ── 13. 成交量 ──
    # FMZ: Dynamic-Volume-Enhanced-Donchian-Channel-Trend-Breakout-Strategy
    if n >= 20:
        vol_ma = float(np.mean(v[-20:]))
        vol_now = float(v[-1])
        if vol_now > vol_ma * 1.5:
            if c[-1] > c[-2]: bull += 1; details['成交量'] = '放量涨'
            else: bear += 1; details['成交量'] = '放量跌'
        else: details['成交量'] = '-'
    else: details['成交量'] = '-'

    # ── 14. BB突破 ──
    # FMZ: Bollinger-Bands-Momentum-Breakout-Strategy
    if 'bb_width' in feats.columns and 'bb_width_20pctile' in feats.columns and n >= 5:
        bbw = float(feats['bb_width'].iloc[-1])
        bbw_p20 = float(feats['bb_width_20pctile'].iloc[-1])
        if bbw < bbw_p20:  # BB压缩
            if c[-1] > float(feats['bb_upper'].iloc[-1]): bull += 2; details['BB突破'] = '压缩后突破上轨'
            elif c[-1] < float(feats['bb_lower'].iloc[-1]): bear += 2; details['BB突破'] = '压缩后跌破下轨'
            else: details['BB突破'] = '压缩中'
        else: details['BB突破'] = '-'
    else: details['BB突破'] = '-'

    # ── 15. 连续K线 ──
    # FMZ: Midnight-Candle-Color-Strategy
    if n >= 3:
        green = sum(1 for i in range(1,4) if c[-i] > (feats['open'].iloc[-i] if 'open' in feats.columns else c[-i-1]))
        red = 3 - green
        if green >= 3: bull += 1; details['连续K线'] = '3连阳'
        elif red >= 3: bear += 1; details['连续K线'] = '3连阴'
        else: details['连续K线'] = '-'
    else: details['连续K线'] = '-'

    # ── 16. RSI方向 ──
    # FMZ: RSI-Momentum-and-ADX-Trend-Strength-Capital-Management
    if 'rsi14' in feats.columns:
        rsi = float(feats['rsi14'].iloc[-1])
        if rsi > 55: bull += 1; details['RSI方向'] = '偏多'
        elif rsi < 45: bear += 1; details['RSI方向'] = '偏空'
        else: details['RSI方向'] = '-'
    else: details['RSI方向'] = '-'

    # ── 17. OBV方向 ──
    # FMZ: OBV-RSI-Combined-Mean-Reversion-Trading-Strategy
    if n >= 10:
        obv = np.zeros(n)
        for i in range(1, n):
            if c[i] > c[i-1]: obv[i] = obv[i-1] + v[i]
            elif c[i] < c[i-1]: obv[i] = obv[i-1] - v[i]
            else: obv[i] = obv[i-1]
        if obv[-1] > obv[-10]: bull += 2; details['OBV'] = '上升'
        elif obv[-1] < obv[-10]: bear += 2; details['OBV'] = '下降'
        else: details['OBV'] = '-'
    else: details['OBV'] = '-'

    # ── 18. 多周期一致 ──
    # FMZ: TrendSync-Pro-SMC-Multi-Timeframe-Trend-Following-Strategy
    if daily_feats is not None and len(daily_feats) >= 2:
        d_ma7 = float(np.mean(daily_feats['close'].values[-7:])) if len(daily_feats) >= 7 else float(daily_feats['close'].iloc[-1])
        d_ma25 = float(np.mean(daily_feats['close'].values[-25:])) if len(daily_feats) >= 25 else d_ma7
        htf_up = daily_feats['close'].iloc[-1] > d_ma25
        htf_dn = daily_feats['close'].iloc[-1] < d_ma25
        ltf_up = c[-1] > np.mean(c[-25:]) if n >= 25 else False
        ltf_dn = c[-1] < np.mean(c[-25:]) if n >= 25 else False
        if htf_up and ltf_up: bull += 4; details['多周期'] = '日+15m一致多'
        elif htf_dn and ltf_dn: bear += 4; details['多周期'] = '日+15m一致空'
        else: details['多周期'] = '-'
    else: details['多周期'] = '-'

    # ── 19. 突破力度 ──
    # FMZ: Dual-Strong-Trend-Tracking-Stop-Loss-Strategy
    if n >= 20:
        ma20 = float(np.mean(c[-20:]))
        atr = float(feats['atr14'].iloc[-1]) if 'atr14' in feats.columns else np.mean(h[-14:]-l[-14:])
        if atr > 0:
            force = (c[-1] - ma20) / atr
            if force > 3: bull += 2; details['突破力度'] = f'{force:.1f}ATR(强多)'
            elif force < -3: bear += 2; details['突破力度'] = f'{force:.1f}ATR(强空)'
            else: details['突破力度'] = '-'
        else: details['突破力度'] = '-'
    else: details['突破力度'] = '-'

    # ── 20. 资金费率 ──
    # FMZ: cap_059_funding_divergence (锁妖塔因子)
    fr = float(feats.get('funding_rate', pd.Series([0])).iloc[-1]) if 'funding_rate' in feats.columns else 0
    if fr < -0.0005 and c[-1] > c[-5] if n >= 5 else False:
        bull += 2; details['资金费率'] = '负费率+价升'
    elif fr > 0.0005 and c[-1] < c[-5] if n >= 5 else False:
        bear += 2; details['资金费率'] = '正费率+价跌'
    else: details['资金费率'] = '-'

    # ── 判定 ──
    if bull >= 50:
        label = '🔥超级做多'
    elif bull >= 35:
        label = '📈强做多'
    elif bear >= 50:
        label = '🔥超级做空'
    elif bear >= 35:
        label = '📉强做空'
    else:
        label = '—'

    return {
        'bull_score': bull,
        'bear_score': bear,
        'label': label,
        'details': details,
    }
