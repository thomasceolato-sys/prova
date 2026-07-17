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
- Vende le posizioni aperte il cui trend si è invertito
- Se ci sono "slot" liberi (vedi MAX_POSITIONS) e liquidità: cerca nuove
  occasioni tra le coppie in trend rialzista e apre nuove posizioni
- Il capitale resta VIRTUALE: nessuna connessione a nessun account reale
- Se configurato, manda un messaggio Telegram ad ogni operazione simulata

MAX_POSITIONS - posizioni multiple in parallelo:
Il codice supporta più posizioni aperte insieme, ma di default
MAX_POSITIONS = 1: con 10€ di capitale, dividerlo su più operazioni
significa commissioni più pesanti in proporzione e rischio di scendere
sotto l'importo minimo per operazione richiesto da molti exchange. Il
supporto c'è già pronto: alza semplicemente MAX_POSITIONS quando il
capitale reale sarà più alto e avrà senso diversificare.

PERCHE' GATE.IO E NON BINANCE PER I DATI:
Binance blocca le richieste dai server "cloud" come quelli di GitHub
Actions (errore 451 "restricted location"), anche per i soli dati
pubblici di mercato. Non e' un problema del nostro codice, e' una
restrizione di Binance su certe infrastrutture. Gate.io offre dati
altrettanto validi per questo scopo e non ha questa restrizione. Per il
trading reale futuro, se eseguito dal tuo PC/casa invece che da un
server cloud, Binance resta un'opzione valida.

