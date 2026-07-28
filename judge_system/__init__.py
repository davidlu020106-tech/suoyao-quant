"""
锁妖塔审判系统 — 独立验证模块

对锁妖塔系统的输出进行独立多维度交叉验证，
从FMZ/GitHub特色策略中提取检测逻辑，
输出审判 verdict 供综合决策参考。
"""

from judge_system.judge_config import JudgeConfig
from judge_system.base_detector import BaseDetector, DetectorResult
from judge_system import detector_registry as DetectorRegistry
from judge_system.judge_engine import JudgeEngine

__version__ = "0.1.0"
