#!/usr/bin/env python3
"""OKX Data Adapter — bridges OKX exchange data into the kol-quant pipeline.

Uses raw HTTP requests (bypasses ccxt which has OKX compatibility issues).

Provides:
  1. fetch_altcoin_list(top_n=30) — get top-N active USDT altcoins by 24h volume
  2. fetch_ohlc(symbol, bar, limit) — get candlestick data via OKX REST API
  3. fetch_all_altcoins_ohlc(altcoins, bar, limit) — batch fetch
  4. build_features_single(df) — compute technical features (mirrors feature_engine)
  5. build_altcoin_panel(top_n, lookback_days) — complete pipeline
  6. save_as_ohlc_json() — save in ohlc_daily.json compatible format
"""
import sys, os, json, time, urllib.request, hashlib, base64, hmac
from datetime import datetime, timezone

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_config import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, BASE

# ──────────────────────────────────────────────
# Core HTTP helpers
# ──────────────────────────────────────────────
def _api_get(path):
    """Make a public GET request to OKX REST API."""
    url = f'https://www.okx.com{path}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f'[OKX] HTTP {e.code} for {path[:60]}')
        return {'code': str(e.code), 'data': []}
    except Exception as e:
        print(f'[OKX] Request error for {path[:60]}: {e}')
        return {'code': '-1', 'data': []}


