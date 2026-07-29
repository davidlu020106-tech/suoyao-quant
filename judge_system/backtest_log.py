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
    except Exception as e:
        print(f'[backtest] load_history error: {e}')
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
    except Exception as e:
        print(f'[backtest] save error: {e}')


def get_current_prices(symbols: list) -> dict:
    """获取多个币种的当前价格（从OKX ticker接口）"""
    prices = {}
    try:
        from okx_data_adapter import _api_get as api_get
        # ★ 修复: 回测使用 SPOT 价格, 与入场品种类型一致
        resp = api_get('/api/v5/market/tickers?instType=SPOT')
        if resp.get('code') == '0':
            for item in resp.get('data', []):
                inst = item['instId']  # e.g. BTC-USDT (SPOT)
                base = inst.replace('-USDT', '')
                if base in symbols:
                    prices[base] = {
                        'last': float(item.get('last', 0)),
                        'high24h': float(item.get('high24h', 0)),
                        'low24h': float(item.get('low24h', 0)),
                    }
    except Exception as e:
        print(f'[backtest] get_current_prices error: {e}')
    # 补缺失的
    for sym in symbols:
        if sym not in prices:
            prices[sym] = None
    return prices


def check_path(prices: dict, entry: float, tp1: float, liq: float,
               direction: str, lev: float):
    """
    ★ 修复: 用24H高低点判断价格路径(先到TP1还是先爆仓)
    
    Returns:
        'tp1_hit': 先到TP1 → 触发止盈
        'liq_hit': 先到爆仓 → 止损
        'floating': 两点都没到 → 浮盈/浮亏
        'unknown': 数据不足
    """
    high = prices.get('high24h', 0) if prices else 0
    low = prices.get('low24h', 0) if prices else 0
    current = prices.get('last', entry) if prices else entry

    if not high or not low:
        # 没有24H高低点数据, 回退到用当前价判断
        if direction == 'short':
            return 'liq_hit' if current >= liq else ('tp1_hit' if current <= tp1 else 'floating')
        else:
            return 'liq_hit' if current <= liq else ('tp1_hit' if current >= tp1 else 'floating')

    if direction == 'short':
        tp1_reached = low <= tp1
        liq_reached = high >= liq
    else:
        tp1_reached = high >= tp1
        liq_reached = low <= liq

    if tp1_reached and liq_reached:
        return 'tp1_hit'  # 两者都到 → 保守判TP1(先触发的概率更高)
    elif tp1_reached:
        return 'tp1_hit'
    elif liq_reached:
        return 'liq_hit'
    return 'floating'


def check_path_kbar(kline_snapshot: list, entry: float, tp1: float, liq: float,
                    direction: str, current_price: float = None):
    """
    ★ 逐K线回放 (替代只看24H高低点)
    
    从推荐时的K线快照中逐根K线判断先到TP1还是先爆仓。
    对比 check_path() 的优势:
      - 不依赖OKX的24H高低点(只能看最近24h)
      - 能精确判断TP1和爆仓的先后顺序
      - 推荐3天前做的也能准确判断
    
    Args:
        kline_snapshot: 推荐时的15m OHLC列表 [{open,high,low,close,volume}, ...]
        entry/tp1/liq: 入场价/止盈价/强平价
        direction: 'long'/'short'
        current_price: 当前最新价格 (可选, 用于补齐快照之后的价格变动)
    
    Returns:
        'tp1_hit': 先到TP1
        'liq_hit': 先到爆仓
        'floating': 两点都没到(快照内未触发, 用current_price判断最终状态)
        'no_data': 快照为空
    """
    if not kline_snapshot or len(kline_snapshot) < 1:
        return 'no_data'

    for bar in kline_snapshot:
        h = float(bar.get('high', 0))
        l = float(bar.get('low', 0))
        if direction == 'short':
            if l <= tp1:
                return 'tp1_hit'
            if h >= liq:
                return 'liq_hit'
        else:
            if h >= tp1:
                return 'tp1_hit'
            if l <= liq:
                return 'liq_hit'

    # K线快照内未触发 → 用当前价判断
    if current_price and current_price != entry:
        if direction == 'short':
            return 'tp1_hit' if current_price <= tp1 else ('liq_hit' if current_price >= liq else 'floating')
        else:
            return 'tp1_hit' if current_price >= tp1 else ('liq_hit' if current_price <= liq else 'floating')

    return 'floating'


