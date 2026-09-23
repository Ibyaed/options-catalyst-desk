import pandas as pd
import numpy as np

def calculate_fib_matrix(high: float, low: float) -> dict:
    diff = high - low
    if diff <= 0:
        return {}
    return {
        "0.0%": round(low, 2),
        "23.6%": round(low + 0.236 * diff, 2),
        "38.2%": round(low + 0.382 * diff, 2),
        "50.0%": round(low + 0.500 * diff, 2),
        "61.8%": round(low + 0.618 * diff, 2),
        "78.6%": round(low + 0.786 * diff, 2),
        "100.0%": round(high, 2),
        "127.2%": round(high + 0.272 * diff, 2),
        "161.8%": round(high + 0.618 * diff, 2),
    }

def detect_regime_and_bias(df: pd.DataFrame, refs: dict) -> dict:
    if df is None or df.empty or len(df) < 15:
        return {
            "current_price": 0.0,
            "recommendation": "HOLD",
            "bias": "HOLD",
            "elliott_phase": "Wave 1 / Wave A (no projection)",
            "fib_level": "Waiting on first impulse",
            "trailing_target": "No target until W1/A completes",
            "options_bias": "Stay Out",
        }

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    price = float(close.iloc[-1])

    look = len(df)
    w_high = float(high.iloc[-look:].max())
    w_low = float(low.iloc[-look:].min())
    span = w_high - w_low
    if span <= 0:
        span = max(price * 0.01, 0.01)

    # Treat last swing as the completed impulse (Wave 1 if up, Wave A if down).
    up_impulse = price >= (w_low + 0.5 * span)
    impulse = span  # Wave 1 or Wave A length

    # Retrace from the impulse extreme
    if up_impulse:
        retrace_pct = (w_high - price) / impulse
        # W2/W4 buy pocket 50-78.6%; W3/W5 if price is extending through high
        if price > w_high:
            rec = "LONG (SPECULATIVE)"
            phase = "Wave 3 / Wave 5 Extension"
            fib = "Extension 100-161.8% of Wave 1 from end of W2"
            target = w_high + 1.618 * impulse
            bias = "Calls (Breakout Expansion)"
        elif 0.50 <= retrace_pct <= 0.786:
            rec = "LONG (SPECULATIVE)"
            phase = "Wave 2 / Wave 4 Retracement"
            fib = "Retrace 50-78.6% of Wave 1"
            target = w_high + 1.00 * impulse
            bias = "Calls (Retrace Pocket)"
        elif retrace_pct > 0.786:
            rec = "HOLD"
            phase = "Wave 2 invalid / possible Wave A"
            fib = "Broke 78.6% of Wave 1"
            target = price
            bias = "Stay Out / Iron Condor"
        else:
            rec = "HOLD"
            phase = "Wave 1 (no projection)"
            fib = "Impulse still forming"
            target = w_high
            bias = "Stay Out"
    else:
        retrace_pct = (price - w_low) / impulse
        if price < w_low:
            rec = "SHORT (SPECULATIVE)"
            phase = "Wave C Extension"
            fib = "Extension 61.8-161.8% of Wave A from end of B"
            target = w_low - 1.618 * impulse
            bias = "Puts (Breakdown Trend)"
        elif 0.50 <= retrace_pct <= 0.786:
            rec = "SHORT (SPECULATIVE)"
            phase = "Wave B Retracement"
            fib = "Retrace 50-78.6% of Wave A"
            target = w_low - 1.00 * impulse
            bias = "Puts (Retrace Pocket)"
        else:
            rec = "HOLD"
            phase = "Wave A (no projection)"
            fib = "Corrective impulse still forming"
            target = w_low
            bias = "Stay Out"

    return {
        "current_price": round(price, 2),
        "recommendation": rec,
        "bias": rec,
        "elliott_phase": phase,
        "fib_level": fib,
        "trailing_target": f"Target: ${target:,.2f}",
        "options_bias": bias,
    }