def _api_signed_get(path):
    """Make a signed GET request to OKX REST API (for private/account endpoints).

    OKX v5 API authentication: HMAC-SHA256 signature.
    """
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    method = 'GET'
    msg = timestamp + method + path
    mac = hmac.new(OKX_SECRET_KEY.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256)
    sign = base64.b64encode(mac.digest()).decode()

    url = f'https://www.okx.com{path}'
    req = urllib.request.Request(url, headers={
        'OK-ACCESS-KEY': OKX_API_KEY,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': OKX_PASSPHRASE,
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:200]
        print(f'[OKX] Signed HTTP {e.code} for {path[:60]}: {body}')
        return {'code': str(e.code), 'data': [], 'msg': body}
    except Exception as e:
        print(f'[OKX] Signed request error for {path[:60]}: {e}')
        return {'code': '-1', 'data': []}


# ──────────────────────────────────────────────
# Account queries (signed endpoints)
# ──────────────────────────────────────────────
def fetch_balance(ccy=None):
    """Query account balance for all currencies or a specific one.

    Args:
        ccy: optional currency code e.g. 'USDT' (None = all currencies)

    Returns:
        dict with total_eq (float) and details (list of {ccy, eq, availBal, frozenBal})
    """
    path = '/api/v5/account/balance'
    if ccy:
        path += f'?ccy={ccy}'
    resp = _api_signed_get(path)
    if resp.get('code') != '0':
        print(f'[OKX] Balance query failed: {resp.get("msg", "unknown")}')
        return {'total_eq': 0, 'details': []}

    data = resp.get('data', [])
    if not data:
        return {'total_eq': 0, 'details': []}

    total_eq = float(data[0].get('totalEq', 0))
    details = []
    for d in data[0].get('details', []):
        details.append({
            'ccy': d.get('ccy', ''),
            'eq': float(d.get('eq', 0)),
            'avail_bal': float(d.get('availBal', 0)),
            'frozen_bal': float(d.get('frozenBal', 0)),
        })

    return {'total_eq': total_eq, 'details': details}


def fetch_positions(inst_type='SWAP', inst_id=None):
    """Query current open positions.

    Args:
        inst_type: 'SWAP' (永续合约), 'FUTURES', 'MARGIN', 'ANY'
        inst_id: optional instrument ID e.g. 'EDGE-USDT-SWAP'

    Returns:
        list of position dicts
    """
    path = f'/api/v5/account/positions?instType={inst_type}'
    if inst_id:
        path += f'&instId={inst_id}'
    resp = _api_signed_get(path)
    if resp.get('code') != '0':
        print(f'[OKX] Positions query failed: {resp.get("msg", "unknown")}')
        return []

    positions = []
    for p in resp.get('data', []):
        pos = float(p.get('pos', 0))
        if pos == 0:
            continue
        positions.append({
            'inst_id': p.get('instId', ''),
            'inst_type': p.get('instType', ''),
            'direction': p.get('posSide', '').upper(),
            'size': abs(pos),
            'entry_px': float(p.get('avgPx', 0)),
            'mark_px': float(p.get('markPx', 0)),
            'liq_px': float(p.get('liqPx', 0)),
            'upl': float(p.get('upl', 0)),
            'upl_ratio': float(p.get('uplRatio', 0)),
            'margin': float(p.get('margin', 0)),
            'lever': float(p.get('lever', 0)),
            'ccy': p.get('ccy', ''),
        })

    return positions


def fetch_trade_history(inst_id=None, limit=50):
    """Query recent filled orders (trade history).

    Uses OKX /api/v5/trade/fills which covers the last 3 days.

    Args:
        inst_id: optional instrument ID e.g. 'EDGE-USDT-SWAP' (None = all)
        limit: max records to return (max 100)

    Returns:
        list of trade dicts sorted by time descending
    """
    path = f'/api/v5/trade/fills?limit={limit}'
    if inst_id:
        path += f'&instId={inst_id}'
    resp = _api_signed_get(path)
    if resp.get('code') != '0':
        print(f'[OKX] Trade history query failed: {resp.get("msg", "unknown")}')
        return []

    trades = []
    for t in resp.get('data', []):
        trades.append({
            'inst_id': t.get('instId', ''),
            'trade_id': t.get('tradeId', ''),
            'side': t.get('side', '').upper(),  # BUY or SELL
            'pos_side': t.get('posSide', '').upper(),  # LONG or SHORT (for derivatives)
            'fill_px': float(t.get('fillPx', 0)),
            'fill_sz': float(t.get('fillSz', 0)),
            'fill_time': t.get('fillTime', ''),
            'fill_vol': float(t.get('fillPnl', 0)) if t.get('fillPnl') else 0,
        })

    # Sort by time descending (most recent first)
    trades.sort(key=lambda x: x['fill_time'], reverse=True)
    return trades


# ──────────────────────────────────────────────
# 1. Altcoin list
# ──────────────────────────────────────────────
STABLE_BASES = {
    'USDT', 'USDC', 'DAI', 'TUSD', 'BUSD', 'FDUSD', 'USDP',
    'EUR', 'GBP', 'AUD', 'SGD', 'AED', 'CNY', 'JPY', 'KRW',
    'USDG', 'TRY', 'BRL', 'CAD', 'CHF', 'HKD', 'MXN',
    'NOK', 'NZD', 'PLN', 'RUB', 'SEK', 'ZAR', 'CZK', 'DKK',
    'ILS', 'INR', 'MYR', 'PHP', 'THB', 'VND', 'XOF',
}

def fetch_altcoin_list(top_n=30, min_volume_usd=500_000):
    """Fetch top-N active USDT altcoins by 24h volume via public tickers endpoint.

    Returns list of dicts: [{symbol, base, volume_24h, last_price, change_24h, open_24h}, ...]
    """
    print('[OKX] Fetching tickers...')
    resp = _api_get('/api/v5/market/tickers?instType=SPOT')
    if resp.get('code') != '0' or 'data' not in resp:
        print(f'[OKX] ticker API failed: {resp.get("msg", "unknown")}')
        return _fallback_altcoin_list(top_n)

    all_tickers = resp['data']
    # Filter: USDT pairs only, exclude stables
    altcoins = []
    for t in all_tickers:
        inst_id = t.get('instId', '')
        if not inst_id.endswith('-USDT'):
            continue
        base = inst_id.replace('-USDT', '')
        if base in STABLE_BASES:
            continue
        # Skip leveraged tokens
        if any(s in base for s in ['3L', '3S', 'UP', 'DOWN', 'BEAR', 'BULL', 'LEND']):
            continue

        vol = float(t.get('volCcy24h', '0') or 0)
        if vol >= min_volume_usd:
            altcoins.append({
                'symbol': f'{base}/USDT',
                'base': base,
                'volume_24h': vol,
                'last_price': float(t.get('last', '0') or 0),
                'open_24h': float(t.get('open24h', '0') or 0),
                'change_24h': t.get('change24h', '0'),
            })

    altcoins.sort(key=lambda x: x['volume_24h'], reverse=True)
    altcoins = altcoins[:top_n]

    print(f'[OKX] Top {len(altcoins)} altcoins (vol>={min_volume_usd:,} USDT):')
    for i, c in enumerate(altcoins, 1):
        change_str = ''
        if c['open_24h'] > 0:
            pct = (c['last_price'] / c['open_24h'] - 1) * 100
            change_str = f'{pct:+.2f}%'
        print(f'  {i:2d}. {c["base"]:12s} vol=${c["volume_24h"]:>12,.0f} last=${c["last_price"]:<12.6f} {change_str}')

    return altcoins


def _fallback_altcoin_list(top_n=30):
    """Hardcoded list of commonly traded altcoins as fallback."""
    popular = [
        'SOL', 'XRP', 'DOGE', 'ADA', 'AVAX', 'DOT', 'LINK', 'MATIC', 'UNI',
        'SHIB', 'LTC', 'BCH', 'ATOM', 'ETC', 'XLM', 'FIL', 'APT', 'ARB',
        'OP', 'NEAR', 'INJ', 'TIA', 'SEI', 'SUI', 'PEPE', 'FLOKI', 'WIF',
        'BONK', 'TRX', 'TON', 'RUNE', 'AAVE', 'MKR', 'SNX', 'CRV', 'COMP',
    ]
    result = [{'symbol': f'{c}/USDT', 'base': c, 'volume_24h': 0,
               'last_price': 0, 'open_24h': 0, 'change_24h': '0'}
              for c in popular[:top_n]]
    print(f'[OKX] Using fallback list: {[c["base"] for c in result]}')
    return result


# ──────────────────────────────────────────────
# 2. OHLC fetching (using OKX REST API, NOT ccxt)
# ──────────────────────────────────────────────
# OKX bar values: 1m,3m,5m,15m,30m,1H,2H,4H,6H,12H,1D,2D,3D,1W,1M,3M
OKX_BAR_MAP = {
    '1h': '1H',
    '2h': '2H',
    '4h': '4H',
    '6h': '6H',
    '12h': '12H',
    '1d': '1D',
    '2d': '2D',
    '1w': '1W',
    '1m': '1M',
}

def fetch_ohlc(symbol, bar='1D', limit=200):
    """Fetch OHLCV candles for a symbol via OKX public REST API.

    Args:
        symbol: e.g. 'SOL/USDT' or 'SOL-USDT'
        bar: '1D', '4H', '1H' (OKX uppercase format)
        limit: number of candles (max 300)

    Returns:
        list of dicts: [{date, open, high, low, close, volume}, ...]
    """
    # Normalize symbol format: SOL/USDT -> SOL-USDT
    inst_id = symbol.replace('/', '-')
    resp = _api_get(f'/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}')

    if resp.get('code') != '0':
        print(f'[OKX] OHLC error for {inst_id} ({bar}): code={resp["code"]}')
        return []

    raw = resp.get('data', [])
    candles = []
    for c in raw:
        # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        try:
            ts_ms = int(c[0])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            candles.append({
                'date': dt,
                'open': float(c[1]),
                'high': float(c[2]),
                'low': float(c[3]),
                'close': float(c[4]),
                'volume': float(c[5]),
            })
        except (ValueError, IndexError) as e:
            continue

    return candles


def fetch_all_altcoins_ohlc(altcoins, bar='1D', limit=365):
    """Fetch OHLC for all altcoins.

    Returns dict: {symbol_key: [candles]} where symbol_key = e.g. 'SOLUSDT'
    """
    result = {}
    total = len(altcoins)
    bar_label = bar
    print(f'[OKX] Fetching {bar} OHLC for {total} altcoins...')

    for i, coin in enumerate(altcoins):
        sym = coin['symbol']
        base = coin['base']
        candles = fetch_ohlc(sym, bar, limit)
        if candles:
            key = f'{base}USDT'
            result[key] = candles
            first_d = candles[0]['date']
            last_d = candles[-1]['date']
            print(f'  [{i+1}/{total}] {base:12s} → {len(candles):3d} candles ({first_d} → {last_d})')
        else:
            print(f'  [{i+1}/{total}] {base:12s} → SKIP')
        time.sleep(0.12)  # rate limit

    print(f'[OKX] Fetched {len(result)}/{total} symbols')
    return result


# ──────────────────────────────────────────────
# 3. Feature builder (standalone, mirrors feature_engine)
# ──────────────────────────────────────────────
def build_features_single(df):
    """Compute technical features for one symbol's OHLC DataFrame.

    Matches the interface of feature_engine.build_features_single
    so the KOL factors can directly consume this output.

    Args:
        df: pd.DataFrame with [open, high, low, close, volume], datetime index

    Returns:
        pd.DataFrame with ~30 feature columns
    """
    c, h, l, o = df['close'], df['high'], df['low'], df['open']
    out = pd.DataFrame(index=df.index)
    out['close'] = c
    out['open'] = o
    out['high'] = h
    out['low'] = l
    out['volume'] = df.get('volume', pd.Series(0, index=df.index))

    # Moving averages
    for n in [7, 20, 50, 100, 200]:
        out[f'ma{n}'] = c.rolling(n, min_periods=1).mean()
    out['ema20'] = c.ewm(span=20, adjust=False).mean()
    out['ema50'] = c.ewm(span=50, adjust=False).mean()

    # Weekly MAs (7-day multiplier for crypto)
    out['ma_20w'] = c.rolling(140, min_periods=1).mean()
    out['ma_50w'] = c.rolling(350, min_periods=1).mean()

    # RSI
    diff = c.diff()
    gain = diff.clip(lower=0)
    loss = (-diff).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out['rsi14'] = 100 - (100 / (1 + rs))
    out['rsi14_prev'] = out['rsi14'].shift(1)
    out['stoch_rsi'] = (out['rsi14'] - out['rsi14'].rolling(14).min()) / \
                       (out['rsi14'].rolling(14).max() - out['rsi14'].rolling(14).min()).replace(0, np.nan)

    # MACD
    ema_fast = c.ewm(span=12, adjust=False).mean()
    ema_slow = c.ewm(span=26, adjust=False).mean()
    out['macd'] = ema_fast - ema_slow
    out['macd_sig'] = out['macd'].ewm(span=9, adjust=False).mean()
    out['macd_hist'] = out['macd'] - out['macd_sig']

    # Bollinger Bands
    bb_mid = out['ma20']
    std = c.rolling(20, min_periods=1).std(ddof=0)
    out['bb_upper'] = bb_mid + 2 * std
    out['bb_lower'] = bb_mid - 2 * std
    out['bb_mid'] = bb_mid
    out['bb_width'] = (out['bb_upper'] - out['bb_lower']) / bb_mid.replace(0, np.nan)
    out['bb_width_20pctile'] = out['bb_width'].rolling(100, min_periods=20).quantile(0.2)

    # ATR
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    out['atr14'] = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    # Keltner Channels (EMA20 + ATR10×2.0)
    ema20 = c.ewm(span=20, adjust=False).mean()
    atr10 = tr.rolling(10, min_periods=10).mean()
    out['kc_mid'] = ema20
    out['kc_upper'] = ema20 + 2.0 * atr10
    out['kc_lower'] = ema20 - 2.0 * atr10
    out['kc_width'] = (out['kc_upper'] - out['kc_lower']) / out['kc_mid'].replace(0, np.nan)

    # ADX
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0)
    atr_ = out['atr14']
    plus_di = 100 * pd.Series(plus_dm, index=h.index).ewm(alpha=1/14, adjust=False).mean() / atr_.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=h.index).ewm(alpha=1/14, adjust=False).mean() / atr_.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out['adx14'] = dx.ewm(span=14, adjust=False).mean()

    # Returns
    for n in [1, 5, 7, 14, 30]:
        out[f'ret_{n}d'] = c.pct_change(n)
    out['fwd_ret_1d'] = c.pct_change(1).shift(-1)
    out['fwd_ret_7d'] = c.pct_change(7).shift(-7)

    # Swing highs/lows
    out['high_20d'] = h.rolling(20, min_periods=1).max()
    out['low_20d'] = l.rolling(20, min_periods=1).min()
    out['high_50d'] = h.rolling(50, min_periods=1).max()
    out['low_50d'] = l.rolling(50, min_periods=1).min()
    out['pct_from_high_50d'] = (c - out['high_50d']) / out['high_50d']
    out['pct_from_low_50d'] = (c - out['low_50d']) / out['low_50d']

    # Bar shape
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    out['body_pct'] = body / rng
    out['upper_wick_pct'] = (h - c.where(c > o, o)) / rng
    out['lower_wick_pct'] = (c.where(c < o, o) - l) / rng
    out['is_green'] = (c > o).astype(int)

    # MA relationships
    out['price_above_ma50'] = (c > out['ma50']).astype(int)
    out['price_above_ma200'] = (c > out['ma200']).astype(int)
    out['ma50_above_ma200'] = (out['ma50'] > out['ma200']).astype(int)

    # Pivot resistance/support levels (Pivot Point Standard)
    out['pivot'] = (h + l + c) / 3
    out['r1'] = 2 * out['pivot'] - l
    out['r2'] = out['pivot'] + (h - l)
    out['s1'] = 2 * out['pivot'] - h
    out['s2'] = out['pivot'] - (h - l)

    # Fibonacci levels based on 50-bar swing
    swing_range = out['high_50d'] - out['low_50d']
    out['fib_382'] = out['high_50d'] - 0.382 * swing_range
    out['fib_500'] = out['high_50d'] - 0.500 * swing_range
    out['fib_618'] = out['high_50d'] - 0.618 * swing_range

    # -- Additional features needed by original KOL factors --
    # rv30: 30-day realized volatility (std of log returns)
    log_ret = np.log(c / c.shift(1))
    out['rv30'] = log_ret.rolling(30, min_periods=10).std() * np.sqrt(365)
    out['rv30_pctile'] = out['rv30'].rolling(200, min_periods=30).apply(
        lambda x: (x.iloc[-1] > x).mean() if len(x) > 1 else 0.5, raw=False)

    # days_below_ma200: consecutive days close below MA200
    below = (c < out['ma200']).astype(int)
    out['days_below_ma200'] = below.groupby((below != below.shift()).cumsum()).cumcount() + 1
    out['days_below_ma200'] = out['days_below_ma200'] * below

    # uptrend_20d: price above ma50 and ma50 above ma200
    out['uptrend_20d'] = ((c > out['ma50']) & (out['ma50'] > out['ma200'])).astype(int)

    # hh_count_20d / ll_count_20d: higher high / lower low counts in 20 bars
    out['hh_count_20d'] = (h > h.shift(1)).rolling(20, min_periods=1).sum()
    out['ll_count_20d'] = (l < l.shift(1)).rolling(20, min_periods=1).sum()

    # body_pct_prev: previous bar's body percentage
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    out['body_pct'] = body / rng
    out['body_pct_prev'] = out['body_pct'].shift(1)

    return out


