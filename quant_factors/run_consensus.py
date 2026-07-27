#!/usr/bin/env python3
"""Master script: runs the full consensus pipeline end-to-end.

Usage:
    python run_consensus.py [symbol] [--date YYYY-MM-DD] [--no-open]

Default: BTCUSDT, latest date, opens HTML in browser.
"""
import sys, os, json, argparse, subprocess, time
import numpy as np
import pandas as pd

BASE = os.path.expanduser('~/shared/materials/crypto_traders_distill')
QF = f'{BASE}/quant_factors'
sys.path.insert(0, QF)

def step(name):
    print(f'\n{"="*60}\n  {name}\n{"="*60}')

def main():
    parser = argparse.ArgumentParser(description='Consensus Pipeline')
    parser.add_argument('symbol', nargs='?', default='BTCUSDT', help='Symbol (BTCUSDT/ETHUSDT/SOLUSDT/DOGEUSDT)')
    parser.add_argument('--date', default=None, help='Snapshot date (YYYY-MM-DD), default=latest')
    parser.add_argument('--no-open', action='store_true', help='Skip opening HTML in browser')
    parser.add_argument('--refresh-ohlc', action='store_true', help='Re-download OHLC from Binance')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    if not symbol.endswith('USDT'):
        symbol += 'USDT'

    # ============================================================
    # Step 1: Optionally refresh OHLC
    # ============================================================
    if args.refresh_ohlc:
        step('1/6 Refreshing OHLC from Binance')
        import urllib.request
        from datetime import datetime, timezone
        def to_ms(d):
            return int(datetime.strptime(d, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()*1000)
        start = to_ms('2024-01-01')
        end = int(time.time()*1000)
        ohlc = json.load(open(f'{BASE}/ohlc_daily.json'))
        for sym in ['BTCUSDT','ETHUSDT','SOLUSDT','DOGEUSDT']:
            url = f'https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&startTime={start}&endTime={end}&limit=1000'
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=30).read())
            candles = [{'date': time.strftime('%Y-%m-%d', time.gmtime(c[0]/1000)),
                        'open': float(c[1]), 'high': float(c[2]),
                        'low': float(c[3]), 'close': float(c[4])} for c in data]
            ohlc[sym] = candles
            print(f'  {sym}: {len(candles)} candles → {candles[-1]["date"]}')
            time.sleep(0.3)
        # Also refresh macro
        for name, ysym in [('DXY','DX-Y.NYB'),('GOLD','GC=F'),('US2Y','^TNX'),('SPX','^GSPC')]:
            try:
                s = to_ms('2024-01-01')//1000
                e = int(time.time())
                yurl = f'https://query1.finance.yahoo.com/v8/finance/chart/{ysym}?period1={s}&period2={e}&interval=1d'
                req = urllib.request.Request(yurl, headers={'User-Agent':'Mozilla/5.0'})
                result = json.loads(urllib.request.urlopen(req, timeout=30).read())
                r = result['chart']['result'][0]
                ts = r['timestamp']
                q = r['indicators']['quote'][0]
                candles = [{'date': time.strftime('%Y-%m-%d', time.gmtime(t)),
                            'open': q['open'][i], 'high': q['high'][i],
                            'low': q['low'][i], 'close': q['close'][i]}
                           for i, t in enumerate(ts) if q['close'][i] is not None]
                macro = json.load(open(f'{BASE}/macro_daily.json'))
                macro[name] = candles
                with open(f'{BASE}/macro_daily.json','w') as f:
                    json.dump(macro, f, indent=2)
                print(f'  {name}: {len(candles)} candles')
            except Exception as ex:
                print(f'  {name}: skip ({ex})')
            time.sleep(0.3)
        with open(f'{BASE}/ohlc_daily.json','w') as f:
            json.dump(ohlc, f, indent=2)
        print('  OHLC refreshed.')
    else:
        step('1/6 Using cached OHLC (use --refresh-ohlc to update)')

    # ============================================================
    # Step 2: Feature engine
    # ============================================================
    step('2/6 Computing features')
    from feature_engine import build_panel, BASE as FE_BASE
    panel = build_panel()
    panel.to_parquet(f'{QF}/features.parquet')
    print(f'  features: {panel.shape}')

    # ============================================================
    # Step 3: Factor evaluation
    # ============================================================
    step('3/6 Evaluating 87 factors')
    from capabilities import CAP_REGISTRY
    features = pd.read_parquet(f'{QF}/features.parquet')
    factor_cols_set = set()

    def run_factors(feats):
        out = {}
        for cid, meta in CAP_REGISTRY.items():
            try:
                res = meta['fn'](feats)
                score = res.score if hasattr(res,'score') else (res.get('score',0) if isinstance(res,dict) else res)
                if hasattr(score,'__len__') and len(score)==len(feats):
                    out[cid] = np.asarray(score, dtype=float)
                else:
                    out[cid] = np.full(len(feats), float(score) if np.isscalar(score) else 0.0)
            except:
                out[cid] = np.zeros(len(feats))
            factor_cols_set.add(cid)
        return pd.DataFrame(out, index=feats.index)

    all_factors = []
    for sym in features.index.get_level_values(0).unique():
        sub = features.loc[sym].copy()
        fac = run_factors(sub)
        fac['symbol'] = sym
        fac['fwd_1d'] = sub['fwd_ret_1d']
        fac['fwd_7d'] = sub['fwd_ret_7d']
        fac['fwd_30d'] = sub['fwd_ret_30d']
        all_factors.append(fac)
    factors_panel = pd.concat(all_factors)
    factors_panel.to_parquet(f'{QF}/factors.parquet')
    print(f'  factors: {factors_panel.shape}, {len(factor_cols_set)} caps evaluated')

    # ============================================================
    # Step 4: Trader composite
    # ============================================================
    step('4/6 Computing trader composites')
    subprocess.run([sys.executable, f'{QF}/trader_composite.py'], capture_output=True, text=True, timeout=120)
    trader_ic = pd.read_csv(f'{QF}/trader_composite_ic.csv')
    pos = (trader_ic['ic_30d'] > 0).sum()
    neg = (trader_ic['ic_30d'] < 0).sum()
    strong = (trader_ic['ic_30d'].abs() > 0.1).sum()
    print(f'  traders: {len(trader_ic)} | pos IC: {pos} | neg IC: {neg} | |IC|>0.1: {strong}')

    # ============================================================
    # Step 5: Consensus snapshot
    # ============================================================
    step('5/6 Building consensus snapshot')
    subprocess.run([sys.executable, f'{QF}/consensus_now.py'], capture_output=True, text=True, timeout=60)
    snap = json.load(open(f'{QF}/consensus_snapshot.json'))
    cons = snap['consensus']
    eq = cons['equal_weight']
    print(f'  Long: {eq["long"]} | Short: {eq["short"]} | Neutral: {eq["neutral"]}')
    print(f'  Trust-adjusted bias: {cons["trust_adjusted"]:+.3f}')
    print(f'  Firing factors: {len(snap["firing_factors"])}')

    # ============================================================
    # Step 6: Render
    # ============================================================
    step('6/6 Rendering Plotly HTML')
    subprocess.run([sys.executable, f'{QF}/render_consensus.py'], capture_output=True, text=True, timeout=60)
    html_path = f'{QF}/consensus_snapshot.html'
    print(f'  saved {html_path}')
    if not args.no_open:
        subprocess.run(['open', html_path])
        print('  opened in browser')

    # ============================================================
    # Summary
    # ============================================================
    price = snap['btc_price']
    firing = snap['firing_factors']
    longs = [f for f in firing if f['score'] > 0]
    shorts = [f for f in firing if f['score'] < 0]

    print(f'\n{"="*60}')
    print(f'  CONSENSUS SUMMARY — {snap["date"]} @ ${price:,.0f}')
    print(f'{"="*60}')
    print(f'  触发因子: {len(firing)} ({len(longs)} long / {len(shorts)} short)')
    print(f'  99 交易员: L={eq["long"]} S={eq["short"]} N={eq["neutral"]}')
    print(f'  Trust-adjusted bias: {cons["trust_adjusted"]:+.3f}')
    bias_label = '偏空' if cons['trust_adjusted'] < -0.01 else '偏多' if cons['trust_adjusted'] > 0.01 else '中性'
    print(f'  结论: {bias_label}')

    # Top 5 aligned traders
    aligned = sorted(snap['traders'], key=lambda t: -(t.get('ic_30d') or 0))[:5]
    print(f'\n  Top 5 高信任交易员:')
    for t in aligned:
        sig = t['signal_now']
        arrow = '🟢' if sig > 0.03 else '🔴' if sig < -0.03 else '⚪'
        print(f'    {arrow} @{t["handle"][:20]:20s} IC={t["ic_30d"]:+.2f} signal={sig:+.3f}')

    return snap

if __name__ == '__main__':
    main()
