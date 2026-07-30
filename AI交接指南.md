# 锁妖塔量化交易系统 — AI交接指南

## 你需要先读的文件（按顺序）

1. `quant_factors/run_daily_picks.py` — 主入口（~1100行），看懂 `analyze_coin()` 和 `run()` 的流程
2. `quant_factors/position_gauges.py` — 12维位置共识（百分位+速度）
3. `quant_factors/super_trend.py` — 20维超级趋势检测
4. `judge_system/detector_registry.py` — 审判系统聚合逻辑
5. `judge_system/backtest_log.py` — 回测（check_path_kbar逐K线回放）

## 给你的提示词

直接把下面这段话发给另一个AI：

```
你是一个Python量化交易系统的开发者。项目在 GitHub: davidlu020106-tech/suoyao-quant。

系统架构:
- 入口: quant_factors/run_daily_picks.py → analyze_coin() 对单币分析 → run() 扫全量
- 数据: OKX API → okx_data_adapter.build_features_single() → 90列特征DataFrame
- KOL投票: 99个交易员×88因子 → kol_vote() 输出多空比
- 过滤: alignment≥0.3 + ADX≥20 + 位置冲突排除 → passed列表
- 综合评分: p_score(锁妖塔40%)+j_score(审判25%)+ts_score(趋势20%)+pos_score(位置15%)
- 审判系统: 5个检测器 → 加权聚合, 方向阈值0.06, 只扫passed币
- 回测: 推荐时保存15m K线快照, check_path_kbar()逐K线回放

改动规则:
1. 所有新参数加可选默认值，不破坏现有调用
2. 不要改 kol_vote() 的KOL加权逻辑
3. 不要改 entry_planner.py 的入场计算
4. 不要改 backtest_log.py 的 save_recommendation 格式
5. 审判系统方向判定不改动（0.06阈值）

推送前:
- python -c "import py_compile; py_compile.compile('文件.py',doraise=True)"
- git add . && git commit -m "..." && git -c http.proxy= push origin main

关键变量:
- feats DataFrame 列: close,high,low,open,volume,ma7-ma200,ema20,ema50,atr14,adx14,rsi14,bb_*,kc_*,pivot,r1,s1,high_20d,low_20d,high_50d,low_50d
- 币种结果dict字段: base,direction,entry,adx,rsi,tp1_profit,pos_score,pos_speed,pos_grade,pos_bias,alignment,alignment_grade,super_label,kol_consensus,htf_bias,mtf_bias,ltf_bias
```

## 常见改动指南

### 加新的过滤条件
- 位置: `analyze_coin()` 的 `passed` 过滤块
- 代码位置: 约第636-650行

### 改综合评分权重
- 位置: 约第870-880行, `final_score = (p_score*0.40 + ...)`
- p_score 公式: 约第838行

### 改KOL共识权重
- 位置: 约第425行, `kol_consensus = htf_pol*0.50 + mtf_pol*0.30 + ltf_pol*0.20`

### 改位置判断阈值
- 代码: `position_gauges.py` 的 `evaluate_all_positions()` 最后的分级逻辑

### 加新模块
- 文件放 `quant_factors/`
- 在 `analyze_coin()` 里 try-except 调用
- 结果加到返回 dict
- 需要显示的话加到对应的 print 行

## 推送命令
```bash
python -c "import py_compile; py_compile.compile('quant_factors/run_daily_picks.py',doraise=True);print('OK')"
git add .
git commit -m "feat/fix: 描述"
git -c http.proxy= push origin main
```