# ──────────────────────────────────────────────
# 4. Full pipeline
# ──────────────────────────────────────────────
def build_altcoin_panel(top_n=30, lookback_days=365):
    """Complete pipeline: fetch altcoins → fetch OHLC → build features.

    NOTE: Returns DAILY data by default. For the KOL factor engine,
    the data needs to be compatible with feature_engine output.

    Returns:
        features: pd.DataFrame indexed by (symbol_key, date) or None if error
        ohlc_dict: dict for saving to json
        altcoin_list: list of {base, symbol, ...}
    """
    # Step 1: Get altcoin list
    altcoins = fetch_altcoin_list(top_n=top_n)
    if not altcoins:
        print('[OKX] No altcoins found!')
        return None, {}, []

    # Step 2: Fetch OHLC
    bar = '1D'
    ohlc_data = fetch_all_altcoins_ohlc(altcoins, bar=bar, limit=lookback_days)

    if not ohlc_data:
        print('[OKX] No OHLC data fetched!')
        return None, {}, altcoins

    # Step 3: Build features
    print(f'\n[OKX] Building features ({len(ohlc_data)} symbols)...')
    features_dict = {}
    ohlc_dict = {}

    for sym_key, candles in ohlc_data.items():
        df = pd.DataFrame(candles)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()

        ohlc_dict[sym_key] = candles

        try:
            feats = build_features_single(df)
            features_dict[sym_key] = feats
        except Exception as e:
            print(f'  [OKX] Feature error for {sym_key}: {e}')

    if features_dict:
        panel = pd.concat(features_dict.values(), keys=features_dict.keys(), names=['symbol', 'date'])
        print(f'[OKX] Panel: {panel.shape[0]} rows x {panel.shape[1]} cols, {len(features_dict)} symbols')
        return panel, ohlc_dict, altcoins

    return None, {}, altcoins


