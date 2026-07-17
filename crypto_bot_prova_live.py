import requests
import time
from datetime import datetime

# ========== CONFIG ==========
CAPITALE = 50.00
MAX_POSIZIONI = 3
TARGET_COINS = 150
F_G_SOGLIA_MIN = 10 # Abbassata per test
CAPITALE_PER_TRADE = CAPITALE / MAX_POSIZIONI

saldo = 57.27
profitto = 7.27
posizioni_aperte = []

# ========== FUNZIONI DATI ==========
def get_fear_greed():
    try:
        url = "https://api.alternative.me/fng/"
        r = requests.get(url, timeout=5)
        return int(r.json()['data'][0]['value'])
    except:
        return 50

def get_binance_data():
    try:
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
        coins.sort(key=lambda x: x['volume'], reverse=True)
        return coins[:TARGET_COINS]
    except Exception as e:
        log(f"Errore Binance: {e}")
        return []

# ========== LOGICA SCANNER FIXATA ==========
def valuta_coin(coin, fg):
    score = 0
    motivi = []

    # Meno restrittivo per test
    if coin['volume'] > 5000000: # 5M invece di 10M
        score += 30
        motivi.append("Volume ok")

    if abs(coin['change_24h']) > 2: # 2% invece di 5%
        score += 25
        motivi.append("Movimento")

    if fg > 40: # 40 invece di 50
        score += 20

    if coin['change_24h'] > -2: # Accetta anche laterali
        score += 25

    return score, motivi

def log(messaggio):
    ora = datetime.now().strftime("%H:%M:%S")
    print(f"[{ora}] {messaggio}")

def stampa_portafoglio(fg):
    print("\n🤖 Bot Scanner Smart Pro - 50€")
    print("📊 Portafoglio")
    print(f"Saldo: {saldo:.2f} €")
    print(f"Profitto: {profitto:.2f} € ({profitto/50*100:.2f}%)")
    print(f"Fear & Greed: {fg}")
    print(f"Posizioni: {len(posizioni_aperte)}/{MAX_POSIZIONI}\n")

# ========== MAIN ==========
if __name__ == "__main__":
    log("Avvio Scanner MAX - VERSIONE BINANCE")
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

        if score >= 60: # Soglia abbassata da 70 a 60
            candidati.append({"coin": coin, "score": score, "motivi": motivi})
            log(f" CANDIDATO: {coin['symbol']} | Score: {score} | {motivi}")
        else:
            if coin['symbol'] in top10_symbols:
                scartati_top10.append({"coin": coin['symbol'], "motivo": f"Score: {score}"})

    log(f"Trovati {len(candidati)} candidati validi")

    print("\n💼 Posizioni Aperte")
    print("Nessuna" if not posizioni_aperte else posizioni_aperte)

    print("\n🚫 Top 10 Scartati")
    for s in scartati_top10[:10]:
        print(f"{s['coin']}\t{s['motivo']}")

    print("\n📈 Ultime Operazioni\nComprati: Nessuno\nVenduti: Nessuno")
    log(f"Ultimo agg: {datetime.now()}")
