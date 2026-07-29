# 锁妖塔量化交易系统 v2.0

把 99 个顶级加密交易员的经验炼成量化因子，每天全量扫描 OKX 山寨币，
三重时间框架（15m + 1H + 日线）KOL 共识 → 审判系统交叉验证 → 精准入场规划 → 自动回测。

```text
输入: OKX 前 50 个活跃币种
流程: 88因子×99KOL → 三重框架过滤 → 5审判检测器 → 综合评分 → 入场方案
输出: 综合推荐 Top 3 + 精准入场价 + 回测验证
```

---

## 核心架构

### 三重时间框架

| 层级 | 周期 | 数据量 | 职责 |
|---|---|---|---|
| **LTF** | 15m | 200根 (50h) | 入场时机、SMC信号、ORB区间、短期KOL |
| **MTF** | 1H | 168根 (7天) | **趋势仲裁者**、中期KOL共识 |
| **HTF** | 日线 | 200根 (8月) | 大趋势方向、Pivot支撑阻力 |

**对齐度评分：**
```
三重一致(1.0) → MTF+HTF一致(0.8) → LTF+MTF一致(0.6) → LTF+HTF一致(0.3) → 三向分歧(0.0)
方向仲裁链: MTF → HTF → LTF
```

### 数据流

```
OKX API → 88因子特征 → 99KOL投票 → 三重框架扫描
    ↓
过滤流水线: 对齐度≥0.6 + ADX≥25 + TP1利润≥100%
    ↓
审判系统 5检测器 → 独立验证 → 分歧标记
    ├── CVD背离检测器       (资金流向)
    ├── FVG缺口检测器        (公允价值)
    ├── 多TF流动性扫荡       (结构突破)
    ├── 流动性级联捕捉       (极端偏离)
    └── 情绪震荡器           (一致性陷阱)
    ↓
反转向量检测: 假突破 + 供需区 + 突破陷阱
趋势强度: (ema7-ema90)/(atr/close) 方向对齐
    ↓
综合推荐 Top 3（四维评分）
    ├── 锁妖塔评分 ×0.2
    ├── 审判评分 ×0.3
    ├── 反转向量 ×0.25
    └── 趋势强度 ×0.25
    ↓
精准入场方案（每个推荐币）
    ├── ICT OTE 第一入场 (20U)
    ├── 海龟回撤 第二入场 (30U)
    └── 强平价 = 理论 ×70%
    ↓
回测上次推荐（最近3次 + 12点整日汇总）
```

---

## 快速开始

```bash
# 一键全量扫描+推荐+审判+入场+回测
python quant_factors/run_daily_picks.py

# 指定参数
python quant_factors/run_daily_picks.py --top 30 --min-r1 2.0 --min-oi 1000000

# 指定币种
python quant_factors/run_daily_picks.py --coins BCH,LPT,UNI

# 单独运行审判系统
python judge_system/run_judge.py --top 40 --compare
```

### CI 自动运行

每小时第 5 分钟自动执行（GitHub Actions），手机适配输出顺序：
1. 综合推荐 Top 3（第一眼）
2. 精准入场方案（第二眼）
3. 回测上次推荐（第三眼）
4. 锁妖塔扫描详情（全量排名/推荐/分批入场）
5. 审判系统验证（检测器评分/分歧币种）

---

## 文件结构