def backtest_records(records: list, label: str = "上次推荐"):
    all_results = []
    total_recs = 0
    total_ok = 0
    total_fail = 0
    total_floating = 0
    total_unknown = 0
    total_pnl = 0.0
    total_pnl_pct = 0.0

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
                total_unknown += 1
                continue

            current = price_data['last']
            # ★ 修复: 两单合计50U
            pos_size = 50
            if direction == 'short':
                pnl_pct = (entry - current) / entry * 100
                pnl_usdt = (entry - current) / entry * pos_size * lev
            else:
                pnl_pct = (current - entry) / entry * 100
                pnl_usdt = (current - entry) / entry * pos_size * lev

            # ★ 逐K线回放优先, 回退到24H高低点
            kline_snap = r.get('df_15m_snapshot', [])
            if kline_snap:
                path = check_path_kbar(kline_snap, entry, tp1, liq, direction, current)
            else:
                path = check_path(price_data, entry, tp1, liq, direction, lev)

            if path == 'tp1_hit':
                # 计算TP1的实际利润(用lev×1/lev=100%)
                tp1_pnl = pos_size * 1.0  # 利润=本金
                status = '到TP1盈利'
                total_ok += 1
                pnl_usdt = tp1_pnl
                pnl_pct = 100.0
            elif path == 'liq_hit':
                status = '爆仓'
                total_fail += 1
                pnl_usdt = -pos_size  # 全损
                pnl_pct = -100.0
            else:
                if direction == 'short':
                    status = '浮盈' if current < entry else '浮亏'
                    total_floating += 1
                else:
                    status = '浮盈' if current > entry else '浮亏'
                    total_floating += 1

            total_pnl += pnl_usdt
            total_pnl_pct += pnl_pct

            all_results.append({
                'base': base, 'direction': direction,
                'entry': entry, 'tp1': tp1, 'liq': liq, 'lev': lev,
                'status': status, 'pnl_pct': round(pnl_pct, 2),
                'pnl_usdt': round(pnl_usdt, 2),
                'current_price': current, 'elapsed': elapsed,
                # ★ 上下文
                'adx': r.get('adx'), 'alignment': r.get('alignment'),
                'kol_15m': r.get('kol_15m', ''), 'kol_1h': r.get('kol_1h', ''),
            })

    # ★ 统计指标
    decided = total_ok + total_fail  # 已出结果的(到TP1或爆仓)
    win_rate = f'{total_ok/decided*100:.0f}%' if decided > 0 else 'N/A'
    avg_pnl = round(total_pnl / max(1, total_recs), 2)
    avg_pnl_pct = round(total_pnl_pct / max(1, total_recs), 2)
    profit_factor = f'{total_ok/max(1, total_fail):.2f}' if total_fail > 0 else ('∞' if total_ok > 0 else 'N/A')

    status_line = f'{total_ok}个到TP1 | {total_fail}个爆仓'
    if total_floating > 0:
        status_line += f' | {total_floating}个持仓中'
    if total_unknown > 0:
        status_line += f' | {total_unknown}个未知'

    summary = f'{label}: {total_recs}个推荐 | {status_line}'
    metrics = f'胜率={win_rate} 盈亏比={profit_factor} 均盈=${avg_pnl}({avg_pnl_pct:+.1f}%)'

    return all_results, summary, metrics


def backtest_last():
    """回测最近5次推荐"""
    records = get_recent_recommendations(5)
    if not records:
        return None, None, None
    return backtest_records(records, "最近5次推荐")


def backtest_today():
    """回测当天所有推荐（12点用）"""
    records = get_today_recommendations()
    if not records:
        return None, None, None
    return backtest_records(records, f"今日汇总({len(records)}次)")


def print_backtest(results: list, summary: str, metrics: str = ''):
    """打印回测结果表格"""
    if not results:
        return

    print()
    print(f'  {"=" * 60}')
    print(f'  ★ {summary}')
    if metrics:
        print(f'  ★ {metrics}')
    print(f'  {"=" * 60}')

    for r in results:
        dir_cn = '做空' if r['direction'] == 'short' else '做多'
        status = r['status']

        if status == '到TP1盈利':
            icon = '[TP1]'
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
            pnl_str = f'+${abs(pnl):.2f} TP1达成'
        elif status == '爆仓':
            pnl_str = f'-${abs(pnl):.2f} 爆仓'
        elif status == '浮盈':
            pnl_str = f'+${abs(pnl):.2f} ({pnl_pct:+.1f}%)'
        elif status == '浮亏':
            pnl_str = f'-${abs(pnl):.2f} ({pnl_pct:+.1f}%)'
        else:
            pnl_str = f'--'

        elapsed = r.get('elapsed', 0)
        if elapsed < 3600:
            time_str = f'{elapsed/60:.0f}分'
        elif elapsed < 86400:
            time_str = f'{elapsed/3600:.1f}小时'
        else:
            time_str = f'{elapsed/86400:.1f}天'

        # 显示上下文
        ctx = ''
        if r.get('alignment'):
            ctx += f' {r["alignment"]}'
        if r.get('kol_15m'):
            ctx += f' KOL={r["kol_15m"]}'

        print(f'  {icon} {r["base"]:<6} {dir_cn}  {time_str}  {pnl_str}{ctx}')
        print(f'     入场={r["entry"]}  当前={r.get("current_price","?")}  TP1={r["tp1"]}  lev={r.get("lev",20)}x')

    print(f'  {"=" * 60}')
    print()
