"""
审判系统配置模块

控制审判系统的全局参数、检测器权重、阈值等。
"""

import os


class JudgeConfig:
    """审判系统全局配置"""

    # ─── 路径 ───
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    QUANT_FACTORS_DIR = os.path.join(PROJECT_ROOT, "quant_factors")

    # ─── 扫描范围 ───
    TOP_N = 40                 # 前 N 个活跃币种
    MIN_R1 = 1.5               # 最低波动率过滤（%）
    MIN_OI = 600_000           # 最低持仓量（USD）

    # ─── 综合评分权重 ───
    # 最终评分 = 锁妖塔评分 * LOCK_PAGODA_WEIGHT + 审判评分 * JUDGE_WEIGHT
    LOCK_PAGODA_WEIGHT = 0.55
    JUDGE_WEIGHT = 0.45

    # ─── 检测器置信度阈值 ───
    DETECTOR_LONG_THRESHOLD = 0.15     # 检测器 > 此值 = 看多
    DETECTOR_SHORT_THRESHOLD = -0.15   # 检测器 < 此值 = 看空
    DETECTOR_STRONG_THRESHOLD = 0.35   # 强信号阈值

    # ─── 分歧判定 ───
    DISAGREE_DIRECTION_THRESHOLD = 0.3  # 方向差异超过此值标记为分歧
    DISAGREE_SCORE_GAP = 2.0            # 评分差异超过此值标记为分歧

    # ─── CVD 背离检测器 ───
    CVD_EMA_LENGTH = 20       # CVD 计算 EMA 周期
    CVD_DIVERGENCE_LOOKBACK = 30  # 背离回溯周期
    CVD_MIN_DIVERGENCE_SCORE = 0.05  # 最小背离幅度

    # ─── FVG 检测器 ───
    FVG_LOOKBACK = 5          # FVG 回溯周期数
    FVG_MIN_GAP_PCT = 0.001   # 最小缺口比例（0.1%）

    # ─── 多TF流动性扫荡 ───
    MTF_HIGH_TF = "240"       # 高时间框架（240分钟=4小时）
    MTF_LOW_TF = "15"         # 低时间框架（15分钟）
    MTF_SL_FACTOR = 1.5       # 止损乘数
    MTF_TP_FACTOR = 3.0       # 止盈乘数

    # ─── 流动性级联 ───
    CASCADE_MA_PERIOD = 50    # 均线周期
    CASCADE_DEVIATION_THRESHOLD = 0.08  # 偏离阈值（8%）
    CASCADE_EXTREME_THRESHOLD = 0.15    # 极端偏离阈值（15%）

    # ─── 情绪震荡器 ───
    SENTIMENT_LOOKBACK = 49     # 情绪回溯周期
    SENTIMENT_FAST_EMA = 40     # 快EMA
    SENTIMENT_SLOW_EMA = 204    # 慢EMA
    SENTIMENT_SIGNAL_LEN = 20   # 信号线周期
    SENTIMENT_OVERBOUGHT = 0.6  # 超买阈值
    SENTIMENT_OVERSOLD = -0.6   # 超卖阈值

    # ─── 宏观压制检测 ───
    MACRO_DXY_STRENGTH_THRESHOLD = 1.0   # DXY 20日涨幅 > 1% = 美元强势
    MACRO_SPX_WEAK_THRESHOLD = -2.0      # SPX 20日跌幅 > 2% = 风险偏好下降
    MACRO_GOLD_SURGE_THRESHOLD = 3.0     # 黄金 20日涨幅 > 3% = 避险情绪

    @classmethod
    def to_dict(cls):
        """将所有配置项转为字典，供日志/序列化使用"""
        return {k: v for k, v in cls.__dict__.items()
                if not k.startswith('_') and k.isupper()}
