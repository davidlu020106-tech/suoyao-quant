#!/usr/bin/env python3
"""锁妖塔 5分钟山寨币全量分析 — 87因子×99交易员全员参与

用法:
    python run_5m_kol_consensus.py
    python run_5m_kol_consensus.py --top 30
    python run_5m_kol_consensus.py --coins SOL,XRP,DOGE
"""
import sys, os, json, urllib.request, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict

QF = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(QF)
sys.path.insert(0, QF)
sys.path.insert(0, BASE)
from local_config import OKX_API_KEY
from okx_data_adapter import build_features_single

STABLE = {'USDT','USDC','DAI','TUSD','BUSD','FDUSD','USDP',
    'EUR','GBP','AUD','SGD','AED','CNY','JPY','KRW','USDG',
    'TRY','BRL','CAD','CHF','HKD','MXN'}

def api_get(path):
    url = 'https://www.okx.com' + path
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req,timeout=15).read())

def fetch_list(top_n=15):
    r = api_get('/api/v5/market/tickers?instType=SPOT')
    coins = []
    for t in r.get('data',[]):
        inst = t['instId']
        if not inst.endswith('-USDT'): continue
        base = inst.replace('-USDT','')
        if base in STABLE: continue
        v = float(t.get('volCcy24h','0') or 0)
        if v>=500000: coins.append({'base':base,'symbol':inst,'vol':v})
    coins.sort(key=lambda x:x['vol'],reverse=True)
    return coins[:top_n]

def fetch_5m(symbol,limit=200):
    try:
        r = api_get('/api/v5/market/candles?instId='+symbol+'&bar=5m&limit='+str(limit))
        raw = r.get('data',[])
        if not raw: return []
        raw.reverse()
        out = []
        for c in raw:
            ts=int(c[0])/1000; dt=datetime.fromtimestamp(ts,tz=timezone.utc)
            out.append({'date':dt.strftime('%Y-%m-%d %H:%M'),
                'open':float(c[1]),'high':float(c[2]),'low':float(c[3]),
                'close':float(c[4]),'volume':float(c[5])})
        return out
    except Exception as e:
        return []

def fetch_funding_rate(base):
    """Fetch current funding rate for a coin's swap contract."""
    try:
        r = api_get(f'/api/v5/public/funding-rate?instId={base}-USDT-SWAP')
        if r.get('code') == '0' and r.get('data'):
            return float(r['data'][0]['fundingRate'])
    except:
        pass
    return 0.0

def fetch_open_interest(base):
    """Fetch open interest (USD) for a coin's swap contract."""
    try:
        r = api_get(f'/api/v5/public/open-interest?instType=SWAP&instId={base}-USDT-SWAP')
        if r.get('code') == '0' and r.get('data'):
            return float(r['data'][0]['oi'])
    except:
        pass
    return 0.0

