import os
import datetime
import subprocess
from zoneinfo import ZoneInfo
from src.config import TRACKED_TICKERS, LOGS_DIR
from src.data.candles import CandleManager
from src.signals.patterns import detect_regime_and_bias

CENTRAL_TZ = ZoneInfo("America/Chicago")

def generate_daily_obsidian_log():
    manager = CandleManager(tickers=TRACKED_TICKERS)
    now = datetime.datetime.now(CENTRAL_TZ)
    date_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.strftime("%Y-%m-%d %H%M Hours %Z")
    
    os.makedirs(LOGS_DIR, exist_ok=True)
    file_path = os.path.join(LOGS_DIR, f"{date_str}-Desk.md")

    table_rows = []
    for sym in TRACKED_TICKERS:
        df = manager.fetch_intraday_data(sym)
        refs = manager.get_reference_levels(sym)
        analysis = detect_regime_and_bias(df, refs)

        price_str = f"${analysis['current_price']:,.2f}" if analysis['current_price'] else "Awaiting Data"
        bull_str = f">${analysis['bull_trigger']:,.2f}"
        bear_str = f">${analysis['bear_trigger']:,.2f}"

        table_rows.append(
            f"| **{sym}** | {price_str} | {analysis['regime']} | {analysis['options_bias']} | >{bull_str} | <{bear_str} | {analysis['note']} |"
        )

    table_content = "\n".join(table_rows)

    markdown_body = (
        f"# 🏛️ Options Catalyst Desk :: {date_str}\n\n"
        f"- **Last Scan:** {timestamp_str}\n"
        f"- **Monitored Universe:** {', '.join(TRACKED_TICKERS)}\n"
        f"- **Cadence:** 5-Minute Intraday Engine (Central US)\n\n"
        f"### Live Desk Board\n"
        f"| Ticker | Price | Regime | Bias (0DTE/35DTE) | Bull Trigger | Bear Trigger | Key Notes |\n"
        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        f"{table_content}\n\n"
        f"---\n"
        f"*Generated autonomously by Options Catalyst Desk Engine.*\n"
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_body)
    
    print(f"[{timestamp_str}] Successfully exported desk log to {file_path}")

def push_obsidian_updates():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("No GitHub token found, skipping sync.")
        return

    repo_url = f"https://{token}@github.com/Ibyaed/options-catalyst-desk.git"
    
    try:
        subprocess.run(["git", "config", "--global", "user.email", "render-bot@options-desk.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "Render Cloud Bot"], check=True)
        subprocess.run(["git", "remote", "set-url", "origin", repo_url], check=True)
        subprocess.run(["git", "add", "obsidian_vault/"], check=True)
        subprocess.run(["git", "commit", "-m", "Auto-sync: Render updated Obsidian logs"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("Successfully synced Obsidian updates to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"Git sync failed or no changes to push: {e}")

if __name__ == "__main__":
    generate_daily_obsidian_log()
    push_obsidian_updates()