def save_ohlc_json(ohlc_dict, output_path=None):
    """Save OHLC data in ohlc_daily.json format."""
    if output_path is None:
        output_path = os.path.join(BASE, 'ohlc_altcoins.json')

    with open(output_path, 'w') as f:
        json.dump(ohlc_dict, f, ensure_ascii=False, indent=2)

    print(f'[OKX] Saved OHLC to {output_path} ({len(ohlc_dict)} symbols)')
    return output_path


# ──────────────────────────────────────────────
# 5. Main (quick test)
# ──────────────────────────────────────────────
if __name__ == '__main__':
    print('=' * 60)
    print('  OKX Data Adapter — Quick Test')
    print('=' * 60)

    print(f'\nAPI Key: {OKX_API_KEY[:8]}...{OKX_API_KEY[-4:]}')

    # Test basic ticker fetch
    altcoins = fetch_altcoin_list(top_n=5)
    print(f'\n--- Top 5 altcoins ---')

    # Test OHLC for first altcoin
    if altcoins:
        sym = altcoins[0]['symbol']
        candles = fetch_ohlc(sym, '1D', 5)
        print(f'\n{sym} (5d OHLC):')
        for c in candles:
            print(f'  {c["date"]} O={c["open"]:.4f} H={c["high"]:.4f} L={c["low"]:.4f} C={c["close"]:.4f}')

    # Quick feature test
    if altcoins:
        sym = altcoins[0]['symbol']
        candles = fetch_ohlc(sym, '1D', 200)
        if candles:
            df = pd.DataFrame(candles)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            feats = build_features_single(df)
            print(f'\nFeature test for {sym}: {feats.shape}')
            print(f'Latest: RSI14={feats["rsi14"].iloc[-1]:.1f} r1={feats["r1"].iloc[-1]:.4f} r2={feats["r2"].iloc[-1]:.4f}')


