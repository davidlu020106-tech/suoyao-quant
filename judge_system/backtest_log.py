"""
推荐回测系统 — 记录每次推荐，下次运行时回测上次结果

流程:
  每次 run_daily_picks.py 运行时:
    1. 加载 recommendation_log.json，读取上一条推荐记录
    2. 获取每个推荐币的当前价格
    3. 判断状态: 到TP1盈利 / 爆仓 / 浮亏 / 浮盈 / 挂单未成交
    4. 输出回测表格
    5. 本次推荐结束后，追加新记录到 recommendation_log.json
"""

import json
import os
import time
from datetime import datetime
from typing import List, Optional


LOG_PATH = None  # 在 init() 时设置


def init(quant_factors_dir: str):
    """初始化日志路径"""
    global LOG_PATH
    LOG_PATH = os.path.join(quant_factors_dir, 'recommendation_log.json')


def load_history() -> list:
    """加载全部推荐历史"""
    if not LOG_PATH or not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except:
        pass
    return []


def get_last_recommendation() -> Optional[dict]:
    """获取上一次推荐记录"""
    history = load_history()
    if not history:
        return None
    return history[-1]


def save_recommendation(coins_data: list):
    """保存本次推荐到历史"""
    history = load_history()
    record = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'timestamp': time.time(),
        'recommendations': coins_data,
    }
    history.append(record)
    # 只保留最近20条
    if len(history) > 20:
        history = history[-20:]
    try:
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except:
        pass


def get_current_prices(symbols: list) -> dict:
    """获取多个币种的当前价格（从OKX ticker接口）"""
    prices = {}
    try:
        from okx_data_adapter import _api_get as api_get
        resp = api_get('/api/v5/market/tickers?instType=SWAP')
        if resp.get('code') == '0':
            for item in resp.get('data', []):
                inst = item['instId']  # e.g. BTC-USDT-SWAP
                base = inst.replace('-USDT-SWAP', '')
                if base in symbols:
                    prices[base] = {
                        'last': float(item.get('last', 0)),
                        'high24h': float(item.get('high24h', 0)),
                        'low24h': float(item.get('low24h', 0)),
                    }
    except:
        pass
    # 补缺失的
    for sym in symbols:
        if sym not in prices:
            prices[sym] = None
    return prices


def backtest_last():
    """
    回测上一次推荐

    Returns:
        (回测结果列表, 距推荐时间字符串) 或 (None, None)
    """
    last = get_last_recommendation()
    if not last:
        return None, None

    recs = last.get('recommendations', [])
    if not recs:
        return None, None

    symbols = [r['base'] for r in recs]
    prices = get_current_prices(symbols)

    # 计算距推荐时间
    rec_time = last.get('timestamp', 0)
    elapsed = time.time() - rec_time
    if elapsed < 60:
        time_str = f'{elapsed:.0f}秒'
    elif elapsed < 3600:
        time_str = f'{elapsed/60:.0f}分钟'
    elif elapsed < 86400:
        time_str = f'{elapsed/3600:.1f}小时'
    else:
        time_str = f'{elapsed/86400:.1f}天'

    results = []
    for r in recs:
        base = r['base']
        direction = r['direction']
        entry = r['entry']
        tp1 = r['tp1']
        liq = r['liq']
        lev = r.get('lev', 20)

        price_data = prices.get(base)
        if not price_data:
            results.append({
                'base': base,
                'direction': direction,
                'entry': entry,
                'tp1': tp1,
                'liq': liq,
                'lev': lev,
                'status': '未知',
                'pnl_pct': 0,
                'pnl_usdt': 0,
                'current_price': None,
            })
            continue

        current = price_data['last']

        # 计算盈亏
        if direction == 'short':
            # 做空: 价格跌=盈利, 价格涨=亏损
            pnl_pct = (entry - current) / entry * 100
            pnl_usdt = (entry - current) / entry * 20 * lev  # 20U * 杠杆
            # 判断状态
            if current >= liq:
                status = '爆仓'
            elif current <= tp1:
                status = '到TP1盈利'
            elif current < entry:
                status = '浮盈'
            elif current > entry:
                status = '浮亏'
            else:
                status = '挂单'
        else:
            # 做多: 价格涨=盈利, 价格跌=亏损
            pnl_pct = (current - entry) / entry * 100
            pnl_usdt = (current - entry) / entry * 20 * lev
            if current <= liq:
                status = '爆仓'
            elif current >= tp1:
                status = '到TP1盈利'
            elif current > entry:
                status = '浮盈'
            elif current < entry:
                status = '浮亏'
            else:
                status = '挂单'

        results.append({
            'base': base,
            'direction': direction,
            'entry': entry,
            'tp1': tp1,
            'liq': liq,
            'lev': lev,
            'status': status,
            'pnl_pct': round(pnl_pct, 2),
            'pnl_usdt': round(pnl_usdt, 2),
            'current_price': current,
        })

    return results, time_str


def print_backtest(results: list, time_str: str):
    """打印回测结果表格"""
    if not results:
        return

    print()
    print(f'  {"=" * 60}')
    print(f'  ★ 上次推荐回测 (距推荐: {time_str})')
    print(f'  {"=" * 60}')

    for r in results:
        dir_cn = '做空' if r['direction'] == 'short' else '做多'
        status = r['status']
        cp = r['current_price']

        # 状态图标
        if status == '到TP1盈利':
            icon = '[OK]'
        elif status == '爆仓':
            icon = '[!!]'
        elif status == '浮盈':
            icon = '[+]'
        elif status == '浮亏':
            icon = '[-]'
        else:
            icon = '[?]'

        pnl = r['pnl_usdt']
        pnl_pct = r['pnl_pct']
        if status in ('到TP1盈利', '浮盈') or (status == '浮亏' and pnl < 0):
            pnl_str = f'+${pnl:.2f} ({pnl_pct:+.2f}%)' if pnl >= 0 else f'-${abs(pnl):.2f} ({pnl_pct:+.2f}%)'
        elif status == '爆仓':
            pnl_str = f'-${abs(pnl):.2f} (爆仓)'
        else:
            pnl_str = f'{pnl:+.2f}USDT'

        print(f'  {icon} {r["base"]:<6} {dir_cn}  入场={r["entry"]}  TP1={r["tp1"]}  强平={r["liq"]}')
        print(f'     状态: {status}  {pnl_str}')
        if cp:
            print(f'     当前价: {cp:.4f}')
        print()

    print(f'  {"=" * 60}')
    print()
