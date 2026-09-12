import os
import re
import json
import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import ccxt

STATE_FILE = "trade_state.json"
VAULT_REPORT_PATH = "obsidian_vault/Daily_Runs/trade_simulator_status.md"
AUDIT_LOG_PATH = "obsidian_vault/Daily_Runs/trade_audit_log.md"

MONITORED_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"]
BASE_ALLOCATION = 2000.0
WEEKLY_INJECTION = 150.0

GOOGLE_FINANCE_MAP = {
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "SOL/USD": "SOL-USD"
}

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
        "weekly_deposit_amount": WEEKLY_INJECTION,
        "last_deposit_date": None
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def log_audit_event(action, details):
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    ts = get_central_str(get_central_now())
    entry = f"- **[{ts}] {action}:** {details}\n"
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(entry)

def get_google_finance_price(symbol, fallback_exchange=None):
    ticker_slug = GOOGLE_FINANCE_MAP.get(symbol)
    if ticker_slug:
        url = f"https://www.google.com/finance/quote/{ticker_slug}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                price_elem = soup.find("div", class_="YMlKec fxKbKc")
                if price_elem:
                    cleaned_price = re.sub(r"[^\d.]", "", price_elem.text.strip())
                    return float(cleaned_price)
        except Exception as e:
            print(f"[Google Finance Warning] Failed fetching {symbol}: {e}. Falling back...")

    if fallback_exchange:
        try:
            return float(fallback_exchange.fetch_ticker(symbol)["last"])
        except Exception as e:
            print(f"[Fallback Error] CCXT failed for {symbol}: {e}")

    return None

def process_weekly_deposit(state, exchange):
    now = get_central_now()
    last_dep_str = state.get("last_deposit_date")

    if not last_dep_str:
        state["last_deposit_date"] = now.date().isoformat()
        state["total_deposited_cash"] = state.get("total_deposited_cash", 6000.0)
        save_state(state)
        return

    last_dep_date = datetime.date.fromisoformat(last_dep_str)
    days_elapsed = (now.date() - last_dep_date).days

    if days_elapsed >= 7:
        deposit_total = float(state.get("weekly_deposit_amount", WEEKLY_INJECTION))
        split_share = deposit_total / len(MONITORED_PAIRS)

        state["total_deposited_cash"] = float(state.get("total_deposited_cash", 6000.0)) + deposit_total
        state["last_deposit_date"] = now.date().isoformat()

        for symbol in MONITORED_PAIRS:
            live_price = get_google_finance_price(symbol, fallback_exchange=exchange)
            if live_price is None:
                continue

            added_units = split_share / live_price

            if symbol in state.get("active_trades", {}):
                pos = state["active_trades"][symbol]
                old_alloc = float(pos["allocation"])
                old_units = float(pos.get("units", old_alloc / pos["entry_price"]))

                new_units = old_units + added_units
                new_alloc = old_alloc + split_share

                pos["entry_price"] = new_alloc / new_units
                pos["allocation"] = new_alloc
                pos["units"] = new_units
            else:
                state.setdefault("active_trades", {})[symbol] = {
                    "allocation": split_share,
                    "entry_price": live_price,
                    "units": added_units
                }

        log_audit_event(
            "WEEKLY DCA DEPOSIT",
            f"Added ${deposit_total:,.2f} USD (+${split_share:,.2f} to BTC, ETH, SOL). Total Principal: ${state['total_deposited_cash']:,.2f} USD"
        )
        save_state(state)

