import tkinter as tk
from tkinter import ttk
from datetime import datetime
from zoneinfo import ZoneInfo
import threading

from src.config import TRACKED_TICKERS
from src.data.candles import CandleManager
from src.data.news import CatalystAgent
from src.data.trending import TrendingScanner
from src.signals.patterns import detect_regime_and_bias
from src.signals.evaluator import HourlyEvaluator

CENTRAL_TZ = ZoneInfo("America/Chicago")

manager = CandleManager(tickers=TRACKED_TICKERS)
catalyst_agent = CatalystAgent()
trending_scanner = TrendingScanner()
evaluator = HourlyEvaluator()

class DesktopOptionsDesk(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Options Catalyst Desk - Native Desktop Engine")
        self.geometry("1100x750")
        self.configure(bg="#060913")

        self.cards_data = {}
        self.build_ui()
        self.refresh_data_async()

    def build_ui(self):
        header_frame = tk.Frame(self, bg="#0b1120", pady=12, padx=16)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header_frame,
            text="OPTIONS CATALYST DESK (5-MIN ENGINE)",
            font=("Segoe UI", 16, "bold"),
            fg="#f8fafc",
            bg="#0b1120"
        )
        title_lbl.pack(side=tk.LEFT)

        self.refresh_btn = tk.Button(
            header_frame,
            text="RECYCLE / REFRESH",
            command=self.refresh_data_async,
            bg="#0f172a",
            fg="#38bdf8",
            activebackground="#1e293b",
            activeforeground="#38bdf8",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2"
        )
        self.refresh_btn.pack(side=tk.RIGHT)

        self.status_lbl = tk.Label(
            self,
            text="Initializing data stream...",
            font=("Segoe UI", 9, "italic"),
            fg="#94a3b8",
            bg="#060913",
            pady=6
        )
        self.status_lbl.pack(fill=tk.X)

        container = tk.Frame(self, bg="#060913")
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        cols = ("Symbol", "Price", "Signal", "Wave Phase", "Fib Zone", "Stop / Trail Target", "Bias")
        self.tree = ttk.Treeview(container, columns=cols, show="headings", height=18)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#0b1120",
            foreground="#e2e8f0",
            rowheight=32,
            fieldbackground="#0b1120",
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background="#0f172a",
            foreground="#38bdf8",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview", background=[("selected", "#1e293b")])

        widths = {
            "Symbol": 90,
            "Price": 95,
            "Signal": 140,
            "Wave Phase": 220,
            "Fib Zone": 200,
            "Stop / Trail Target": 170,
            "Bias": 160
        }

        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths.get(col, 120), anchor=tk.W)

        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_data_async(self):
        self.refresh_btn.config(text="UPDATING...", state=tk.DISABLED)
        threading.Thread(target=self._fetch_and_update, daemon=True).start()

    def _fetch_and_update(self):
        now = datetime.now(CENTRAL_TZ)
        now_str = now.strftime("%H:%M:%S CDT")

        records = []
        for sym in TRACKED_TICKERS:
            try:
                df = manager.fetch_intraday_data(sym)
                refs = manager.get_reference_levels(sym)
                analysis = detect_regime_and_bias(df, refs)

                price = analysis.get("current_price", 0.0)
                price_str = f"${price:,.2f}" if price > 0 else "Active"
                rec = analysis.get("recommendation", "HOLD / NEUTRAL")
                ew = analysis.get("elliott_phase", "Consolidation")
                fib = analysis.get("fib_level", "N/A")
                trail = analysis.get("trailing_target", "N/A")
                bias = analysis.get("options_bias", "Stay Out")

                records.append((sym, price_str, rec, ew, fib, trail, bias))
            except Exception as e:
                records.append((sym, "Error", "OFFLINE", str(e), "--", "--", "--"))

        self.after(0, self._render_rows, records, now_str)

    def _render_rows(self, records, timestamp):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in records:
            self.tree.insert("", tk.END, values=r)

        self.status_lbl.config(text=f"Last synchronized: {timestamp} | 5-Minute Intraday Engine Active")
        self.refresh_btn.config(text="RECYCLE / REFRESH", state=tk.NORMAL)

if __name__ == "__main__":
    app = DesktopOptionsDesk()
    app.mainloop()