"""
检测器注册中心 — 管理所有审判检测器的注册、查找和批量执行

类似 capabilities/registry.py 的设计模式。
"""

from typing import Dict, List, Optional, Type
import pandas as pd

from judge_system.base_detector import BaseDetector, DetectorResult


# 全局注册表
_DETECTOR_REGISTRY: Dict[str, BaseDetector] = {}


def register_detector(detector: BaseDetector) -> BaseDetector:
    """
    注册一个检测器实例

    Args:
        detector: 检测器实例

    Returns:
        检测器实例本身
    """
    name = detector.name
    if name in _DETECTOR_REGISTRY:
        raise ValueError(f"检测器 '{name}' 已注册")
    _DETECTOR_REGISTRY[name] = detector
    return detector


def unregister_detector(name: str):
    """注销检测器"""
    _DETECTOR_REGISTRY.pop(name, None)


def get_detector(name: str) -> Optional[BaseDetector]:
    """按名称获取检测器"""
    return _DETECTOR_REGISTRY.get(name)


def list_detectors() -> List[str]:
    """列出所有已注册的检测器名称"""
    return list(_DETECTOR_REGISTRY.keys())


def run_all(symbol: str, df: pd.DataFrame, **kwargs) -> Dict[str, DetectorResult]:
    """
    运行所有已注册的检测器

    Args:
        symbol: 币种名称
        df: OHLC DataFrame
        **kwargs: 额外参数
            data_period: '15m' / '1H' / '4H' / '1D' 自动调整检测器窗口
            bars_per_unit: 等效日线K线数 (96=15m, 24=1H, 6=4H, 1=日线)

    Returns:
        {检测器名称: DetectorResult} 字典
    """
    results = {}
    for name, detector in _DETECTOR_REGISTRY.items():
        try:
            results[name] = detector.detect(symbol, df, **kwargs)
        except Exception as e:
            results[name] = DetectorResult(
                detector_name=name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                triggered=False,
                detail=f"检测异常: {e}"
            )
    return results


def aggregate_results(results: Dict[str, DetectorResult]) -> DetectorResult:
    """
    聚合多个检测器的结果为一个综合结果

    使用加权平均：每个检测器的 score * confidence / sum(confidence)

    Args:
        results: {检测器名称: DetectorResult} 字典

    Returns:
        聚合后的 DetectorResult
    """
    if not results:
        return DetectorResult(
            detector_name='aggregate',
            direction='neutral',
            score=0.0,
            confidence=0.0,
            detail='无检测器运行'
        )

    total_weight = 0.0
    weighted_score = 0.0
    triggered_count = 0
    active_count = 0  # 非中性检测器数量
    details = []

    for name, r in results.items():
        w = r.confidence  # ★ 修复: 只用信心度加权, 不用score²
        weighted_score += r.score * w
        total_weight += w
        if r.triggered:
            triggered_count += 1
        if r.direction != 'neutral':
            active_count += 1  # ★ 修复: 中性检测器不计入分母
        if r.triggered or abs(r.score) > 0.05:
            details.append(f"{name}: {r.direction}({r.score:.3f})")

    if total_weight > 0:
        agg_score = weighted_score / total_weight
    else:
        agg_score = 0.0

    # 判断方向
    if agg_score > 0.1:
        direction = 'long'
    elif agg_score < -0.1:
        direction = 'short'
    else:
        direction = 'neutral'

    # ★ 修复: 置信度只基于有方向的检测器, 中性不算不同意
    confidence = min(1.0, (triggered_count / max(1, active_count)) * 0.6 + abs(agg_score) * 0.4)

    return DetectorResult(
        detector_name='aggregate',
        direction=direction,
        score=agg_score,
        confidence=confidence,
        triggered=abs(agg_score) > 0.1,
        detail=' | '.join(details)
    )
