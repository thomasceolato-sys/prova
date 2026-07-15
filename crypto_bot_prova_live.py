import requests
import pandas as pd
import numpy as np
import time
import json
import os
from datetime import datetime

CAPITALE_INIZIALE = 50.0
MAX_POSITIONS = 3
RISCHIO_PER_TRADE = 0.03
TARGET_PER_TRADE = 0.05
SCANNER_TOP_N = 100
TIMEFRAME = "1h"
COMMISSIONE = 0.001

FILE_POSIZIONI = "posizioni.json"
FILE_DASHBOARD = "dashboard_data.json" # AGGIUNTO

def get_top_100():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency": "usdt", "order": "volume_desc", "per_page": SCANNER_TOP_N, "page": 1}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code!= 200: raise Exception("Ban")
        data = r.json()
        return [x['symbol'].upper() + "USDT" for x in data if x.get('total_volume',0) > 5000000]
    except:
        print("CoinGecko bloccato. Uso lista TOP10")
        return ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","TONUSDT","ADAUSDT","TRXUSDT","SHIBUSDT"]

def get_klines(symbol):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": TIMEFRAME, "limit": 200}
    r = requests.get(url, params=params)
    if r.status_code!= 200: return pd.DataFrame()
    data = r.json()
    df = pd.DataFrame(data, columns=['t','o','h','l','c','v','ct','qv','n','tbb','tbq','x'])
    df['c'] = df['c'].astype(float)
    df['v'] = df['v'].astype(float)
    return df

def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/").json()
        return int(r['data'][0]['value'])
    except: return 50

def get_eur_usdt():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        usd_to_eur = r['rates']['EUR']
        return 1 / usd_to_eur
    except: return 0.92

def calc_indicatori(df):
    if len(df) < 200: return None
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
        if last is None: return 0, 0, ["Pochi dati"]
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

def salva_dashboard(saldo_eur, fg, posizioni):
    data = {
        "timestamp": str(datetime.now()),
        "saldo_eur": saldo_eur,
        "fear_greed": fg,
        "posizioni": posizioni,
        "status": "OK"
    }
    with open(FILE_DASHBOARD, 'w') as f: json.dump(data, f)

def main():
    print(f"[{datetime.now()}] Avvio Scanner Smart 50€")
    posizioni = carica_posizioni()
    capitale_libero = CAPITALE_INIZIALE - sum([p['investito'] for p in posizioni])
    fg = get_fear_greed()
    eur = get_eur_usdt()
    print(f"Fear & Greed: {fg} | Tasso EUR: {eur:.4f} | Capitale libero: {capitale_libero:.2f}€")
    
    # CREA SUBITO LA DASHBOARD ANCHE SE NON FA NULLA
    salva_dashboard(capitale_libero * eur, fg, posizioni)
    
    # 1. GESTISCI POSIZIONI
    for p in posizioni[:]:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={p['symbol']}")
        if r.status_code!= 200: continue
        prezzo_att = float(r.json()['price'])
        pnl = (prezzo_att - p['entry']) / p['entry']
        if pnl >= TARGET_PER_TRADE or pnl <= -RISCHIO_PER_TRADE:
            print(f"VENDO {p['symbol']} PnL: {pnl*100:.2f}%")
            posizioni.remove(p)
            capitale_libero += p['investito'] * (1 + pnl - COMMISSIONE)
    
    # 2. CERCA NUOVE ENTRATE
    if len(posizioni) < MAX_POSITIONS and fg < 75 and capitale_libero > 15:
        print("Scannerizzo...")
        candidati = []
        for sym in get_top_100()[:20]:
            score, price, motivi = valuta_coin(sym)
            if score >= 3:
                candidati.append({"symbol": sym, "price": price, "score": score})
            else:
                print(f"SCARTATO {sym}: {motivi}")
            time.sleep(0.2)
        
        candidati = sorted(candidati, key=lambda x: x['score'], reverse=True)
        for c in candidati[:MAX_POSITIONS - len(posizioni)]:
            investito = capitale_libero / (MAX_POSITIONS - len(posizioni))
            print(f"COMPRO {c['symbol']} a {c['price']} Score: {c['score']}/5")
            posizioni.append({"symbol": c['symbol'], "entry": c['price'], "investito": investito})
            capitale_libero -= investito
    
    salva_posizioni(posizioni)
    
    # 3. AGGIORNA DASHBOARD FINALE
    totale_usdt = capitale_libero
    for p in posizioni:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={p['symbol']}")
        if r.status_code == 200:
            prezzo_att = float(r.json()['price'])
            totale_usdt += p['investito'] * (1 + (prezzo_att - p['entry'])/p['entry'])
    
    salva_dashboard(totale_usdt * eur, fg, posizioni)
    print("Ciclo completato")

if __name__ == "__main__":
    main()
