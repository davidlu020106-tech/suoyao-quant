#!/usr/bin/env python3
"""Fetch OKX trade history and generate trade analysis document.

Uses authenticated OKX REST API to retrieve:
  - Recent fills (last 3 days): /api/v5/trade/fills
  - Historical fills (last 3 months): /api/v5/trade/fills-history
  - Account balance: /api/v5/account/balance

Output:
  - trade_history_analysis.md — formatted trade analysis document
  - trade_history_data.json — raw trade data for further analysis
"""
import sys, os, json, time, hmac, base64, hashlib
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'quant_factors'))
from local_config import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, BASE

# ══════════════════════════════════════════════
# OKX Signed Request Helper
# ══════════════════════════════════════════════
def _sign_request(method, request_path, body=''):
    """Create OKX API authentication headers."""
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    msg = ts + method.upper() + request_path + body
    mac = hmac.new(bytes(OKX_SECRET_KEY, 'utf-8'), bytes(msg, 'utf-8'), hashlib.sha256)
    sign = base64.b64encode(mac.digest()).decode('utf-8')
    return {
        'OK-ACCESS-KEY': OKX_API_KEY,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-TIMESTAMP': ts,
        'OK-ACCESS-PASSPHRASE': OKX_PASSPHRASE,
        'Content-Type': 'application/json',
    }

def api_get(path):
    """Make authenticated GET request to OKX REST API."""
    import urllib.request
    url = f'https://www.okx.com{path}'
    headers = _sign_request('GET', path)
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8')
        print(f'[OKX] HTTP {e.code} for {path[:60]}: {err}')
        return {'code': str(e.code), 'data': []}
    except Exception as e:
        print(f'[OKX] Request error: {e}')
        return {'code': '-1', 'data': []}

# ══════════════════════════════════════════════
# Fetch Functions
# ══════════════════════════════════════════════
def fetch_balance():
    """Fetch account balance."""
    resp = api_get('/api/v5/account/balance')
    if resp.get('code') == '0':
        return resp['data']
    return []

def fetch_recent_fills(limit=100):
    """Fetch recent transaction fills (last 3 days)."""
    resp = api_get(f'/api/v5/trade/fills?limit={limit}')
    if resp.get('code') == '0':
        return resp['data']
    return []

def fetch_order_history(limit=100, inst_type='SPOT'):
    """Fetch order history (last 7 days)."""
    resp = api_get(f'/api/v5/trade/orders-history?instType={inst_type}&limit={limit}')
    if resp.get('code') == '0':
        return resp['data']
    return []

def fetch_positions():
    """Fetch current positions."""
    resp = api_get('/api/v5/account/positions')
    if resp.get('code') == '0':
        return resp['data']
    return []

# ══════════════════════════════════════════════
# Analysis
# ══════════════════════════════════════════════
def analyze_trades(fills, orders=None):
    """Analyze trade history and return structured results."""
    if not fills:
        return None

    # Group by instrument
    by_coin = defaultdict(list)
    for f in fills:
        inst = f.get('instId', '?')
        by_coin[inst].append(f)

    total_trades = len(fills)
    total_volume = sum(float(f.get('fillSz', '0') or 0) * float(f.get('fillPx', '0') or 0) for f in fills)
    total_fee = sum(float(f.get('fee', '0') or 0) for f in fills)

    # Count buy vs sell fills
    buy_count = sum(1 for f in fills if f.get('side', '') == 'buy')
    sell_count = sum(1 for f in fills if f.get('side', '') == 'sell')

    # By coin summary
    coin_summary = {}
    for inst, trades in by_coin.items():
        coin = inst.split('-')[0]
        buy_vol = sum(float(t.get('fillSz', '0') or 0) for t in trades if t.get('side') == 'buy')
        sell_vol = sum(float(t.get('fillSz', '0') or 0) for t in trades if t.get('side') == 'sell')
        avg_buy = sum(float(t.get('fillSz', '0') or 0) * float(t.get('fillPx', '0') or 0) for t in trades if t.get('side') == 'buy') / buy_vol if buy_vol > 0 else 0
        avg_sell = sum(float(t.get('fillSz', '0') or 0) * float(t.get('fillPx', '0') or 0) for t in trades if t.get('side') == 'sell') / sell_vol if sell_vol > 0 else 0
        net = sell_vol - buy_vol
        fees = sum(float(t.get('fee', '0') or 0) for t in trades)
        coin_summary[coin] = {
            'instId': inst,
            'buy_qty': buy_vol,
            'sell_qty': sell_vol,
            'avg_buy_price': avg_buy,
            'avg_sell_price': avg_sell,
            'net_qty': net,
            'total_fee': fees,
            'trade_count': len(trades),
        }

    return {
        'total_trades': total_trades,
        'total_volume_usd': total_volume,
        'total_fee_usd': total_fee,
        'buy_count': buy_count,
        'sell_count': sell_count,
        'by_coin': coin_summary,
        'raw_fills': fills[:20],  # keep recent 20
    }

