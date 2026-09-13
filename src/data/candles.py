import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time
from zoneinfo import ZoneInfo

# Set timezone strictly to Central Time (Odessa, TX)
CENTRAL_TZ = ZoneInfo("America/Chicago")

class CandleManager:
    def __init__(self, tickers: list):
        self.tickers = tickers

    def fetch_intraday_data(self, symbol: str) -> pd.DataFrame:
        """Fetch 30-minute candles and strictly filter out overnight 'dead air'."""
        try:
            ticker = yf.Ticker(symbol)
            # Fetch data with extended hours included so we can manually slice it
            df = ticker.history(period="1mo", interval="30m", prepost=True)
            
            if df.empty:
                return pd.DataFrame()
            
            # Convert timestamp index to Central Time (CDT)
            df.index = df.index.tz_convert(CENTRAL_TZ)
            
            # Define our strict active window: 
            # 08:00 CDT candle captures the 08:00 - 08:30 window (includes the 15-min pre-market prep)
            # 15:30 CDT candle captures the 15:30 - 16:00 window (closes at the end of the 60-min after-hours wrap-up)
            start_time = time(8, 0)  
            end_time = time(15, 30)  
            
            # Extract time from the index and filter out the overnight junk
            df_time = df.index.time
            active_market_mask = (df_time >= start_time) & (df_time <= end_time)
            
            # Apply the filter mask
            filtered_df = df.loc[active_market_mask].copy()

            if filtered_df.empty or len(filtered_df) < 10:
                return pd.DataFrame()
                
            return filtered_df
            
        except Exception as e:
            print(f"[Candle 30M Filtering Error] {symbol}: {e}")
            return pd.DataFrame()

    def fetch_realtime_snapshot(self) -> dict:
        snapshot = {}
        for sym in self.tickers:
            df = self.fetch_intraday_data(sym)
            if not df.empty:
                snapshot[sym] = {
                    "price": float(df["Close"].iloc[-1]),
                    "high": float(df["High"].iloc[-1]),
                    "low": float(df["Low"].iloc[-1]),
                    "volume": float(df["Volume"].iloc[-1]),
                }
            else:
                snapshot[sym] = {"price": 0.0, "high": 0.0, "low": 0.0, "volume": 0.0}
        return snapshot

    def get_reference_levels(self, symbol: str) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="1d")
            if len(df) >= 2:
                prev_bar = df.iloc[-2]
                prev_close = float(prev_bar["Close"])
                pdh = float(prev_bar["High"])
                pdl = float(prev_bar["Low"])
            elif not df.empty:
                prev_bar = df.iloc[-1]
                prev_close = float(prev_bar["Close"])
                pdh = float(prev_bar["High"])
                pdl = float(prev_bar["Low"])
            else:
                prev_close, pdh, pdl = 100.0, 105.0, 95.0

            pivot = (pdh + pdl + prev_close) / 3.0
            r1 = (2 * pivot) - pdl
            s1 = (2 * pivot) - pdh
            s2 = pivot - (pdh - pdl)

            return {
                "prev_close": round(prev_close, 2),
                "pdh": round(pdh, 2),
                "pdl": round(pdl, 2),
                "pivot": round(pivot, 2),
                "r1": round(r1, 2),
                "s1": round(s1, 2),
                "s2": round(s2, 2)
            }
        except Exception as e:
            print(f"[Reference Levels Error] {symbol}: {e}")
            return {
                "prev_close": 100.0, "pdh": 105.0, "pdl": 95.0,
                "pivot": 100.0, "r1": 105.0, "s1": 95.0, "s2": 90.0
            }