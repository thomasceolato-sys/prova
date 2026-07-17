import requests
import time
from datetime import datetime

# ========== CONFIG ==========
CAPITALE = 50.00
MAX_POSIZIONI = 3
TARGET_COINS = 150
F_G_SOGLIA_MIN = 10 # Abbassata per test con F&G basso
CAPITALE_PER_TRADE = CAPITALE / MAX_POSIZIONI

saldo = 57.27
profitto = 7.27
posizioni_aperte = []

# ========== FUNZIONI DATI ==========
def get_fear_greed():
    """Prende F&G da alternative.me - gratis e senza limiti"""
    try:
        url = "https://api.alternative.me/fng/"
        r = requests.get(url, timeout=5)
        return int(r.json()['data'][0]['value'])
    except:
        return 50

def get_binance_data():
    """Prende 150 coin da Binance in 1 chiamata sola - NO LIMITI"""
    try:
        log("Chiamo BINANCE API...")
        url = "https://api.binance.com/api/v3/ticker/24hr"
        r = requests.get(url, timeout=10)
        data = r.json()

        coins = []
        for coin in data:
            if coin['symbol'].endswith('USDT'):
                coins.append({
                    'symbol': coin['symbol'],
                    'price': float(coin['lastPrice']),
                    'volume': float(coin['quoteVolume']),
                    'change_24h': float(coin['priceChangePercent'])
                })
        # Ordina per volume e prendi le top 150
        coins.sort(key=lambda x: x['volume'], reverse=True)
        log(f"Ricevuti {len(coins)} dati da Binance")
        return coins[:TARGET_COINS]
    except Exception as e:
        log(f"Errore Binance: {e}")
        return []

# ========== LOGICA SCANNER ==========
def valuta_coin(coin, fg):
    """Logica scoring semplificata per trovare trade anche con F&G basso"""
    score = 0
    motivi = []

    if coin['volume'] > 5000000: # 5M volume
        score += 30
        motivi.append("Volume ok")

    if abs(coin['change_24h']) > 2: # Movimento >2%
        score += 25
        motivi.append("Movimento")

    if fg > 40: # Mercato non in estrema paura
        score += 20

    if coin['change_24h'] > -2: # Non in forte dump
        score += 25

    return score, motivi

def log(messaggio):
    ora = datetime.now().strftime("%H:%M:%S")
    print(f"[{ora}] {messaggio}")

def stampa_portafoglio(fg):
    print("\n🤖 Bot Scanner Smart Pro - 50€ - VERSIONE BINANCE")
    print("📊 Portafoglio")
    print(f"Saldo: {saldo:.2f} €")
    print(f"Profitto: {profitto:.2f} € ({profitto/50*100:.2f}%)")
    print(f"Fear & Greed: {fg}")
    print(f"Posizioni: {len(posizioni_aperte)}/{MAX_POSIZIONI}\n")

# ========== MAIN ==========
if __name__ == "__main__":
    log("=== AVVIO SCANNER MAX V2 BINANCE ===")
    fg = get_fear_greed()
    log(f"F&G: {fg} | Capitale Libero: {CAPITALE:.2f}€")
    stampa_portafoglio(fg)

    log("Inizio scansione...")
    coins = get_binance_data()

    if not coins:
        log("Errore: 0 dati ricevuti da Binance")
        exit()

    candidati = []
    scartati_top10 = []
    top10_symbols = ['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT',
                     'DOGEUSDT','TONUSDT','ADAUSDT','TRXUSDT','SHIBUSDT']

    for i, coin in enumerate(coins):
        log(f"Progresso: {i+1}/{len(coins)} coin")
        score, motivi = valuta_coin(coin, fg)

        if score >= 60: # Soglia per essere "valido"
            candidati.append({"coin": coin, "score": score, "motivi": motivi})
            log(f" CANDIDATO: {coin['symbol']} | Score: {score} | {motivi}")
        else:
            if coin['symbol'] in top10_symbols:
                scartati_top10.append({"coin": coin['symbol'], "motivo": f"Score: {score}"})

    log(f"Trovati {len(candidati)} candidati validi")

    # ========== STAMPA RISULTATI ==========
    print("\n💼 Posizioni Aperte")
    print("Nessuna" if not posizioni_aperte else posizioni_aperte)

    print("\n🚫 Top 10 Scartati")
    for s in scartati_top10[:10]:
        print(f"{s['coin']}\t{s['motivo']}")

    print("\n📈 Ultime Operazioni")
    print("Comprati: Nessuno")
    print("Venduti: Nessuno")

    print(f"\n📝 Log Attività")
    log(f"Ultimo agg: {datetime.now()}")