```
suoyao-quant/
├── quant_factors/                  ★ 锁妖塔扫描系统
│   ├── run_daily_picks.py          ★ 主入口（全量扫描+推荐+审判+入场+回测）
│   ├── run_5m_kol_consensus.py     5分钟扫描（备用）
│   ├── okx_data_adapter.py         OKX数据接口层 + normalize_ohlc_df
│   ├── feature_engine.py           特征工程（~90列技术特征）
│   ├── entry_timing.py             入场时机分析（ORB/VWAP）
│   ├── smc_entry_signal.py         SMC结构分析
│   ├── local_config.py             API密钥配置
│   ├── capabilities/               88个因子评估器
│   │   ├── registry.py            因子注册中心
│   │   ├── indicators.py          技术指标（9个）
│   │   ├── patterns.py            形态识别（22个）
│   │   ├── structural.py          结构性偏斜（8个）
│   │   ├── cycle.py               周期因子（2个）
│   │   ├── regime.py              市场状态（5个）
│   │   ├── macro.py               宏观相关性（7个）
│   │   ├── derivatives.py         衍生品信号（7个）
│   │   ├── onchain.py             链上信号（5个）
│   │   ├── risk.py                风险管理（3个）
│   │   ├── events.py              事件驱动（2个）
│   │   └── emerged.py             涌现因子（18个）
│   └── capabilities_v1.json       470条能力库
│
├── judge_system/                   ★ 审判系统
│   ├── __init__.py                 模块入口
│   ├── judge_config.py            全局配置（33项参数）
│   ├── base_detector.py           检测器基类
│   ├── detector_registry.py       注册中心（聚合权重置信度）
│   ├── judge_engine.py            审判引擎（扫描/对比/分歧检测）
│   ├── run_judge.py               审判系统主入口
│   ├── entry_planner.py           精准入场规划器（ICT OTE/海龟回撤）
│   ├── backtest_log.py            推荐回测系统
│   └── detectors/                 5个核心检测器
│       ├── cvd_divergence.py      CVD背离检测
│       ├── fvg_detector.py        FVG缺口检测
│       ├── mtf_liquidity_sweep.py  多TF流动性扫荡
│       ├── liquidity_cascade.py    流动性级联捕捉
│       └── sentiment_oscillator.py 情绪震荡器
│
├── profiles_v2/                   99个交易员档案JSON
├── .github/workflows/hourly_scan.yml  CI配置
└── 系统使用文档_v2.md             完整文档
```

---

## 关键配置

| 参数 | 默认值 | 说明 |
|---|---|---|
| 强平价 | 理论 ×70% | 维持保证金占用 |
| 杠杆 | OKX最大 | 从API实时获取 |
| TP1 | 利润=本金 | entry × (1 ± 1/lev) |
| 仓位 | 20U + 30U | 分批入场 |
| LTF K线 | 15m × 200 | ~50小时覆盖 |
| MTF K线 | 1H × 168 | 7天趋势仲裁 |
| HTF K线 | 日线 × 200 | 8个月大趋势 |

---

## 已修复的问题

系统上线后修复了 9/10 个导致推荐变反指的核心问题：

| # | 问题 | 修复 |
|---|---|---|
| ① | 情绪检测器需250根K线→永久失效 | 改为60根+NaN防护 |
| ② | 中性KOL默认做空→系统偏空 | 三路分支，中性跳过 |
| ③ | "20日"实际是20根K线=5小时 | 标记为后续迭代（需HTF/LTF分离） |
| ④ | 综合评分score²加权 | 改为仅信心度加权 |
| ⑤ | Pivot来自15m范围 | 改用日线high/low |
| ⑥ | 回测用合约价验证现货 | 改用SPOT价格 |
| ⑦ | ADX两套实现不一致 | 统一使用 calc_adx |
| ⑧ | API错误全部静默 | 替换为带日志异常处理 |
| ⑨ | 趋势强度clamp丢方向 | 返回raw+aligned双值 |
| ⑩ | 数据列名不一致 | 新增 normalize_ohlc_df |

---

## 参考的 FMZ 策略

系统设计参考了 FMZ 策略广场的 50+ 策略，核心 10 组对照：

| 问题 | FMZ参考策略 | 核心启示 |
|---|---|---|
| 三重时间框架 | 15m突破多框架协同 / Ichimoku云 / 双趋势过滤 | HTF定方向/MTF仲裁/LTF执行 |
| 审判交叉验证 | 复合CTA系统 / KOL蒸馏共识v4.0 | 多检测器等权投票 |
| 精准入场 | Camarilla枢轴 / Overnight Fibonacci | ICT OTE+海龟回撤双入场 |
| 情绪判断 | ADX-RSI联动 / 暗度陈仓双向 | RSI+ADX组合只需30根K线 |

---

## ⚠️ 声明

这是研究项目，不是交易建议。回测 ≠ 实盘。杠杆交易存在爆仓风险。
请自行承担风险。

## License

MIT
