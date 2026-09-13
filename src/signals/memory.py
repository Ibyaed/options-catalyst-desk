import json
import os

MEMORY_FILE = "eval_history.json"

class AgentMemoryBank:
    def __init__(self, memory_path=MEMORY_FILE):
        self.memory_path = memory_path

    def get_symbol_track_record(self, symbol: str) -> dict:
        """Analyzes historical win/loss ratios and recent pitfalls for a specific symbol."""
        if not os.path.exists(self.memory_path):
            return {"win_rate": "N/A", "penalty": 0.0, "notes": "No memory on record."}

        try:
            with open(self.memory_path, "r") as f:
                data = json.load(f)
        except Exception:
            return {"win_rate": "N/A", "penalty": 0.0, "notes": "Memory unreadable."}

        completed = [d for d in data.get("completed", []) if d.get("symbol") == symbol]
        if not completed:
            return {"win_rate": "100%", "penalty": 0.0, "notes": "Clean slate / Initial run."}

        wins = sum(1 for d in completed if d.get("outcome") == "WIN")
        losses = sum(1 for d in completed if d.get("outcome") == "LOSS")
        total = wins + losses

        if total == 0:
            return {"win_rate": "100%", "penalty": 0.0, "notes": "Awaiting first settlement."}

        ratio = (wins / total) * 100
        
        # Adaptive Penalty / Reinforcement Loop:
        # If win rate drops below 45%, apply conservative bias penalty
        penalty = 0.0
        notes = f"Historical: {ratio:.0f}% win rate ({wins}W / {losses}L)."
        if ratio < 50.0:
            penalty = 0.25  # Require higher ATR confirmation buffer
            notes += " [Self-Correction: Tightening trigger bands due to recent whipsaws]"
        elif ratio >= 75.0:
            notes += " [High Conviction: Strong trend follow-through observed]"

        return {
            "win_rate": f"{ratio:.0f}%",
            "penalty": penalty,
            "wins": wins,
            "losses": losses,
            "notes": notes
        }