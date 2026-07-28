"""
审判系统主入口 — 全市场扫描 + 交叉验证

用法:
  python judge_system/run_judge.py                     # 默认40币
  python judge_system/run_judge.py --top 60            # 扫描60币
  python judge_system/run_judge.py --coins BTC,ETH     # 指定币种
  python judge_system/run_judge.py --compare            # 与锁妖塔对比

数据流:
  1. 从 OKX 获取活跃币种列表
  2. 对每个币种获取 15m K线
  3. 运行5个检测器 → 独立评分
  4. 聚合结果 → 6维度校验
  5. 与锁妖塔对比（可选）
  6. 输出审判 verdict
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'quant_factors'))

from judge_system.judge_config import JudgeConfig
from judge_system.judge_engine import JudgeEngine, JudgeVerdict
from judge_system.detector_registry import (
    register_detector, list_detectors, run_all, aggregate_results
)


def ensure_detectors_registered():
    """确保所有检测器已注册"""
    from judge_system.detectors.fvg_detector import FvgDetector
    from judge_system.detectors.cvd_divergence import CvdDivergenceDetector
    from judge_system.detectors.mtf_liquidity_sweep import MtfLiquiditySweepDetector
    from judge_system.detectors.liquidity_cascade import LiquidityCascadeDetector
    from judge_system.detectors.sentiment_oscillator import SentimentOscillatorDetector

    existing = list_detectors()
    detectors = [
        ('fvg_detector', FvgDetector()),
        ('cvd_divergence', CvdDivergenceDetector()),
        ('mtf_liquidity_sweep', MtfLiquiditySweepDetector()),
        ('liquidity_cascade', LiquidityCascadeDetector()),
        ('sentiment_oscillator', SentimentOscillatorDetector()),
    ]
    for name, inst in detectors:
        if name not in existing:
            register_detector(inst)


def fetch_coin_list(top_n: int) -> list:
    """从 OKX 获取活跃币种列表"""
    try:
        from okx_data_adapter import fetch_altcoin_list
        coins = fetch_altcoin_list(top_n)
        return [c['base'] for c in coins] if coins else []
    except Exception as e:
        print(f"[警告] OKX API 不可用: {e}")
        # 返回测试币种
        return ['BTC', 'ETH', 'SOL', 'DOGE', 'ADA', 'LPT', 'WLD', 'KAITO']


def fetch_coin_data(symbol: str, timeframe: str = '15m', limit: int = 200):
    """获取单个币种数据"""
    try:
        from okx_data_adapter import fetch_ohlc
        raw = fetch_ohlc(f"{symbol}USDT", timeframe, limit)
        if raw and len(raw) >= 50:
            import pandas as pd
            df = pd.DataFrame(raw)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'vol_currency']
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
    except Exception as e:
        print(f"  [警告] {symbol} 数据获取失败: {e}")
    return None


def load_pagoda_results() -> dict:
    """加载锁妖塔的扫描结果"""
    # 尝试从两个可能的输出文件加载
    candidates = [
        os.path.join(PROJECT_ROOT, 'quant_factors', 'altcoin_5m_kol_ranking.json'),
        os.path.join(PROJECT_ROOT, 'quant_factors', 'daily_picks.json'),
    ]

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list) or len(data) == 0:
                continue

            results = {}
            for item in data:
                symbol = item.get('base', '')
                if not symbol:
                    continue

                # 处理 altcoin_5m_kol_ranking.json 格式
                if 'kol_long' in item and 'kol_short' in item:
                    kol_long = item.get('kol_long', 0)
                    kol_short = item.get('kol_short', 0)
                    total = kol_long + kol_short
                    if total > 0:
                        direction = 'long' if kol_long > kol_short else 'short'
                        score = (kol_long - kol_short) / total * (item.get('score', 5) or 5) / 5
                    else:
                        direction = 'neutral'
                        score = 0
                    detail = f"KOL: {kol_long}/{kol_short} ADX:{item.get('adx','?')}"
                # 处理 daily_picks.json 格式
                elif 'm5_bias' in item and 'daily_bias' in item:
                    m5_dir = item.get('m5_bias', 'neutral')
                    daily_dir = item.get('daily_bias', 'neutral')
                    # 如果双周期一致，用日线方向
                    if m5_dir == daily_dir:
                        direction = daily_dir
                    elif item.get('consistent'):
                        direction = daily_dir
                    else:
                        direction = 'neutral'
                    m5_l = item.get('m5_long', 0)
                    m5_s = item.get('m5_short', 0)
                    total = m5_l + m5_s
                    score = ((m5_l - m5_s) / max(total, 1)) * (item.get('adx', 25) / 50) if total > 0 else 0
                    detail = f"KOL: {m5_l}/{m5_s} ADX:{item.get('adx','?')} 一致:{item.get('consistent','?')}"
                else:
                    continue

                results[symbol] = {
                    'direction': direction,
                    'score': score,
                    'detail': detail,
                }

            if results:
                src = os.path.basename(path)
                print(f"[审判系统] 已加载锁妖塔结果: {src} ({len(results)}币)")
                return results

        except Exception as e:
            print(f"[警告] 加载 {path} 失败: {e}")

    print("[审判系统] 未找到锁妖塔结果，将独立运行（无对比）")
    return {}


def print_verdict_table(verdicts: dict, top_n: int = 20):
    """打印审判结果表格"""
    print("\n" + "=" * 90)
    print("锁妖塔审判系统 — 全市场扫描结果")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 90)

    headers = ['#', '币种', '审判方向', '评分', '置信度', '分歧', '详细检测']
    print(f"{'#':>3} {'币种':<8} {'方向':<10} {'评分':<8} {'置信度':<8} {'分歧':<6} {'检测器':<30}")
    print("-" * 90)

    sorted_coins = sorted(verdicts.items(),
                          key=lambda x: abs(x[1].judge_score),
                          reverse=True)

    for i, (symbol, v) in enumerate(sorted_coins[:top_n], 1):
        dir_icon = {'long': 'LONG', 'short': 'SHORT', 'neutral': '---'}.get(v.judge_direction, '???')
        dis_icon = '!!' if v.disagreement else '--'
        det_summary = ' | '.join([
            f"{n}:{d.direction[:1]}{d.score:.1f}"
            for n, d in v.detector_results.items()
            if d.triggered or abs(d.score) > 0.1
        ])[:35]

        print(f"{i:>3} {symbol:<8} {dir_icon:<10} {v.judge_score:<8.3f} "
              f"{v.judge_confidence:<8.2f} {dis_icon:<6} {det_summary:<30}")

    print("-" * 90)

    # 分歧汇总
    disagreements = [(s, v) for s, v in verdicts.items() if v.disagreement]
    if disagreements:
        print(f"\n分歧币种 ({len(disagreements)}):")
        for symbol, v in disagreements:
            print(f"  {symbol}: 锁妖塔={v.pagoda_direction} 审判={v.judge_direction} "
                  f"| {v.disagreement_detail}")


def main():
    parser = argparse.ArgumentParser(description='锁妖塔审判系统')
    parser.add_argument('--top', type=int, default=JudgeConfig.TOP_N,
                        help=f'扫描币种数量 (默认 {JudgeConfig.TOP_N})')
    parser.add_argument('--coins', type=str, default=None,
                        help='指定币种，逗号分隔')
    parser.add_argument('--compare', action='store_true',
                        help='与锁妖塔结果对比')
    parser.add_argument('--timeframe', type=str, default='15m',
                        help='K线周期 (默认 15m)')
    parser.add_argument('--save', action='store_true',
                        help='保存结果到 JSON')
    args = parser.parse_args()

    # 确保检测器注册
    ensure_detectors_registered()
    print(f"检测器: {list_detectors()}")

    # 获取币种列表
    if args.coins:
        symbols = [c.strip().upper() for c in args.coins.split(',')]
    else:
        symbols = fetch_coin_list(args.top)

    print(f"扫描币种: {len(symbols)}")
    if not symbols:
        print("无币种可扫描")
        return

    # 加载锁妖塔结果（可选）
    pagoda_results = load_pagoda_results() if args.compare else {}

    # 初始化引擎
    engine = JudgeEngine()

    # 扫描每个币种
    verdicts = {}
    for i, symbol in enumerate(symbols, 1):
        print(f"\r[{i}/{len(symbols)}] {symbol}...", end='', flush=True)
        df = fetch_coin_data(symbol, args.timeframe)
        if df is None:
            continue

        pagoda = pagoda_results.get(symbol)
        verdict = engine.scan_coin(symbol, df, pagoda)
        verdicts[symbol] = verdict

    print()

    # 输出结果
    print_verdict_table(verdicts)

    # 保存
    if args.save:
        path = engine.save_verdicts(verdicts)
        print(f"\n结果已保存: {path}")

    # 引擎摘要
    engine.print_summary(verdicts)


if __name__ == '__main__':
    main()
