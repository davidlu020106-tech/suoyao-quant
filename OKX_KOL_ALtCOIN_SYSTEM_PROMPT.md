# OKX 山寨币 KOL 共识阻力位分析系统提示词

> 集成 **crypto-kol-quant（锁妖塔）** 99 位加密 KOL × 87 个量化因子 + OKX 实时数据
> 生成时间：2026-07-15

---

## 系统概述

本系统是一个双层分析引擎：

```
┌─────────────────────────────────────────────┐
│           山寨币分析报告                      │
├─────────────────────────────────────────────┤
│  Layer 1: 技术面阻力位分析                    │
│   ├─ Pivot Point R1/R2/S1/S2                │
│   ├─ Fibonacci 回撤位                        │
│   ├─ MA 趋势 + RSI 动量 + 成交量确认          │
│   └─ 10分制入场评分 + 止盈/止损建议            │
├─────────────────────────────────────────────┤
│  Layer 2: KOL 量化因子共识                    │
│   ├─ 87 个因子评估器（技术/周期/链上/宏观）     │
│   ├─ 99 位交易员档案加权                      │
│   ├─ 因子触发统计（多/空/中性）                │
│   └─ 加权偏度计算                            │
└─────────────────────────────────────────────┘
```

---

## 环境配置

### 工作区路径

```
C:\Users\VT\AppData\Roaming\reasonix\global-workspace\k线\山寨币\
└── crypto-kol-quant/                # 克隆的 repo 根目录
    ├── quant_factors/               # Python 量化引擎
    │   ├── run_altcoin_consensus.py  # ★ 统一启动脚本
    │   ├── okx_data_adapter.py      # OKX 实时数据适配层
    │   ├── local_config.py          # API 密钥 + 路径配置
    │   ├── feature_engine.py        # 特征引擎（原项目）
    │   ├── capabilities/            # 87 个因子评估器
    │   │   ├── __init__.py
    │   │   ├── registry.py          # 因子注册中心
    │   │   ├── indicators.py        # 技术指标类因子
    │   │   ├── cycle.py             # 周期类因子
    │   │   ├── pattern.py           # 形态类因子
    │   │   ├── regime.py            # 市场状态类
    │   │   ├── macro.py             # 宏观类因子
    │   │   ├── onchain.py           # 链上数据类
    │   │   ├── derivatives.py       # 衍生品信号
    │   │   ├── structural.py        # 结构性因子
    │   │   ├── risk.py              # 风险管理
    │   │   └── events.py            # 事件驱动
    │   ├── trader_composite.py      # 交易员复合信号
    │   ├── consensus_now.py         # 共识快照
    │   ├── render_consensus.py      # Plotly 可视化
    │   └── run_consensus.py         # 原项目入口（仅BTC/ETH/SOL/DOGE）
    ├── profiles_v2/                 # 99 位 KOL 交易员档案
    │   ├── Yodaskk.json
    │   ├── LedgerStatus.json
    │   ├── ... (99 files)
    ├── ohlc_daily.json              # 缓存的价格数据
    └── macro_daily.json             # 宏观数据（DXY/GOLD/SPX/US2Y）
```

### Python 依赖

```
pip install ccxt pandas numpy plotly scipy pyarrow
```

### API 密钥配置

配置文件：`crypto-kol-quant/quant_factors/local_config.py`

```python
OKX_API_KEY = 'bad0d891-b7b6-4624-8458-738fc6f2b3b9'
OKX_SECRET_KEY = 'AFCF************************C6AD'
OKX_PASSPHRASE = 'LMM1*****************************************lbl@'
```

---

## 使用方法

### 方式一：一键运行（推荐）

```bash
# 进入工作区
cd crypto-kol-quant

# 快速分析前15个山寨币（仅阻力位，秒出）
python quant_factors/run_altcoin_consensus.py

# 分析前30个币种
python quant_factors/run_altcoin_consensus.py --top 30

# 指定币种（含完整KOL因子分析）
python quant_factors/run_altcoin_consensus.py --coins SOL,XRP,DOGE,PI,ZEC

# 快速模式（不含KOL因子分析，只做阻力位）
python quant_factors/run_altcoin_consensus.py --quick
```

### 方式二：分步执行

```python
from quant_factors.run_altcoin_consensus import run_pipeline

# 全自动分析
results = run_pipeline(top_n=20, quick=False)

# 结果包含每个币种的完整分析
for r in results:
    print(f"{r['base']}: score={r['entry']['score']} signal={r['entry']['signal']}")
    print(f"  R1={r['levels']['r1']:.4f} R2={r['levels']['r2']:.4f}")
    print(f"  Entry zone: {r['entry']['entry_zone']}")
```

