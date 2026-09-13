import pandas as pd
import numpy as np
from datetime import datetime

def run_multi_agent_assessment(symbol: str, df: pd.DataFrame, refs: dict, catalyst_headline: str = "") -> dict:
    current_p = float(refs.get("prev_close", 100.0))
    if df is not None and not df.empty and "Close" in df.columns:
        current_p = float(df["Close"].iloc[-1])

    pdh = float(refs.get("pdh", current_p * 1.015))
    pdl = float(refs.get("pdl", current_p * 0.985))

    # Bi-Weekly (10-14 DTE) Multipliers: Wider targets & invalidations to absorb intraday noise
    bull_trig = round(max(pdh, current_p * 1.008), 2)
    bull_t1 = round(bull_trig * 1.025, 2)
    bull_t2 = round(bull_trig * 1.050, 2)
    bull_inval = round(bull_trig * 0.988, 2)
    bull_rr = round((bull_t1 - bull_trig) / max(0.05, (bull_trig - bull_inval)), 2)

    bear_trig = round(min(pdl, current_p * 0.992), 2)
    bear_t1 = round(bear_trig * 0.975, 2)
    bear_t2 = round(bear_trig * 0.950, 2)
    bear_inval = round(bear_trig * 1.012, 2)
    bear_rr = round((bear_trig - bear_t1) / max(0.05, (bear_inval - bear_trig)), 2)

    # Desk Bias & Regime
    if current_p > pdh:
        rating = "Overweight / Calls"
        bias_color = "#10b981"
        target_p = bull_t1
        regime = "Expanding (Trend)"
        gamma = "Positive (Expansion)"
        ict_phase = "Distribution / Run"
    elif current_p < pdl:
        rating = "Underweight / Puts"
        bias_color = "#ef4444"
        target_p = bear_t1
        regime = "Expanding (Trend)"
        gamma = "Negative (Short Gamma)"
        ict_phase = "Liquidity Purge"
    else:
        rating = "Neutral / Spreads"
        bias_color = "#f59e0b"
        target_p = round((pdh + pdl) / 2, 2)
        regime = "Compressing (Range)"
        gamma = "Neutral (Theta Positive)"
        ict_phase = "Consolidation / Accumulation"

    upside_pct = round(((target_p - current_p) / current_p) * 100, 2)

    company_names = {
        "TSLA": "Tesla, Inc.",
        "SPCX": "Space Exploration Technologies Corp.",
        "NVDA": "NVIDIA Corporation",
        "AMD": "Advanced Micro Devices, Inc.",
        "NFLX": "Netflix, Inc.",
        "GME": "GameStop Corp.",
        "SPY": "SPDR S&P 500 ETF Trust",
        "ADBE": "Adobe Inc."
    }

    return {
        "symbol": symbol,
        "company_name": company_names.get(symbol, f"{symbol} Asset Corp"),
        "rating": rating,
        "bias_color": bias_color,
        "premarket_price": f"${current_p:,.2f}",
        "price_target": f"${target_p:,.2f}",
        "target_upside": f"{upside_pct:+.2f}% vs last",
        "regime": regime,
        "ict_phase": ict_phase,
        "gamma": gamma,
        "reference_level": f"${pdh:,.2f}",
        "bull_leg": {
            "trigger": f"${bull_trig:,.2f}",
            "targets": f"${bull_t1:,.2f} / ${bull_t2:,.2f}",
            "invalidate": f"${bull_inval:,.2f}",
            "rr": f"{bull_rr:.2f} planned"
        },
        "bear_leg": {
            "trigger": f"${bear_trig:,.2f}",
            "targets": f"${bear_t1:,.2f} / ${bear_t2:,.2f}",
            "invalidate": f"${bear_inval:,.2f}",
            "rr": f"{bear_rr:.2f} planned"
        },
        "desk_view": (
            f"Trading Desk Bi-Weekly Model (10–14 DTE): Volatility profile favors swing expansion without "
            f"0DTE theta clipping. Optimal execution focuses on weekly contract rollover targeting structural liquidity pivots."
        ),
        "thesis_bullets": [
            f"Bi-Weekly Horizon: Positioned to capture 10–14 DTE delta trend while dampening intraday noise.",
            f"Gamma Stability: Subdued gamma pin risk prevents premature stop-outs during midday chop.",
            f"Institutional Target: Planned invalidation strictly anchored to multi-day liquidity brackets."
        ],
        "key_levels": {
            "s2": f"${pdl * 0.985:,.2f}",
            "s1": f"${pdl:,.2f}",
            "pmh": f"${pdh:,.2f}",
            "r1": f"${pdh * 1.015:,.2f}"
        },
        "catalyst_headline": catalyst_headline or "Active institutional order flow."
    }