def run_simulation_cycle():
    exchange = ccxt.coinbase()
    state = load_state()
    now = get_central_now()
    now_str = get_central_str(now)
    time_mil = now.strftime("%H%M")  # Military time (e.g. 1640)

    process_weekly_deposit(state, exchange)

    cb_time_str = state.get("circuit_breaker_until")
    cb_active = False

    if cb_time_str:
        try:
            cb_until = datetime.datetime.fromisoformat(cb_time_str)
            if now < cb_until and not state.get("manual_override", False):
                cb_active = True
            else:
                state["circuit_breaker_until"] = None
                state["manual_override"] = False
                log_audit_event("CIRCUIT BREAKER RESET", "Lockout elapsed. Trading operations resumed.")
                save_state(state)
        except Exception:
            state["circuit_breaker_until"] = None
            save_state(state)

    table_rows = []
    portfolio_valuation = 0.0
    total_unrealized_pnl = 0.0
    active_trades = state.get("active_trades", {})

    for symbol in MONITORED_PAIRS:
        curr_price = get_google_finance_price(symbol, fallback_exchange=exchange)
        if curr_price is None:
            continue

        if symbol not in active_trades and not cb_active:
            alloc = BASE_ALLOCATION
            units = alloc / curr_price
            active_trades[symbol] = {
                "allocation": alloc,
                "entry_price": curr_price,
                "units": units
            }
            log_audit_event("POSITION ENTERED", f"Opened {symbol} at ${curr_price:,.2f} (Stake: ${alloc:,.2f} USD)")

        if symbol in active_trades:
            pos = active_trades[symbol]
            invested_total = float(pos["allocation"])
            units = float(pos["units"])
            avg_entry = float(pos["entry_price"])

            position_value = units * curr_price
            pnl_dollars = position_value - invested_total
            growth_pct = (pnl_dollars / invested_total) * 100 if invested_total > 0 else 0.0

            tp_target_price = avg_entry * 1.05
            sl_target_price = avg_entry * 0.98

            if curr_price >= tp_target_price:
                state["cumulative_realized_pnl"] += pnl_dollars
                log_audit_event("TAKE-PROFIT HIT (+5%)", f"Sold {symbol} at ${curr_price:,.2f} | Realized: ${pnl_dollars:+,.2f} USD")
                del active_trades[symbol]
                continue
            elif curr_price <= sl_target_price:
                state["cumulative_realized_pnl"] += pnl_dollars
                lockout_end = now + datetime.timedelta(hours=12)
                state["circuit_breaker_until"] = lockout_end.isoformat()
                log_audit_event("STOP-LOSS HIT (-2%)", f"Sold {symbol} at ${curr_price:,.2f} | Loss: ${pnl_dollars:+,.2f} USD | 12h Circuit Breaker engaged until {get_central_str(lockout_end)}")
                del active_trades[symbol]
                cb_active = True
                continue

            portfolio_valuation += position_value
            total_unrealized_pnl += pnl_dollars

            table_rows.append(
                f"| {symbol} | ${invested_total:,.2f} | ${position_value:,.2f} | {growth_pct:+.2f}% | ${pnl_dollars:+,.2f} | ${avg_entry:,.2f} | ${curr_price:,.2f} | {time_mil} CST | ${tp_target_price:,.2f} |"
            )
        else:
            table_rows.append(
                f"| {symbol} | $0.00 | $0.00 | 0.00% | $0.00 | — | ${curr_price:,.2f} | {time_mil} CST | — |"
            )

    state["active_trades"] = active_trades
    save_state(state)

    total_deposited = float(state.get("total_deposited_cash", 6000.0))
    cum_realized = float(state.get("cumulative_realized_pnl", 0.0))
    net_portfolio_roi = ((portfolio_valuation + cum_realized - total_deposited) / total_deposited) * 100 if total_deposited > 0 else 0.0

    if cb_active and state.get("circuit_breaker_until"):
        cb_dt = datetime.datetime.fromisoformat(state["circuit_breaker_until"])
        status_banner = f"> ⛔ **CIRCUIT BREAKER ACTIVE:** System halted until **{get_central_str(cb_dt)}** due to -2% stop-loss. Set `manual_override: true` in `trade_state.json` to resume early."
    else:
        status_banner = "🟢 **All Systems Nominal:** Portfolio positions tracking within parameters."

    table_body = "\n".join(table_rows)
    btn_block = "```button\nname 🔄 Refresh Prices Now\ntype command\naction Shell Commands: Execute Trade Simulator\nclass button-refresh\n```"

    report = f"""# 🎯 Multi-Asset Trade Simulator Dashboard

{btn_block}

- **Run Timestamp:** {now_str} (Source: Google Finance)
- **Total Principal Deposited:** ${total_deposited:,.2f} USD (+$150/week DCA)
- **Current Portfolio Valuation:** ${portfolio_valuation:,.2f} USD
- **Cumulative Realized PnL:** ${cum_realized:+,.2f} USD
- **Current Unrealized PnL:** ${total_unrealized_pnl:+,.2f} USD
- **Total Portfolio Growth (ROI):** {net_portfolio_roi:+.2f}%
- **Risk Rules:** Target Profit = +5% / Stop Loss = -2% on allocated capital

{status_banner}

### Active Positions & Growth
| Asset | Invested Total | Position Value | Asset Growth | Unrealized PnL | Avg Entry | Current Price | Last Check | TP Target (+5%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_body}
"""

    os.makedirs(os.path.dirname(VAULT_REPORT_PATH), exist_ok=True)
    with open(VAULT_REPORT_PATH, "w") as f:
        f.write(report)

    print(f"[{now_str}] Multi-asset check complete ({time_mil} CST). Unrealized PnL: ${total_unrealized_pnl:+,.2f}")

if __name__ == "__main__":
    run_simulation_cycle()
