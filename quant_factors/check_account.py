#!/usr/bin/env python3
"""一键查看 OKX 账户余额、持仓和成交历史。

用法:
    python quant_factors/check_account.py
    python quant_factors/check_account.py --ccy USDT     # 只看 USDT
    python quant_factors/check_account.py --inst EDGE     # 只看 EDGE 持仓
    python quant_factors/check_account.py --history       # 查看最近成交记录
    python quant_factors/check_account.py --history --inst EDGE  # 只看 EDGE 成交
"""
import sys, os, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_data_adapter import fetch_balance, fetch_positions, fetch_trade_history
from local_config import OKX_API_KEY


def fmt_price(px, ref=0):
    if px == 0:
        return '-'
    if ref > 1000:
        return f'{px:.2f}'
    if ref > 100:
        return f'{px:.3f}'
    if ref > 1:
        return f'{px:.4f}'
    return f'{px:.6f}'


def show_balance(ccy=None):
    print('=' * 60)
    print('  OKX \u8d26\u6237\u4f59\u989d')
    print('=' * 60)

    bal = fetch_balance(ccy)
    print(f'\n  \u603b\u6743\u76ca: ${bal["total_eq"]:.2f}')

    if bal['details']:
        print(f'\n  {"\u5e01\u79cd":<8s} {"\u6743\u76ca":>14s} {"\u53ef\u7528":>14s} {"\u51bb\u7ed3":>14s}')
        print(f'  {"----":<8s} {"----":>14s} {"----":>14s} {"----":>14s}')
        for d in bal['details']:
            if d['eq'] > 0.0001:
                print(f'  {d["ccy"]:<8s} {d["eq"]:>14.6f} {d["avail_bal"]:>14.6f} {d["frozen_bal"]:>14.6f}')
    else:
        print('  (\u65e0\u4f59\u989d\u6570\u636e)')


def show_positions(filter_inst=None):
    print('\n' + '=' * 60)
    print('  \u5f53\u524d\u6301\u4ed3')
    print('=' * 60)

    positions = fetch_positions()
    if filter_inst:
        positions = [p for p in positions if filter_inst.upper() in p['inst_id'].upper()]

    if not positions:
        print('\n  \u65e0\u6301\u4ed3')
        return

    h1 = '\u5408\u7ea6'
    h2 = '\u65b9\u5411'
    h3 = '\u6570\u91cf'
    h4 = '\u5165\u573a\u4ef7'
    h5 = '\u6807\u8bb0\u4ef7'
    h6 = '\u6e05\u7b97\u4ef7'
    h7 = '\u672a\u5b9e\u73b0\u76c8\u4e8f'
    h8 = '\u6760\u6746'
    print(f'\n  {h1:<20s} {h2:<7s} {h3:>8s} {h4:>12s} {h5:>12s} {h6:>12s} {h7:>10s} {h8:>6s}')
    print(f'  {"----":<20s} {"----":<7s} {"----":>8s} {"----":>12s} {"----":>12s} {"----":>12s} {"----":>10s} {"----":>6s}')
    for p in positions:
        upl_str = f'{p["upl"]:+.2f}' if p['upl'] >= 0 else f'{p["upl"]:.2f}'
        print(f'  {p["inst_id"]:<20s} {p["direction"]:<7s} {p["size"]:>8.1f} '
              f'{fmt_price(p["entry_px"], p["entry_px"]):>12s} '
              f'{fmt_price(p["mark_px"], p["entry_px"]):>12s} '
              f'{fmt_price(p["liq_px"], p["entry_px"]):>12s} '
              f'{upl_str:>10s} {p["lever"]:>5.1f}x')

    total_upl = sum(p['upl'] for p in positions)
    print(f'\n  \u603b\u672a\u5b9e\u73b0\u76c8\u4e8f: ${total_upl:+.2f}')
    if total_upl > 0:
        print(f'  \u72b6\u6001: \u76c8\u5229\u4e2d')
    elif total_upl < 0:
        print(f'  \u72b6\u6001: \u4e8f\u635f\u4e2d')
    else:
        print(f'  \u72b6\u6001: \u6301\u5e73')


def show_trade_history(filter_inst=None, limit=30):
    print('\n' + '=' * 60)
    print('  \u6700\u8fd1\u6210\u4ea4\u5386\u53f2')
    print('=' * 60)

    trades = fetch_trade_history(limit=limit)
    if filter_inst:
        trades = [t for t in trades if filter_inst.upper() in t['inst_id'].upper()]

    if not trades:
        print('\n  \u65e0\u6210\u4ea4\u8bb0\u5f55')
        return

    # 统计汇总
    total_pnl = sum(t['fill_vol'] for t in trades)
    buys = sum(1 for t in trades if t['side'] == 'BUY')
    sells = sum(1 for t in trades if t['side'] == 'SELL')

    h1 = '\u65f6\u95f4'
    h2 = '\u5408\u7ea6'
    h3 = '\u65b9\u5411'
    h4 = '\u6570\u91cf'
    h5 = '\u4ef7\u683c'
    h6 = '\u76c8\u4e8f(PnL)'
    print(f'\n  {h1:<14s} {h2:<18s} {h3:<7s} {h4:>8s} {h5:>10s} {h6:>12s}')
    print(f'  {"----":<14s} {"----":<18s} {"----":<7s} {"----":>8s} {"----":>10s} {"----":>12s}')
    for t in trades:
        ts = t['fill_time']
        if ts and len(ts) > 10:
            dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
            ts = dt.strftime('%m-%d %H:%M')
        pnl_str = f'{t["fill_vol"]:+.2f}' if t['fill_vol'] != 0 else '  -'
        print(f'  {ts:<14s} {t["inst_id"]:<18s} {t["side"]:<7s} {t["fill_sz"]:>8.1f} '
              f'{fmt_price(t["fill_px"], t["fill_px"]):>10s} {pnl_str:>12s}')

    print(f'\n  \u7edf\u8ba1: {len(trades)} \u7b14\u6210\u4ea4 | BUY x{buys} | SELL x{sells} | \u603bPnL=${total_pnl:+.2f}')


def main():
    parser = argparse.ArgumentParser(description='OKX \u8d26\u6237\u67e5\u8be2\u5de5\u5177')
    parser.add_argument('--ccy', help='\u53ea\u770b\u6307\u5b9a\u5e01\u79cd\u4f59\u989d\uff0c\u5982 USDT')
    parser.add_argument('--inst', help='\u53ea\u770b\u6307\u5b9a\u5408\u7ea6\u6216\u5e01\u79cd\uff0c\u5982 EDGE')
    parser.add_argument('--history', action='store_true', help='\u67e5\u770b\u6700\u8fd1\u6210\u4ea4\u5386\u53f2')
    parser.add_argument('--limit', type=int, default=30, help='\u6210\u4ea4\u8bb0\u5f55\u6761\u6570 (max 100)')
    args = parser.parse_args()

    print(f'API Key: {OKX_API_KEY[:8]}...{OKX_API_KEY[-4:]}')

    if args.history:
        show_trade_history(args.inst, args.limit)
    else:
        show_balance(args.ccy)
        show_positions(args.inst)


if __name__ == '__main__':
    main()
