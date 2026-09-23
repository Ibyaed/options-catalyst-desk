import os
import json
import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")
HISTORY_FILE = "eval_history.json"
VAULT_ACCURACY_LOG = "obsidian_vault/Daily_Runs/hourly_accuracy_log.md"

class HourlyEvaluator:
    def __init__(self):
        self.history = self._load()

    def _load(self) -> dict:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"predictions": [], "completed": []}

    def _save(self):
        with open(HISTORY_FILE, "w") as f:
            json.dump(self.history, f, indent=2)

    def record_recommendation(self, symbol: str, price: float, bias: str, bull_trig: float, bear_trig: float):
        """Records a recommendation snapshot if one hasn't been logged in the last 45 mins."""
        now = datetime.datetime.now(CENTRAL_TZ)
        now_ts = now.timestamp()

        # Deduplicate: Don't log the same ticker multiple times in the same hour
        for p in self.history["predictions"]:
            if p["symbol"] == symbol and (now_ts - p["timestamp"] < 2700):
                return

        self.history["predictions"].append({
            "id": f"{symbol}_{int(now_ts)}",
            "symbol": symbol,
            "timestamp": now_ts,
            "time_str": now.strftime("%Y-%m-%d %H%M Hours %Z"),
            "entry_price": price,
            "bias": bias,
            "bull_trigger": bull_trig,
            "bear_trigger": bear_trig
        })
        self._save()

    def evaluate_outcomes(self, live_prices: dict):
        """Audits predictions older than 60 minutes (3600 seconds) against current market prints."""
        now = datetime.datetime.now(CENTRAL_TZ)
        now_ts = now.timestamp()
        remaining = []

        for p in self.history["predictions"]:
            elapsed = now_ts - p["timestamp"]
            sym = p["symbol"]
            curr_p = live_prices.get(sym, 0.0)

            # Evaluate once 1 hour has elapsed
            if elapsed >= 3600 and curr_p > 0.0:
                outcome = "NEUTRAL"
                delta_pct = ((curr_p - p["entry_price"]) / p["entry_price"]) * 100

                if "Calls" in p["bias"] or "Momentum" in p["bias"]:
                    outcome = "WIN" if curr_p >= p["bull_trigger"] else "LOSS" if curr_p <= p["bear_trigger"] else "NEUTRAL"
                elif "Puts" in p["bias"] or "Breakdown" in p["bias"]:
                    outcome = "WIN" if curr_p <= p["bear_trigger"] else "LOSS" if curr_p >= p["bull_trigger"] else "NEUTRAL"
                elif "Stay Out" in p["bias"] or "Iron Condor" in p["bias"]:
                    outcome = "WIN" if (p["bear_trigger"] <= curr_p <= p["bull_trigger"]) else "LOSS"

                record = {
                    "time": p["time_str"],
                    "eval_time": now.strftime("%H%M Hours %Z"),
                    "symbol": sym,
                    "bias": p["bias"],
                    "entry": p["entry_price"],
                    "exit": curr_p,
                    "delta_pct": round(delta_pct, 2),
                    "outcome": outcome
                }
                self.history["completed"].append(record)
                self._append_obsidian(record)
            else:
                remaining.append(p)

        self.history["predictions"] = remaining
        self._save()

    def _append_obsidian(self, r: dict):
        try:
            os.makedirs(os.path.dirname(VAULT_ACCURACY_LOG), exist_ok=True)
            need_header = not os.path.exists(VAULT_ACCURACY_LOG) or os.path.getsize(VAULT_ACCURACY_LOG) == 0
            with open(VAULT_ACCURACY_LOG, "a", encoding="utf-8") as f:
                if need_header:
                    f.write("# 🧪 Hourly Options Recommendation Audit Log\n\n")
                    f.write("| Entry Time | Eval Time | Symbol | Bias Given | Entry Price | 1hr Price | Move % | Verdict |\n")
                    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
                verdict_icon = "🟢 WIN" if r["outcome"] == "WIN" else "🔴 LOSS" if r["outcome"] == "LOSS" else "⚪ NEUTRAL"
                f.write(f"| {r['time']} | {r['eval_time']} | **{r['symbol']}** | {r['bias']} | ${r['entry']:,.2f} | ${r['exit']:,.2f} | {r['delta_pct']:+.2f}% | {verdict_icon} |\n")
        except Exception as e:
            print(f"[Obsidian Log Error] {e}")

    def get_stats(self) -> dict:
        done = self.history.get("completed", [])
        if not done:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": "N/A", "recent": []}
        wins = sum(1 for d in done if d["outcome"] == "WIN")
        losses = sum(1 for d in done if d["outcome"] == "LOSS")
        total = wins + losses
        win_rate = f"{(wins / total) * 100:.1f}%" if total > 0 else "100%"
        return {
            "total": len(done),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "recent": done[-5:]
        }
    def get_performance_stats(self):
        s = self.get_stats()
        return {
            "win_rate": s.get("win_rate", "N/A"),
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "total": s.get("total", 0),
        }