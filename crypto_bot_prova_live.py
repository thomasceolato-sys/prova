import requests
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime

# ===== CONFIG =====
CAPITALE_INIZIALE = 50.0 # €
MAX_POSITIONS = 3
RISCHIO_PER_TRADE = 0.03 # 3% SL
TARGET_PER_TRADE = 0.05 # 5% TP
SCANNER_TOP_N = 100
TIMEFRAME = "1h"
COMMISSIONE = 0.001 # 0.1%

FILE_POSIZIONI = "posizioni.json"
FILE_STORICO = "storico.json"

# ===== UTILS =====
def get_top_100():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usdt", "order": "volume_desc", "per_page": SCANNER_TOP_N, "page": 1}
    r = requests.get(url, params=params).json()
    return [x['symbol'].upper() + "USDT" for x in r if x['total_volume'] > 5000000]

def get_klines(symbol):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": TIMEFRAME, "limit": 200}
    r = requests.get(url, params=params).json()
    df = pd.DataFrame(r, columns=['t','o','h','l','c','v','ct','qv','n','tbb','tbq','x'])
    df['c'] = df['c'].astype(float)
    df['v'] = df['v'].astype(float)
    return df

def get_fear_greed():
    r = requests.get("https://api.alternative.me/fng/").json()
    return int(r['data'][0]['value'])

def get_eur_usdt():
    r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT").json()
    return float(r['price'])

def calc_indicatori(df):
    df['SMA50'] = df['c'].rolling(50).mean()
    df['SMA200'] = df['c'].rolling(200).mean()
    df['EMA21'] = df['c'].ewm(span=21).mean()
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['VOL_MED'] = df['v'].rolling(20).mean()
    return df.iloc[-1]

def valuta_coin(symbol):
    try:
        df = get_klines(symbol)
        last = calc_indicatori(df)
        punteggio = 0
        motivi = []
        if last['SMA50'] > last['SMA200']: punteggio += 1
        else: motivi.append("Trend ribassista")
        if 40 < last['RSI'] < 65: punteggio += 1
        else: motivi.append(f"RSI {last['RSI']:.1f}")
        if last['v'] > last['VOL_MED'] * 2: punteggio += 1
        else: motivi.append("Volume basso")
        if last['c'] > last['EMA21']: punteggio += 1
        else: motivi.append("Sotto EMA21")
        return punteggio, last['c'], motivi
    except: return 0, 0, ["Errore dati"]

def salva_posizioni(pos):
    with open(FILE_POSIZIONI, 'w') as f: json.dump(pos, f)
def carica_posizioni():
    try: 
        with open(FILE_POSIZIONI, 'r') as f: return json.load(f)
    except: return []

# ===== LOGICA BOT =====
def main():
    print(f"[{datetime.now()}] Avvio Scanner Smart 50€")
    posizioni = carica_posizioni()
    capitale_libero = CAPITALE_INIZIALE - sum([p['investito'] for p in posizioni])
    fg = get_fear_greed()
    eur = get_eur_usdt()
    print(f"Fear & Greed: {fg} | Capitale libero: {capitale_libero:.2f}€")
    
    # 1. GESTISCI POSIZIONI APERTE
    for p in posizioni[:]:
        prezzo_att = float(requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={p['symbol']}").json()['price'])
        pnl = (prezzo_att - p['entry']) / p['entry']
        if pnl >= TARGET_PER_TRADE or pnl <= -RISCHIO_PER_TRADE:
            print(f"VENDO {p['symbol']} PnL: {pnl*100:.2f}%")
            posizioni.remove(p)
            capitale_libero += p['investito'] * (1 + pnl - COMMISSIONE)
    
    # 2. CERCA NUOVE ENTRATE
    if len(posizioni) < MAX_POSITIONS and fg < 75 and capitale_libero > 15:
        print("Scannerizzo top 100...")
        candidati = []
        for sym in get_top_100():
            score, price, motivi = valuta_coin(sym)
            if score >= 3:
                candidati.append({"symbol": sym, "price": price, "score": score})
            else:
                print(f"SCARTATO {sym}: {motivi}")
        
        candidati = sorted(candidati, key=lambda x: x['score'], reverse=True)
        for c in candidati[:MAX_POSITIONS - len(posizioni)]:
            investito = capitale_libero / (MAX_POSITIONS - len(posizioni))
            print(f"COMPRO {c['symbol']} a {c['price']} Score: {c['score']}/5")
            posizioni.append({"symbol": c['symbol'], "entry": c['price'], "investito": investito})
            capitale_libero -= investito
    
    salva_posizioni(posizioni)
    
    # 3. SALVA PER DASHBOARD
    totale_usdt = capitale_libero + sum([p['investito'] * (1 + (float(requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={p['symbol']}").json()['price']) - p['entry'])/p['entry']) for p in posizioni])
    data = {
        "timestamp": str(datetime.now()),
        "saldo_eur": totale_usdt / eur,
        "fear_greed": fg,
        "posizioni": posizioni
    }
    with open("dashboard_data.json", 'w') as f: json.dump(data, f)
    print("Ciclo completato")

if __name__ == "__main__":
    main()