# ══════════════════════════════════════════════
# Document Generation
# ══════════════════════════════════════════════
def generate_trade_document(balance, fills, positions, analysis):
    """Generate a formatted trade analysis markdown document."""
    lines = []
    now = datetime.now(timezone.utc)
    lines.append(f'# OKX 交易记录分析报告')
    lines.append(f'')
    lines.append(f'> 生成时间：{now.strftime("%Y-%m-%d %H:%M:%S")} UTC')
    lines.append(f'> API Key: {OKX_API_KEY[:8]}...{OKX_API_KEY[-4:]}')
    lines.append(f'')

    # ── Account Summary ──
    lines.append(f'## 账户概览')
    lines.append(f'')
    if balance:
        for acct in balance[:1]:
            total_eq = float(acct.get('totalEq', '0') or 0)
            lines.append(f'- **总权益**: ${total_eq:,.2f}')
            lines.append(f'- **账户模式**: {acct.get("acctLv", "?")}')
            details = acct.get('details', [])
            lines.append(f'- **币种数量**: {len(details)}')
            for d in details[:5]:
                ccy = d.get('ccy', '?')
                eq = float(d.get('eq', '0') or 0)
                if eq > 0:
                    lines.append(f'  - {ccy}: {eq:.4f}')
            if len(details) > 5:
                lines.append(f'  - ... 共 {len(details)} 个币种')
    lines.append(f'')

    # ── Positions ──
    if positions:
        lines.append(f'## 当前持仓')
        lines.append(f'')
        lines.append(f'| 币种 | 方向 | 数量 | 开仓价 | 当前盈亏 | 保证金 |')
        lines.append(f'|------|------|------|--------|---------|--------|')
        for p in positions:
            inst = p.get('instId', '?')
            pos = float(p.get('pos', '0') or 0)
            side = p.get('posSide', '?')
            entry = float(p.get('avgPx', '0') or 0)
            upl = float(p.get('upl', '0') or 0)
            margin = float(p.get('imr', '0') or 0)
            lines.append(f'| {inst} | {side} | {pos:.4f} | ${entry:.4f} | ${upl:+.2f} | ${margin:.2f} |')
        lines.append(f'')

    # ── Trade Analysis ──
    if analysis:
        lines.append(f'## 交易统计')
        lines.append(f'')
        lines.append(f'- **总成交笔数**: {analysis["total_trades"]}')
        lines.append(f'- **买入笔数**: {analysis["buy_count"]}  |  **卖出笔数**: {analysis["sell_count"]}')
        lines.append(f'- **总交易额**: ${analysis["total_volume_usd"]:,.2f}')
        lines.append(f'- **总手续费**: ${analysis["total_fee_usd"]:.4f}')
        lines.append(f'')

        # By coin
        lines.append(f'### 分币种统计')
        lines.append(f'')
        lines.append(f'| 币种 | 交易次数 | 买入量 | 卖出量 | 均价(买) | 均价(卖) | 净头寸 | 手续费 |')
        lines.append(f'|------|---------|--------|--------|----------|----------|--------|--------|')
        for coin, s in sorted(analysis['by_coin'].items()):
            lines.append(f'| {coin} | {s["trade_count"]} | {s["buy_qty"]:.4f} | {s["sell_qty"]:.4f} | ${s["avg_buy_price"]:.4f} | ${s["avg_sell_price"]:.4f} | {s["net_qty"]:+.4f} | ${s["total_fee"]:.4f} |')
        lines.append(f'')

        # Recent trades
        lines.append(f'### 最近成交')
        lines.append(f'')
        lines.append(f'| 时间 | 币种 | 方向 | 价格 | 数量 | 金额 | 手续费 |')
        lines.append(f'|------|------|------|------|------|------|--------|')
        for f in analysis['raw_fills'][:10]:
            ts = datetime.fromtimestamp(int(f.get('ts', '0'))/1000).strftime('%m-%d %H:%M')
            inst = f.get('instId', '?')
            side = f.get('side', '?')
            px = float(f.get('fillPx', '0') or 0)
            sz = float(f.get('fillSz', '0') or 0)
            vol = px * sz
            fee = float(f.get('fee', '0') or 0)
            lines.append(f'| {ts} | {inst} | {side} | ${px:.4f} | {sz:.4f} | ${vol:.2f} | ${fee:.4f} |')
        lines.append(f'')

        # PnL estimate for closed positions (simplified)
        lines.append(f'### 策略建议')
        lines.append(f'')
        lines.append(f'基于当前持仓和市场数据，建议关注以下监控点：')
        for inst, s in sorted(analysis['by_coin'].items()):
            coin = inst.split('-')[0]
            if abs(s['net_qty']) > 0:
                lines.append(f'- **{coin}**: 净头寸 {s["net_qty"]:+.4f}')
        lines.append(f'')

    # ── Footer ──
    lines.append(f'---')
    lines.append(f'*由 OKX API 自动生成 · 数据仅供分析参考*')
    lines.append(f'*交易有风险，决策需谨慎*')
    lines.append(f'')

    return '\n'.join(lines)

