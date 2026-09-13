import os
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
from src.config import TRACKED_TICKERS
from src.signals.patterns import detect_regime_and_bias

CENTRAL_TZ = ZoneInfo("America/Chicago")
VAULT_REPORT = "obsidian_vault/Daily_Runs/historical_fib_elliott_backtest.md"

def run_historical_backtest(start_date="2026-08-28"):
    summary_results = []

    for sym in TRACKED_TICKERS:
        print(f"[*] Downloading 5m data for {sym} since {start_date}...")
        ticker = yf.Ticker(sym)
        df = ticker.history(start=start_date, interval="5m")

        if df.empty or len(df) < 35:
            print(f"[-] Insufficient data for {sym}.")
            continue

        trades = []
        active_pos = None

        for i in range(35, len(df)):
            window = df.iloc[:i]
            current_bar = df.iloc[i]
            current_price = float(current_bar["Close"])
            bar_time = current_bar.name.tz_convert(CENTRAL_TZ).strftime("%Y-%m-%d %H%M")

            refs = {
                "prev_close": float(window["Close"].iloc[-2]),
                "pdh": float(window["High"].max()),
                "pdl": float(window["Low"].min())
            }

            analysis = detect_regime_and_bias(window, refs)
            rec = analysis["recommendation"]
            ew = analysis["elliott_phase"]
            fib_details = analysis.get("fib_details", {})

            fib_100 = fib_details.get("100.0%", current_price * 1.01)
            fib_127 = fib_details.get("127.2%", current_price * 1.02)
            fib_161 = fib_details.get("161.8%", current_price * 1.03)

            # Chop Filter: Ignore neutral / consolidation phases
            if active_pos is None:
                if rec == "STRONG LONG":
                    active_pos = {
                        "type": "LONG",
                        "entry": current_price,
                        "stop_loss": current_price * 0.99,
                        "peak_price": current_price,
                        "time": bar_time,
                        "ew": ew,
                        "fib_127": fib_127,
                        "fib_161": fib_161,
                        "trailing_active": False
                    }
                elif rec == "STRONG SHORT":
                    active_pos = {
                        "type": "SHORT",
                        "entry": current_price,
                        "stop_loss": current_price * 1.01,
                        "trough_price": current_price,
                        "time": bar_time,
                        "ew": ew,
                        "trailing_active": False
                    }
            else:
                entry = active_pos["entry"]
                if active_pos["type"] == "LONG":
                    # Update peak tracking
                    if current_price > active_pos["peak_price"]:
                        active_pos["peak_price"] = current_price

                    # Level 1 Adjustment: Move stop to Break-Even at 127.2% extension
                    if current_price >= active_pos["fib_127"] and active_pos["stop_loss"] < entry:
                        active_pos["stop_loss"] = entry

                    # Level 2 Adjustment: Activate 0.5% trailing stop above 161.8% extension
                    if current_price >= active_pos["fib_161"]:
                        active_pos["trailing_active"] = True

                    if active_pos["trailing_active"]:
                        trail_target = active_pos["peak_price"] * 0.995
                        if trail_target > active_pos["stop_loss"]:
                            active_pos["stop_loss"] = trail_target

                    # Check Exit
                    pnl = (current_price - entry) / entry
                    if current_price <= active_pos["stop_loss"] or "TAKE PROFIT" in rec:
                        trades.append({"symbol": sym, "type": "LONG", "pnl": pnl, "entry": entry, "exit": current_price, "ew": active_pos["ew"]})
                        active_pos = None

                elif active_pos["type"] == "SHORT":
                    # Update trough tracking
                    if current_price < active_pos["trough_price"]:
                        active_pos["trough_price"] = current_price

                    # Trail at +2% target or cover signal
                    pnl = (entry - current_price) / entry
                    if current_price >= active_pos["stop_loss"] or pnl >= 0.02 or "COVER" in rec:
                        trades.append({"symbol": sym, "type": "SHORT", "pnl": pnl, "entry": entry, "exit": current_price, "ew": active_pos["ew"]})
                        active_pos = None

        if trades:
            tdf = pd.DataFrame(trades)
            wins = len(tdf[tdf["pnl"] > 0])
            total = len(tdf)
            win_rate = (wins / total) * 100
            cum_ret = tdf["pnl"].sum() * 100
            summary_results.append({
                "symbol": sym,
                "total_trades": total,
                "win_rate": f"{win_rate:.1f}%",
                "cum_ret": f"{cum_ret:+.2f}%",
                "top_phase": tdf["ew"].value_counts().idxmax() if not tdf.empty else "N/A"
            })

    now_str = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d %H%M Hours %Z")
    table_rows = "\n".join([
        f"| **{r['symbol']}** | {r['total_trades']} | {r['win_rate']} | {r['cum_ret']} | {r['top_phase']} |"
        for r in summary_results
    ])

    report = f"""# 📊 Historical 5m Fib (161.8% Trail) & Elliott Wave Backtest

- **Backtest Period:** {start_date} to {now_str[:10]}
- **Run Timestamp:** {now_str}
- **Resolution:** 5-Minute Candles
- **Strategy:** Fibonacci 161.8% Dynamic Trailing Stops + Break-Even at 127.2% + Chop Filter

| Asset | Total Signals | Win Rate | Cumulative Theoretical Return | Dominant Setup |
| :--- | :--- | :--- | :--- | :--- |
{table_rows}
"""
    os.makedirs(os.path.dirname(VAULT_REPORT), exist_ok=True)
    with open(VAULT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[Success] Backtest complete. Report written to {VAULT_REPORT}")

if __name__ == "__main__":
    run_historical_backtest("2026-08-28")
