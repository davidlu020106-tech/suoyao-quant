#!/usr/bin/env python3
"""综合日线+5分钟排行 — 仅列方向一致的币"""
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
    fib = float(row.get('fib_618', c)); bbw = float(row.get('bb_width', 0)); hist = float(row.get('macd_hist', 0))
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


def main():
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 加载交易员profile
    profs = {}
    pd_ = os.path.join(BASE, 'profiles_v2')
    for f in sorted(os.listdir(pd_)):
        if f.endswith('.json'):
            try:
                p = json.load(open(os.path.join(pd_, f), encoding='utf-8'))
                profs[f.replace('.json', '')] = p
            except:
                pass
    reg = CAP_REGISTRY
    rids = set(reg.keys())
    print(f'交易员: {len(profs)} | 因子: {len(reg)}')
    
    # 读取5分钟排行
    path_5m = os.path.join(QF, 'altcoin_5m_kol_ranking.json')
    with open(path_5m, encoding='utf-8') as f:
        m5_data = json.load(f)
    
    targets = [r['base'] for r in m5_data]
    print(f'目标币种: {len(targets)}')
    
    daily_results = {}
    for i, base in enumerate(targets):
        print(f'\n[{i+1}/{len(targets)}] {base} ...', end=' ')
        try:
            sym = f'{base}-USDT'
            r = api_get(f'/api/v5/market/candles?instId={sym}&bar=1D&limit=200')
            raw = r.get('data', [])
            if not raw:
                print('无日线数据')
                continue
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
            
            hh = float(feats['high'].max())
            ll = float(feats['low'].min())
            pv = (hh + ll + cur) / 3
            
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
            
            fs = {}
            for cid in reg:
                try:
                    fs[cid] = cscore(cid, lat, fr, oi, pv)
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
            
            daily_results[base] = {
                'daily_avg': avg, 'daily_long': ln, 'daily_short': sn
            }
            
            dir_s = '🟢多' if avg > 0.01 else ('🔴空' if avg < -0.01 else '⚪中')
            print(f'日线L/S={ln}/{sn} avg={avg:+.3f} ({dir_s})')
            time.sleep(0.3)
        except Exception as e:
            print(f'错: {e}')
            time.sleep(0.3)
    
    # 综合排行
    print(f'\n\n{"="*95}')
    print(f'  ★ 综合排行 — 仅列5分钟+日线方向一致的币')
    print(f'{"="*95}')
    
    combined = []
    for r in m5_data:
        base = r['base']
        if base not in daily_results:
            continue
        dr = daily_results[base]
        m5_avg = r['kol_avg']
        
        daily_bias = 'long' if dr['daily_avg'] > 0.01 else ('short' if dr['daily_avg'] < -0.01 else 'neutral')
        m5_bias = 'long' if m5_avg > 0.01 else ('short' if m5_avg < -0.01 else 'neutral')
        consistent = (daily_bias == m5_bias)
        
        combined.append({
            'base': base,
            'daily_avg': dr['daily_avg'],
            'daily_long': dr['daily_long'],
            'daily_short': dr['daily_short'],
            'm5_avg': m5_avg,
            'm5_long': r['kol_long'],
            'm5_short': r['kol_short'],
            'm5_score': r['score'],
            'daily_bias': daily_bias,
            'm5_bias': m5_bias,
            'consistent': consistent
        })
    
    # 排序：一致的按5分钟偏度绝对值排前面
    consistent_list = [c for c in combined if c['consistent']]
    inconsistent_list = [c for c in combined if not c['consistent']]
    consistent_list.sort(key=lambda c: abs(c['m5_avg']), reverse=True)
    
    header = f"{'#':>3s} {'币种':<7s} {'日线偏度':>9s} {'5m偏度':>9s} {'日线L/S':>10s} {'5m L/S':>10s} {'方向':>6s} {'5m评分':>7s}"
    print(header)
    print('-' * 95)
    
    for i, c in enumerate(consistent_list, 1):
        dir_s = '🟢看多' if c['daily_bias'] == 'long' else '🔴看空'
        print(f"  {i:>2d} {c['base']:<7s} {c['daily_avg']:>+8.3f}  {c['m5_avg']:>+8.3f}  "
              f"{c['daily_long']:>2d}/{c['daily_short']:<2d}      {c['m5_long']:>2d}/{c['m5_short']:<2d}      "
              f"{dir_s:>6s}  {c['m5_score']:.1f}")
    
    print('-' * 95)
    print(f'✅ 方向一致: {len(consistent_list)}个')
    if inconsistent_list:
        print(f'❌ 方向冲突: {len(inconsistent_list)}个 — {" ".join([c["base"] for c in inconsistent_list])}')
    print()
    
    # TOP推荐（从一致性里选）
    if consistent_list:
        short_consistent = [c for c in consistent_list if c['m5_bias'] == 'short']
        long_consistent = [c for c in consistent_list if c['m5_bias'] == 'long']
        
        short_consistent.sort(key=lambda c: c['m5_score'], reverse=True)
        long_consistent.sort(key=lambda c: c['m5_score'], reverse=True)
        
        print(f'{"="*60}')
        print(f'  ★ 综合推荐 (日线+5分钟方向一致)')
        print(f'{"="*60}')
        
        if short_consistent:
            print(f'\n  🔴 做空推荐:')
            for i, c in enumerate(short_consistent[:3], 1):
                print(f'    #{i} {c["base"]:<6s} 日线L/S={c["daily_long"]}/{c["daily_short"]} 5m L/S={c["m5_long"]}/{c["m5_short"]} 评分{c["m5_score"]:.1f}')
        
        if long_consistent:
            print(f'\n  🟢 做多推荐:')
            for i, c in enumerate(long_consistent[:3], 1):
                print(f'    #{i} {c["base"]:<6s} 日线L/S={c["daily_long"]}/{c["daily_short"]} 5m L/S={c["m5_long"]}/{c["m5_short"]} 评分{c["m5_score"]:.1f}')
        
        print()


if __name__ == '__main__':
    main()
