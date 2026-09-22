import os
import json
import urllib.request
import pandas as pd
import numpy as np
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

# Absolute path to retrospective memory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEMORY_PATH = os.path.join(BASE_DIR, "obsidian_vault", "Daily_Runs", "agent_memory_state.md")

def get_latest_agent_memory() -> str:
    """Reads retrospective lessons learned from past trades."""
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return "No prior retrospective memory recorded."

def generate_ollama_thesis(symbol: str, company: str, price: float, rating: str, headline: str) -> str:
    """Queries local Ollama instance incorporating retrospective memory."""
    memory_context = get_latest_agent_memory()

    prompt = f"""You are an equity options quantitative desk risk officer analyzing ${symbol} ({company}).
DO NOT confuse the ticker with software or acronyms.

Algorithmic Quantitative Signals:
- Quantitative Model Bias: {rating}
- Last Price: ${price:,.2f}
- Catalyst: {headline}

Obsidian Retrospective Trade Memory:
{memory_context}

Task:
Provide exactly 2 concise sentences explaining the operational thesis.
CRITICAL INSTRUCTION:
1. You MUST align your strategy strictly with the Quantitative Model Bias: "{rating}".
   - If "Neutral / Spreads": emphasize theta decay, range consolidation, iron condors, or waiting for trigger confirmation. DO NOT recommend directional calls or puts.
   - If "Overweight / Calls": analyze upside delta expansion while factoring past volatility lessons.
   - If "Underweight / Puts": analyze downside breakdown trend and capital preservation.
2. Synthesize past session lessons (managing risk, position sizing) directly into this specific ticker's context.
"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 120
        }
    }

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ai_text = data.get("response", "").strip()
            if ai_text:
                return ai_text
    except Exception as e:
        pass

    return (
        f"Trading Desk Bi-Weekly Model (10–14 DTE): Volatility profile favors {rating} swing expansion. "
        f"Execution focuses on structural liquidity pivots and managed delta risk."
    )

def run_multi_agent_assessment(symbol: str, df: pd.DataFrame, refs: dict, catalyst_headline: str = "") -> dict:
    current_p = float(refs.get("prev_close", 100.0))
    if df is not None and not df.empty and "Close" in df.columns:
        current_p = float(df["Close"].iloc[-1])

    pdh = float(refs.get("pdh", current_p * 1.015))
    pdl = float(refs.get("pdl", current_p * 0.985))

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

    company_name = company_names.get(symbol, f"{symbol} Asset Corp")
    desk_view_ai = generate_ollama_thesis(symbol, company_name, current_p, rating, catalyst_headline)

    return {
        "symbol": symbol,
        "company_name": company_name,
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
            "targets": f"\({bull_t1:,.2f} /\){bull_t2:,.2f}",
            "invalidate": f"${bull_inval:,.2f}",
            "rr": f"{bull_rr:.2f} planned"
        },
        "bear_leg": {
            "trigger": f"${bear_trig:,.2f}",
            "targets": f"\({bear_t1:,.2f} /\){bear_t2:,.2f}",
            "invalidate": f"${bear_inval:,.2f}",
            "rr": f"{bear_rr:.2f} planned"
        },
        "desk_view": desk_view_ai,
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