### 方式三：原项目 KOL 共识（仅 BTC/ETH/SOL/DOGE）

```bash
cd crypto-kol-quant
python quant_factors/run_consensus.py BTCUSDT
# 输出 consensus_snapshot.html + consensus_snapshot.json
```

### 方式四：数据适配器独立使用

```python
from quant_factors.okx_data_adapter import (
    fetch_altcoin_list, fetch_ohlc, build_altcoin_panel
)

# 获取当前最活跃的山寨币
altcoins = fetch_altcoin_list(top_n=20)

# 获取单个币种 OHLC
candles = fetch_ohlc('SOL/USDT', bar='1D', limit=100)

# 全自动构建特征面板
panel, ohlc_data, coin_list = build_altcoin_panel(top_n=30, lookback_days=365)
```

---

## 核心算法说明

### 阻力位计算（Pivot Point Standard）

```
Pivot = (H + L + C) / 3
R1 = 2 * Pivot - L         # 第一阻力 → TP1
R2 = Pivot + (H - L)       # 第二阻力 → TP2
S1 = 2 * Pivot - H         # 第一支撑
S2 = Pivot - (H - L)       # 第二支撑 → 止损
```

### Fibonacci 辅助位

```
Fib_382 = High_50d - 0.382 * (High_50d - Low_50d)
Fib_618 = High_50d - 0.618 * (High_50d - Low_50d)
```

### 入场评分体系（10分制）

| 维度 | 权重 | 说明 |
|------|------|------|
| 支撑位距离 | 3.0 | 越接近 S1/S2 得分越高 |
| RSI 位置 | 2.0 | 超卖区加分，超买区扣分 |
| 趋势方向 | 2.0 | MA50/MA200 多头发散加分 |
| 成交量确认 | 1.5 | 放量加分 |
| 阻力位空间 | 1.5 | R1/R2 空间越大加分越多 |

评分信号：
- **≥7.0**：STRONG BUY — 强烈买入信号
- **5.0-6.9**：BUY — 温和买入
- **3.0-4.9**：WATCH — 观望，等待更好入场
- **<3.0**：PASS — 跳过

### 止盈策略

```
TP1 = R1      (分批止盈 30%)
TP2 = R2      (分批止盈 40%)
TP3 = R2 + (R2 - Close)  (剩余 30%，追踪)
止损 = S2
```

### KOL 共识算法

87 个因子分别输出 `[-1, +1]` 范围内的分数：
- **> 0.05**：看多信号
- **< -0.05**：看空信号
- **其他**：中性

加权偏度 = Σ(因子分数) / Σ(|因子分数|)

---

## KOL 因子分类（87个）

| 类别 | 数量 | 示例因子 |
|------|------|---------|
| 技术指标 (indicator_rule) | 9 | RSI背离/金叉死叉/布林带/斐波那契/均线收复 |
| 周期 (cycle) | 3 | 4年周期/减半周期 |
| 市场状态 (regime) | 4 | 趋势/盘整/强势上升/强势下降 |
| 形态 (pattern_setup) | 12 | SFP假突破/流动性清扫/箱体边缘/三角收敛 |
| 结构性 (structural_bias) | 8 | 价格行为/趋势延续/高点低点结构 |
| 宏观 (macro_correlation) | 8 | DXY逆相关/SPX联动的金/美债利率 |
| 衍生品 (derivatives_signal) | 6 | 资金费率/未平仓量/多空比 |
| 链上 (onchain_signal) | 8 | MVRV Z-Score/NVT/NUPL/长期持有者 |
| 风险 (risk_rule) | 5 | 波动率/相关性/尾部风险 |
| 事件 (event_reaction) | 4 | 减半/ETF/监管/CPI |
| 涌现 (emerged) | 20 | 用户自定义的新因子 |

---

## 输出示例

