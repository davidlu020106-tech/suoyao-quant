#!/usr/bin/env python3
"""锁妖塔 — 每日综合扫描 (1小时+日线双周期过滤)

流程:
  1. OKX取前N个活跃币种
  2. 1小时分析 → 88因子×99交易员 → 过滤(R1≥1.5%, OI≥600K)
  3. 日线分析 → 方向判断
  4. 综合过滤: 双周期一致 + ADX≥25 + TP1利润≥100%
  5. 输出标准表格 + 保存daily_picks.md

用法:
    python quant_factors/run_daily_picks.py
    python quant_factors/run_daily_picks.py --top 50 --min-r1 1.5
"""
import sys, os, json, urllib.request, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import OrderedDict

QF = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(QF)
sys.path.insert(0, QF)
sys.path.insert(0, BASE)
from local_config import OKX_API_KEY
from okx_data_adapter import build_features_single
from capabilities import CAP_REGISTRY

STABLE = {'USDT','USDC','DAI','TUSD','BUSD','FDUSD','USDP',
    'EUR','GBP','AUD','SGD','AED','CNY','JPY','KRW','USDG',
    'TRY','BRL','CAD','CHF','HKD','MXN'}

# ═══════════════════════════════════════
# OKX API
# ═══════════════════════════════════════

def api_get(path):
    url = 'https://www.okx.com' + path
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def fetch_list(top_n=15):
    r = api_get('/api/v5/market/tickers?instType=SPOT')
    coins = []
    for t in r.get('data', []):
        inst = t['instId']
        if not inst.endswith('-USDT'): continue
        base = inst.replace('-USDT', '')
        if base in STABLE: continue
        v = float(t.get('volCcy24h', '0') or 0)
        if v >= 500000:
            coins.append({'base': base, 'symbol': inst, 'vol': v})
    coins.sort(key=lambda x: x['vol'], reverse=True)
    return coins[:top_n]


def fetch_ohlc(symbol, bar='1H', limit=200):
    try:
        r = api_get(f'/api/v5/market/candles?instId={symbol}&bar={bar}&limit={limit}')
        raw = r.get('data', [])
        if not raw: return []
        raw.reverse()
        out = []
        for c in raw:
            ts = int(c[0]) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            out.append({'date': dt.strftime('%Y-%m-%d %H:%M'),
                        'open': float(c[1]), 'high': float(c[2]),
                        'low': float(c[3]), 'close': float(c[4]),
                        'volume': float(c[5])})
        return out
    except:
        return []


def fetch_funding_rate(base):
    try:
        r = api_get(f'/api/v5/public/funding-rate?instId={base}-USDT-SWAP')
        if r.get('code') == '0' and r.get('data'):
            return float(r['data'][0]['fundingRate'])
    except:
        pass
    return 0.0


def fetch_open_interest(base):
    try:
        r = api_get(f'/api/v5/public/open-interest?instType=SWAP&instId={base}-USDT-SWAP')
        if r.get('code') == '0' and r.get('data'):
            return float(r['data'][0]['oi'])
    except:
        pass
    return 0.0


# ═══════════════════════════════════════
# 因子评分 (单行评估, 与run_5m_kol_consensus一致)
# ═══════════════════════════════════════