PERCHE' ANCORA IN SIMULAZIONE:
Le versioni precedenti (solo backtest) hanno già mostrato più di un bug
scovato solo grazie ai test con dati sintetici. Meglio osservare anche
questa versione con soldi finti per un po' prima di pensare a collegare
quelli veri.

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
MAX_POSITIONS = 1              # posizioni aperte in parallelo. Vedi nota sopra: a 10€ conviene 1.
STOP_LOSS_PCT = 0.05           # vendita immediata se una posizione scende oltre il 5% dal prezzo di acquisto,
                                # indipendentemente dal trend delle medie mobili (limita i danni nei crolli veloci)
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
    """
    Recupera lo stato salvato dall'esecuzione precedente, altrimenti riparte
    da zero. Migra automaticamente il vecchio formato a posizione singola
    (holding_symbol/holding_amount) al nuovo formato a lista di posizioni,
    così una posizione già aperta con la versione precedente non si perde.
    """
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)

        if 'positions' not in state:
            positions = []
            if state.get('holding_symbol'):
                symbol = state['holding_symbol']
                buy_price = None
                buy_time = None
                for t in reversed(state.get('trades', [])):
                    if t.get('tipo') == 'ACQUISTO' and t.get('symbol') == symbol:
                        buy_price = t.get('prezzo')
                        buy_time = t.get('quando')
                        break
                positions.append({
                    'symbol': symbol,
                    'amount': state.get('holding_amount', 0.0),
                    'prezzo_acquisto': buy_price,
                    'quando': buy_time
                })
            state['positions'] = positions
            state.pop('holding_symbol', None)
            state.pop('holding_amount', None)

        state.setdefault('trades', [])
        state.setdefault('market_breadth', None)
        state.setdefault('fear_greed', None)
        return state

    return {
        'balance': INITIAL_BALANCE, 'positions': [],
        'trades': [], 'market_breadth': None, 'fear_greed': None
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


def get_fear_greed_index():
    """
    Recupera l'indice Fear & Greed crypto da alternative.me (dato pubblico
    reale, aggregato da volatilità, volumi, social, dominance e trend di
    ricerca - non generato da noi, non un punteggio di 'confidenza' inventato).
    Dati forniti da alternative.me.
    """
    try:
        response = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        response.raise_for_status()
        entry = response.json()['data'][0]
        return {'valore': int(entry['value']), 'classificazione': entry['value_classification']}
    except Exception as e:
        print(f"(Avviso: Fear & Greed Index non disponibile questo ciclo: {e})")
        return None


def check_once(exchange, state):
    """Un singolo ciclo di analisi e decisione, con supporto a più posizioni in parallelo."""
    positions = state['positions']

    # 1) Controlliamo le posizioni aperte: vendiamo quelle il cui trend si è invertito
    still_open = []
    for p in positions:
        try:
            current = analyze_symbol(exchange, p['symbol'], TIMEFRAME, SMA_SHORT, SMA_LONG)
        except Exception as e:
            current = None
            print(f"(Errore nel controllare {p['symbol']}: {e})")

        if current is None:
            print(f"Dati non disponibili per {p['symbol']} in questo ciclo, riprovo al prossimo.")
            still_open.append(p)
        else:
            loss_pct = None
            if p.get('prezzo_acquisto'):
                loss_pct = (current['price'] - p['prezzo_acquisto']) / p['prezzo_acquisto']
            stop_loss_hit = loss_pct is not None and loss_pct <= -STOP_LOSS_PCT

            if stop_loss_hit or current['trend'] == -1:
                proceeds = p['amount'] * current['price'] * (1 - FEE_PCT)
                motivo = (
                    f"STOP-LOSS ({loss_pct * 100:.2f}%)" if stop_loss_hit
                    else "trend invertito"
                )
                state['trades'].append({
                    'tipo': 'VENDITA', 'symbol': p['symbol'],
                    'prezzo': current['price'], 'quando': pd.Timestamp.now().isoformat(),
                    'motivo': motivo
                })
                notify(
                    f"[PROVA - soldi finti] VENDITA simulata ({motivo}): "
                    f"{p['symbol']} a {current['price']:.4f} {QUOTE_CURRENCY} "
                    f"-> +{proceeds:.4f} {QUOTE_CURRENCY} al saldo"
                )
                state['balance'] = state['balance'] + proceeds
            else:
                print(f"Continuo a tenere {p['symbol']}, trend ancora rialzista o neutro.")
                still_open.append(p)

    positions = still_open
    open_symbols = {p['symbol'] for p in positions}
    available_slots = MAX_POSITIONS - len(positions)

    # 2) Se abbiamo slot liberi e liquidità, cerchiamo nuove occasioni
    if available_slots > 0 and state['balance'] > 0:
        symbols = get_top_symbols(exchange, N_COINS, QUOTE_CURRENCY)
        analyses = []
        for symbol in symbols:
            try:
                result = analyze_symbol(exchange, symbol, TIMEFRAME, SMA_SHORT, SMA_LONG)
                if result:
                    analyses.append(result)
            except Exception as e:
                print(f"(Salto {symbol}: {e})")

        state['market_breadth'] = {
            'rialziste': len([a for a in analyses if a['trend'] == 1]),
            'analizzate': len(analyses),
            'quando': pd.Timestamp.now().isoformat()
        }

        fg = get_fear_greed_index()
        state['fear_greed'] = fg
        skip_for_greed = fg is not None and fg['classificazione'] == 'Extreme Greed'

        bullish = [a for a in analyses if a['trend'] == 1 and a['symbol'] not in open_symbols]

        if bullish and skip_for_greed:
            print(
                f"Trend rialzista trovato, ma Fear & Greed Index in 'Extreme Greed' "
                f"({fg['valore']}/100): salto nuovi acquisti per prudenza questo ciclo."
            )
        elif bullish:
            candidates = sorted(bullish, key=lambda a: -a['momentum'])[:available_slots]
            budget_per_position = state['balance'] / len(candidates)
            for c in candidates:
                spendable = budget_per_position * (1 - FEE_PCT)
                amount = spendable / c['price']
                positions.append({
                    'symbol': c['symbol'], 'amount': amount,
                    'prezzo_acquisto': c['price'], 'quando': pd.Timestamp.now().isoformat()
                })
                state['trades'].append({
                    'tipo': 'ACQUISTO', 'symbol': c['symbol'],
                    'prezzo': c['price'], 'quando': pd.Timestamp.now().isoformat()
                })
                notify(
                    f"[PROVA - soldi finti] ACQUISTO simulato: "
                    f"{c['symbol']} a {c['price']:.4f} {QUOTE_CURRENCY}"
                )
            state['balance'] = state['balance'] - (budget_per_position * len(candidates))
        else:
            print("Nessuna coppia in trend rialzista al momento. Resto liquido.")

    state['positions'] = positions
    return state


def main():
    exchange = ccxt.gate()
    state = load_state()
    state = check_once(exchange, state)
    save_state(state)


if __name__ == '__main__':
    main()