```text
+=== 山寨币 KOL 共识阻力位分析引擎 ===+
|  OKX + 锁妖塔(99 KOL / 87 因子)         |
+=========================================+

  时间: 2026-07-15 15:44 UTC

========================================================================================================================
  山寨币多维度分析报告 — 2026-07-15 15:44 UTC
========================================================================================================================

  # 币种         价格       信号            评分        R1        R2        S1        S2       MA50     MA200   RSI   24hVol
------------------------------------------------------------------------------------------------------------------------
  1 PI          0.0835  [BUY]BUY       6.0     0.0891    0.0946    0.0763    0.0691      0.12      0.17  21.2     1.7x
  2 HYPE       66.9470  [BUY]BUY       5.8    68.1950   69.4430   65.0700   63.1930     65.56     42.91  51.6     0.5x
  3 ZEC       551.0600  [BUY]BUY       5.0   569.1367  587.2133  534.3567  517.6533    467.62    380.13  63.7     1.3x
  4 BTC     64627.2000 [WATCH]WATCH    4.8 65181.8667 65736.5333 64168.0667 63708.9333 64174.86 73601.04  54.5     0.5x
  5 ETH      1869.7900 [WATCH]WATCH    4.8  1891.2433 1912.6967 1854.6333 1839.4767  1748.38  2206.70  60.9     0.3x
------------------------------------------------------------------------------------------------------------------------
  [BUY!] STRONG BUY >=7  [BUY] BUY 5-7  [WATCH] WATCH 3-5  [PASS] PASS <3

*** 最佳入场候选 (Top 5) ***

  PI           [BUY] 评分: 6.0/10
               当前: $0.0835  |  Pivot: $0.0819
               第一阻力 R1: $0.0891 (TP1)
               第二阻力 R2: $0.0946 (TP2)
               第一支撑 S1: $0.0763
               第二支撑 S2: $0.0691
               入场区: $0.0691 - $0.0763
               止盈: TP1=$0.0891 | TP2=$0.0946 | TP3=$0.1058
               止损: $0.0691  |  RSI: 21.2
               依据: below MA50, above S1; RSI oversold; downtrend (below MA200); high volume; R2 headroom 13.3%
               KOL因子: 多=0 空=2 中性=85  偏=-1.0000
```

---

## 扩展指南

### 添加新的交易对

1. **自动接入**：`run_altcoin_consensus.py` 会自动按成交量筛选
2. **手动指定**：`--coins SOL,XRP,DOGE`
3. **代码接入**：直接调用 `okx_data_adapter.fetch_altcoin_list()`

### 在 OKX 添加新的 K 线时间周期

在 `okx_data_adapter.py` 中修改：
```python
# 支持：1m,3m,5m,15m,30m,1H,2H,4H,6H,12H,1D,2D,3D,1W,1M,3M
candles = fetch_ohlc('SOL/USDT', bar='4H', limit=500)
```

### 添加自定义因子

1. 在 `quant_factors/capabilities/` 下新建 Python 文件
2. 使用 `@register(id, type, bias, confidence)` 装饰器
3. 函数签名：`def my_factor(feat: pd.DataFrame) -> CapabilityOutput`

### 连接其他交易所

只需替换 `okx_data_adapter.py` 中的 `get_exchange()` 函数，切换到任何 ccxt 支持的交易所。

---

## FMZ 量化策略移植说明

您提供的 FMZ Binance 期货 bot 的核心逻辑已迁移到本系统：

| FMZ 原逻辑 | 本系统实现 |
|------------|-----------|
| `exchange.GetAccount()` | `okx_data_adapter.get_exchange()` |
| `exchange.GetPosition()` | 通过 ticker 价格 + 特征跟踪 |
| 持仓再平衡 | 改为"入场评分 + 阻力位"决策 |
| `LogStatus(table)` | 格式化表格输出 |
| 多币种管理 | `fetch_altcoin_list()` 自动筛选 |
| 冰山委托 | 保留为策略建议 |

---

## 安全提示

- ⚠️ API 密钥已配置在 `local_config.py`，请勿提交到公开仓库
- ⚠️ 本工具仅提供分析建议，不执行自动交易
- ⚠️ 加密货币交易风险极高，请做好风险管理
- ⚠️ 回测 ≠ 实盘，KOL 因子历史 IC 不代表未来收益

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `quant_factors/run_altcoin_consensus.py` | ★ 一键执行入口 |
| `quant_factors/okx_data_adapter.py` | OKX 实时数据获取 + 特征计算 |
| `quant_factors/local_config.py` | API 密钥 + 工作区路径配置 |
| `quant_factors/feature_engine.py` | 88 个技术特征计算（原项目） |
| `quant_factors/capabilities/` | 87 个 KOL 量化因子 |
| `quant_factors/trader_composite.py` | 99 位交易员复合信号 |
| `quant_factors/consensus_now.py` | 实时共识快照 |
| `quant_factors/render_consensus.py` | Plotly 可视化渲染 |
| `profiles_v2/` | 99 位 KOL 交易员档案 |
| `ohlc_daily.json` | 历史日线数据缓存 |
| `macro_daily.json` | 宏观数据缓存（DXY/GOLD/SPX） |
