"""
KOL 绩效追踪 — 记录每个交易员的投票准确率，自动调整权重。

用法:
    from kol_tracker import load_weights, update_after_backtest
    
    # 投票前获取权重
    weights = load_weights(profiles)  # {handle: float}
    
    # 回测后更新权重
    update_after_backtest(bt_result, profiles, vote_record)
"""

import json
import os
import time
from datetime import datetime

_PERF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kol_performance.json')


def load_performance() -> dict:
    """加载KOL绩效数据 {handle: {correct, total, weight, last_updated}}"""
    if not os.path.exists(_PERF_PATH):
        return {}
    try:
        with open(_PERF_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_performance(perf: dict):
    """保存KOL绩效数据"""
    with open(_PERF_PATH, 'w', encoding='utf-8') as f:
        json.dump(perf, f, indent=2, ensure_ascii=False)


def load_weights(profiles: dict, min_samples: int = 5) -> dict:
    """加载KOL权重 {handle: float}, 默认1.0(等权)
    
    Args:
        profiles: KOL档案 {handle: profile_dict}
        min_samples: 最小样本量, 少于此次数时用默认权重1.0
    """
    perf = load_performance()
    weights = {}
    for handle in profiles:
        p = perf.get(handle)
        if p and p.get('total', 0) >= min_samples:
            # 贝叶斯平滑: (correct + 1) / (total + 2)
            weights[handle] = (p['correct'] + 1) / (p['total'] + 2)
        else:
            weights[handle] = 1.0
    return weights


def update_after_backtest(backtest_results: list, profiles: dict):
    """
    根据回测结果更新KOL绩效。
    
    对于每个到TP1的推荐: 所有投票方向正确的KOL +1 correct/+1 total
    对于每个爆仓的推荐: 所有投票方向错误的KOL +0 correct/+1 total
    
    Args:
        backtest_results: [{base, direction, status, ...}, ...] 来自backtest_log
        profiles: KOL档案
    """
    perf = load_performance()
    now = datetime.now().isoformat()

    for r in backtest_results:
        actual_dir = r.get('direction', '')
        status = r.get('status', '')

        if status not in ('到TP1盈利', '爆仓'):
            continue  # 只统计已出结果的推荐

        is_correct = (status == '到TP1盈利')
        
        for handle in profiles:
            if handle not in perf:
                perf[handle] = {'correct': 0, 'total': 0, 'weight': 1.0, 'last_updated': now}
            
            p = perf[handle]
            prof = profiles.get(handle, {})
            bias = prof.get('bias_default', 'neutral')
            
            # 判断该KOL的默认方向是否与推荐方向一致
            kol_dir = 'long' if bias in ('long', 'long_tilted') else ('short' if bias in ('short', 'short_tilted') else 'neutral')
            
            if kol_dir == 'neutral':
                continue  # 中性KOL不统计
            
            p['total'] += 1
            if (kol_dir == actual_dir and is_correct) or (kol_dir != actual_dir and not is_correct):
                p['correct'] += 1
            
            p['weight'] = (p['correct'] + 1) / (p['total'] + 2)
            p['last_updated'] = now

    save_performance(perf)


def get_stats() -> dict:
    """获取KOL绩效摘要"""
    perf = load_performance()
    total_kols = len(perf)
    active = sum(1 for p in perf.values() if p.get('total', 0) >= 5)
    avg_weight = sum(p.get('weight', 1.0) for p in perf.values()) / max(1, total_kols)
    return {
        'total_kols': total_kols,
        'active_kols': active,
        'avg_weight': round(avg_weight, 3),
        'path': _PERF_PATH,
    }