# ──────────────────────────────────────────────
# 5. MTF Trend Confirmation (Higher Timeframe EMA)
# ──────────────────────────────────────────────
def check_mtf_trend(symbol, higher_tf='1H', ema_period=20):
    """Check higher timeframe EMA trend for multi-timeframe confirmation.

    Fetches higher timeframe OHLC data, calculates EMA, and determines
    whether price is above/below the EMA for trend direction.

    Args:
        symbol: e.g. 'EDGE-USDT'
        higher_tf: higher timeframe bar size, e.g. '1H', '4H', '1D'
        ema_period: EMA period for trend filter (default 20)

    Returns:
        dict with: direction ('BULL', 'BEAR', 'NEUTRAL'),
                   price, ema_value, distance_pct, bars_fetched
    """
    result = {
        'direction': 'NEUTRAL',
        'price': 0,
        'ema': 0,
        'distance_pct': 0,
        'bars_fetched': 0,
        'error': None,
    }
    try:
        candles = fetch_ohlc(symbol, higher_tf, ema_period + 30)
        if not candles or len(candles) < ema_period:
            result['error'] = f'Not enough {higher_tf} data'
            return result

        closes = [c['close'] for c in candles]
        prices = np.array(closes)
        result['bars_fetched'] = len(prices)

        # Calculate EMA
        alpha = 2.0 / (ema_period + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = p * alpha + ema * (1 - alpha)
        # Use last close for the EMA value (slightly simplified but close enough)
        ema_values = [prices[0]]
        for p in prices[1:]:
            ema_values.append(p * alpha + ema_values[-1] * (1 - alpha))

        result['price'] = prices[-1]
        result['ema'] = ema_values[-1]
        result['distance_pct'] = (prices[-1] - ema_values[-1]) / ema_values[-1] * 100

        if prices[-1] > ema_values[-1]:
            result['direction'] = 'BULL'
        else:
            result['direction'] = 'BEAR'

    except Exception as e:
        result['error'] = str(e)

    return result
