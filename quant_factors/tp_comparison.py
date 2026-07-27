"""Compare old pivot-based vs new ATR-based TP levels"""
import sys, json, urllib.request, time
sys.path.insert(0, 'quant_factors')

STABLE = {'USDT','USDC','DAI','TUSD','BUSD','FDUSD','USDP','EUR','GBP','AUD','SGD','AED','CNY','JPY','KRW','USDG','TRY','BRL','CAD','CHF','HKD','MXN'}

def api_get(p):
    url='https://www.okx.com'+p
    r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(r,timeout=15).read())

r=api_get('/api/v5/market/tickers?instType=SPOT')
coins=[]
for t in r.get('data',[]):
    inst=t['instId']
    if not inst.endswith('-USDT'): continue
    base=inst.replace('-USDT','')
    if base in STABLE: continue
    v=float(t.get('volCcy24h','0') or 0)
    if v>=500000: coins.append({'base':base,'symbol':inst,'vol':v})
coins.sort(key=lambda x:x['vol'],reverse=True)
coins=coins[:10]

print()
print(f'{"Coin":<8} {"OldR1%":>8} {"NewR1%":>8} {"OldR2%":>8} {"NewR2%":>8} {"Lev":>6} {"ATR##":>8}')
print('-'*60)

for c in coins[:10]:
    base=c['base']; sym=c['symbol']
    data=api_get('/api/v5/market/candles?instId='+sym+'&bar=5m&limit=200')
    raw=data.get('data',[])
    if not raw: continue
    raw.reverse()
    cls=[float(x[4]) for x in raw]
    his=[float(x[2]) for x in raw]
    los=[float(x[3]) for x in raw]
    cur=cls[-1]
    
    # ATR(14)
    tr=[]
    for i in range(1,len(raw)):
        tr.append(max(float(raw[i][2])-float(raw[i][3]), abs(float(raw[i][2])-float(raw[i-1][4])), abs(float(raw[i][3])-float(raw[i-1][4]))))
    atr=sum(tr[-14:])/14 if len(tr)>=14 else 1
    
    # Old: 200-bar pivot
    hh200=max(his); ll200=min(los)
    p200=(hh200+ll200+cur)/3; r1_old=2*p200-ll200; r2_old=p200+(hh200-ll200)
    
    # NEW: ATR multiples
    r1_new=cur+atr*1.5
    r2_new=cur+atr*3.0
    
    new_lev=min(125,cur/(atr*1.5)) if atr>0 else 1
    
    old1=(r1_old-cur)/cur*100
    new1=(r1_new-cur)/cur*100
    old2=(r2_old-cur)/cur*100
    new2=(r2_new-cur)/cur*100
    
    print(f'{base:<8s} {old1:>+7.2f}% {new1:>+7.2f}% {old2:>+7.2f}% {new2:>+7.2f}% {new_lev:>5.0f}x ${atr:>6.4f}')
    time.sleep(0.1)

print()
print('NEW method: TP1=atr*1.5, TP2=atr*3.0, Liq=atr*1.5 (adapts to volatility)')
