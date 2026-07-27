#!/usr/bin/env python3
"""日线级别 KOL 共识分析（山寨币版）"""
import sys, os, json, urllib.request, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone

QF = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QF)
from capabilities import CAP_REGISTRY
from okx_data_adapter import build_features_single


def api_get(path):
    url = 'https://www.okx.com' + path
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def cscore(cid, row, fr, oi, pv):
    c = float(row['close']); h = float(row['high']); l = float(row['low']); o = float(row['open'])
    ma20 = float(row.get('ma20', c)); ma50 = float(row.get('ma50', c)); ma200 = float(row.get('ma200', c))
    rsi = float(row.get('rsi14', 50)); r1_ = float(row.get('r1', c)); s1_ = float(row.get('s1', c))
    fib = float(row.get('fib_618', c)); bbw = float(row.get('bb_width', 0))
    hist = float(row.get('macd_hist', 0)); rng = h - l; body = abs(c - o)
    
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
    if cid in ['emg_008_w50ema_bull_bear_divider', 'emg_014_horizontal_reclaim']: return 0.4 if c > ma50 else -0.4
    if cid == 'emg_022_200w_mechanical_buy': return 0.5 if c < ma200 * 0.9 else -0.2
    if cid == 'emg_029_200w_value_zone': return 0.5 if c < ma200 * 0.85 else -0.1
    if cid == 'emg_028_20w_200w_double_reclaim': return 0.4 if c > ma200 and c > ma50 else -0.3
    if cid == 'emg_001_quarterly_vwap': return 0.3 if c > pv else -0.3
    if cid == 'cap_037_halving_cycle': return -0.30
    if cid == 'cap_038_4year_cycle': return -0.40
    if cid == 'emg_005_4year_same_day_compare': return -0.25
    if cid == 'emg_006_days_in_tight_range': return 0.1
    if cid == 'emg_023_monthly_seasonality': return 0.1 if datetime.now().month in [10, 11, 12, 1, 2, 3] else -0.1
    if cid in ['cap_023_elliott_wave_3', 'cap_024_wyckoff_accumulation_spring', 'cap_026_smc_order_block_retest']: return 0.3 if c > ma50 else -0.3
    if cid in ['cap_025_wyckoff_distribution_upthrust', 'cap_049_ict_fair_value_gap']: return -0.3 if c < ma50 else 0.3
    if cid in ['cap_001_falling_wedge_breakout', 'cap_003_bull_flag', 'cap_006_inverse_head_shoulders']: return 0.35 if c > ma50 else -0.2
    if cid in ['cap_002_rising_wedge_breakdown', 'cap_004_bear_flag', 'cap_005_head_shoulders_top']: return -0.35 if c < ma50 else 0.2
    if cid in ['cap_012_sfp', 'cap_014_trend_pullback', 'cap_052_liquidity_grab', 'cap_057_fake_breakout', 'emg_013_box_breakout']: return 0.3 if c > ma20 else -0.3
    if cid == 'cap_053_doji': return 0.3 if rng > 0 and body / rng < 0.1 else 0.0
    if cid == 'cap_054_engulfing': return 0.3 if c > o else 0.0
    if cid == 'cap_055_pin_bar':
        uw = h - max(c, o); lw = min(c, o) - l
        if rng > 0 and min(uw, lw) / rng < 0.1 and max(uw, lw) / rng > 0.5:
            return 0.4 if lw > uw else -0.4
        return 0.0
    if cid == 'cap_056_double_needle_bottom': return 0.3 if rsi < 40 else 0.0
    if cid in ['cap_027_dxy_inverse_btc', 'cap_028_spx_risk_on', 'cap_040_etf_flows_proxy']: return 0.1 if c > ma50 else -0.1
    if cid == 'cap_041_dont_catch_falling_knives': return -0.5 if rsi < 30 else 0.0
    if cid == 'cap_043_cut_losses_early': return -0.3 if c < s1_ else 0.0
    if cid == 'emg_009_range_middle_filter':
        pos = (c - s1_) / max(r1_ - s1_, 0.01); return 0.0 if 0.3 < pos < 0.7 else (0.3 if pos < 0.3 else -0.3)
    if cid == 'emg_031_keltner_mean_revert':
        kcu = float(row.get('kc_upper', c)); kcl = float(row.get('kc_lower', c))
        adx14 = float(row.get('adx14', 25))
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


