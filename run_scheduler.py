import subprocess
import time
import schedule

def run_all_tasks():
    print("\n[Scheduler] Dispatching Market Tasks...")
    subprocess.run(["python", "strategies/ema_cross.py"])
    subprocess.run(["python", "strategies/trade_simulator.py"])

# Initial run on launch
run_all_tasks()

# Cycle every minute
schedule.every(1).minutes.do(run_all_tasks)

print("[Scheduler] Active and cycling every minute. Press Ctrl + C to stop.\n")
while True:
    schedule.run_pending()
    time.sleep(1)