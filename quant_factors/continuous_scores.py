"""Continuous scoring system - preserves original factor logic but returns continuous [-1,+1] scores"""
import numpy as np

def continuous_score_all(cid, row, feats=None, derivatives=None):
    """Unified continuous scoring for all 87 factors.
    Each factor: preserves original logic as the core signal,
    but returns continuous [-1,+1] based on how close conditions are met.
    
    Args:
        cid: capability/factor ID
        row: single row of features (dict or Series)
        feats: full feature DataFrame (needed for some multi-bar factors)
        derivatives: dict with funding_rate, oi_usd, ls_ratio (optional)
    """
    c = float(row['close'])
    h = float(row['high'])
    l = float(row['low'])
    o = float(row['open'])
    v = float(row.get('volume', 0))
    
    ma7 = float(row.get('ma7', c))
    ma20 = float(row.get('ma20', c))
    ma50 = float(row.get('ma50', c))
    ma200 = float(row.get('ma200', c))
    rsi = float(row.get('rsi14', 50))
    r1 = float(row.get('r1', c))
    r2 = float(row.get('r2', c))
    s1 = float(row.get('s1', c))
    s2 = float(row.get('s2', c))
    pivot = float(row.get('pivot', c))
    fib618 = float(row.get('fib_618', c))
    bbw = float(row.get('bb_width', 0))
    bbu = float(row.get('bb_upper', c))
    bbl = float(row.get('bb_lower', c))
    hist = float(row.get('macd_hist', 0))
    atr = float(row.get('atr14', 0))
    adx = float(row.get('adx14', 25))
    body = abs(c - o)
    rng = h - l if h > l else 1
    
    ret_1d = float(row.get('ret_1d', 0))
    ret_5d = float(row.get('ret_5d', 0))
    ret_7d = float(row.get('ret_7d', 0))
    ret_30d = float(row.get('ret_30d', 0))
    is_green = float(row.get('is_green', 0))
    price_above_ma50 = float(row.get('price_above_ma50', 0))
    price_above_ma200 = float(row.get('price_above_ma200', 0))
    ma50_above_ma200 = float(row.get('ma50_above_ma200', 0))
    high_20d = float(row.get('high_20d', h))
    low_20d = float(row.get('low_20d', l))
    high_50d = float(row.get('high_50d', h))
    low_50d = float(row.get('low_50d', l))
    bb_width_20p = float(row.get('bb_width_20pctile', bbw))
    uptrend_20d = float(row.get('price_above_ma50', 0))
    upper_wick_pct = float(row.get('upper_wick_pct', 0))
    lower_wick_pct = float(row.get('lower_wick_pct', 0))
    body_pct = float(row.get('body_pct', 1))
    
    # ==================== REGIME (5 caps) ====================
    
    if cid == 'cap_044_regime_trending_up':
        # Original: price>MA200 & MA50>MA200 & ADX>25
        cond1 = (c / ma200) if ma200 > 0 else 1  # >1 means above
        cond2 = (ma50 / ma200) if ma200 > 0 else 1  # >1 means golden cross
        cond3 = adx / 25  # >1 means trending
        score = (cond1 - 1) * 0.5 + (cond2 - 1) * 0.3 + min(cond3, 1) * 0.2
        return max(-0.5, min(1.0, score))
    
    if cid == 'cap_045_regime_trending_down':
        cond1 = (1 - c / ma200) if ma200 > 0 else 0  # >0 means below
        cond2 = (1 - ma50 / ma200) if ma200 > 0 else 0  # >0 means death cross
        cond3 = adx / 25
        score = cond1 * 0.5 + cond2 * 0.3 + min(cond3, 1) * 0.2
        return max(-1.0, min(0.5, -score))
    
    if cid == 'cap_046_regime_ranging':
        range_pos = (c - low_20d) / max(high_20d - low_20d, 0.001)
        ranging = (adx < 25) * 1.0 + (bbw < bb_width_20p * 1.5) * 0.5
        if ranging > 1:
            return (0.5 - range_pos) * 2  # -1 at top, +1 at bottom
        return 0.0
    
    if cid == 'cap_047_regime_volatile':
        if atr > 0 and c > 0:
            vol_ratio = (atr / c) / 0.02  # normalized to 2% daily move
            if vol_ratio > 1.5:
                return -min(0.5, (vol_ratio - 1.5) * 0.3)  # volatile = cautious
        return 0.0
    
    if cid == 'cap_070_parabolic_exhaustion':
        if ret_7d > 0.15 and rsi > 75:
            return -min(1.0, (ret_7d - 0.15) / 0.1 + (rsi - 75) / 10)
        if ret_7d > 0.1 and rsi > 70:
            return -0.2  # approaching
        return 0.0
    
    # ==================== INDICATORS (9 caps) ====================
    
    if cid == 'cap_015_rsi_bullish_divergence':
        if feats is not None and len(feats) > 20:
            close_20b = float(feats['close'].iloc[-21]) if len(feats) > 21 else c
            rsi_20b = float(feats['rsi14'].iloc[-21]) if len(feats) > 21 else rsi
            price_lower = c < close_20b
            rsi_higher = rsi > rsi_20b
            if price_lower and rsi_higher:
                return 0.7
            rsi_diff = (rsi - rsi_20b) / 30  # normalized divergence strength
            return max(-0.2, min(0.5, rsi_diff))
        return 0.0
    
    if cid == 'cap_016_rsi_bearish_divergence':
        if feats is not None and len(feats) > 20:
            close_20b = float(feats['close'].iloc[-21]) if len(feats) > 21 else c
            rsi_20b = float(feats['rsi14'].iloc[-21]) if len(feats) > 21 else rsi
            price_higher = c > close_20b
            rsi_lower = rsi < rsi_20b
            if price_higher and rsi_lower:
                return -0.7
            return 0.0
        return 0.0
    
    if cid == 'cap_017_rsi_oversold_bounce':
        if rsi < 30:
            return 0.7
        if rsi < 40:
            return 0.4 - (40 - rsi) / 40 * 0.4
        if rsi < 45:
            return 0.1
        return 0.0
    
    if cid == 'cap_018_ma_golden_cross':
        # Continuous: how far MA50 is above MA200
        if ma200 > 0:
            ratio = (ma50 - ma200) / ma200
            return max(-0.5, min(0.5, ratio * 50))
        return 0.0
    
    if cid == 'cap_019_ma_death_cross':
        if ma200 > 0:
            ratio = (ma200 - ma50) / ma200
            return max(-0.5, min(0.5, -ratio * 50))
        return 0.0
    
    if cid == 'cap_020_macd_histogram_cross':
        if hist > 0:
            return min(0.5, hist * 5)
        elif hist < 0:
            return max(-0.5, hist * 5)
        return 0.0
    
    if cid == 'cap_021_bb_squeeze_breakout':
        if bb_width_20p > 0 and bbw / bb_width_20p < 1.2:
            if c > bbu:
                return 0.6
            if c < bbl:
                return -0.6
            # Squeezing but not broken out
            return -0.1 if bbw / bb_width_20p < 0.8 else 0.0
        return 0.0
    
    if cid == 'cap_022_fib_618_support':
        if c > 0 and fib618 > 0:
            dist = abs(c - fib618) / c
            if dist < 0.02 and is_green:
                return 0.7
            if dist < 0.05:
                return 0.3 * (1 - dist / 0.05)
            if dist < 0.10:
                return 0.1
        return 0.0
    
    if cid == 'cap_069_moving_average_reclaim':
        if c > ma200:
            if ma200 > 0:
                return min(0.6, (c - ma200) / ma200 * 10)
        else:
            if ma200 > 0:
                return max(-0.6, (c - ma200) / ma200 * 5)
        return 0.0
    
    # ==================== CYCLE (5 caps) ====================
    
    if cid == 'cap_037_halving_cycle':
        return -0.30  # 2026-07: ~27 months post halving
    
    if cid == 'cap_038_4year_cycle':
        return -0.40
    
    if cid == 'emg_005_4year_same_day_compare':
        return -0.25
    
    if cid == 'emg_006_days_in_tight_range':
        return 0.1
    
    if cid == 'emg_023_monthly_seasonality':
        from datetime import datetime
        m = datetime.now().month
        return 0.1 if m in [10, 11, 12, 1, 2, 3] else -0.1
    
    # ==================== STRUCTURAL (8 caps) ====================
    
    if cid == 'cap_023_elliott_wave_3':
        cond1 = ret_30d
        cond2 = 55 <= rsi <= 80
        cond3 = ma50_above_ma200
        if cond1 > 0.15 and cond2 and cond3:
            return min(0.6, cond1 * 2)
        if cond1 > 0.05 and cond3:
            return 0.2
        return 0.0 if cond3 else -0.2
    
    if cid == 'cap_024_wyckoff_accumulation_spring':
        near_low = c < low_50d * 1.03
        wick_below = l < low_50d
        close_above = c > low_50d
        if near_low and wick_below and close_above and lower_wick_pct > 0.3:
            return 0.6
        if near_low and lower_wick_pct > 0.2:
            return 0.2
        return 0.0
    
    if cid == 'cap_025_wyckoff_distribution_upthrust':
        near_high = c > high_50d * 0.97
        wick_above = h > high_50d
        close_below = c < high_50d
        if near_high and wick_above and close_below and upper_wick_pct > 0.3:
            return -0.6
        return 0.0
    
    if cid == 'cap_026_smc_order_block_retest':
        return 0.2 if ma50_above_ma200 else -0.2
    
    if cid == 'cap_048_ict_breaker_block':
        return -0.2 if not price_above_ma200 else 0.2
    
    if cid == 'cap_049_ict_fair_value_gap':
        return 0.0
    
    if cid == 'cap_065_btc_dominance_shift':
        return 0.0
    
    if cid == 'cap_hh_defense':
        if low_20d > low_50d * 0.95 and price_above_ma50:
            return 0.5
        return 0.0
    
    # ==================== PATTERNS (26 caps) ====================
    
    if cid in ['cap_001_falling_wedge_breakout', 'cap_003_bull_flag',
               'cap_006_inverse_head_shoulders', 'cap_008_double_bottom',
               'cap_009_cup_and_handle', 'cap_010_ascending_triangle']:
        return 0.35 if price_above_ma50 else -0.2
    
    if cid in ['cap_002_rising_wedge_breakdown', 'cap_004_bear_flag',
               'cap_005_head_shoulders_top', 'cap_007_double_top',
               'cap_011_descending_triangle']:
        return -0.35 if not price_above_ma50 else 0.2
    
    if cid == 'cap_012_sfp':
        if h > high_20d and c < high_20d:
            return -0.5  # failed breakout up
        if l < low_20d and c > low_20d:
            return 0.5   # failed breakout down
        return 0.0
    
    if cid == 'cap_013_range_fade':
        range_pos = (c - low_20d) / max(high_20d - low_20d, 0.001)
        if range_pos > 0.85:
            return -0.4
        if range_pos < 0.15:
            return 0.4
        return 0.0
    
    if cid == 'cap_014_trend_pullback':
        if ma50_above_ma200 and (c > ma50 * 0.97) and (c < ma50 * 1.03):
            return 0.5 if is_green else 0.2
        return 0.0
    
    if cid in ['cap_050_three_drives', 'cap_051_quasimodo']:
        return -0.2 if rsi > 65 else 0.0
    
    if cid == 'cap_052_liquidity_grab':
        if l < low_20d and lower_wick_pct > 0.3 and c > o:
            return 0.5
        if h > high_20d and upper_wick_pct > 0.3 and c < o:
            return -0.5
        return 0.0
    
    if cid == 'cap_053_doji':
        return 0.2 if rng > 0 and body / rng < 0.1 else 0.0
    
    if cid == 'cap_054_engulfing':
        return 0.3 if (c - o) > 0 and body > float(row.get('body_pct_prev', 0)) else 0.0
    
    if cid == 'cap_055_pin_bar':
        if rng > 0 and body / rng < 0.25:
            if upper_wick_pct > 0.6:
                return -0.4
            if lower_wick_pct > 0.6:
                return 0.4
        return 0.0
    
    if cid == 'cap_056_double_needle_bottom':
        return 0.3 if rsi < 40 else 0.0
    
    if cid == 'cap_057_fake_breakout':
        return 0.0
    
    if cid == 'cap_058_triple_bottom':
        return 0.3 if low_20d > low_50d * 0.95 else 0.0
    
    # ==================== DERIVATIVES - MOCK (7 caps) ====================
    # ==================== DERIVATIVES (7 caps) ====================
    if cid in ['cap_031_funding_extreme_neg', 'cap_032_funding_extreme_pos',
               'cap_033_oi_climb', 'cap_034_liquidation_cluster',
               'cap_059_funding_divergence', 'cap_060_basis_blowout',
               'cap_061_options_skew']:
        if derivatives is None:
            return 0.0
        fr = derivatives.get('funding_rate', 0)
        oi = derivatives.get('oi_usd', 0)
        ls = derivatives.get('ls_ratio', 1.0)
        
        if cid == 'cap_031_funding_extreme_neg':
            # Extreme negative funding = bearish sentiment extreme = possible bounce
            if fr < -0.001: return 0.6  # funding < -0.1%
            if fr < -0.0005: return 0.3
            return 0.0
        
        if cid == 'cap_032_funding_extreme_pos':
            # Extreme positive funding = bullish extreme = overheated
            if fr > 0.001: return -0.5
            if fr > 0.0005: return -0.2
            return 0.0
        
        if cid == 'cap_033_oi_climb':
            # OI climbing = new money entering
            if oi > 0: return min(0.3, oi / 1e8 * 0.1)
            return 0.0
        
        if cid == 'cap_034_liquidation_cluster':
            return 0.0  # Need liquidation data
        
        if cid == 'cap_059_funding_divergence':
            # Price down but funding positive = bearish divergence
            return 0.0  # Need price+funding history
        
        if cid == 'cap_060_basis_blowout':
            # Basis too high = futures premium
            return 0.0
        
        if cid == 'cap_061_options_skew':
            return 0.0  # Need options data
        return 0.0
    
    # ==================== MACRO (7 caps) ====================
    if cid in ['cap_027_dxy_inverse_btc', 'cap_028_spx_risk_on',
               'cap_029_yields_liquidity', 'cap_030_gold_safe_haven',
               'cap_062_m2_growth', 'cap_063_ism_pmi', 'cap_064_credit_spreads']:
        if derivatives is not None and 'ls_ratio' in derivatives:
            ls = derivatives.get('ls_ratio', 1.0)
            if ls > 2.0:
                return -0.15  # Excessive bullish = overheated
            if ls < 0.5:
                return 0.15   # Excessive bearish = extreme
        return 0.1 if price_above_ma50 else -0.1
    
    # ==================== ONCHAIN - PROXY (5 caps) ====================
    if cid in ['cap_035_exchange_inflow', 'cap_066_stablecoin_supply']:
        vol_ratio = v / (feats['volume'].rolling(20).mean().iloc[-1]) if feats is not None and 'volume' in feats.columns else 1
        if v > 0 and vol_ratio > 2:
            return -0.15 if price_above_ma50 else 0.15  # Abnormal volume
        return 0.0
    if cid in ['cap_036_lth_holding', 'cap_067_nvt_extreme', 'cap_068_mvrv_zscore']:
        return 0.0
    
    # ==================== EVENTS - MOCK (2 caps) ====================
    if cid in ['cap_039_fomc_risk_off', 'cap_040_etf_flows_proxy']:
        return 0.0
    
    # ==================== SMC STRUCTURE BREAK (1 cap) ====================
    if cid == 'cap_071_smc_structure_break':
        """SMC Structure Break with Volume Spike + RSI Confirmation.
        
        Translated from FMZ/TradingView Pine Script strategy:
          - Swing high/low detection (5-bar pivot lookback)
          - Structure break: price breaks through last swing level
          - Volume spike: volume > 2x 20-period SMA volume
          - RSI confirmation: RSI<50 for long, RSI>50 for short
        
        Returns continuous [-1, +1] score.
        """
        # Need feats for multi-bar calculations
        if feats is None or 'volume' not in feats.columns:
            return 0.0
        
        closes = feats['close'].values
        highs = feats['high'].values
        lows = feats['low'].values
        vols = feats['volume'].values if 'volume' in feats.columns else None
        n = len(closes)
        
        # Swing high/low detection (5-bar pivot)
        sl = 5  # swing lookback
        last_sh = None  # last swing high
        last_sl_val = None  # last swing low
        
        for i in range(sl, n):
            right_limit = min(sl, n - 1 - i)
            if right_limit < 1:
                continue
            # Swing high: peak with at least 1 bar each side
            if all(highs[i] >= highs[i-j] for j in range(1, min(sl, i)+1)) and all(highs[i] >= highs[i+j] for j in range(1, right_limit+1)):
                last_sh = (i, highs[i])
            # Swing low: trough with at least 1 bar each side
            if all(lows[i] <= lows[i-j] for j in range(1, min(sl, i)+1)) and all(lows[i] <= lows[i+j] for j in range(1, right_limit+1)):
                last_sl_val = (i, lows[i])
        
        # Current bar
        cur_c = closes[-1]
        cur_h = highs[-1]
        cur_l = lows[-1]
        cur_v = vols[-1] if vols is not None else 0
        prev_c = closes[-2] if n >= 2 else cur_c
        
        # Volume spike: current volume > 2x 20-bar average volume
        vol_avg = np.mean(vols[-20:]) if vols is not None and len(vols) >= 20 else 0
        vol_spike = cur_v > vol_avg * 2.0 if vol_avg > 0 else False
        
        # Score for LONG: structure break above last swing low + vol spike + RSI < 50
        long_score = 0.0
        if last_sl_val is not None:
            level = last_sl_val[1]
            # Price breaks above the swing low (resistance turned support)
            if prev_c <= level <= cur_c and vol_spike and rsi < 50:
                # Full strength
                strength = min(vol_spike * 1.0 + (1 - rsi/50) * 0.5, 1.0)
                long_score = 0.5 + strength * 0.5
            elif prev_c <= level <= cur_c and rsi < 50:
                long_score = 0.3  # Structure break but no volume
            elif abs(cur_c - level) / cur_c < 0.01 and vol_spike and rsi < 50:
                long_score = 0.2  # Near breakout with volume
        
        # Score for SHORT: structure break below last swing high + vol spike + RSI > 50
        short_score = 0.0
        if last_sh is not None:
            level = last_sh[1]
            # Price breaks below the swing high (support turned resistance)
            if prev_c >= level >= cur_c and vol_spike and rsi > 50:
                strength = min(vol_spike * 1.0 + (rsi/50 - 1) * 0.5, 1.0)
                short_score = -0.5 - strength * 0.5
            elif prev_c >= level >= cur_c and rsi > 50:
                short_score = -0.3
            elif abs(cur_c - level) / cur_c < 0.01 and vol_spike and rsi > 50:
                short_score = -0.2
        
        # Take the stronger signal
        if abs(long_score) > abs(short_score):
            return long_score
        else:
            return short_score
    
    # ==================== EMA5/20 CROSS (1 cap) ====================
    if cid == 'cap_072_ema_cross_5_20':
        """EMA5/20 cross detection — fast trend change signal.
        
        EMA5 crossing above EMA20 = bullish (short-term momentum up)
        EMA5 crossing below EMA20 = bearish (short-term momentum down)
        
        Needs feats (full DataFrame) to check previous bar for crossover.
        """
        if feats is None or 'close' not in feats.columns:
            return 0.0
        closes = feats['close'].values
        n = len(closes)
        if n < 25:
            return 0.0
        
        # Calculate EMA5 and EMA20
        alpha5 = 2.0 / 6
        alpha20 = 2.0 / 21
        ema5 = [closes[0]]
        ema20 = [closes[0]]
        for p in closes[1:]:
            ema5.append(p * alpha5 + ema5[-1] * (1 - alpha5))
            ema20.append(p * alpha20 + ema20[-1] * (1 - alpha20))
        
        ema5_v = ema5[-1]
        ema20_v = ema20[-1]
        ema5_prev = ema5[-2] if len(ema5) >= 2 else ema5_v
        ema20_prev = ema20[-2] if len(ema20) >= 2 else ema20_v
        
        # Current position
        if ema5_v > ema20_v:
            position_score = 0.3
        elif ema5_v < ema20_v:
            position_score = -0.3
        else:
            position_score = 0.0
        
        # Crossover detection (more weight)
        if ema5_prev <= ema20_prev and ema5_v > ema20_v:
            return 0.6  # Golden cross (bullish)
        elif ema5_prev >= ema20_prev and ema5_v < ema20_v:
            return -0.6  # Death cross (bearish)
        
        # No cross, return position bias
        return position_score
    
    # ==================== ORB + FVG (1 cap) ====================
    if cid == 'cap_073_orb_fvg':
        """ORB dynamic range breakout + FVG gap confirmation.
        
        Detects:
          - ORB: price breaking above/below 12-bar range
          - FVG: 3-candle fair value gap (ICT-style)
          - Combined signal = stronger conviction
        
        Returns [-1, +1] based on direction and confirmation strength.
        """
        if feats is None or 'close' not in feats.columns:
            return 0.0
        closes = feats['close'].values
        highs = feats['high'].values
        lows = feats['low'].values
        n = len(closes)
        if n < 15:
            return 0.0
        
        # ORB: 12-bar range (exclude current bar)
        window = 12
        orb_high = max(highs[-window-1:-1])
        orb_low = min(lows[-window-1:-1])
        cur_c = closes[-1]
        prev_c = closes[-2]
        break_above = prev_c <= orb_high <= cur_c and orb_high > 0
        break_below = prev_c >= orb_low >= cur_c and orb_low > 0
        
        # FVG: 3-candle gap
        fvg_bull = highs[-3] < lows[-1] if n >= 4 else False
        fvg_bear = lows[-3] > highs[-1] if n >= 4 else False
        
        # Score calculation
        if break_above and fvg_bull:
            return 0.7  # ORB breakout + FVG gap up = strong bullish
        elif break_above:
            return 0.3  # ORB breakout alone = mild bullish
        elif break_below and fvg_bear:
            return -0.7  # ORB breakdown + FVG gap down = strong bearish
        elif break_below:
            return -0.3  # ORB breakdown alone = mild bearish
        elif fvg_bull:
            return 0.2  # FVG alone (gap up)
        elif fvg_bear:
            return -0.2  # FVG alone (gap down)
        
        return 0.0
    
    # ==================== RISK (4 caps) ====================
    
    if cid == 'cap_041_dont_catch_falling_knives':
        return -0.5 if rsi < 30 else 0.0
    
    if cid == 'cap_042_position_sizing':
        return 0.0
    
    if cid == 'cap_043_cut_losses_early':
        return -0.3 if c < s1 else 0.0
    
    if cid == 'emg_009_range_middle_filter':
        range_pos = (c - s1) / max(r1 - s1, 0.01)
        return 0.0 if 0.3 < range_pos < 0.7 else (0.3 if range_pos < 0.3 else -0.3)
    
    # ==================== EMERGED (15 caps) ====================
    if cid in ['emg_001_quarterly_vwap', 'emg_007_htf_reclaim_retest',
               'emg_027_ohlc_anchor_framework', 'emg_030_htf_close_anchor',
               'emg_013_box_breakout', 'emg_017_break_target_projection']:
        return 0.3 if price_above_ma50 else -0.3
    
    if cid in ['emg_008_w50ema_bull_bear_divider', 'emg_014_horizontal_reclaim']:
        return 0.4 if price_above_ma50 else -0.4
    
    if cid == 'emg_010_broadening_wedge':
        return 0.2 if rsi < 50 else -0.2
    
    if cid in ['emg_022_200w_mechanical_buy', 'emg_029_200w_value_zone']:
        if c < ma200 * 0.9:
            return 0.5
        if c < ma200:
            return 0.2
        return -0.1
    
    if cid == 'emg_028_20w_200w_double_reclaim':
        return 0.4 if c > ma200 and price_above_ma50 else -0.3
    
    # Default
    return 0.0