def analyze_daily(base, profs, reg, rids):
    print(f'\n{"="*70}')
    print(f'  ★ 日线级别分析: {base}')
    print(f'{"="*70}')

    sym = f'{base}-USDT'
    r = api_get(f'/api/v5/market/candles?instId={sym}&bar=1D&limit=200')
    raw = r.get('data', [])
    if not raw:
        print(f'  ❌ 无日线数据')
        return

    raw.reverse()
    cdl = []
    for c in raw:
        ts = int(c[0]) / 1000
        cdl.append({'date': datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d'),
                     'open': float(c[1]), 'high': float(c[2]), 'low': float(c[3]),
                     'close': float(c[4]), 'volume': float(c[5])})

    df = pd.DataFrame(cdl)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()

    feats = build_features_single(df)
    lat = feats.iloc[-1]
    cur = float(lat['close'])
    rsi = float(lat.get('rsi14', 50))
    ma50 = float(lat.get('ma50', cur))
    ma200 = float(lat.get('ma200', cur))
    adx = float(lat.get('adx14', 0))

    hh = float(feats['high'].max())
    ll = float(feats['low'].min())
    pv = (hh + ll + cur) / 3
    r1 = 2 * pv - ll
    r2 = pv + (hh - ll)
    s1 = 2 * pv - hh
    s2 = pv - (hh - ll)

    try:
        fr_r = api_get(f'/api/v5/public/funding-rate?instId={base}-USDT-SWAP')
        fr = float(fr_r['data'][0]['fundingRate']) if fr_r.get('code') == '0' and fr_r.get('data') else 0
    except:
        fr = 0
    try:
        oi_r = api_get(f'/api/v5/public/open-interest?instType=SWAP&instId={base}-USDT-SWAP')
        oi = float(oi_r['data'][0]['oi']) if oi_r.get('code') == '0' and oi_r.get('data') else 0
    except:
        oi = 0

    # 技术面总览
    print(f'\n  📊 技术面')
    print(f'  当前价: ${cur:.6f}')
    print(f'  RSI: {rsi:.1f}  |  ADX: {adx:.1f}')
    print(f'  MA50: ${ma50:.4f}  |  MA200: ${ma200:.4f}')
    
    if cur > ma200 and ma50 > ma200:
        print(f'  ✅ 多头主导 + 金叉 = 上升趋势')
    elif cur < ma200 and ma50 < ma200:
        print(f'  ❌ 空头主导 + 死叉 = 下降趋势')
    elif cur > ma200:
        print(f'  ⚠️ 价格在MA200之上但MA50<MA200(反弹中)')
    else:
        print(f'  ⚠️ 价格在MA200之下(熊市反弹或盘整)')
    
    print(f'  阻力: R1=${r1:.4f} (+{(r1/cur-1)*100:.2f}%)')
    print(f'  阻力: R2=${r2:.4f} (+{(r2/cur-1)*100:.2f}%)')
    print(f'  支撑: S1=${s1:.4f}')
    print(f'  支撑: S2=${s2:.4f}')

    print(f'\n  📊 衍生品')
    print(f'  资金费率: {fr*100:+.4f}%')
    print(f'  持仓量: {oi/1000000:.1f}M')
    if oi > 50000000: print(f'  ⚠️ 高持仓量')
    if abs(fr) > 0.001: print(f'  ⚠️ 费率极端({fr*100:+.4f}%) → {"轧空风险" if fr<0 else "多头拥挤"}')

    # KOL投票引擎
    fs = {}
    for cid in reg:
        try: fs[cid] = cscore(cid, lat, fr, oi, pv)
        except: fs[cid] = 0.0

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
    firing = {k: v for k, v in fs.items() if abs(v) > 0.05}
    lf = sum(1 for v in firing.values() if v > 0)
    sf = len(firing) - lf

    # 输出
    print(f'\n  {"="*40}')
    print(f'  ★ KOL 日线共识结果')
    print(f'  {"="*40}')
    print(f'  KOL投票: 🟢做多 {ln}人  |  🔴做空 {sn}人  |  ⚪中性 {nn}人')
    print(f'  偏度: {avg:+.4f}')
    
    if avg > 0.05:
        print(f'  🔵 方向: 强烈看多')
    elif avg > 0.01:
        print(f'  🟢 方向: 偏多')
    elif avg < -0.05:
        print(f'  🔴 方向: 强烈看空')
    elif avg < -0.01:
        print(f'  🔴 方向: 偏空')
    else:
        print(f'  ⚪ 方向: 中性偏多' if avg > 0 else '  ⚪ 方向: 中性偏空')
    
    print(f'  触发因子: {len(firing)}个 ({lf}多 / {sf}空)')
    
    # 列出得分最高的因子
    sorted_firing = sorted(firing.items(), key=lambda x: abs(x[1]), reverse=True)
    print(f'\n  Top 触发因子:')
    for k, v in sorted_firing[:8]:
        arrow = '🟢' if v > 0 else '🔴'
        print(f'    {arrow} {k}: {v:+.2f}')
    
    print(f'\n  🎯 TP1(R1): ${r1:.4f} (+{(r1/cur-1)*100:.2f}%)')
    print(f'  🛑 S2: ${s2:.4f} (-{(1-s2/cur)*100:.2f}%)')
    return True


if __name__ == '__main__':
    # 加载交易员profiles
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prof_dir = os.path.join(BASE, 'profiles_v2')
    profs = {}
    for f in sorted(os.listdir(prof_dir)):
        if f.endswith('.json'):
            try:
                p = json.load(open(os.path.join(prof_dir, f), encoding='utf-8'))
                profs[f.replace('.json', '')] = p
            except:
                pass

    reg = CAP_REGISTRY
    rids = set(reg.keys())

    coins = ['ALLO', 'ORDI']
    for c in coins:
        analyze_daily(c, profs, reg, rids)
        time.sleep(0.5)
