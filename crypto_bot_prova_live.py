import requests
import time
from datetime import datetime

# ========== CONFIG ==========
CAPITALE = 50.00
MAX_POSIZIONI = 3
TARGET_COINS = 150
F_G_SOGLIA_MIN = 20 # Non compra se F&G < 20
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
    """Prende 150 coin da Binance in 1 chiamata sola"""
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
        # Ordina per volume e prendi le top 150
        coins.sort(key=lambda x: x['volume'], reverse=True)
        return coins[:TARGET_COINS]
    except Exception as e:
        log(f"Errore Binance: {e}")
        return []

# ========== LOGICA SCANNER ==========
def valuta_coin(coin, fg):
    """La tua logica di scoring. Modificala come vuoi"""
    score = 0
    motivi = []

    # Esempio regole base
    if coin['volume'] > 10000000: # 10M volume
        score += 30
        motivi.append("Volume alto")

    if abs(coin['change_24h']) > 5: # Movimento >5%
        score += 25
        motivi.append("Volatilità")

    if fg > 50: # Mercato greedy
        score += 20

    if coin['change_24h'] > 0:
        score += 25

    return score, motivi

def log(messaggio):
    ora = datetime.now().strftime("%H:%M:%S")
    print(f"[{ora}] {messaggio}")

def stampa_portafoglio():
    print("\n🤖 Bot Scanner Smart Pro - 50€")
    print("📊 Portafoglio")
    print(f"Saldo: {saldo:.2f} €")
    print(f"Profitto: {profitto:.2f} € ({profitto/50*100:.2f}%)")
    print(f"Fear & Greed: {fg}")
    print(f"Posizioni: {len(posizioni_aperte)}/{MAX_POSIZIONI}\n")

# ========== MAIN ==========
if __name__ == "__main__":
    log("Avvio Scanner MAX")
    fg = get_fear_greed()
    log(f"F&G: {fg} | Capitale Libero: {CAPITALE:.2f}€")

    stampa_portafoglio()

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

        if score >= 70: # Soglia per essere "valido"
            candidati.append({"coin": coin, "score": score, "motivi": motivi})
        else:
            if coin['symbol'] in top10_symbols:
                scartati_top10.append({"coin": coin['symbol'], "motivo": f"Score basso: {score}"})

    log(f"Trovati {len(candidati)} candidati validi")

    # ========== STAMPA RISULTATI ==========
    print("\n💼 Posizioni Aperte")
    if posizioni_aperte:
        for p in posizioni_aperte:
            print(f"{p}")
    else:
        print("Nessuna")

    print("\n🚫 Top 10 Scartati")
    for s in scartati_top10[:10]:
        print(f"{s['coin']}\t{s['motivo']}")

    print("\n📈 Ultime Operazioni")
    print("Comprati: Nessuno")
    print("Venduti: Nessuno")

    print(f"\n📝 Log Attività")
    log(f"Ultimo agg: {datetime.now()}")