# ══════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════
if __name__ == '__main__':
    print('=' * 60)
    print('  OKX Trade History Fetcher')
    print('=' * 60)

    print('\n[1/4] Fetching account balance...')
    balance = fetch_balance()
    print(f'  Balance data: {len(balance)} accounts')

    print('\n[2/4] Fetching current positions...')
    positions = fetch_positions()
    print(f'  Positions: {len(positions)}')

    print('\n[3/4] Fetching recent fills...')
    fills = fetch_recent_fills(limit=50)
    print(f'  Recent fills: {len(fills)}')

    print('\n[4/4] Analyzing...')
    analysis = analyze_trades(fills)

    # Generate document
    doc = generate_trade_document(balance, fills, positions, analysis)
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, 'trade_history_analysis.md')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(doc)
    print(f'\n  Document saved: {output_path}')

    # Save raw data
    raw_path = os.path.join(output_dir, 'trade_history_data.json')
    raw_data = {
        'balance': balance,
        'positions': positions,
        'fills': fills[:30],
        'analysis': analysis,
    }
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2, default=str)
    print(f'  Raw data saved: {raw_path}')

    # Print quick summary
    if balance:
        for acct in balance[:1]:
            eq = float(acct.get('totalEq', '0') or 0)
            print(f'\n  账户总权益: ${eq:,.2f}')
    if analysis:
        print(f'  近3天成交: {analysis["total_trades"]} 笔')
        print(f'  总交易额: ${analysis["total_volume_usd"]:,.2f}')
        print(f'  活跃币种: {len(analysis["by_coin"])} 个')