def cscore(cid,row):
    c=float(row['close']); h=float(row['high']); l=float(row['low']); o=float(row['open'])
    ma7=float(row.get('ma7',c)); ma20=float(row.get('ma20',c))
    ma50=float(row.get('ma50',c)); ma200=float(row.get('ma200',c))
    rsi=float(row.get('rsi14',50)); r1=float(row.get('r1',c)); r2=float(row.get('r2',c))
    s1=float(row.get('s1',c)); s2=float(row.get('s2',c))
    pivot=float(row.get('pivot',c)); fib=float(row.get('fib_618',c))
    bbw=float(row.get('bb_width',0)); hist=float(row.get('macd_hist',0))
    body=abs(c-o); rng=h-l
    # Regime
    if cid=='cap_044_regime_trending_up': return 0.6 if c>ma50 else -0.4
    if cid=='cap_045_regime_trending_down': return 0.6 if c<ma50 else -0.4
    if cid=='cap_046_regime_ranging': return 0.5 if rng>0 and (h-l)/c<0.005 else 0.0
    if cid=='cap_047_regime_volatile': return 0.6 if rng>0 and (h-l)/c>0.01 else 0.0
    if cid=='cap_070_parabolic_exhaustion': return 0.5 if abs(float(row.get('ret_5d',0)))>0.02 else 0.0
    # Indicators
    if cid=='cap_015_rsi_bullish_divergence': return 0.3 if rsi>50 and c>ma50 else -0.1
    if cid=='cap_016_rsi_bearish_divergence': return -0.3 if rsi<50 and c<ma50 else 0.1
    if cid=='cap_017_rsi_oversold_bounce': return 0.5 if rsi<35 else (0.2 if rsi<45 else 0)
    if cid=='cap_018_ma_golden_cross': return 0.5 if ma50>ma200 else -0.5
    if cid=='cap_019_ma_death_cross': return -0.5 if ma50<ma200 else 0.5
    if cid=='cap_020_macd_histogram_cross': return 0.4 if hist>0 else -0.4
    if cid=='cap_021_bb_squeeze_breakout': return 0.4 if bbw<0.003 else (-0.2 if bbw>0.008 else 0.0)
    if cid=='cap_022_fib_618_support':
        d=abs(c-fib)/c if c>0 else 1; return 0.7 if d<0.01 else (0.3 if d<0.03 else 0.0)
    if cid=='cap_069_moving_average_reclaim': return 0.6 if c>ma200 else -0.6
    if cid in ['emg_008_w50ema_bull_bear_divider','emg_014_horizontal_reclaim']: return 0.4 if c>ma50 else -0.4
    if cid=='emg_022_200w_mechanical_buy': return 0.5 if c<ma200*0.9 else -0.2
    if cid=='emg_029_200w_value_zone': return 0.5 if c<ma200*0.85 else -0.1
    if cid=='emg_028_20w_200w_double_reclaim': return 0.4 if c>ma200 and c>ma50 else -0.3
    if cid=='emg_001_quarterly_vwap': return 0.3 if c>pivot else -0.3
    # Cycle
    if cid=='cap_037_halving_cycle': return -0.30
    if cid=='cap_038_4year_cycle': return -0.40
    if cid=='emg_005_4year_same_day_compare': return -0.25
    if cid=='emg_006_days_in_tight_range': return 0.1
    if cid=='emg_023_monthly_seasonality': return 0.1 if datetime.now().month in [10,11,12,1,2,3] else -0.1
    # Structural
    if cid in ['cap_023_elliott_wave_3','cap_024_wyckoff_accumulation_spring',
               'cap_026_smc_order_block_retest']: return 0.3 if c>ma50 else -0.3
    if cid in ['cap_025_wyckoff_distribution_upthrust','cap_049_ict_fair_value_gap']: return -0.3 if c<ma50 else 0.3
    if cid=='cap_065_btc_dominance_shift': return 0.0
    # Patterns
    if cid in ['cap_001_falling_wedge_breakout','cap_003_bull_flag',
               'cap_006_inverse_head_shoulders']: return 0.35 if c>ma50 else -0.2
    if cid in ['cap_002_rising_wedge_breakdown','cap_004_bear_flag',
               'cap_005_head_shoulders_top']: return -0.35 if c<ma50 else 0.2
    if cid in ['cap_012_sfp','cap_014_trend_pullback','cap_052_liquidity_grab',
               'cap_057_fake_breakout','emg_013_box_breakout']: return 0.3 if c>ma20 else -0.3
    # Candlestick
    if cid=='cap_053_doji': return 0.3 if rng>0 and body/rng<0.1 else 0.0
    if cid=='cap_054_engulfing': return 0.3 if c>o else 0.0
    if cid=='cap_055_pin_bar':
        uw=h-max(c,o); lw=min(c,o)-l
        if rng>0 and min(uw,lw)/rng<0.1 and max(uw,lw)/rng>0.5: return 0.4 if lw>uw else -0.4
        return 0.0
    if cid=='cap_056_double_needle_bottom': return 0.3 if rsi<40 else 0.0
    # Macro proxy
    if cid in ['cap_027_dxy_inverse_btc','cap_028_spx_risk_on','cap_040_etf_flows_proxy']:
        return 0.1 if c>ma50 else -0.1
    # Risk
    if cid=='cap_041_dont_catch_falling_knives': return -0.5 if rsi<30 else 0.0
    if cid=='cap_043_cut_losses_early': return -0.3 if c<s1 else 0.0
    if cid=='emg_009_range_middle_filter':
        pos=(c-s1)/max(r1-s1,0.01); return 0.0 if 0.3<pos<0.7 else (0.3 if pos<0.3 else -0.3)
    # Keltner Channel mean reversion
    if cid=='emg_031_keltner_mean_revert':
        kcu=float(row.get('kc_upper',c)); kcl=float(row.get('kc_lower',c))
        adx14=float(row.get('adx14',25))
        if kcu-kcl<=0: return 0.0
        dist_l=(c-kcl)/(kcu-kcl)  # 0=下轨, 1=上轨
        if adx14<25 and dist_l>0.8: return 0.5   # 震荡+接近下轨→做多
        if adx14<25 and dist_l<0.2: return -0.5  # 震荡+接近上轨→做空
        return 0.0
    # === Derivatives (live OKX data) ===
    fr=float(row.get('funding_rate',0))
    oi=float(row.get('open_interest',0))
    if cid=='cap_031_funding_extreme_neg':
        if fr<-0.001: return 0.8     # 年化-36%, 极度负费率→轧空
        if fr<-0.0005: return 0.6    # 年化-18%
        if fr<-0.0001: return 0.3
        return 0.0
    if cid=='cap_032_funding_extreme_pos':
        if fr>0.001: return -0.8     # 极度正费率→多头拥挤
        if fr>0.0005: return -0.6
        if fr>0.0001: return -0.3
        return 0.0
    if cid=='cap_033_oi_climb':
        if oi>50_000_000: return 0.4   # 持仓量大=市场活跃
        if oi>10_000_000: return 0.25
        if oi>1_000_000: return 0.1
        return 0.0
    if cid=='cap_059_funding_divergence':
        # 价格跌但费率仍正→潜在反弹; 价格涨但费率负→潜在回调
        if fr>0.0005 and rsi<40: return 0.5    # 跌+费率正=分歧做多
        if fr<-0.0005 and rsi>60: return -0.5  # 涨+费率负=分歧做空
        return 0.0
    return 0.0

