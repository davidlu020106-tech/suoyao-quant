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


def get_recent_recommendations(n: int = 3) -> list:
    """获取最近N次推荐记录"""
    history = load_history()
    if not history:
        return []
    return history[-n:]


def get_today_recommendations() -> list:
    """获取当天所有推荐记录"""
    history = load_history()
    if not history:
        return []
    today = datetime.now().strftime('%Y-%m-%d')
    return [r for r in history if r.get('date', '').startswith(today)]


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


def backtest_records(records: list, label: str = "上次推荐"):
    """
    回测多条推荐记录

    Args:
        records: 推荐记录列表，每条包含 recommendations 列表
        label: 标签（"最近3次" / "今日汇总"）

    Returns:
        (回测结果列表, 汇总字符串)
    """
    all_results = []
    total_recs = 0
    total_ok = 0
    total_fail = 0
    total_pending = 0

    for rec in records:
        recs = rec.get('recommendations', [])
        if not recs:
            continue
        total_recs += len(recs)
        symbols = [r['base'] for r in recs]
        prices = get_current_prices(symbols)
        rec_time = rec.get('timestamp', 0)
        elapsed = time.time() - rec_time

        for r in recs:
            base = r['base']
            direction = r['direction']
            entry = r['entry']
            tp1 = r['tp1']
            liq = r['liq']
            lev = r.get('lev', 20)
            price_data = prices.get(base)

            if not price_data:
                all_results.append({
                    'base': base, 'direction': direction,
                    'entry': entry, 'tp1': tp1, 'liq': liq, 'lev': lev,
                    'status': '未知', 'pnl_pct': 0, 'pnl_usdt': 0,
                    'current_price': None, 'elapsed': elapsed,
                })
                continue

            current = price_data['last']
            if direction == 'short':
                pnl_pct = (entry - current) / entry * 100
                pnl_usdt = (entry - current) / entry * 20 * lev
                if current >= liq:
                    status = '爆仓'; total_fail += 1
                elif current <= tp1:
                    status = '到TP1盈利'; total_ok += 1
                elif current < entry:
                    status = '浮盈'
                elif current > entry:
                    status = '浮亏'
                else:
                    status = '挂单'; total_pending += 1
            else:
                pnl_pct = (current - entry) / entry * 100
                pnl_usdt = (current - entry) / entry * 20 * lev
                if current <= liq:
                    status = '爆仓'; total_fail += 1
                elif current >= tp1:
                    status = '到TP1盈利'; total_ok += 1
                elif current > entry:
                    status = '浮盈'
                elif current < entry:
                    status = '浮亏'
                else:
                    status = '挂单'; total_pending += 1

            all_results.append({
                'base': base, 'direction': direction,
                'entry': entry, 'tp1': tp1, 'liq': liq, 'lev': lev,
                'status': status, 'pnl_pct': round(pnl_pct, 2),
                'pnl_usdt': round(pnl_usdt, 2),
                'current_price': current, 'elapsed': elapsed,
            })

    summary = f'{label}: {total_recs}个推荐 | {total_ok}个到TP1 | {total_fail}个爆仓 | {total_pending}个挂单'
    return all_results, summary


def backtest_last():
    """回测最近3次推荐"""
    records = get_recent_recommendations(3)
    if not records:
        return None, None
    return backtest_records(records, "最近3次推荐")


def backtest_today():
    """回测当天所有推荐（12点用）"""
    records = get_today_recommendations()
    if not records:
        return None, None
    return backtest_records(records, f"今日汇总({len(records)}次)")


def print_backtest(results: list, summary: str):
    """打印回测结果表格"""
    if not results:
        return

    print()
    print(f'  {"=" * 60}')
    print(f'  ★ {summary}')
    print(f'  {"=" * 60}')

    for r in results:
        dir_cn = '做空' if r['direction'] == 'short' else '做多'
        status = r['status']

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
        if status == '到TP1盈利':
            pnl_str = f'+${abs(pnl):.2f} (+{abs(pnl_pct):.2f}%) TP1达成'
        elif status == '爆仓':
            pnl_str = f'-${abs(pnl):.2f} ({pnl_pct:+.2f}%) 爆仓'
        elif status == '浮盈':
            pnl_str = f'+${abs(pnl):.2f} ({pnl_pct:+.2f}%)'
        elif status == '浮亏':
            pnl_str = f'-${abs(pnl):.2f} ({pnl_pct:+.2f}%)'
        else:
            pnl_str = f'-- (挂单中)'

        elapsed = r.get('elapsed', 0)
        if elapsed < 3600:
            time_str = f'{elapsed/60:.0f}分'
        elif elapsed < 86400:
            time_str = f'{elapsed/3600:.1f}小时'
        else:
            time_str = f'{elapsed/86400:.1f}天'

        print(f'  {icon} {r["base"]:<6} {dir_cn}  {time_str}  {pnl_str}')
        print(f'     入场={r["entry"]}  当前={r.get("current_price","?")}  TP1={r["tp1"]}')

    print(f'  {"=" * 60}')
    print()
