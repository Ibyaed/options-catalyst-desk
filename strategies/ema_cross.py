import os
import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import requests

VAULT_REPORT_PATH = "obsidian_vault/Daily_Runs/daily_market_check.md"

# Equity/Index targets for options screening
WATCHLIST = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL"]

def get_central_now():
    return datetime.datetime.now(ZoneInfo("America/Chicago"))

def get_central_str(dt):
    return dt.strftime("%Y-%m-%d %H%M Hours %Z")

def fetch_intraday_data(symbol):
    """Fetch 5-minute intraday candles via Yahoo Finance API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2d&interval=5m"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()["chart"]["result"][0]
        timestamps = data["timestamp"]
        quotes = data["indicators"]["quote"][0]
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quotes["open"],
            "high": quotes["high"],
            "low": quotes["low"],
            "close": quotes["close"],
            "volume": quotes["volume"]
        }).dropna()
        df["timestamp"] = df["timestamp"].dt.tz_convert("America/Chicago")
        return df
    except Exception as e:
        print(f"[Data Error] Failed fetching 5m candles for {symbol}: {e}")
        return None

def compute_fib_grid(low_price, high_price):
    """
    Computes Fibonacci range from -200% to +200% based on
    anchor range (Low = 0.0, High = 1.0).
    """
    diff = high_price - low_price
    levels = {
        "-200.0%": high_price - (diff * 3.0),
        "-161.8%": high_price - (diff * 2.618),
        "-100.0%": high_price - (diff * 2.0),
        "0.0% (Low)": low_price,
        "38.2%": low_price + (diff * 0.382),
        "50.0%": low_price + (diff * 0.500),
        "61.8%": low_price + (diff * 0.618),
        "100.0% (High)": high_price,
        "161.8%": low_price + (diff * 1.618),
        "200.0%": low_price + (diff * 2.0)
    }
    return levels

def evaluate_elliott_wave_setup(df):
    """Identifies Wave 3 breakout conditions vs speculative setups."""
    if len(df) < 30:
        return "Insufficient Data", None, 0.0, 0.0

    today = get_central_now().date()
    today_df = df[df["timestamp"].dt.date == today]
    prior_df = df[df["timestamp"].dt.date < today]

    if today_df.empty or prior_df.empty:
        curr_low = df["low"].tail(20).min()
        curr_high = df["high"].tail(20).max()
    else:
        curr_low = today_df["low"].min()
        curr_high = prior_df["high"].max()

    fibs = compute_fib_grid(curr_low, curr_high)
    curr_close = df["close"].iloc[-1]
    
    # 20-period moving average to gauge short-term trend
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    latest_ema9 = df["ema9"].iloc[-1]
    latest_ema21 = df["ema21"].iloc[-1]

    # Signal definitions
    if curr_close > fibs["100.0% (High)"] and latest_ema9 > latest_ema21:
        signal = "?? Wave 3 Confirmed Breakout (Calls)"
    elif curr_close > fibs["61.8%"] and latest_ema9 > latest_ema21:
        signal = "? Wave 3 Speculative Entry"
    elif curr_close < fibs["0.0% (Low)"]:
        signal = "?? Lower Low Spike (Wick Reversal Watch)"
    else:
        signal = "Neutral / Consolidation"

    return signal, fibs, curr_low, curr_high

def run_options_screener():
    now_str = get_central_str(get_central_now())
    table_rows = []

    for symbol in WATCHLIST:
        df = fetch_intraday_data(symbol)
        if df is None or df.empty:
            table_rows.append(f"| {symbol} | N/A | Data Error | N/A | N/A | N/A |")
            continue

        curr_price = df["close"].iloc[-1]
        signal, fibs, low_p, high_p = evaluate_elliott_wave_setup(df)

        tp1 = f"${fibs['161.8%']:,.2f}" if fibs else "N/A"
        tp2 = f"${fibs['200.0%']:,.2f}" if fibs else "N/A"
        sl = f"${fibs['0.0% (Low)']:,.2f}" if fibs else "N/A"

        table_rows.append(
            f"| **{symbol}** | ${curr_price:,.2f} | {signal} | {tp1} | {tp2} | {sl} |"
        )

    table_body = "\n".join(table_rows)
    report = f"""# ?? Options Momentum Screener (5m Elliott Wave + Fibs)

- **Scan Timestamp:** {now_str}
- **Strategy:** 5m Candle Wave 3 Breakout & Retracement (-200% to +200% Fib Grid)
- **Target Call Return:** 20% Intraday

| Symbol | Price | Setup Status | TP 1 (161.8%) | TP 2 (200.0%) | Invalidation Stop |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_body}
"""
    os.makedirs(os.path.dirname(VAULT_REPORT_PATH), exist_ok=True)
    with open(VAULT_REPORT_PATH, "w") as f:
        f.write(report)

    print(f"[{now_str}] Screener run completed. Written to {VAULT_REPORT_PATH}")

if __name__ == "__main__":
    run_options_screener()