def cscore(cid, row, fr, oi):
    c = float(row['close']); h = float(row['high']); l = float(row['low']); o = float(row['open'])
    ma20 = float(row.get('ma20', c)); ma50 = float(row.get('ma50', c)); ma200 = float(row.get('ma200', c))
    rsi = float(row.get('rsi14', 50)); r1_ = float(row.get('r1', c)); s1_ = float(row.get('s1', c))
    fib = float(row.get('fib_618', c)); bbw = float(row.get('bb_width', 0))
    hist = float(row.get('macd_hist', 0)); pv = float(row.get('pivot', c))
    rng = h - l; body = abs(c - o)

    if cid == 'cap_044_regime_trending_up': return 0.6 if c > ma50 else -0.4
    if cid == 'cap_045_regime_trending_down': return 0.6 if c < ma50 else -0.4
    if cid == 'cap_046_regime_ranging': return 0.5 if rng > 0 and (h - l) / c < 0.005 else 0.0
    if cid == 'cap_047_regime_volatile': return 0.6 if rng > 0 and (h - l) / c > 0.01 else 0.0
    if cid == 'cap_070_parabolic_exhaustion': return 0.5 if abs(float(row.get('ret_5d', 0))) > 0.02 else 0.0
    if cid == 'cap_015_rsi_bullish_divergence': return 0.3 if rsi > 50 and c > ma50 else -0.1
    if cid == 'cap_016_rsi_bearish_divergence': return -0.3 if rsi < 50 and c < ma50 else 0.1
    if cid == 'cap_017_rsi_oversold_bounce': return 0.5 if rsi < 35 else (0.2 if rsi < 45 else 0)
    if cid == 'cap_018_ma_golden_cross': return 0.5 if ma50 > ma200 else -0.5
    if cid == 'cap_019_ma_death_cross': return -0.5 if ma50 < ma200 else 0.5
    if cid == 'cap_020_macd_histogram_cross': return 0.4 if hist > 0 else -0.4
    if cid == 'cap_021_bb_squeeze_breakout': return 0.4 if bbw < 0.003 else (-0.2 if bbw > 0.008 else 0.0)
    if cid == 'cap_022_fib_618_support':
        d = abs(c - fib) / c if c > 0 else 1; return 0.7 if d < 0.01 else (0.3 if d < 0.03 else 0.0)
    if cid == 'cap_069_moving_average_reclaim': return 0.6 if c > ma200 else -0.6
    if cid in ('emg_008_w50ema_bull_bear_divider', 'emg_014_horizontal_reclaim'): return 0.4 if c > ma50 else -0.4
    if cid == 'emg_022_200w_mechanical_buy': return 0.5 if c < ma200 * 0.9 else -0.2
    if cid == 'emg_029_200w_value_zone': return 0.5 if c < ma200 * 0.85 else -0.1
    if cid == 'emg_028_20w_200w_double_reclaim': return 0.4 if c > ma200 and c > ma50 else -0.3
    if cid == 'emg_001_quarterly_vwap': return 0.3 if c > pv else -0.3
    if cid in ('cap_037_halving_cycle', 'cap_038_4year_cycle', 'emg_005_4year_same_day_compare'): return -0.30
    if cid == 'emg_006_days_in_tight_range': return 0.1
    if cid == 'emg_023_monthly_seasonality': return 0.1 if datetime.now().month in (10, 11, 12, 1, 2, 3) else -0.1
    if cid in ('cap_023_elliott_wave_3', 'cap_024_wyckoff_accumulation_spring', 'cap_026_smc_order_block_retest'): return 0.3 if c > ma50 else -0.3
    if cid in ('cap_025_wyckoff_distribution_upthrust', 'cap_049_ict_fair_value_gap'): return -0.3 if c < ma50 else 0.3
    if cid in ('cap_001_falling_wedge_breakout', 'cap_003_bull_flag', 'cap_006_inverse_head_shoulders'): return 0.35 if c > ma50 else -0.2
    if cid in ('cap_002_rising_wedge_breakdown', 'cap_004_bear_flag', 'cap_005_head_shoulders_top'): return -0.35 if c < ma50 else 0.2
    if cid in ('cap_012_sfp', 'cap_014_trend_pullback', 'cap_052_liquidity_grab', 'cap_057_fake_breakout', 'emg_013_box_breakout'): return 0.3 if c > ma20 else -0.3
    if cid == 'cap_053_doji': return 0.3 if rng > 0 and body / rng < 0.1 else 0.0
    if cid == 'cap_054_engulfing': return 0.3 if c > o else 0.0
    if cid == 'cap_055_pin_bar':
        uw = h - max(c, o); lw = min(c, o) - l
        if rng > 0 and min(uw, lw) / rng < 0.1 and max(uw, lw) / rng > 0.5:
            return 0.4 if lw > uw else -0.4
        return 0.0
    if cid == 'cap_056_double_needle_bottom': return 0.3 if rsi < 40 else 0.0
    if cid in ('cap_027_dxy_inverse_btc', 'cap_028_spx_risk_on', 'cap_040_etf_flows_proxy'): return 0.1 if c > ma50 else -0.1
    if cid == 'cap_041_dont_catch_falling_knives': return -0.5 if rsi < 30 else 0.0
    if cid == 'cap_043_cut_losses_early': return -0.3 if c < s1_ else 0.0
    if cid == 'emg_009_range_middle_filter':
        pos = (c - s1_) / max(r1_ - s1_, 0.01); return 0.0 if 0.3 < pos < 0.7 else (0.3 if pos < 0.3 else -0.3)
    if cid == 'emg_031_keltner_mean_revert':
        kcu = float(row.get('kc_upper', c)); kcl = float(row.get('kc_lower', c)); adx14 = float(row.get('adx14', 25))
        if kcu - kcl <= 0: return 0.0
        dist_l = (c - kcl) / (kcu - kcl)
        if adx14 < 25 and dist_l > 0.8: return 0.5
        if adx14 < 25 and dist_l < 0.2: return -0.5
        return 0.0
    if cid == 'cap_031_funding_extreme_neg':
        if fr < -0.001: return 0.8
        if fr < -0.0005: return 0.6
        if fr < -0.0001: return 0.3
        return 0.0
    if cid == 'cap_032_funding_extreme_pos':
        if fr > 0.001: return -0.8
        if fr > 0.0005: return -0.6
        if fr > 0.0001: return -0.3
        return 0.0
    if cid == 'cap_033_oi_climb':
        if oi > 50000000: return 0.4
        if oi > 10000000: return 0.25
        if oi > 1000000: return 0.1
        return 0.0
    if cid == 'cap_059_funding_divergence':
        if fr > 0.0005 and rsi < 40: return 0.5
        if fr < -0.0005 and rsi > 60: return -0.5
        return 0.0
    return 0.0


def match_cap(pid, rids):
    if pid in rids: return pid
    parts = pid.split('_')
    if len(parts) >= 2 and parts[0] == 'cap' and parts[1].isdigit():
        m = [c for c in rids if c.startswith('cap_' + parts[1] + '_')]
        return m[0] if m else None
    return None


# ═══════════════════════════════════════
# KOL 投票引擎
# ═══════════════════════════════════════

def kol_vote(latest_row, reg, rids, profs, fr, oi):
    """全交易员投票, 返回 (long_n, short_n, neutral_n, avg_bias)"""
    fs = {}
    for cid in reg:
        try:
            fs[cid] = cscore(cid, latest_row, fr, oi)
        except:
            fs[cid] = 0.0

    tsigs = []
    for h, p in profs.items():
        tw, ws = 0.0, 0.0
        for cap in (p.get('capabilities_used', []) or []):
            rid = cap.get('id', ''); w = float(cap.get('weight', 0))
            mid = match_cap(rid, rids)
            if mid:
                s = fs.get(mid, 0)
                if s != 0:
                    ws += w * s
                    tw += abs(w)
        if tw > 0:
            sig = ws / tw
        else:
            b = p.get('bias_default', 'neutral')
            sig = 0.15 if b == 'long_tilted' else (-0.15 if b == 'short_tilted' else 0.0)
        tsigs.append(sig)

    arr = np.array(tsigs)
    ln = int(np.sum(arr > 0.03))
    sn = int(np.sum(arr < -0.03))
    nn = len(arr) - ln - sn
    avg = float(np.mean(arr))
    return ln, sn, nn, avg


# ═══════════════════════════════════════
# 单币分析 (1小时 + 日线)
# ═══════════════════════════════════════

