"""
审判系统主入口 — 全市场扫描 + 交叉验证

用法:
  python judge_system/run_judge.py                     # 默认40币
  python judge_system/run_judge.py --top 60            # 扫描60币
  python judge_system/run_judge.py --coins BTC,ETH     # 指定币种
  python judge_system/run_judge.py --compare            # 与锁妖塔对比
  python judge_system/run_judge.py --table              # 只输出表格（给锁妖塔调用）
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
        result = [c['base'] for c in coins] if coins else []
        if result:
            return result
    except Exception as e:
        print(f"  [审判] OKX API不可用: {e}")
    # 回退列表
    return ['BTC', 'ETH', 'SOL', 'DOGE', 'ADA', 'LPT', 'WLD', 'KAITO', 'LINK', 'UNI',
            'XRP', 'AVAX', 'DOT', 'MATIC', 'ATOM', 'ARB', 'OP', 'APT', 'SUI', 'TIA']


def fetch_coin_data(symbol: str, timeframe: str = '15m', limit: int = 200):
    """获取单个币种数据"""
    try:
        from okx_data_adapter import fetch_ohlc
        raw = fetch_ohlc(f"{symbol}-USDT", timeframe, limit)
        if raw and len(raw) >= 50:
            import pandas as pd
            df = pd.DataFrame(raw)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'vol_currency']
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
    except Exception as e:
        pass
    return None


def load_pagoda_results() -> dict:
    """加载锁妖塔的扫描结果"""
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
                    detail = f"KOL:{kol_long}/{kol_short} ADX:{item.get('adx','?')}"
                elif 'm5_bias' in item and 'daily_bias' in item:
                    m5_dir = item.get('m5_bias', 'neutral')
                    daily_dir = item.get('daily_bias', 'neutral')
                    if m5_dir == daily_dir or item.get('consistent'):
                        direction = daily_dir
                    else:
                        direction = 'neutral'
                    m5_l = item.get('m5_long', 0)
                    m5_s = item.get('m5_short', 0)
                    total = m5_l + m5_s
                    score = ((m5_l - m5_s) / max(total, 1)) * (item.get('adx', 25) / 50) if total > 0 else 0
                    detail = f"KOL:{m5_l}/{m5_s} ADX:{item.get('adx','?')}"
                else:
                    continue

                results[symbol] = {'direction': direction, 'score': score, 'detail': detail}

            if results:
                return results
        except Exception:
            pass
    return {}


def print_verdict_table(verdicts: dict, pagoda: dict, top_n: int = 20):
    """
    以锁妖塔风格输出审判结果表格
    直接输出到 stdout，供锁妖塔调用
    """
    if not verdicts:
        print("  [审判] 无数据")
        return

    print()
    print(f'  {"─" * 55}')
    print(f'  ╔══ 审判系统验证 ═══════════════════════════╗')
    print(f'  ║  5检测器: CVD背离/FVG缺口/多TF扫荡/      ║')
    print(f'  ║           流动性级联/情绪震荡器           ║')
    print(f'  ╚═══════════════════════════════════════════╝')
    print(f'  {"─" * 55}')

    # 统计
    dis_count = sum(1 for v in verdicts.values() if v.disagreement)
    long_n = sum(1 for v in verdicts.values() if v.judge_direction == 'long')
    short_n = sum(1 for v in verdicts.values() if v.judge_direction == 'short')
    neutral_n = sum(1 for v in verdicts.values() if v.judge_direction == 'neutral')

    env = '偏多' if long_n > short_n * 2 else ('偏空' if short_n > long_n * 2 else '均衡')
    print(f'  大盘环境: {env}  |  看多={long_n} 看空={short_n} 中性={neutral_n}')
    if dis_count:
        print(f'  ⚠️ 与锁妖塔分歧: {dis_count}币')
    print(f'  {"─" * 55}')

    # ─── 做多推荐表 ───
    longs = [(s, v) for s, v in verdicts.items() if v.judge_direction == 'long']
    if longs:
        longs.sort(key=lambda x: x[1].judge_score, reverse=True)
        print(f'  ── 审判看多 ──')
        print(f'  {"#":>3} {"币种":<8} {"评分":>7} {"置信":>5} {"分歧":>4}  CVD    FVG    MTF    级联   情绪')
        print(f'  {"─" * 55}')
        for i, (symbol, v) in enumerate(longs[:10], 1):
            det = v.detector_results
            def ds(name):
                r = det.get(name)
                if not r: return '  -  '
                s = r.score
                return f'{s:+.2f}' if abs(s) > 0.05 else '  -  '
            dis = ' !!' if v.disagreement else '  -'
            print(f'  {i:>3} {symbol:<8} {v.judge_score:>+7.3f} {v.judge_confidence:>5.2f} {dis:>4}'
                  f'  {ds("cvd_divergence"):>6} {ds("fvg_detector"):>6} {ds("mtf_liquidity_sweep"):>6}'
                  f'  {ds("liquidity_cascade"):>6} {ds("sentiment_oscillator"):>6}')

    # ─── 做空推荐表 ───
    shorts = [(s, v) for s, v in verdicts.items() if v.judge_direction == 'short']
    if shorts:
        shorts.sort(key=lambda x: x[1].judge_score)
        print(f'  ── 审判看空 ──')
        print(f'  {"#":>3} {"币种":<8} {"评分":>7} {"置信":>5} {"分歧":>4}  CVD    FVG    MTF    级联   情绪')
        print(f'  {"─" * 55}')
        for i, (symbol, v) in enumerate(shorts[:10], 1):
            det = v.detector_results
            def ds(name):
                r = det.get(name)
                if not r: return '  -  '
                s = r.score
                return f'{s:+.2f}' if abs(s) > 0.05 else '  -  '
            dis = ' !!' if v.disagreement else '  -'
            print(f'  {i:>3} {symbol:<8} {v.judge_score:>+7.3f} {v.judge_confidence:>5.2f} {dis:>4}'
                  f'  {ds("cvd_divergence"):>6} {ds("fvg_detector"):>6} {ds("mtf_liquidity_sweep"):>6}'
                  f'  {ds("liquidity_cascade"):>6} {ds("sentiment_oscillator"):>6}')

    # ─── 分歧详情 ───
    disagreements = [(s, v) for s, v in verdicts.items() if v.disagreement]
    if disagreements:
        print(f'  {"─" * 55}')
        print(f'  ⚠️ 分歧币种详情:')
        for symbol, v in disagreements:
            det_details = []
            for n, d in v.detector_results.items():
                if d.triggered or abs(d.score) > 0.1:
                    det_details.append(f'{n.split("_")[0]}={d.direction[:1]}{d.score:.1f}')
            print(f'    {symbol}: 锁妖塔={v.pagoda_direction} 审判={v.judge_direction}'
                  f'  [{", ".join(det_details)}]')

    print(f'  {"─" * 55}')
    print(f'  检测器说明: CVD=CVD背离  FVG=FVG缺口  MTF=多TF扫荡')
    print(f'             级联=流动性级联  情绪=情绪震荡器')
    print()


def run_judge(top_n=40, coins=None, compare=True, save=False, table_only=False,
              coins_data=None):
    """
    审判系统主函数 — 供外部调用

    Args:
        top_n: 扫描币种数量
        coins: 指定币种列表（可选）
        compare: 是否与锁妖塔对比
        save: 是否保存JSON
        table_only: 是否只输出表格（供锁妖塔调用）
        coins_data: 预加载的 {symbol: DataFrame} 字典（复用锁妖塔数据）

    Returns:
        (verdicts dict, 分歧数量)
    """
    ensure_detectors_registered()

    # 获取币种列表
    if coins:
        symbols = [c.strip().upper() for c in coins]
    else:
        symbols = fetch_coin_list(top_n)

    if not symbols:
        print("  [审判] 无币种可扫描")
        return {}, 0

    # 加载锁妖塔结果
    pagoda_results = load_pagoda_results() if compare else {}

    # 初始化引擎
    engine = JudgeEngine()

    # 扫描每个币种
    verdicts = {}
    for i, symbol in enumerate(symbols, 1):
        if not table_only:
            print(f"\r  [审判] [{i}/{len(symbols)}] {symbol}...", end='', flush=True)
        
        # 优先复用预加载的数据
        if coins_data and symbol in coins_data:
            df = coins_data[symbol]
        else:
            df = fetch_coin_data(symbol)
        
        if df is None:
            continue
        pagoda = pagoda_results.get(symbol)
        verdict = engine.scan_coin(symbol, df, pagoda)
        verdicts[symbol] = verdict

    if not table_only:
        print()

    # 输出表格
    if verdicts:
        print_verdict_table(verdicts, pagoda_results)

    # 保存
    if save:
        path = engine.save_verdicts(verdicts)
        if not table_only:
            print(f"  [审判] 已保存: {path}")

    dis_count = sum(1 for v in verdicts.values() if v.disagreement)
    return verdicts, dis_count


def main():
    parser = argparse.ArgumentParser(description='锁妖塔审判系统')
    parser.add_argument('--top', type=int, default=JudgeConfig.TOP_N,
                        help=f'扫描币种数量 (默认 {JudgeConfig.TOP_N})')
    parser.add_argument('--coins', type=str, default=None, help='指定币种，逗号分隔')
    parser.add_argument('--compare', action='store_true', help='与锁妖塔结果对比')
    parser.add_argument('--save', action='store_true', help='保存结果到JSON')
    parser.add_argument('--table', action='store_true', help='只输出表格（供锁妖塔调用）')
    args = parser.parse_args()

    coins_list = [c.strip().upper() for c in args.coins.split(',')] if args.coins else None
    run_judge(top_n=args.top, coins=coins_list, compare=args.compare or args.table,
              save=args.save, table_only=args.table)


if __name__ == '__main__':
    main()