def match_cap(pid,rids):
    if pid in rids: return pid
    parts=pid.split('_')
    if len(parts)>=2 and parts[0]=='cap' and parts[1].isdigit():
        p='cap_'+parts[1]; m=[c for c in rids if c.startswith(p+'_')]
        return m[0] if m else None
    return None

def analyze(feats,reg,rids,profs,name):
    if feats is None or len(feats)<20: return None
    lat=feats.iloc[-1]; cur=float(lat['close'])
    hh=float(feats['high'].max()); ll=float(feats['low'].min())
    pv=(hh+ll+cur)/3; r1=2*pv-ll; r2=pv+(hh-ll); s1=2*pv-hh; s2=pv-(hh-ll)
    r1u=(r1-cur)/cur*100; r2u=(r2-cur)/cur*100; s2d=(cur-s2)/cur*100
    ml=min(125,cur/(cur-s2)) if cur>s2 else 1; rr=r1u/s2d if s2d>0 else 0
    rsi=float(lat.get('rsi14',50))
    score_long=0
    if rsi<35: score_long+=3
    elif rsi<45: score_long+=2
    elif rsi<55: score_long+=1
    if float(lat.get('price_above_ma50',0)): score_long+=1.5
    if float(lat.get('price_above_ma200',0)): score_long+=1
    if r1u>3: score_long+=1.5
    elif r1u>1.5: score_long+=0.5
    score_long=min(10,max(0,score_long))
    
    score_short=0
    if rsi>65: score_short+=3
    elif rsi>55: score_short+=2
    elif rsi>45: score_short+=1
    if not float(lat.get('price_above_ma50',1)): score_short+=1.5
    if not float(lat.get('price_above_ma200',1)): score_short+=1
    if s2d>3: score_short+=1.5
    elif s2d>1.5: score_short+=0.5
    score_short=min(10,max(0,score_short))

    fs={}
    for cid,meta in reg.items():
        try: fs[cid]=cscore(cid,lat)
        except: fs[cid]=0.0

    tsigs=[]
    for h,p in profs.items():
        tw,ws=0.0,0.0
        for cap in (p.get('capabilities_used',[]) or []):
            rid=cap.get('id',''); w=float(cap.get('weight',0))
            mid=match_cap(rid,rids)
            if mid:
                s=fs.get(mid,0)
                if s!=0: ws+=w*s; tw+=abs(w)
        if tw>0: sig=ws/tw
        else:
            b=p.get('bias_default','neutral')
            sig=0.15 if b=='long_tilted' else (-0.15 if b=='short_tilted' else 0.0)
        tsigs.append(sig)

    arr=np.array(tsigs)
    ln=int(np.sum(arr>0.03)); sn=int(np.sum(arr<-0.03)); nn=len(arr)-ln-sn
    av=float(np.mean(arr))
    firing={k:v for k,v in fs.items() if abs(v)>0.05}
    lf=sum(1 for v in firing.values() if v>0); sf=len(firing)-lf
    return {'base':name,'entry':cur,'r1':r1,'r2':r2,'s1':s1,'s2':s2,
        'r1_up':r1u,'r2_up':r2u,'s2_down':s2d,'max_lev':ml,'rr':rr,
        'score':score_long,'score_short':score_short,'rsi':rsi,'kol_long':ln,'kol_short':sn,'kol_neutral':nn,
        'kol_avg':av,'firing_total':len(firing)}

