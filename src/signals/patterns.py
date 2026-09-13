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
    if df.empty or len(df) < 15:
        return {
            "current_price": 0.0,
            "recommendation": "NEUTRAL / WAIT",
            "elliott_phase": "Wave 1 (Base Accumulation)",
            "fib_level": "Golden Pocket (50–61.8%)",
            "trailing_target": "Target: $0.00",
            "options_bias": "Calls (Breakout Expansion)",
        }

    close = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values
    current_price = round(float(close[-1]), 2)

    # 30-minute EMAs
    ema8 = pd.Series(close).ewm(span=8).mean().iloc[-1]
    ema21 = pd.Series(close).ewm(span=21).mean().iloc[-1]
    ema55 = pd.Series(close).ewm(span=55).mean().iloc[-1]

    lookback = min(40, len(df))
    swing_high = float(np.max(highs[-lookback:]))
    swing_low = float(np.min(lows[-lookback:]))
    fibs = calculate_fib_matrix(swing_high, swing_low)

    # Calculate Fib bracket wording
    fib_50 = fibs.get("50.0%", swing_low)
    fib_618 = fibs.get("61.8%", swing_high)
    diff = swing_high - swing_low

    if diff > 0:
        ratio = (current_price - swing_low) / diff
        if 0.45 <= ratio <= 0.68:
            fib_level = "Golden Pocket (50–61.8%)"
        elif ratio < 0.45:
            fib_level = "Deep Retracement (<61.8%)"
        else:
            fib_level = "Extension (100–161.8%)"
    else:
        fib_level = "Golden Pocket (50–61.8%)"

    # 30-minute ATR for target/inval distance
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(abs(highs[1:] - close[:-1]), abs(lows[1:] - close[:-1]))
    )
    atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else 1.20

    # Trend & Elliott Wave phase classification matching the previous UI
    if current_price >= ema21 and ema8 >= ema21:
        recommendation = "LONG (SPECULATIVE)"
        elliott_phase = "Wave 1 (Base Accumulation)"
        target_val = round(current_price + (1.5 * atr), 2)
        trailing_target = f"Target: ${target_val:,.2f}"
        options_bias = "Calls (Breakout Expansion)"
    elif current_price < ema55 and ema8 < ema21:
        # Check for exhaustion bounce vs trending breakdown
        if current_price <= swing_low + (0.3 * atr):
            recommendation = "COVER / BUY REVERSAL"
            elliott_phase = "Wave C (Exhaustion Low)"
            inval_val = round(current_price - (0.8 * atr), 2)
            trailing_target = f"Inval: ${inval_val:,.2f}"
            options_bias = "Stay Out / Iron Condor"
        else:
            recommendation = "SHORT (SPECULATIVE)"
            elliott_phase = "Wave 3 Bearish / Wave C"
            inval_val = round(current_price + (1.2 * atr), 2)
            trailing_target = f"Inval: ${inval_val:,.2f}"
            options_bias = "Puts (Breakdown Trend)"
    else:
        recommendation = "COVER / BUY REVERSAL"
        elliott_phase = "Wave 1 (Base Accumulation)"
        inval_val = round(current_price - atr, 2)
        trailing_target = f"Inval: ${inval_val:,.2f}"
        options_bias = "Calls (Breakout Expansion)"

    return {
        "current_price": current_price,
        "recommendation": recommendation,
        "elliott_phase": elliott_phase,
        "fib_level": fib_level,
        "trailing_target": trailing_target,
        "options_bias": options_bias,
    }