def analyze_coin(base, reg, rids, profs, min_r1=1.5, min_oi=600000, lev_map=None):
    """对一个币做1小时和日线双周期分析, 返回结果dict或None"""
    sym = f'{base}-USDT'

    # ── 1小时K线 ──
    cdl_h1 = fetch_ohlc(sym, '15m', 200)
    if len(cdl_h1) < 20: return None

    df = pd.DataFrame(cdl_h1)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    feats = build_features_single(df)
    lat = feats.iloc[-1]
    cur = float(lat['close'])

    # 衍生品
    fr = fetch_funding_rate(base)
    oi = fetch_open_interest(base)

    # KOL投票
    ln, sn, nn, m5_avg = kol_vote(lat, reg, rids, profs, fr, oi)

    # Pivot
    hh = float(feats['high'].max()); ll = float(feats['low'].min())
    pv = (hh + ll + cur) / 3; r1 = 2 * pv - ll; r2 = pv + (hh - ll)
    s1 = 2 * pv - hh; s2 = pv - (hh - ll)
    r1_up = (r1 / cur - 1) * 100
    s2_down = (1 - s2 / cur) * 100

    # 杠杆 (优先用预取数据)
    okx_lev = lev_map.get(base, 20) if lev_map else 20

    # ADX + 趋势方向
    adx = 0
    adx_trend = ''
    adx_hours_left = 0
    try:
        closes = np.array([c['close'] for c in cdl_h1])
        highs = np.array([c['high'] for c in cdl_h1])
        lows = np.array([c['low'] for c in cdl_h1])
        from smc_entry_signal import calc_adx
        adx, _ = calc_adx(closes, highs, lows, 14)
        
        # 算ADX序列判断趋势方向
        n_bar = len(closes)
        alpha = 1/14
        up = np.diff(highs); dn = -np.diff(lows)
        plus_dm = np.where((up > dn) & (up > 0), up, 0)
        minus_dm = np.where((dn > up) & (dn > 0), dn, 0)
        tr = np.maximum(np.maximum(highs[1:]-lows[1:], np.abs(highs[1:]-closes[:-1])), np.abs(lows[1:]-closes[:-1]))
        atr_s = np.zeros(len(tr)); atr_s[0] = np.mean(tr[:14])
        pdi_s = np.zeros(len(tr)); mdi_s = np.zeros(len(tr))
        for i in range(1, len(tr)):
            atr_s[i] = atr_s[i-1] + alpha*(tr[i]-atr_s[i-1])
            pdi_s[i] = pdi_s[i-1] + alpha*(plus_dm[i]-pdi_s[i-1])
            mdi_s[i] = mdi_s[i-1] + alpha*(minus_dm[i]-mdi_s[i-1])
        pdi_v = 100*pdi_s/atr_s; mdi_v = 100*mdi_s/atr_s
        dx = 100*np.abs(pdi_v-mdi_v)/(pdi_v+mdi_v+1e-10)
        adx_all = np.zeros(len(dx)); adx_all[13] = np.mean(dx[:14])
        for i in range(14, len(dx)):
            adx_all[i] = adx_all[i-1] + alpha*(dx[i]-adx_all[i-1])
        
        if len(adx_all) >= 20:
            recent = np.mean(adx_all[-10:])
            prior = np.mean(adx_all[-20:-10])
            adx_trend = '↑' if recent > prior else '↓'
            # 估算跌破25所需小时数
            if adx >= 25 and recent < prior:
                changes = np.diff(adx_all[-20:])
                avg_chg = np.mean(changes) if len(changes) > 0 else 0
                if avg_chg < 0:
                    bars_left = (adx - 25) / abs(avg_chg)
                    adx_hours_left = bars_left * 0.25  # 15分钟K线
    except:
        pass

    # 过滤1: R1≥min_r1, OI≥min_oi
    if r1_up < min_r1: return None
    if oi < min_oi: return None

    # TP1利润 (做多用R1, 做空用S2)
    if m5_avg > 0.01:  # 偏多
        tp1_pct = r1_up
        direction = 'long'
    else:  # 偏空或中性→默认做空方向
        tp1_pct = s2_down
        direction = 'short'

    tp1_profit = tp1_pct * okx_lev

    # TP1可行性
    tp1_req_pct = 100.0 / okx_lev  # 翻倍所需%
    liq_ratio = cur / abs(cur - s2) if abs(cur - s2) > 0.001 else 1
    safe_lev = (okx_lev <= liq_ratio)
    atr_val = float(lat.get('atr14', 0))
    if cur > 0 and atr_val > 0:
        atr_daily_pct = (atr_val / cur * 100) * 96 * 0.7
        days_to_tp1 = tp1_req_pct / atr_daily_pct if atr_daily_pct > 0 else 999
    else:
        days_to_tp1 = 999
    tp1_score = 0
    if safe_lev: tp1_score += 4
    tp1_score += max(0, min(3, int(3 - (days_to_tp1 - 1))))
    if adx >= 25: tp1_score += 3
    elif adx >= 12: tp1_score += 1

    # ── 日线 ──
    cdl_daily = fetch_ohlc(sym, '1D', 200)
    daily_avg = 0.0
    daily_ln = daily_sn = 0
    if len(cdl_daily) >= 20:
        df_d = pd.DataFrame(cdl_daily)
        df_d['date'] = pd.to_datetime(df_d['date'])
        df_d = df_d.set_index('date').sort_index()
        feats_d = build_features_single(df_d)
        lat_d = feats_d.iloc[-1]
        daily_ln, daily_sn, _, daily_avg = kol_vote(lat_d, reg, rids, profs, fr, oi)
        time.sleep(0.15)  # 控制API频率

    # 方向一致性
    m5_bias = 'long' if m5_avg > 0.01 else ('short' if m5_avg < -0.01 else 'neutral')
    daily_bias = 'long' if daily_avg > 0.01 else ('short' if daily_avg < -0.01 else 'neutral')
    consistent = (m5_bias == daily_bias) and m5_bias != 'neutral'

    # 市场状态
    if adx >= 25: state = '趋势'
    elif adx >= 12: state = '过渡'
    else: state = '震荡'

    # ORB区间（最近12根15分钟K线）
    orb_low = min(c['low'] for c in cdl_h1[-13:-1]) if len(cdl_h1) >= 14 else cur * 0.99
    orb_high = max(c['high'] for c in cdl_h1[-13:-1]) if len(cdl_h1) >= 14 else cur * 1.01

    return {
        'base': base,
        'entry': cur,
        'r1': r1, 'r2': r2, 's1': s1, 's2': s2,
        'r1_up': r1_up, 's2_down': s2_down,
        'orb_low': orb_low, 'orb_high': orb_high,
        'm5_avg': m5_avg, 'm5_bias': m5_bias,
        'm5_long': ln, 'm5_short': sn, 'm5_neutral': nn,
        'daily_avg': daily_avg, 'daily_bias': daily_bias,
        'daily_long': daily_ln, 'daily_short': daily_sn,
        'consistent': consistent,
        'adx': adx, 'adx_trend': adx_trend, 'adx_hours_left': adx_hours_left,
        'rsi': float(lat.get('rsi14', 50)),
        'kc_pos': float((cur - float(lat.get('kc_lower', cur))) / max(float(lat.get('kc_upper', cur)) - float(lat.get('kc_lower', cur)), 0.001)),
        'funding_rate': fr, 'open_interest': oi,
        'okx_lev': okx_lev,
        'tp1_pct': tp1_pct,
        'tp1_profit': tp1_profit,
        'tp1_score': tp1_score,
        'tp1_pass': tp1_score >= 5,
        'market_state': state,
        'direction': direction,
        'fr_pct': fr * 100,
        'df_15m': cdl_h1,  # 原始15m K线数据，供审判系统复用
    }


