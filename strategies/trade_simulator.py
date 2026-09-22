import os
import json
import datetime
from zoneinfo import ZoneInfo
import requests

STATE_FILE = "trade_state.json"
VAULT_REPORT_PATH = "obsidian_vault/Daily_Runs/trade_simulator_status.md"
AUDIT_LOG_PATH = "obsidian_vault/Daily_Runs/trade_audit_log.md"

WATCHLIST = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL"]
BASE_ALLOCATION = 2000.0

def get_central_now():
    return datetime.datetime.now(ZoneInfo("America/Chicago"))

def get_central_str(dt):
    return dt.strftime("%Y-%m-%d %H%M Hours %Z")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "active_trades": {},
        "circuit_breaker_until": None,
        "manual_override": False,
        "cumulative_realized_pnl": 0.0,
        "total_deposited_cash": 6000.0,
        "daily_target_pct": 20.0
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def log_audit_event(action, details):
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    ts = get_central_str(get_central_now())
    entry = f"- **[{ts}] {action}:** {details}\n"
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)

def get_live_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        price = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception:
        return None

def run_simulation_cycle():
    state = load_state()
    now = get_central_now()
    now_str = get_central_str(now)
    time_mil = now.strftime("%H%M")

    table_rows = []
    portfolio_valuation = 0.0
    total_unrealized_pnl = 0.0
    active_trades = state.get("active_trades", {})

    for symbol in WATCHLIST:
        curr_price = get_live_price(symbol)
        if curr_price is None:
            continue

        if symbol in active_trades:
            pos = active_trades[symbol]
            invested_total = float(pos["allocation"])
            units = float(pos["units"])
            avg_entry = float(pos["entry_price"])

            position_value = units * curr_price
            pnl_dollars = position_value - invested_total
            growth_pct = (pnl_dollars / invested_total) * 100 if invested_total > 0 else 0.0

            tp_target_price = avg_entry * 1.02
            sl_target_price = avg_entry * 0.99

            if curr_price >= tp_target_price:
                state["cumulative_realized_pnl"] += pnl_dollars
                log_audit_event("TAKE-PROFIT HIT (+20% Target)", rf"Closed {symbol} at ({curr_price:,.2f} | Realized:){pnl_dollars:+,.2f} USD")
                del active_trades[symbol]
                continue
            elif curr_price <= sl_target_price:
                state["cumulative_realized_pnl"] += pnl_dollars
                log_audit_event("STOP-LOSS HIT (Invalidation)", f"Cut {symbol} at \({curr_price:,.2f} | Realized:\){pnl_dollars:+,.2f} USD")
                del active_trades[symbol]
                continue

            portfolio_valuation += position_value
            total_unrealized_pnl += pnl_dollars

            table_rows.append(
                f"| {symbol} | \({invested_total:,.2f} |\){position_value:,.2f} | {growth_pct:+.2f}% | \({pnl_dollars:+,.2f} |\){avg_entry:,.2f} | \({curr_price:,.2f} | {time_mil} CST |\){tp_target_price:,.2f} |"
            )
        else:
            table_rows.append(
                f"| {symbol} | $0.00 | $0.00 | 0.00% | $0.00 | — | ${curr_price:,.2f} | {time_mil} CST | — |"
            )

    state["active_trades"] = active_trades
    save_state(state)

    total_deposited = float(state.get("total_deposited_cash", 6000.0))
    cum_realized = float(state.get("cumulative_realized_pnl", 0.0))
    invested_cash = sum(float(pos["allocation"]) for pos in active_trades.values())
    unallocated_cash = total_deposited - invested_cash
    current_equity = unallocated_cash + portfolio_valuation + cum_realized
    net_portfolio_roi = ((current_equity - total_deposited) / total_deposited) * 100 if total_deposited > 0 else 0.0

    status_banner = "🟢 **Options Catalyst Desk Active:** Monitoring 5m Elliott Wave 3 Breakouts."

    table_body = "\n".join(table_rows)
    btn_block = "```button\nname 🔄 Refresh Prices Now\ntype command\naction Shell Commands: Execute Trade Simulator\nclass button-refresh\n```"

    report = f"""# 🎯 Options Momentum Trade Simulator

{btn_block}

- **Run Timestamp:** {now_str}
- **Target Call Return:** +20% Daily
- **Current Portfolio Valuation:** ${portfolio_valuation:,.2f} USD
- **Cumulative Realized PnL:** ${cum_realized:+,.2f} USD
- **Current Unrealized PnL:** ${total_unrealized_pnl:+,.2f} USD
- **Total Portfolio Growth (ROI):** {net_portfolio_roi:+.2f}%

{status_banner}

### Monitored Contracts & Active Positions
| Asset | Invested Total | Position Value | Asset Growth | Unrealized PnL | Avg Entry | Current Price | Last Check | TP Target (Calls) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_body}
"""
    os.makedirs(os.path.dirname(VAULT_REPORT_PATH), exist_ok=True)
    with open(VAULT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[{now_str}] Options simulation cycle complete. Report written to {VAULT_REPORT_PATH}")

if __name__ == "__main__":
    run_simulation_cycle()