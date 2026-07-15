import requests, pandas as pd, json, time
from datetime import datetime

CAPITALE_INIZIALE = 50.0
MAX_POSITIONS = 3
RISCHIO_PER_TRADE = 0.03
TARGET_PER_TRADE = 0.05
SCANNER_TOP_N = 100
TIMEFRAME = "1h"
COMMISSIONE = 0.001

FILE_POSIZIONI = "posizioni.json"
FILE_DASHBOARD = "dashboard_data.json"
LOG = []

def log(msg): 
    print(msg)
    LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_top_100():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency": "usdt", "order": "volume_desc", "per_page": SCANNER_TOP_N, "page": 1}, timeout=10)
        return [x['symbol'].upper() + "USDT" for x in r.json() if x.get('total_volume',0) > 5000000]
    except:
        return ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]

def get_klines(symbol):
    r = requests.get(f"https://api.binance.com/api/v3/klines", params={"symbol": symbol, "interval": TIMEFRAME, "limit": 200})
    if r.status_code!= 200: return pd.DataFrame()
    df = pd.DataFrame(r.json(), columns=['t','o','h','l','c','v','ct','qv','n','tbb','tbq','x'])
    df['c'] = df['c'].astype(float); df['v'] = df['v'].astype(float)
    return df

def get_fear_greed():
    try: return int(requests.get("https://api.alternative.me/fng/").json()['data'][0]['value'])
    except: return 50

def get_eur_usdt():
    try: return 1 / requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()['rates']['EUR']
    except: return 0.92

def calc_indicatori(df):
    if len(df) < 200: return None
    df['SMA50'] = df['c'].rolling(50).mean()
    df['SMA200'] = df['c'].rolling(200).mean()
    df['EMA21'] = df['c'].ewm(span=21).mean()
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    df['VOL_MED'] = df['v'].rolling(20).mean()
    return df.iloc[-1]

def valuta_coin(symbol):
    df = get_klines(symbol); last = calc_indicatori(df)
    if last is None: return 0, 0, ["Pochi dati"], {}
    punteggio = 0; motivi = []; dati = {}
    dati['prezzo'] = last['c']; dati['rsi'] = last['RSI']; dati['vol'] = last['v']
    if last['SMA50'] > last['SMA200']: punteggio += 1
    else: motivi.append("Trend KO")
    if 40 < last['RSI'] < 65: punteggio += 1
    else: motivi.append(f"RSI {last['RSI']:.1f}")
    if last['v'] > last['VOL_MED'] * 2: punteggio += 1
    else: motivi.append("Vol basso")
    if last['c'] > last['EMA21']: punteggio += 1
    else: motivi.append("Sotto EMA21")
    return punteggio, last['c'], motivi, dati

def salva_posizioni(pos):
    with open(FILE_POSIZIONI, 'w') as f: json.dump(pos, f)
def carica_posizioni():
    try: return json.load(open(FILE_POSIZIONI, 'r'))
    except: return []

def salva_dashboard(saldo_eur, fg, posizioni, scartati, comprati, venduti):
    data = {
        "timestamp": str(datetime.now()),
        "saldo_eur": saldo_eur, "fear_greed": fg,
        "posizioni": posizioni, "scartati": scartati,
        "comprati": comprati, "venduti": venduti, "log": LOG[-20:]
    }
    with open(FILE_DASHBOARD, 'w') as f: json.dump(data, f)

def main():
    log("Avvio Scanner Smart 50€")
    posizioni = carica_posizioni()
    capitale_libero = CAPITALE_INIZIALE - sum([p['investito'] for p in posizioni])
    fg = get_fear_greed(); eur = get_eur_usdt()
    log(f"F&G: {fg} | Capitale: {capitale_libero:.2f}€")
    scartati = []; comprati = []; venduti = []
    
    salva_dashboard(capitale_libero * eur, fg, posizioni, scartati, comprati, venduti)
    
    for p in posizioni[:]:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={p['symbol']}")
        if r.status_code!= 200: continue
        prezzo_att = float(r.json()['price'])
        pnl = (prezzo_att - p['entry']) / p['entry']
        p['pnl'] = pnl * 100
        if pnl >= TARGET_PER_TRADE or pnl <= -RISCHIO_PER_TRADE:
            log(f"VENDO {p['symbol']} PnL: {pnl*100:.2f}%")
            venduti.append({"symbol": p['symbol'], "pnl": f"{pnl*100:.2f}%"})
            posizioni.remove(p)
            capitale_libero += p['investito'] * (1 + pnl - COMMISSIONE)
    
    if len(posizioni) < MAX_POSITIONS and fg < 75 and capitale_libero > 15:
        log("Scannerizzo top 20...")
        candidati = []
        for sym in get_top_100()[:20]:
            score, price, motivi, dati = valuta_coin(sym)
            if score >= 3: candidati.append({"symbol": sym, "price": price, "score": score, "dati": dati})
            else: scartati.append({"symbol": sym, "motivo": ", ".join(motivi)})
            time.sleep(0.2)
        
        candidati = sorted(candidati, key=lambda x: x['score'], reverse=True)
        for c in candidati[:MAX_POSITIONS - len(posizioni)]:
            investito = capitale_libero / (MAX_POSITIONS - len(posizioni))
            log(f"COMPRO {c['symbol']} a {c['price']:.4f} Score: {c['score']}/4")
            comprati.append(c)
            posizioni.append({"symbol": c['symbol'], "entry": c['price'], "investito": investito, "pnl": 0})
            capitale_libero -= investito
    
    salva_posizioni(posizioni)
    totale_usdt = capitale_libero
    for p in posizioni:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={p['symbol']}")
        if r.status_code == 200:
            prezzo_att = float(r.json()['price'])
            p['pnl'] = ((prezzo_att - p['entry'])/p['entry'])*100
            totale_usdt += p['investito'] * (1 + (prezzo_att - p['entry'])/p['entry'])
    
    salva_dashboard(totale_usdt * eur, fg, posizioni, scartati[:10], comprati, venduti)
    log("Ciclo completato")

if __name__ == "__main__": main()