# ═══════════════════════════════════════
# 格式化
# ═══════════════════════════════════════

def fmt_price(p):
    if p > 10: return f'${p:.2f}'
    elif p > 1: return f'${p:.4f}'
    elif p > 0.001: return f'${p:.6f}'
    else: return f'${p:.8f}'


def fmt_pos(kc_pos):
    """Keltner通道位置 → emoji标识"""
    if kc_pos > 1.05: return '🔴上轨上'
    if kc_pos > 0.80: return '🟡偏高'
    if kc_pos > 0.20: return '🟢中位'
    if kc_pos > -0.05: return '🔵偏低'
    return '🟣下轨下'


def fmt_target(r, is_long):
    """取TP1目标价"""
    if is_long:
        return r['r1']
    else:
        return r['s2']


def run(top_n=50, min_r1=1.5, min_oi=600000, coins=None):
    print()
    print('  ╔══════════════════════════════════════╗')
    print('  ║   锁妖塔 — 每日综合扫描              ║')
    now_str_short = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'  ║   {now_str_short}                 ║')
    print('  ╚══════════════════════════════════════╝')
    print(f'  因子: {len(CAP_REGISTRY)} | 交易员: 99')
    print(f'  扫描: 前{top_n}币 | 过滤: R1≥{min_r1}% OI≥{min_oi/1e6:.1f}M')

    reg = CAP_REGISTRY; rids = set(reg.keys())

    # 加载交易员
    profs = {}
    pd_ = os.path.join(BASE, 'profiles_v2')
    for f in sorted(os.listdir(pd_)):
        if f.endswith('.json'):
            try:
                p = json.load(open(os.path.join(pd_, f), encoding='utf-8'))
                profs[f.replace('.json', '')] = p
            except:
                pass

    if coins:
        coins_list = [{'base': c.upper(), 'symbol': c.upper() + '-USDT', 'vol': 0} for c in coins]
        print(f'  指定币种: {len(coins_list)}个')
    else:
        coins_list = fetch_list(top_n)
        print(f'  币种: {len(coins_list)}')
    print()

    # 预取杠杆数据
    lev_map = {}
    try:
        inst = api_get('/api/v5/public/instruments?instType=SWAP')
        if inst.get('code') == '0':
            for d in inst.get('data', []):
                di = d['instId']
                if di.endswith('-USDT-SWAP'):
                    base_n = di.replace('-USDT-SWAP', '')
                    lev_map[base_n] = int(d.get('lever', 20))
    except:
        pass
    print(f'  杠杆数据: {len(lev_map)}个币')

    results = []
    for i, coin in enumerate(coins_list):
        base = coin['base']
        r = analyze_coin(base, reg, rids, profs, min_r1, min_oi, lev_map)
        if r:
            results.append(r)
            arrow = '✅' if r['consistent'] else '⚠️'
            print(f'  [{i+1}/{len(coins_list)}] {base:<8s} 15m L/S={r["m5_long"]}/{r["m5_short"]:<2d} '
                  f'D L/S={r["daily_long"]}/{r["daily_short"]:<2d} '
                  f'ADX={r["adx"]:.0f} R1={r["r1_up"]:.1f}% Pft={r["tp1_profit"]:.0f}% '
                  f'{arrow}')
        else:
            print(f'  [{i+1}/{len(coins_list)}] {base:<8s} 跳过')
        time.sleep(0.1)

    # ── 综合过滤 ──
    passed = [r for r in results if r['consistent'] and r['adx'] >= 25 and r['tp1_profit'] >= 100]
    short_ok = [r for r in passed if r['direction'] == 'short']
    long_ok = [r for r in passed if r['direction'] == 'long']

    # ── 大盘环境过滤 ──
    consistent_results = [r for r in results if r['consistent']]
    long_count = sum(1 for r in consistent_results if r['direction'] == 'long')
    short_count = sum(1 for r in consistent_results if r['direction'] == 'short')
    if short_count >= long_count * 2 and short_count >= 3:
        long_ok = []  # 市场偏空，不做多
        market_env = '🔴 市场偏空'
    elif long_count >= short_count * 2 and long_count >= 3:
        short_ok = []  # 市场偏多，不做空
        market_env = '🟢 市场偏多'
    else:
        market_env = '⚪ 市场均衡'

    short_ok.sort(key=lambda r: r['tp1_profit'], reverse=True)
    long_ok.sort(key=lambda r: r['tp1_profit'], reverse=True)

    # ── 输出 ──
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    sep = '=' * 90
    dash2 = '-' * 95

    # 排名：按日线方向分组 + 组内ADX排序
    long_group = [r for r in results if r['daily_avg'] > 0.01]
    short_group = [r for r in results if r['daily_avg'] < -0.01]
    neutral_group = [r for r in results if -0.01 <= r['daily_avg'] <= 0.01]
    long_group.sort(key=lambda r: -r['adx'])
    short_group.sort(key=lambda r: -r['adx'])
    neutral_group.sort(key=lambda r: -r['adx'])
    ranked = long_group + short_group + neutral_group

    print(f'\n\n  {sep}')
    print(f'  ★ 全量排名 (按信号 空←→多 排列)')
    print(f'  {now_str}')
    print(f'  {sep}')
    print(f'  扫描: {len(coins_list)}币 → 基础通过: {len(results)}')
    print(f'  ✅=方向一致  ⚠️=方向冲突')
    print()
    hdr = (f'  {"序":>2s} {"币种":<6s} {"方向":>2s} {"强度":>5s} {"方向":>2s} {"小时":>4s} {"位置":<6s}'
           f' {"RSI":>4s} {"入场价":>10s} {"止盈价":>10s} {"杠杆":>4s} {"TP1利润%":>8s}'
           f' {"15mKOL":>7s} {"日KOL":>6s} {"偏度":>6s}')
    print(hdr)
    print(f'  {dash2}')
    for i, r in enumerate(ranked, 1):
        arrow_m = '✅' if r['consistent'] else '⚠️'
        hrs_str = f'{r["adx_hours_left"]:.0f}h' if r.get("adx_hours_left", 0) > 0 else ''
        pos_str = fmt_pos(r.get('kc_pos', 0.5))
        if r['direction'] == 'long':
            target = r['r1']
            d_arrow = '🟢'
        else:
            target = r['s2']
            d_arrow = '🔴'
        profit_str = f'{r["tp1_profit"]:.0f}%'
        print(f'  {i:>2d} {r["base"]:<6s} {d_arrow:>2s} {r["adx"]:>5.1f} {r.get("adx_trend",""):>2s} {hrs_str:>4s} {pos_str:<6s}'
              f' {r["rsi"]:>4.0f} {fmt_price(r["entry"]):>10s} {fmt_price(target):>10s}'
              f' {r["okx_lev"]:>3d}x {profit_str:>8s}'
              f' {r["m5_long"]}/{r["m5_short"]:>3d} {r["daily_long"]}/{r["daily_short"]:>3d}'
              f' {arrow_m:>4s} {r["m5_avg"]:>+5.2f}')
    print()

    # ── 推荐 (严格过滤 TOP3) ──
    print(f'  {sep}')
    print(f'  ★ 今日推荐 {market_env}')
    print(f'  {now_str}')
    print(f'  {sep}')
    print()

    if short_ok:
        print(f'  ── 做空推荐 ──')
        hdr = (f'  {"序":>2s} {"币种":<6s} {"强度":>5s} {"方向":>2s} {"小时":>4s} {"位置":<6s}'
               f' {"RSI":>4s} {"入场价":>10s} {"止盈价":>10s} {"杠杆":>4s} {"TP1利润%":>8s}'
               f' {"15mKOL":>7s} {"日KOL":>6s}')
        print(hdr)
        print(f'  {dash2}')
        for i, r in enumerate(short_ok[:5], 1):
            target = fmt_target(r, False)
            profit_str = f'{r["tp1_profit"]:.0f}%'
            hrs_str = f'{r["adx_hours_left"]:.0f}h' if r.get("adx_hours_left", 0) > 0 else ''
            pos_str = fmt_pos(r.get('kc_pos', 0.5))
            print(f'  {i:>2d} {r["base"]:<6s} {r["adx"]:>5.1f} {r.get("adx_trend",""):>2s} {hrs_str:>4s} {pos_str:<6s}'
                  f' {r["rsi"]:>4.0f} {fmt_price(r["entry"]):>10s} {fmt_price(target):>10s}'
                  f' {r["okx_lev"]:>3d}x {profit_str:>8s}'
                  f' {r["m5_long"]}/{r["m5_short"]:>3d} {r["daily_long"]}/{r["daily_short"]:>3d}')
        print()

    if long_ok:
        print(f'  ── 做多推荐 ──')
        hdr = (f'  {"序":>2s} {"币种":<6s} {"强度":>5s} {"方向":>2s} {"小时":>4s} {"位置":<6s}'
               f' {"RSI":>4s} {"入场价":>10s} {"止盈价":>10s} {"杠杆":>4s} {"TP1利润%":>8s}'
               f' {"15mKOL":>7s} {"日KOL":>6s}')
        print(hdr)
        print(f'  {dash2}')
        for i, r in enumerate(long_ok[:5], 1):
            target = fmt_target(r, True)
            profit_str = f'{r["tp1_profit"]:.0f}%'
            hrs_str = f'{r["adx_hours_left"]:.0f}h' if r.get("adx_hours_left", 0) > 0 else ''
            pos_str = fmt_pos(r.get('kc_pos', 0.5))
            print(f'  {i:>2d} {r["base"]:<6s} {r["adx"]:>5.1f} {r.get("adx_trend",""):>2s} {hrs_str:>4s} {pos_str:<6s}'
                  f' {r["rsi"]:>4.0f} {fmt_price(r["entry"]):>10s} {fmt_price(target):>10s}'
                  f' {r["okx_lev"]:>3d}x {profit_str:>8s}'
                  f' {r["m5_long"]}/{r["m5_short"]:>3d} {r["daily_long"]}/{r["daily_short"]:>3d}')
        print()

    # ── 分批入场参考 ──
    if short_ok or long_ok:
        print(f'  ── 分批入场参考 ──')
        for r in (short_ok[:3] + long_ok[:5])[:5]:
            is_long = r['direction'] == 'long'
            dir_cn = '做多' if is_long else '做空'
            liq = r['entry'] - (r['entry'] / r['okx_lev']) if is_long else r['entry'] + (r['entry'] / r['okx_lev'])
            stop = liq + r['entry'] * 0.002 * (1 if is_long else -1)
            orb_ref = r.get('orb_low', r['entry'] * 0.99) if is_long else r.get('orb_high', r['entry'] * 1.01)
            if is_long:
                orb_ref = max(orb_ref, stop + r['entry'] * 0.001)
            else:
                orb_ref = min(orb_ref, stop - r['entry'] * 0.001)
            tag = 'ORB下沿' if is_long else 'ORB上沿'
            target = r['r1'] if is_long else r['s2']
            hrs = r.get('adx_hours_left', 0)
            hrs_s = f' | 趋势 {hrs:.0f}h' if hrs > 0 else ''
            print(f'  ▶ {r["base"]} {dir_cn}')
            print(f'    入场1 {fmt_price(r["entry"])}(20U) → 入场2 {fmt_price(orb_ref)}(30U) {tag}{hrs_s}')
            print(f'    止损 {fmt_price(stop)} | TP1 {fmt_price(target)}')
        print()

    # ── 未通过的原因统计 ──
    total = len(results)
    no_consistency = sum(1 for r in results if not r['consistent'])
    no_adx = sum(1 for r in results if r['consistent'] and r['adx'] < 25)
    no_profit = sum(1 for r in results if r['consistent'] and r['adx'] >= 25 and r['tp1_profit'] < 100)

    print(f'  {dash2}')
    print(f'  过滤统计:')
    print(f'    - 基础通过(R1≥{min_r1}%+OI≥{min_oi/1e6:.1f}M): {total}')
    print(f'    - 方向冲突排除: {no_consistency}')
    print(f'    - ADX<25排除: {no_adx}')
    print(f'    - TP1利润<100%排除: {no_profit}')
    print(f'    - 最终推荐: {len(passed)}')
    print()

    # ── 审判系统验证（复用锁妖塔已拉取的K线数据）──
    try:
        from judge_system.run_judge import run_judge, ensure_detectors_registered
        ensure_detectors_registered()
        # 从扫描结果中提取15m K线数据，避免重复拉取
        coins_data = {}
        for r in results:
            if 'df_15m' in r:
                import pandas as pd
                raw = r['df_15m']
                # raw 是 dict 列表，直接转 DataFrame 即可
                df = pd.DataFrame(raw)
                # 确保需要的列存在
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                if 'timestamp' not in df.columns and 'date' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['date'])
                if 'timestamp' in df.columns:
                    df = df.sort_values('timestamp').reset_index(drop=True)
                coins_data[r['base']] = df
        coin_symbols = [c['base'] for c in coins_list] if coins_list else None
        verdicts, dis_count = run_judge(top_n=top_n, coins=coin_symbols, compare=True, table_only=True,
                                        coins_data=coins_data)

        # ── 综合推荐：锁妖塔 + 审判系统 ──
        if verdicts and passed:
            print(f'  {"=" * 60}')
            print(f'  ★ 综合推荐 Top 3 — 锁妖塔 + 审判系统融合')
            print(f'  {"=" * 60}')

            # 对每个通过的推荐，综合评分
            combined = []
            for r in passed:
                base = r['base']
                v = verdicts.get(base)

                # 锁妖塔评分（归一化到0~1）
                p_score = min(r['adx'] / 50, 1.0) * 0.5 + min(r['tp1_profit'] / 500, 1.0) * 0.5
                p_dir = r['direction']  # 'long' or 'short'

                if v and abs(v.judge_score) > 0.1:
                    # 审判系统有明确信号
                    j_dir = v.judge_direction
                    j_score = abs(v.judge_score)

                    if p_dir == j_dir:
                        # 方向一致 → 强推荐
                        final_score = p_score * 0.4 + j_score * 0.6
                        tag = '✅一致'
                    else:
                        # 方向相反 → 不推荐
                        final_score = -1.0
                        tag = '❌分歧'
                else:
                    # 审判系统无信号，只用锁妖塔
                    final_score = p_score * 0.5
                    tag = '⚪仅锁妖塔'

                combined.append({
                    'base': base,
                    'direction': p_dir,
                    'score': final_score,
                    'tag': tag,
                    'entry': r['entry'],
                    'tp1': r['r1'] if p_dir == 'long' else r['s2'],
                    'adx': r['adx'],
                    'kol': f'{r["m5_long"]}/{r["m5_short"]}',
                })

            # 过滤掉分歧的，按综合评分排序
            valid = [c for c in combined if c['score'] > 0]
            valid.sort(key=lambda x: x['score'], reverse=True)

            for i, c in enumerate(valid[:3], 1):
                dir_arrow = '🟢做多' if c['direction'] == 'long' else '🔴做空'
                print(f'  {i}. {c["base"]:<6} {dir_arrow}  '
                      f'评分={c["score"]:.2f}  ADX={c["adx"]:.0f}  '
                      f'入场={fmt_price(c["entry"])}  TP1={fmt_price(c["tp1"])}  '
                      f'KOL={c["kol"]}  {c["tag"]}')

            disagreements = [c for c in combined if c['score'] < 0]
            if disagreements:
                print(f'  {"-" * 60}')
                print(f'  ⚠️ 分歧排除: {", ".join(c["base"] for c in disagreements)}')

            print(f'  {"=" * 60}')
            print()

            # ── 精准入场方案 ──
            for c in valid[:3]:
                base = c['base']
                # 从 results 里找对应的 OHLC 数据
                r = next((x for x in results if x['base'] == base), None)
                if r and 'df_15m' in r:
                    import pandas as _pd
                    raw = r['df_15m']
                    df = _pd.DataFrame(raw)
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        if col in df.columns:
                            df[col] = _pd.to_numeric(df[col], errors='coerce')
                    if 'timestamp' not in df.columns and 'date' in df.columns:
                        df['timestamp'] = _pd.to_datetime(df['date'])
                    if 'timestamp' in df.columns:
                        df = df.sort_values('timestamp').reset_index(drop=True)

                    from judge_system.entry_planner import plan_entry, print_entry_plan
                    plan = plan_entry(base, c['direction'], c['entry'],
                                      r.get('okx_lev', 20), df)
                    print(f'  --- 精准入场: {base} ---')
                    print_entry_plan(plan)

    except Exception as e:
        print(f'  [审判] 跳过: {e}')
    print()

    # ── 保存 ──
    op = os.path.join(QF, 'daily_picks.json')
    # 去掉 df_15m 字段（只用于审判系统，无需保存到JSON）
    passed_clean = []
    for r in passed:
        clean = {k: v for k, v in r.items() if k != 'df_15m'}
        passed_clean.append(clean)
    json.dump(passed_clean, open(op, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    # 保存Markdown
    md_lines = [
        f'# 锁妖塔每日推荐 — {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'',
        f'## 概览',
        f'- 扫描: {len(coins_list)}币 → 通过: {total} → 最终推荐: {len(passed)}',
        f'- 执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'- 过滤标准: 双周期一致 + ADX≥25 + TP1利润≥100%',
        f'',
    ]
    if short_ok:
        md_lines.append('## 🔴 做空推荐')
        md_lines.append('| # | 币种 | ADX | RSI | 入场价 | 止盈价 | 涨幅% | 杠杆 | TP1利润 | KOL(15m) | KOL(日) | 费率 |')
        md_lines.append('|---|:----:|:---:|:---:|:------:|:------:|:-----:|:----:|:-------:|:-------:|:-------:|:----:|')
        for i, r in enumerate(short_ok[:5], 1):
            t = fmt_target(r, False)
            md_lines.append(f'| {i} | {r["base"]} | {r["adx"]:.1f} | {r["rsi"]:.0f} | {fmt_price(r["entry"])} | {fmt_price(t)} | {r["s2_down"]:+.2f}% | {r["okx_lev"]}x | {r["tp1_profit"]:.0f}% | {r["m5_long"]}/{r["m5_short"]} | {r["daily_long"]}/{r["daily_short"]} | {r["fr_pct"]:+.4f}% |')
    if long_ok:
        md_lines.append('')
        md_lines.append('## 🟢 做多推荐')
        md_lines.append('| # | 币种 | ADX | RSI | 入场价 | 止盈价 | 涨幅% | 杠杆 | TP1利润 | KOL(15m) | KOL(日) | 费率 |')
        md_lines.append('|---|:----:|:---:|:---:|:------:|:------:|:-----:|:----:|:-------:|:-------:|:-------:|:----:|')
        for i, r in enumerate(long_ok[:5], 1):
            t = fmt_target(r, True)
            md_lines.append(f'| {i} | {r["base"]} | {r["adx"]:.1f} | {r["rsi"]:.0f} | {fmt_price(r["entry"])} | {fmt_price(t)} | {r["r1_up"]:+.2f}% | {r["okx_lev"]}x | {r["tp1_profit"]:.0f}% | {r["m5_long"]}/{r["m5_short"]} | {r["daily_long"]}/{r["daily_short"]} | {r["fr_pct"]:+.4f}% |')
    md_path = os.path.join(QF, 'daily_picks.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))

    # 保存Word文档
    try:
        save_to_docx(passed, short_ok, long_ok, results, len(coins_list), len(results), now_str, QF, market_env)
    except Exception as e:
        print(f'  Word生成跳过: {e}')
    print()

    return passed


def save_to_docx(passed, short_ok, long_ok, all_results, total_coins, total_passed, now_str, QF, market_env=''):
    """生成Word交易报告 (横板)"""
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT
    from docx.oxml.ns import qn

    doc = Document()
    
    # 横板
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21.0)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)

    # ── 区块1：报告头 ──
    title = doc.add_heading(f'锁妖塔每日交易报告 {market_env}', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f'生成时间: {now_str}')
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(100, 100, 100)

    doc.add_paragraph()  # 空行

    # 概览
    info = doc.add_paragraph()
    info.add_run(f'扫描币种: {total_coins}个').bold = True
    info.add_run(f'  →  基础通过: {total_passed}个')
    noc = sum(1 for r in passed if not r.get('consistent', True))
    noa = sum(1 for r in passed if r.get('consistent', True) and r.get('adx',0) < 25)
    nop = sum(1 for r in passed if r.get('consistent', True) and r.get('adx',0) >= 25 and r.get('tp1_profit',0) < 100)
    info.add_run(f'  →  最终推荐: {len(passed)}个')

    doc.add_paragraph()

    # ── 通用表格样式 ──
    def set_cell_text(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=8):
        cell.text = ''
        p = cell.paragraphs[0]
        p.alignment = align
        run = p.add_run(str(text))
        run.font.size = Pt(size)
        run.bold = bold
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)

    def add_heading_row(table, headers):
        row = table.rows[0]
        for i, h in enumerate(headers):
            set_cell_text(row.cells[i], h, bold=True, size=9)

    def add_data_row(table, row_idx, values):
        row = table.rows[row_idx]
        for i, v in enumerate(values):
            set_cell_text(row.cells[i], str(v), size=8)

    # ── 区块2：全量排名TOP10 ──
    if all_results:
        ranked = sorted(all_results, key=lambda r: r['m5_avg'])
        doc.add_heading('全量排名 (空←→多)', level=1)
        headers = ['序','币种','方向','强度','方向','小时','位置','RSI','入场价','止盈价','杠杆','TP1利润%','15mKOL','日KOL','偏度']
        n = len(ranked)
        table = doc.add_table(rows=1 + n, cols=len(headers))
        table.style = 'Table Grid'
        add_heading_row(table, headers)
        for i, r in enumerate(ranked):
            is_long = r.get('direction') == 'long'
            d_arrow = '🟢多' if is_long else '🔴空'
            hrs = f'{r["adx_hours_left"]:.0f}h' if r.get("adx_hours_left", 0) > 0 else ''
            pos = fmt_pos(r.get('kc_pos', 0.5))
            target = r['r1'] if is_long else r['s2']
            vals = [i+1, r['base'], d_arrow, f'{r["adx"]:.1f}', r.get('adx_trend',''),
                    hrs, pos, f'{r["rsi"]:.0f}',
                    fmt_price(r['entry']), fmt_price(target),
                    f'{r["okx_lev"]}x', f'{r["tp1_profit"]:.0f}%',
                    f'{r["m5_long"]}/{r["m5_short"]}', f'{r["daily_long"]}/{r["daily_short"]}',
                    f'{r["m5_avg"]:+.2f}']
            add_data_row(table, i+1, vals)
        doc.add_paragraph()

    # ── 图例（列注释） ──
    legend_items = [
        ('序', '排名序号'),
        ('币种', '交易对'),
        ('强度', 'ADX趋势强度，≥25为强趋势'),
        ('方向', '↑增强/↓减弱'),
        ('小时', '预计ADX跌破25的小时数'),
        ('位置', 'Keltner通道位置：🔴上轨上/🟡偏高/🟢中位/🔵偏低/🟣下轨下'),
        ('RSI', '相对强弱指数，>70超买，<30超卖'),
        ('入场价', '当前价格，信号确认时参考'),
        ('止盈价', 'TP1目标价：做多=R1阻力位，做空=S2支撑位'),
        ('杠杆', 'OKX该币种最大允许杠杆'),
        ('TP1利润%', '到TP1的利润=涨幅%×杠杆，≥100%即翻倍'),
        ('15mKOL', '15分钟K线KOL投票：看多人数/看空人数'),
        ('日KOL', '日线KOL投票：看多人数/看空人数'),
    ]

    # ── 做多表格 ──
    if long_ok:
        doc.add_heading('🟢 做多推荐', level=1)
        headers = ['序','币种','强度','方向','小时','位置','RSI','入场1','加仓','止损','止盈','杠杆','TP1利润%','15mKOL','日KOL']
        table = doc.add_table(rows=1 + len(long_ok[:5]), cols=len(headers))
        table.style = 'Table Grid'
        add_heading_row(table, headers)
        for i, r in enumerate(long_ok[:5]):
            hrs = f'{r["adx_hours_left"]:.0f}h' if r.get("adx_hours_left", 0) > 0 else ''
            pos = fmt_pos(r.get('kc_pos', 0.5))
            liq = r['entry'] - (r['entry'] / r['okx_lev'])
            stop = liq + r['entry'] * 0.002
            orb_ref = max(r.get('orb_low', r['entry'] * 0.99), stop + r['entry'] * 0.001)
            vals = [i+1, r['base'], f'{r["adx"]:.1f}', r.get('adx_trend',''), hrs, pos,
                    f'{r["rsi"]:.0f}', fmt_price(r['entry']), fmt_price(orb_ref),
                    fmt_price(stop), fmt_price(r['r1']),
                    f'{r["okx_lev"]}x', f'{r["tp1_profit"]:.0f}%',
                    f'{r["m5_long"]}/{r["m5_short"]}', f'{r["daily_long"]}/{r["daily_short"]}']
            add_data_row(table, i+1, vals)
        doc.add_paragraph()

    # ── 做空表格 ──
    if short_ok:
        doc.add_heading('🔴 做空推荐', level=1)
        headers = ['序','币种','强度','方向','小时','位置','RSI','入场1','加仓','止损','止盈','杠杆','TP1利润%','15mKOL','日KOL']
        table = doc.add_table(rows=1 + len(short_ok[:5]), cols=len(headers))
        table.style = 'Table Grid'
        add_heading_row(table, headers)
        for i, r in enumerate(short_ok[:5]):
            hrs = f'{r["adx_hours_left"]:.0f}h' if r.get("adx_hours_left", 0) > 0 else ''
            pos = fmt_pos(r.get('kc_pos', 0.5))
            liq = r['entry'] + (r['entry'] / r['okx_lev'])
            stop = liq - r['entry'] * 0.002
            orb_ref = min(r.get('orb_high', r['entry'] * 1.01), stop - r['entry'] * 0.001)
            vals = [i+1, r['base'], f'{r["adx"]:.1f}', r.get('adx_trend',''), hrs, pos,
                    f'{r["rsi"]:.0f}', fmt_price(r['entry']), fmt_price(orb_ref),
                    fmt_price(stop), fmt_price(r['s2']),
                    f'{r["okx_lev"]}x', f'{r["tp1_profit"]:.0f}%',
                    f'{r["m5_long"]}/{r["m5_short"]}', f'{r["daily_long"]}/{r["daily_short"]}']
            add_data_row(table, i+1, vals)
        doc.add_paragraph()

    # ── 分批入场参考 ──
    if passed:
        doc.add_heading('分批入场参考', level=1)
        liq_info_added = False
        for i, r in enumerate(passed[:3]):
            is_long = r['direction'] == 'long'
            dir_cn = '做多' if is_long else '做空'
            target = r['r1'] if is_long else r['s2']
            liq = r['entry'] - (r['entry'] / r['okx_lev']) if is_long else r['entry'] + (r['entry'] / r['okx_lev'])
            stop = liq + r['entry'] * 0.002 * (1 if is_long else -1)
            orb_ref = r.get('orb_low', r['entry'] * 0.99) if is_long else r.get('orb_high', r['entry'] * 1.01)
            # 入场2不能超过止损
            if is_long:
                orb_ref = max(orb_ref, stop + r['entry'] * 0.001)
            else:
                orb_ref = min(orb_ref, stop - r['entry'] * 0.001)
            p = doc.add_paragraph()
            p.add_run(f'{i+1}. {r["base"]} {dir_cn}').bold = True
            p.add_run(f'  |  入场1 {fmt_price(r["entry"])}(20U)')
            p.add_run(f'  →  入场2 {fmt_price(orb_ref)}(30U) ORB{"下沿" if is_long else "上沿"}')
            p.add_run(f'  |  止损 {fmt_price(stop)}')
            p.add_run(f'  |  TP1 {fmt_price(target)}')
            hrs = r.get('adx_hours_left', 0)
            if hrs > 0:
                p.add_run(f'  |  趋势预估 {hrs:.0f}h')

    # ── 列注释 ──
    doc.add_paragraph()
    doc.add_heading('列注释说明', level=2)
    for name, desc in legend_items:
        p = doc.add_paragraph()
        p.add_run(f'  {name}：').bold = True
        p.add_run(desc)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)

    # 保存
    docx_path = os.path.join(QF, f'daily_picks_{datetime.now().strftime("%Y-%m-%d_%H%M")}.docx')
    doc.save(docx_path)
    print(f'  已保存: {docx_path}')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--top', type=int, default=50)
    p.add_argument('--min-r1', type=float, default=1.5)
    p.add_argument('--min-oi', type=float, default=600000)
    p.add_argument('--coins', type=str, help='指定币种(逗号分隔)，如 BCH,LPT,UNI')
    a = p.parse_args()
    coins_list = a.coins.split(',') if a.coins else None
    run(top_n=a.top, min_r1=a.min_r1, min_oi=int(a.min_oi), coins=coins_list)
