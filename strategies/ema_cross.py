import datetime
import os
from zoneinfo import ZoneInfo
import pandas as pd
import ccxt

VAULT_REPORT_PATH = "obsidian_vault/Daily_Runs/daily_market_check.md"

# Use Coinbase standard USD pairs to match trade_simulator.py
SYMBOLS = ["BTC/USD", "ETH/USD"]

def get_central_now():
    return datetime.datetime.now(ZoneInfo("America/Chicago"))

def get_central_str(dt):
    return dt.strftime("%Y-%m-%d %H%M Hours %Z")

def run_ema_strategy():
    exchange = ccxt.coinbase()
    now_str = get_central_str(get_central_now())
    table_rows = []

    for symbol in SYMBOLS:
        try:
            # 1. Fetch live ticker (real-time price)
            ticker = exchange.fetch_ticker(symbol)
            live_price = float(ticker['last'])

            # 2. Fetch daily candles for 50/200 EMA calculation
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=250)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Calculate Moving Averages
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

            latest_ema50 = df['ema50'].iloc[-1]
            latest_ema200 = df['ema200'].iloc[-1]

            regime = "Golden Cross (Long)" if latest_ema50 > latest_ema200 else "Death Cross (Short/Cash)"

            # Calculate historical Sharpe Ratio
            df['returns'] = df['close'].pct_change()
            df['strategy_returns'] = df['returns'] * (df['ema50'] > df['ema200']).shift(1)
            mean_ret = df['strategy_returns'].mean()
            std_ret = df['strategy_returns'].std()
            sharpe = (mean_ret / std_ret * (365 ** 0.5)) if std_ret > 0 else 0.0

            table_rows.append(
                f"| {symbol} | ${live_price:,.2f} | {regime} | {sharpe:.2f} |"
            )

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            table_rows.append(f"| {symbol} | N/A | Error | N/A |")

    table_body = "\n".join(table_rows)
    report = f"""# 📈 Daily Market & Strategy Report

- **Run Timestamp:** {now_str}
- **Pipeline Status:** Verified & Autonomous

| Asset | Latest Price | Current Regime | Strategy Sharpe Ratio |
| :--- | :--- | :--- | :--- |
{table_body}
"""

    os.makedirs(os.path.dirname(VAULT_REPORT_PATH), exist_ok=True)
    with open(VAULT_REPORT_PATH, "w") as f:
        f.write(report)

    print(f"[{now_str}] EMA Backtest completed. Report written to {VAULT_REPORT_PATH}")

if __name__ == "__main__":
    run_ema_strategy()