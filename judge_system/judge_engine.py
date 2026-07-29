"""
审判引擎 — 协调所有检测器，执行全市场扫描，输出审判结果

工作流程:
1. 从 OKX 获取活跃币种列表
2. 对每个币种获取 OHLC 数据
3. 运行所有已注册检测器
4. 聚合检测结果
5. 与锁妖塔输出交叉对比
6. 输出审判结果
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from judge_system.judge_config import JudgeConfig
from judge_system.base_detector import DetectorResult
from judge_system.detector_registry import (
    register_detector, run_all, aggregate_results, list_detectors
)


@dataclass
class JudgeVerdict:
    """
    审判 verdict — 对一个币种的完整审判结果

    Attributes:
        symbol: 币种名称
        judge_score: 审判系统综合评分 [-1, +1]
        judge_direction: 审判方向 'long' / 'short' / 'neutral'
        judge_confidence: 审判置信度 [0, 1]
        detector_results: 各检测器结果
        pagoda_score: 锁妖塔评分（如提供）
        pagoda_direction: 锁妖塔方向
        disagreement: 是否与锁妖塔分歧
        disagreement_detail: 分歧原因
        verdict: 最终结论
    """
    symbol: str
    judge_score: float = 0.0
    judge_direction: str = 'neutral'
    judge_confidence: float = 0.0
    detector_results: Dict[str, DetectorResult] = field(default_factory=dict)
    pagoda_score: Optional[float] = None
    pagoda_direction: Optional[str] = None
    pagoda_detail: Optional[str] = None
    disagreement: bool = False
    disagreement_detail: str = ''
    verdict: str = '观望'

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'judge_score': round(self.judge_score, 4),
            'judge_direction': self.judge_direction,
            'judge_confidence': round(self.judge_confidence, 4),
            'detectors': {k: {
                'direction': v.direction,
                'score': round(v.score, 4),
                'confidence': round(v.confidence, 4),
                'triggered': v.triggered,
                'detail': v.detail
            } for k, v in self.detector_results.items()},
            'pagoda_score': round(self.pagoda_score, 4) if self.pagoda_score else None,
            'pagoda_direction': self.pagoda_direction,
            'disagreement': self.disagreement,
            'disagreement_detail': self.disagreement_detail,
            'verdict': self.verdict,
        }


class JudgeEngine:
    """
    审判引擎 — 核心调度器
    """

    def __init__(self, config: JudgeConfig = None):
        self.config = config or JudgeConfig()
        self._initialized = False

    def initialize(self):
        """初始化：注册所有检测器"""
        if self._initialized:
            return

        # 注册内置检测器
        self._register_builtin_detectors()

        self._initialized = True

    def _register_builtin_detectors(self):
        """注册内置检测器（如果尚未注册）"""
        from judge_system import detector_registry as reg

        # (模块路径, 类名, 注册名)
        detector_classes = [
            ("judge_system.detectors.cvd_divergence", "CvdDivergenceDetector", "cvd_divergence"),
            ("judge_system.detectors.fvg_detector", "FvgDetector", "fvg_detector"),
            ("judge_system.detectors.mtf_liquidity_sweep", "MtfLiquiditySweepDetector", "mtf_liquidity_sweep"),
            ("judge_system.detectors.liquidity_cascade", "LiquidityCascadeDetector", "liquidity_cascade"),
            ("judge_system.detectors.sentiment_oscillator", "SentimentOscillatorDetector", "sentiment_oscillator"),
        ]

        for module_path, class_name, reg_name in detector_classes:
            if reg.get_detector(reg_name) is not None:
                continue  # 已注册，跳过
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                reg.register_detector(cls())
            except (ImportError, AttributeError) as e:
                print(f'  [Judge] detector {class_name} load error: {e}')

    def scan_coin(self, symbol: str, df: pd.DataFrame,
                  pagoda_result: Optional[dict] = None,
                  **kwargs) -> JudgeVerdict:
        """
        对单个币种执行审判扫描

        Args:
            symbol: 币种名称
            df: OHLC DataFrame
            pagoda_result: 锁妖塔对该币种的分析结果（可选）
            **kwargs: 额外参数传给检测器

        Returns:
            JudgeVerdict
        """
        if not self._initialized:
            self.initialize()

        # 1. 运行所有检测器
        detector_results = run_all(symbol, df, **kwargs)

        # 2. 聚合检测结果
        agg = aggregate_results(detector_results)

        # 3. 构建 verdict
        verdict = JudgeVerdict(
            symbol=symbol,
            judge_score=agg.score,
            judge_direction=agg.direction,
            judge_confidence=agg.confidence,
            detector_results=detector_results,
        )

        # 4. 与锁妖塔对比（如提供）
        if pagoda_result:
            self._compare_with_pagoda(verdict, pagoda_result)

        # 5. 生成最终结论
        verdict.verdict = self._generate_verdict(verdict)

        return verdict

    def _compare_with_pagoda(self, verdict: JudgeVerdict,
                              pagoda_result: dict):
        """与锁妖塔结果对比，标记分歧"""
        # 提取锁妖塔方向
        pagoda_dir = pagoda_result.get('direction', 'neutral')
        pagoda_score = pagoda_result.get('score', 0)
        pagoda_detail = pagoda_result.get('detail', '')

        verdict.pagoda_direction = pagoda_dir
        verdict.pagoda_score = pagoda_score
        verdict.pagoda_detail = pagoda_detail

        # 判断方向分歧
        judge_dir = verdict.judge_direction

        if judge_dir == 'neutral' or pagoda_dir == 'neutral':
            # 有一方中立不算分歧
            verdict.disagreement = False
            return

        # 方向相反 = 严重分歧
        if (judge_dir == 'long' and pagoda_dir == 'short') or \
           (judge_dir == 'short' and pagoda_dir == 'long'):
            verdict.disagreement = True
            verdict.disagreement_detail = (
                f"方向相反！锁妖塔看{pagoda_dir}，审判系统看{judge_dir}"
            )
            return

        # 方向相同但评分差距大
        judge_score = verdict.judge_score
        score_gap = abs(judge_score) - abs(pagoda_score) if pagoda_score else 0
        if abs(score_gap) > self.config.DISAGREE_SCORE_GAP:
            verdict.disagreement = True
            verdict.disagreement_detail = (
                f"评分差距大：审判系统 {verdict.judge_score:.2f} vs "
                f"锁妖塔 {pagoda_score:.2f}"
            )

    def _generate_verdict(self, verdict: JudgeVerdict) -> str:
        """生成最终结论文字"""
        if verdict.disagreement:
            return f"⚠️ 分歧 — {verdict.disagreement_detail}"

        if abs(verdict.judge_score) < 0.1:
            return "⚪ 观望 — 审判系统无明显倾向"

        if verdict.judge_confidence < 0.3:
            return f"🟡 谨慎{verdict.judge_direction} — 置信度偏低"

        return f"🟢 支持{verdict.judge_direction} — 审判系统确认"

    def scan_market(self, coins_data: Dict[str, pd.DataFrame],
                    pagoda_results: Optional[Dict[str, dict]] = None,
                    **kwargs) -> Dict[str, JudgeVerdict]:
        """
        全市场扫描

        Args:
            coins_data: {symbol: df} 字典
            pagoda_results: {symbol: pagoda_result} 字典（可选）
            **kwargs: 额外参数

        Returns:
            {symbol: JudgeVerdict} 字典
        """
        if not self._initialized:
            self.initialize()

        verdicts = {}
        for symbol, df in coins_data.items():
            pagoda = (pagoda_results or {}).get(symbol)
            verdicts[symbol] = self.scan_coin(symbol, df, pagoda, **kwargs)

        return verdicts

    def save_verdicts(self, verdicts: Dict[str, JudgeVerdict],
                      output_dir: str = None):
        """保存审判结果到 JSON"""
        if output_dir is None:
            output_dir = self.config.QUANT_FACTORS_DIR

        data = {
            'timestamp': datetime.now().isoformat(),
            'judge_version': '0.1.0',
            'detectors_used': list_detectors(),
            'coins': {s: v.to_dict() for s, v in verdicts.items()}
        }

        path = os.path.join(output_dir, 'judge_verdict.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return path

    def print_summary(self, verdicts: Dict[str, JudgeVerdict]):
        """打印审判摘要"""
        print("\n" + "=" * 60)
        print("锁妖塔审判系统 — 扫描摘要")
        print("=" * 60)

        # 统计
        longs = sum(1 for v in verdicts.values() if v.judge_direction == 'long')
        shorts = sum(1 for v in verdicts.values() if v.judge_direction == 'short')
        neutrals = sum(1 for v in verdicts.values() if v.judge_direction == 'neutral')
        disagreements = sum(1 for v in verdicts.values() if v.disagreement)

        print(f"扫描币种: {len(verdicts)}")
        print(f"  看多: {longs} | 看空: {shorts} | 中性: {neutrals}")
        print(f"  与锁妖塔分歧: {disagreements}")

        if disagreements > 0:
            print("\n⚠️ 分歧币种:")
            for s, v in verdicts.items():
                if v.disagreement:
                    print(f"  {s}: 锁妖塔={v.pagoda_direction} | "
                          f"审判={v.judge_direction} | {v.disagreement_detail}")

        # 检测器统计
        detectors = list_detectors()
        if detectors:
            print(f"\n检测器 ({len(detectors)}):")
            for name in detectors:
                triggered = sum(
                    1 for v in verdicts.values()
                    if v.detector_results.get(name, DetectorResult()).triggered
                )
                print(f"  {name}: 触发 {triggered}/{len(verdicts)}")



