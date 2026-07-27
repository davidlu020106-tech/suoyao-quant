"""检查具体入场价→TP1价在72h内的历史出现次数"""

import requests, time

def check_tp1_history(base, entry_price, tp1_price, direction, tolerance=0.003):
    """检查历史上当价格到过入场价附近时，72h内是否到过TP1价。
    
    Args:
        base: 币种名 e.g. 'BCH'
        entry_price: 具体入场价
        tp1_price: 具体TP1价
        direction: 'BUY' 或 'SELL'
        tolerance: 价格匹配容差 (默认0.3%)
    
    Returns:
        dict: {hit, total, rate}
    """
    try:
        # 取500根1H K线 ≈ 20天
        d = requests.get(
            'https://www.okx.com/api/v5/market/candles?instId='+base+'-USDT&bar=1H&limit=500',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10
        ).json()
        raw = d.get('data', [])
        if not raw: return {'hit': 0, 'total': 0, 'rate': 0}
        raw.reverse()
        
        closes = [float(x[4]) for x in raw]
        highs = [float(x[2]) for x in raw]
        lows = [float(x[3]) for x in raw]
        
        hit = 0
        total = 0
        entry_band = entry_price * tolerance
        
        for i in range(len(closes) - 72):  # 留72小时窗口
            if abs(closes[i] - entry_price) <= entry_band:
                total += 1
                window_high = max(highs[i:i+72])
                window_low = min(lows[i:i+72])
                
                if direction == 'SELL':
                    if window_low <= tp1_price:
                        hit += 1
                else:
                    if window_high >= tp1_price:
                        hit += 1
        
        rate = hit / total * 100 if total > 0 else 0
        return {'hit': hit, 'total': total, 'rate': round(rate, 1)}
    except Exception as e:
        return {'hit': 0, 'total': 0, 'rate': 0, 'error': str(e)[:40]}
