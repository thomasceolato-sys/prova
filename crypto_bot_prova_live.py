"""
Bot di trading crypto - "PROVA" LIVE (paper trading in tempo reale)
======================================================================
Pensato per girare su GitHub Actions: ogni esecuzione fa UN controllo
(analizza le coppie più scambiate, decide se comprare/vendere in modo
simulato, salva lo stato) e poi termina. E' GitHub Actions a farlo
ripartire ogni 15 minuti tramite una schedulazione, non un ciclo infinito
dentro lo script.

COSA FA:
- Ogni esecuzione controlla le N coppie con più volume nelle ultime 24h
  (calcolate dal vivo, non una lista fissa scelta da me)
- Se non ha una posizione aperta: cerca quella col trend rialzista più
  marcato e "compra" (simulato)
- Se ha una posizione aperta: la vende (simulato) se il trend si inverte
- Il capitale resta VIRTUALE: nessuna connessione a nessun account reale
- Se configurato, manda un messaggio Telegram ad ogni operazione simulata

PERCHE' GATE.IO E NON BINANCE PER I DATI:
Binance blocca le richieste dai server "cloud" come quelli di GitHub
Actions (errore 451 "restricted location"), anche per i soli dati
pubblici di mercato. Non e' un problema del nostro codice, e' una
restrizione di Binance su certe infrastrutture. Gate.io offre dati
altrettanto validi per questo scopo e non ha questa restrizione. Per il
trading reale futuro, se eseguito dal tuo PC/casa invece che da un
server cloud, Binance resta un'opzione valida.

PERCHE' ANCORA IN SIMULAZIONE:
La versione precedente (solo backtest) aveva un bug scovato solo grazie ai
test con dati sintetici. Meglio osservare anche questa versione con soldi
finti per un po' prima di pensare a collegare quelli veri.

CONFIGURAZIONE TELEGRAM (opzionale):
Il bot legge il token e il chat id dalle variabili d'ambiente TELEGRAM_TOKEN
e TELEGRAM_CHAT_ID. Su GitHub Actions si impostano come "Secrets" del
repository (vedi le istruzioni fornite a parte). Senza, il bot funziona lo
stesso ma scrive solo nei log di GitHub, senza notifiche sul telefono.

SE PREFERISCI FARLO GIRARE SU UN PC SEMPRE ACCESO invece che con GitHub
Actions, basta richiamare main() dentro un ciclo, ad esempio:
    import time
    while True:
        main()
        time.sleep(900)  # 15 minuti
"""

import ccxt
import pandas as pd
import json
import os
import requests


# ----------------------------------------------------------------
# CONFIGURAZIONE
# ----------------------------------------------------------------
N_COINS = 20                   # quante coppie (le più scambiate) analizzare ad ogni esecuzione
QUOTE_CURRENCY = 'USDT'        # valuta di riferimento, es. BTC/USDT
TIMEFRAME = '1h'               # intervallo delle candele per gli indicatori
INITIAL_BALANCE = 10           # capitale virtuale di partenza
FEE_PCT = 0.001                # commissione simulata per trade (0.1%, valore tipico spot)
SMA_SHORT = 20
SMA_LONG = 50
STATE_FILE = 'stato_bot.json'  # qui il bot salva cosa sta facendo, tra un'esecuzione e l'altra

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


def notify(message):
    """Stampa sempre nei log; se configurato, invia anche su Telegram."""
    print(message)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10)
        except Exception as e:
            print(f"(Avviso: notifica Telegram non riuscita: {e})")


def load_state():
    """Recupera lo stato salvato dall'esecuzione precedente, altrimenti riparte da zero."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        'balance': INITIAL_BALANCE, 'holding_symbol': None,
        'holding_amount': 0.0, 'trades': []
    }


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_top_symbols(exchange, n, quote_currency):
    """Restituisce le n coppie spot con più volume scambiato nelle ultime 24h."""
    tickers = exchange.fetch_tickers()
    candidates = []
    for symbol, ticker in tickers.items():
        if symbol.endswith(f'/{quote_currency}') and ticker.get('quoteVolume'):
            candidates.append((symbol, ticker['quoteVolume']))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in candidates[:n]]


def analyze_symbol(exchange, symbol, timeframe, short_window, long_window):
    """Scarica le candele recenti di una coppia e calcola il trend attuale + la sua 'forza'."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=long_window + 5)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if len(df) < long_window:
        return None

    sma_short = df['close'].rolling(window=short_window).mean().iloc[-1]
    sma_long = df['close'].rolling(window=long_window).mean().iloc[-1]
    last_price = df['close'].iloc[-1]

    if pd.isna(sma_short) or pd.isna(sma_long):
        return None

    trend = 1 if sma_short > sma_long else (-1 if sma_short < sma_long else 0)
    momentum = (sma_short - sma_long) / sma_long

    return {'symbol': symbol, 'trend': trend, 'momentum': momentum, 'price': last_price}


def check_once(exchange, state):
    """Un singolo ciclo di analisi e decisione."""
    if state['holding_symbol'] is None:
        symbols = get_top_symbols(exchange, N_COINS, QUOTE_CURRENCY)
        analyses = []
        for symbol in symbols:
            try:
                result = analyze_symbol(exchange, symbol, TIMEFRAME, SMA_SHORT, SMA_LONG)
                if result:
                    analyses.append(result)
            except Exception as e:
                print(f"(Salto {symbol}: {e})")

        bullish = [a for a in analyses if a['trend'] == 1]
        if bullish:
            best = max(bullish, key=lambda a: a['momentum'])
            spendable = state['balance'] * (1 - FEE_PCT)
            amount = spendable / best['price']

            state['holding_symbol'] = best['symbol']
            state['holding_amount'] = amount
            state['balance'] = 0.0
            state['trades'].append({
                'tipo': 'ACQUISTO', 'symbol': best['symbol'],
                'prezzo': best['price'], 'quando': pd.Timestamp.now().isoformat()
            })
            notify(
                f"[PROVA - soldi finti] ACQUISTO simulato: "
                f"{best['symbol']} a {best['price']:.4f} {QUOTE_CURRENCY}"
            )
        else:
            print("Nessuna coppia in trend rialzista al momento. Resto liquido.")

    else:
        try:
            current = analyze_symbol(
                exchange, state['holding_symbol'], TIMEFRAME, SMA_SHORT, SMA_LONG
            )
        except Exception as e:
            current = None
            print(f"(Errore nel controllare {state['holding_symbol']}: {e})")

        if current is None:
            print(
                f"Dati non disponibili per {state['holding_symbol']} "
                f"in questo ciclo, riprovo al prossimo."
            )
        elif current['trend'] == -1:
            proceeds = state['holding_amount'] * current['price'] * (1 - FEE_PCT)
            state['trades'].append({
                'tipo': 'VENDITA', 'symbol': state['holding_symbol'],
                'prezzo': current['price'], 'quando': pd.Timestamp.now().isoformat()
            })
            notify(
                f"[PROVA - soldi finti] VENDITA simulata: "
                f"{state['holding_symbol']} a {current['price']:.4f} "
                f"{QUOTE_CURRENCY} -> saldo virtuale: "
                f"{proceeds:.4f} {QUOTE_CURRENCY}"
            )
            state['balance'] = proceeds
            state['holding_symbol'] = None
            state['holding_amount'] = 0.0
        else:
            print(f"Continuo a tenere {state['holding_symbol']}, trend ancora rialzista o neutro.")

    return state


def main():
    exchange = ccxt.gateio()
    state = load_state()
    state = check_once(exchange, state)
    save_state(state)


if __name__ == '__main__':
    main()