def run(top_n=15,coins=None,min_r1=2.0,min_oi=600000):
    print(); print('  Suoyao 5m Altcoin Analysis'); print('  ========================');
    print(f'  {87} factors x {99} traders x 5m')
    print(f'  Min R1 filter: >= {min_r1}%')
    print(f'  Min OI filter: >= {min_oi/1000000:.1f}M')

    from capabilities import CAP_REGISTRY
    reg=CAP_REGISTRY; rids=set(reg.keys())
    print(f'  Factors: {len(reg)} loaded')

    profs={}; pd_=os.path.join(BASE,'profiles_v2')
    for f in sorted(os.listdir(pd_)):
        if f.endswith('.json'):
            try:
                p=json.load(open(os.path.join(pd_,f),encoding='utf-8'))
                profs[f.replace('.json','')]=p
            except: pass
    print(f'  Traders: {len(profs)} loaded')

    if coins:
        if isinstance(coins, str):
            cl=[c.strip().upper() for c in coins.split(',')]
        else:
            cl=[c.upper() for c in coins]
        alt=[{'base':c,'symbol':c+'-USDT'} for c in cl]
    else: alt=fetch_list(top_n)
    
    # Fetch OKX max leverage for each coin from SWAP instruments
    okx_lev = {}
    try:
        inst_resp = api_get('/api/v5/public/instruments?instType=SWAP')
        if inst_resp.get('code') == '0':
            for d in inst_resp.get('data', []):
                inst = d['instId']
                if inst.endswith('-USDT-SWAP'):
                    base = inst.replace('-USDT-SWAP', '')
                    okx_lev[base] = int(d.get('lever', 20))
    except:
        pass
    
    print(f'  Coins: {len(alt)}')
    print()

    results=[]
    for i,coin in enumerate(alt):
        base=coin['base']; sym=coin.get('symbol',base+'-USDT')
        cdl=fetch_5m(sym,200)
        if len(cdl)<20:
            print(f'  [{i+1}/{len(alt)}] {base:<10s} skip')
            continue
        df=pd.DataFrame(cdl); df['date']=pd.to_datetime(df['date'])
        df=df.set_index('date').sort_index(); feats=build_features_single(df)
        # Inject derivatives data for factor evaluation
        feats['funding_rate'] = fetch_funding_rate(base)
        feats['open_interest'] = fetch_open_interest(base)
        r=analyze(feats,reg,rids,profs,base)
        if r:
            r['okx_lev'] = okx_lev.get(base, 20)
            # Calculate ADX
            try:
                from capabilities.patterns import np
                closes_arr = np.array([c['close'] for c in cdl])
                highs_arr = np.array([c['high'] for c in cdl])
                lows_arr = np.array([c['low'] for c in cdl])
                from smc_entry_signal import calc_adx
                adx_val, _ = calc_adx(closes_arr, highs_arr, lows_arr, 14)
                r['adx'] = adx_val
            except:
                r['adx'] = 0
            # Calculate ORB range (last 12 candles before current)
            if len(cdl) >= 14:
                orb_candles = cdl[-13:-1]  # last 12 candles (exclude current)
                r['orb_high'] = max(c['high'] for c in orb_candles)
                r['orb_low'] = min(c['low'] for c in orb_candles)
                recent_vols = [c['volume'] for c in cdl[-20:-1]]
                avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
                current_vol = cdl[-1]['volume']
                r['orb_vol_ratio'] = round(current_vol / avg_vol, 1) if avg_vol > 0 else 0
                # ORB trigger signal
                ent = r['entry']
                if ent <= r['orb_low'] * 1.002 and r['orb_vol_ratio'] >= 1.5:
                    r['orb_signal'] = 'short'
                elif ent >= r['orb_high'] * 0.998 and r['orb_vol_ratio'] >= 1.5:
                    r['orb_signal'] = 'long'
                else:
                    r['orb_signal'] = ''
            else:
                r['orb_high'] = r['orb_low'] = r['entry']
                r['orb_vol_ratio'] = 0
                r['orb_signal'] = ''
            # Donchian Channel (20-period high/low for stop/exit reference)
            if len(cdl) >= 21:
                dc_candles = cdl[-21:-1]
                r['dc_high'] = max(c['high'] for c in dc_candles)
                r['dc_low'] = min(c['low'] for c in dc_candles)
            else:
                r['dc_high'] = r['dc_low'] = r['entry']
            # Derivatives raw data (already in feats for scoring)
            r['funding_rate'] = round(float(feats['funding_rate'].iloc[-1]), 8)
            r['open_interest'] = round(float(feats['open_interest'].iloc[-1]), 2)
            # Keltner Channel + Market State + ATR
            r['kc_upper'] = round(float(feats['kc_upper'].iloc[-1]), 8)
            r['kc_lower'] = round(float(feats['kc_lower'].iloc[-1]), 8)
            r['kc_mid'] = round(float(feats['kc_mid'].iloc[-1]), 8)
            r['atr14_val'] = round(float(feats['atr14'].iloc[-1]), 8)
            adx_v = r.get('adx', 0)
            if adx_v >= 25: r['market_state'] = '趋势'
            elif adx_v >= 12: r['market_state'] = '过渡'
            else: r['market_state'] = '震荡'
            # === TP1 Feasibility Check (uses OKX max leverage per coin) ===
            USER_LEV = r.get('okx_lev', 50)  # OKX allots max leverage per coin
            tp1_pct = 100.0 / USER_LEV
            liq_ratio = abs(r.get('max_lev', 1))
            safe_lev = (USER_LEV <= liq_ratio)
            # ATR daily equivalent
            atr_val = r.get('atr14_val', 0)
            entry = r['entry']
            if entry > 0 and atr_val > 0:
                atr_daily_pct = (atr_val / entry * 100) * 288 * 0.7
                days_to_tp1 = tp1_pct / atr_daily_pct if atr_daily_pct > 0 else 999
            else:
                atr_daily_pct = 0
                days_to_tp1 = 999
            # Composite score (0-10)
            score_fea = 0
            if safe_lev: score_fea += 4
            score_fea += max(0, min(3, int(3 - (days_to_tp1 - 1))))  # <=1d=3, 2d=2, 3d=1, >4d=0
            if adx_v >= 25: score_fea += 3
            elif adx_v >= 12: score_fea += 1
            r['tp1_score'] = score_fea
            r['tp1_pass'] = score_fea >= 5
            r['tp1_days'] = round(days_to_tp1, 1) if days_to_tp1 < 999 else 99
            r['tp1_ratio'] = round(liq_ratio / USER_LEV, 1) if liq_ratio > 0 else 0
            results.append(r)
            out_score=r['score']; out_r1u=r['r1_up']; out_r2u=r['r2_up']
            out_ml=r.get('okx_lev', 20); out_kl=r['kol_long']; out_ks=r['kol_short']; out_kn=r['kol_neutral']
            out_fr=r.get('funding_rate',0); out_oi=r.get('open_interest',0)
            print(f'  [{i+1}/{len(alt)}] {base:<10s} score={out_score:.1f} R1=+{out_r1u:.2f}% R2=+{out_r2u:.2f}% lev={out_ml:.0f}x  KOL: L={out_kl} S={out_ks} N={out_kn}  fr={out_fr:+.5%} OI={out_oi:.0f}')
        time.sleep(0.1)

    if not results: print('No results'); return
    results.sort(key=lambda r: (r['score']*2+r['r1_up']*1.5+r['rr']*10),reverse=True)
    
    # 过滤低波动+低流动性币种
    raw_total=len(results)
    results=[r for r in results if r['r1_up']>=min_r1]
    dropped=raw_total-len(results)
    print(f'  Filter: {dropped} low-vol coins removed (R1<{min_r1}%), {len(results)} remain')
    raw_total=len(results)
    results=[r for r in results if r.get('open_interest',0)>=min_oi]
    dropped2=raw_total-len(results)
    print(f'  Filter: {dropped2} low-liq coins removed (OI<{min_oi/1000000:.1f}M), {len(results)} remain')
    print()
    if not results: print('No coins pass filter'); return

    print()
    
    # Split into short/long groups
    shorts = [r for r in results if r['kol_avg'] < -0.01]
    longs  = [r for r in results if r['kol_avg'] > 0.01]
    neuts  = [r for r in results if -0.01 <= r['kol_avg'] <= 0.01]
    
    # Sort each group by score
    shorts.sort(key=lambda r: (r['score_short']*2+r['r1_up']*1.5+r['rr']*10+r.get('tp1_score',0)*3), reverse=True)
    longs.sort(key=lambda r: (r['score']*2+r['r1_up']*1.5+r['rr']*10+r.get('tp1_score',0)*3), reverse=True)
    
    def fmt_price(ent):
        if ent > 10: return '${:.2f}'.format(ent)
        elif ent > 1: return '${:.4f}'.format(ent)
        else: return '${:.6f}'.format(ent)
    
    USER_LEV = 20  # User's fixed leverage
    
    def fmt_orb(high, low, ent):
        """Compact ORB range string"""
        if ent > 10:
            return f'${low:.1f}-{high:.1f}'
        elif ent > 1:
            return f'${low:.2f}-{high:.2f}'
        elif ent > 0.01:
            return f'${low:.4f}-{high:.4f}'
        else:
            return f'${low:.6f}-{high:.6f}'
    
    # === SHORT RANKING ===
    W = 133  # table width
    print()
    print('=' * W)
    print('  SHORT RANKING')
    print('=' * W)
    hdr_fmt = '{:>3s} {:<7s} {:>6s} {:>4s} {:>10s} {:>16s} {:>6s} {:>9s} {:>5s} {:>5s} {:>5s} {:>8s}'
    row_fmt = '{:>3d} {:<7s} {:>6s} {:>4s} {:>10s} {:>16s} {:>6s} {:>9s} {:>5s} {:>5s} {:>5s} {:>8s}'
    print(hdr_fmt.format('#', 'Symbol', 'KOL', 'Scr', 'Entry', 'ORB区间', '状态', 'Fee%', 'ADX', 'RSI', 'TP1', 'Act'))
    print('-' * W)
    for i, r in enumerate(shorts[:10], 1):
        b = r['base']; ent = r['entry']; sc = r['score_short']
        kl = r['kol_long']; ks = r['kol_short']
        rsi_v = r['rsi']; adx_v = r.get('adx', 0)
        orb_str = fmt_orb(r.get('orb_high', ent), r.get('orb_low', ent), ent)
        fr_pct = r.get('funding_rate', 0) * 100
        state = r.get('market_state', '')
        # Action: Keltner reversal for震荡, ORB for趋势/过渡
        kcu = r.get('kc_upper', ent); kcl = r.get('kc_lower', ent)
        kc_range = kcu - kcl
        if kc_range > 0:
            kc_pos = (ent - kcl) / kc_range  # 0=下轨, 1=上轨
        else:
            kc_pos = 0.5
        rsi_ok = rsi_v < 60 and rsi_v > 30
        if state == '震荡':
            # Keltner reversal signals in ranging market
            if kc_pos > 0.8 and rsi_v > 55 and ks > 50:
                action = '~SHT'  # Keltner反转做空
            else:
                action = 'WATCH'
        else:
            # ORB breakout signals in trending/transition market
            can_enter = (r.get('orb_signal', '') == 'short' and ks > 60 and sc >= 3.0 and rsi_ok)
            if ks > 60 and sc >= 3.0:
                if rsi_v < 30:
                    action = 'WATCH'
                else:
                    action = ' SHT' if not can_enter else '>>SHT'
            else:
                action = 'WATCH'
        tp1_s = r.get('tp1_score', 0)
        tp1_tag = 'OK' if tp1_s >= 5 else ('~~' if tp1_s >= 3 else 'NO')
        print(row_fmt.format(i, b, '{}/{}'.format(kl, ks), '{:.1f}'.format(sc),
                         fmt_price(ent), orb_str, state, '{:+.4f}%'.format(fr_pct),
                         '{:.1f}'.format(adx_v), '{:.1f}'.format(rsi_v), tp1_tag, action))
    
    print()
    print('=' * W)
    print('  LONG RANKING')
    print('=' * W)
    print(hdr_fmt.format('#', 'Symbol', 'KOL', 'Scr', 'Entry', 'ORB区间', '状态', 'Fee%', 'ADX', 'RSI', 'TP1', 'Act'))
    print('-' * W)
    for i, r in enumerate(longs[:10], 1):
        b = r['base']; ent = r['entry']; sc = r['score']
        kl = r['kol_long']; ks = r['kol_short']
        rsi_v = r['rsi']; adx_v = r.get('adx', 0)
        orb_str = fmt_orb(r.get('orb_high', ent), r.get('orb_low', ent), ent)
        fr_pct = r.get('funding_rate', 0) * 100
        state = r.get('market_state', '')
        # Action: Keltner reversal for震荡, ORB for趋势/过渡
        kcu = r.get('kc_upper', ent); kcl = r.get('kc_lower', ent)
        kc_range = kcu - kcl
        if kc_range > 0:
            kc_pos = (ent - kcl) / kc_range
        else:
            kc_pos = 0.5
        rsi_ok = rsi_v < 70 and rsi_v > 30
        if state == '震荡':
            # Keltner reversal signals in ranging market
            if kc_pos < 0.2 and rsi_v < 45 and kl > 50:
                action = '~LNG'  # Keltner反转做多
            else:
                action = 'WATCH'
        else:
            # ORB breakout signals in trending/transition market
            can_enter = (r.get('orb_signal', '') == 'long' and kl > 50 and sc >= 3.0 and rsi_ok)
            if kl > 50 and rsi_v > 40 and sc >= 3.0:
                if rsi_v > 70:
                    action = 'WATCH'
                else:
                    action = ' LNG' if not can_enter else '>>LNG'
            else:
                action = 'WATCH'
        tp1_s = r.get('tp1_score', 0)
        tp1_tag = 'OK' if tp1_s >= 5 else ('~~' if tp1_s >= 3 else 'NO')
        print(row_fmt.format(i, b, '{}/{}'.format(kl, ks), '{:.1f}'.format(sc),
                         fmt_price(ent), orb_str, state, '{:+.4f}%'.format(fr_pct),
                         '{:.1f}'.format(adx_v), '{:.1f}'.format(rsi_v), tp1_tag, action))
    print()
    
    print()
    
    # === Stop Loss Reference Helper ===
    def sl_ref(r, d):
        """Format multi-level stop loss reference."""
        ent = r['entry']
        if d == 'short':
            tight = r.get('orb_high', ent)   # 紧: ORB上沿(涨破=失败)
            mid_sl = r.get('kc_upper', ent)  # 中: Keltner上轨
            atr = r.get('atr14_val', 0)
            wide = ent + atr * 1.0 if atr > 0 else ent * 1.02
            dc_low = r.get('dc_low', ent)
            dc_high = r.get('dc_high', ent)
        else:
            tight = r.get('orb_low', ent)    # 紧: ORB下沿(跌破=失败)
            mid_sl = r.get('kc_lower', ent)  # 中: Keltner下轨
            atr = r.get('atr14_val', 0)
            wide = ent - atr * 1.0 if atr > 0 else ent * 0.98
            dc_low = r.get('dc_low', ent)
            dc_high = r.get('dc_high', ent)
        return f'紧{fmt_price(tight)} 中{fmt_price(mid_sl)} 宽{fmt_price(wide)}  DC{fmt_price(dc_low)}-{fmt_price(dc_high)}'
    
    # === 今日推荐 (TOP 3短 + TOP 3多, 含详细理由) ===
    def detail_reason(r, d):
        """Return a one-line reason string."""
        b = r['base']; kl = r['kol_long']; ks = r['kol_short']
        adx_v = r.get('adx', 0); state = r.get('market_state', '')
        fr_pct = r.get('funding_rate', 0) * 100
        tp1_s = r.get('tp1_score', 0); rsi_v = r['rsi']
        if d == 'short':
            consensus = f'{kl}/{ks}看空'
            kol_pct = ks / (kl + ks + r.get('kol_neutral', 1)) * 100
        else:
            consensus = f'{kl}/{ks}看多'
            kol_pct = kl / (kl + ks + r.get('kol_neutral', 1)) * 100
        parts = []
        if kol_pct > 70: parts.append(f'KOL强共识({consensus})')
        elif kol_pct > 55: parts.append(f'KOL偏{consensus}')
        if adx_v >= 25: parts.append(f'趋势确认(ADX={adx_v:.0f})')
        elif adx_v >= 12: parts.append(f'过渡(ADX={adx_v:.0f})')
        else: parts.append(f'震荡(ADX={adx_v:.0f})')
        if tp1_s >= 7: parts.append('TP1优秀')
        elif tp1_s >= 5: parts.append('TP1可行')
        else: parts.append('TP1边界')
        if abs(fr_pct) > 0.03: parts.append(f'费率{fr_pct:+.3f}%*')
        if rsi_v > 70: parts.append(f'RSI超买{rsi_v:.0f}')
        elif rsi_v < 30: parts.append(f'RSI超卖{rsi_v:.0f}')
        return ' | '.join(parts)
    
    print()
    print('=' * 70)
    print('  == 今日推荐  ==')
    print('=' * 70)
    if shorts:
        print()
        print('  [做空]')
        for i, r in enumerate(shorts[:3], 1):
            b = r['base']; ent = r['entry']; sc = r['score_short']
            kl = r['kol_long']; ks = r['kol_short']
            r1v = r['r1']; s2v = r['s2']
            ref_str = sl_ref(r, 'short')
            tp1_s = r.get('tp1_score', 0)
            tp1_tag = 'OK' if tp1_s >= 5 else ('~~' if tp1_s >= 3 else 'NO')
            reason = detail_reason(r, 'short')
            print(f'  #{i} {b:<7s} | KOL {kl}/{ks} 评分{sc:.1f} | TP1:{tp1_tag}')
            print(f'    入场{fmt_price(ent)}  TP1{fmt_price(s2v)}  TP2{fmt_price(2*s2v-r1v)}  保本{fmt_price(ent)}')
            print(f'    止损: {ref_str}')
            print(f'    理由: {reason}')
    
    if longs:
        print()
        print('  [做多]')
        for i, r in enumerate(longs[:3], 1):
            b = r['base']; ent = r['entry']; sc = r['score']
            kl = r['kol_long']; ks = r['kol_short']
            r1v = r['r1']; r2v = r.get('r2', r1v*1.03)
            ref_str = sl_ref(r, 'long')
            tp1_s = r.get('tp1_score', 0)
            tp1_tag = 'OK' if tp1_s >= 5 else ('~~' if tp1_s >= 3 else 'NO')
            reason = detail_reason(r, 'long')
            print(f'  #{i} {b:<7s} | KOL {kl}/{ks} 评分{sc:.1f} | TP1:{tp1_tag}')
            print(f'    入场{fmt_price(ent)}  TP1{fmt_price(r1v)}  TP2{fmt_price(r2v)}  保本{fmt_price(ent)}')
            print(f'    止损: {ref_str}')
            print(f'    理由: {reason}')
    print()
    
    print()
    
    # Auto-run entry timing analysis for top 3 short + top 3 long
    print('=' * 60)
    print('  入场时机分析 (做空TOP3 + 做多TOP3) - ORB+VWAP模式')
    print('=' * 60)
    try:
        from entry_timing import 综合分析 as 入场分析
        for group_name, group in [('做空', shorts[:3]), ('做多', longs[:3])]:
            for r in group:
                b = r['base']
                result = 入场分析(f'{b}-USDT', group_name, 'both')
                if result:
                    sig = result.get('信号', '等待')
                    entry_px = result.get('入场价', 0)
                    reason = result.get('原因', '')
                    print(f'\n  {group_name}分析: {b}')
                    print(f'  ├ 信号: {sig}')
                    if entry_px: print(f'  ├ 建议入场价: ${entry_px:.4f}')
                    print(f'  └ 原因: {reason}')
                    if result.get('ORB'):
                        o = result['ORB']
                        print(f'     ORB区间: ${o.get("区间上沿",0):.4f}-${o.get("区间下沿",0):.4f} | 量{o.get("放量比",0):.1f}x')
                    if result.get('VWAP'):
                        v = result['VWAP']
                        print(f'     VWAP: ${v.get("VWAP",0):.4f} 当前价${v.get("当前价",0):.4f} RSI:{v.get("RSI",0)}')
    except Exception as e:
        print(f'  入场分析跳过: {e}')
    print()

    out=[]
    for r in results:
        out.append({k:round(float(v),4) if isinstance(v,(float,np.floating)) else v for k,v in r.items()})
    op=os.path.join(QF,'altcoin_5m_kol_ranking.json')
    json.dump(out,open(op,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    total=len(results)
    print(f'Saved: {op}')
    print(f'Total: {total} coins x {87}factor x {99}trader = {87*99*total} evaluations')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--top',type=int,default=15)
    p.add_argument('--coins',type=str); p.add_argument('--min-r1',type=float,default=2.0,help='Min R1%% filter')
    p.add_argument('--min-oi',type=float,default=600000,help='Min open interest filter (default 600K)')
    a=p.parse_args(); c=a.coins.split(',') if a.coins else None
    run(top_n=a.top,coins=c,min_r1=a.min_r1,min_oi=int(a.min_oi))
