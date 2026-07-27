"""Fetch derivatives data (OI, funding, L/S ratio) from OKX public API"""
import requests, time

def get_oi(instId):
    """Get open interest for a swap contract"""
    try:
        r = requests.get('https://www.okx.com/api/v5/public/open-interest?instId='+instId,
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10).json()
        if r.get('code') == '0' and r.get('data'):
            d = r['data'][0]
            return {
                'oi': float(d.get('oi', 0)),        # in contracts
                'oi_usd': float(d.get('oiUsd', 0)),  # in USD
                'oi_ccy': float(d.get('oiCcy', 0)),  # in coin
            }
    except: pass
    return None

def get_funding(instId):
    """Get current funding rate for a swap contract"""
    try:
        r = requests.get('https://www.okx.com/api/v5/public/funding-rate?instId='+instId,
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10).json()
        if r.get('code') == '0' and r.get('data'):
            d = r['data'][0]
            return {
                'funding_rate': float(d.get('fundingRate', 0)),  # e.g. 0.00005 = 0.005%
                'funding_time': int(d.get('fundingTime', 0)),
                'next_rate': float(d.get('nextFundingRate', 0)) if d.get('nextFundingRate') else None,
            }
    except: pass
    return None

def get_ls_ratio(ccy, period='1D'):
    """Get long/short account ratio"""
    try:
        r = requests.get('https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy='+ccy+'&period='+period+'&limit=1',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10).json()
        if r.get('code') == '0' and r.get('data'):
            return float(r['data'][-1][1])  # latest ratio
    except: pass
    return None

def get_all_derivatives(base):
    """Get all derivatives data for a coin"""
    inst = base + '-USDT-SWAP'
    result = {'funding_rate': 0, 'oi_usd': 0, 'oi_change_24h': 0, 'ls_ratio': 1.0}
    
    oi = get_oi(inst)
    if oi:
        result['oi_usd'] = oi['oi_usd']
    
    funding = get_funding(inst)
    if funding:
        result['funding_rate'] = funding['funding_rate']
    
    ls = get_ls_ratio(base)
    if ls:
        result['ls_ratio'] = ls
    
    return result

if __name__ == '__main__':
    for base in ['BTC', 'ETH', 'SOL', 'EDGE', 'APE']:
        d = get_all_derivatives(base)
        fr = d['funding_rate']*100
        oi = d['oi_usd']/1e6
        ls = d['ls_ratio']
        print(f'{base:<6s} funding={fr:+.4f}%  oi=${oi:.1f}M  L/S={ls:.2f}')
        time.sleep(0.2)
