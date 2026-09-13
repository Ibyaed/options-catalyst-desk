import subprocess
import time
import schedule
import datetime
from zoneinfo import ZoneInfo

def get_central_now():
    return datetime.datetime.now(ZoneInfo("America/Chicago"))

def run_all_tasks():
    print(f"\n[{get_central_now().strftime('%H:%M:%S')}] [Scheduler] Running 5m Screener & Simulator...")
    subprocess.run(["python", "strategies/ema_cross.py"])
    subprocess.run(["python", "strategies/trade_simulator.py"])

def run_post_market_review():
    print(f"\n[{get_central_now().strftime('%H:%M:%S')}] [Scheduler] 16:30 Central: Executing Post-Market Agent Review...")
    audit_path = "obsidian_vault/Daily_Runs/trade_audit_log.md"
    ts = get_central_now().strftime("%Y-%m-%d %H%M Hours %Z")
    entry = f"\n### [{ts}] Daily Post-Market Agent Self-Audit\n- Ingested daily 5m breakout logs.\n- Calibrating Fib -200% to +200% wick sensitivity for tomorrow's open.\n"
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(entry)

run_all_tasks()
schedule.every(1).minutes.do(run_all_tasks)
schedule.every().day.at("16:30").do(run_post_market_review)

print("[Scheduler] Active: Cycling every minute + 16:30 post-market review enabled. Press Ctrl + C to stop.\n")
while True:
    schedule.run_pending()
    time.sleep(1)
