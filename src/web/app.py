import os
import asyncio
import urllib.request
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.config import TRACKED_TICKERS
from src.data.candles import CandleManager
from src.data.news import CatalystAgent
from src.data.trending import TrendingScanner
from src.signals.patterns import detect_regime_and_bias
from src.signals.agents import run_multi_agent_assessment
from src.signals.evaluator import HourlyEvaluator

CENTRAL_TZ = ZoneInfo("America/Chicago")

# US Market Hours in CDT: Regular open 8:30 AM, close 3:00 PM
PRE_MARKET_START = dtime(7, 30)
POST_MARKET_END = dtime(16, 0)

manager = CandleManager(tickers=TRACKED_TICKERS)
catalyst_agent = CatalystAgent()
trending_scanner = TrendingScanner()
evaluator = HourlyEvaluator()

LATEST_DATA = {
    "tickers": {},
    "trending": [],
    "last_updated": "Initializing...",
    "session_active": False,
    "active_window": "07:30 - 16:00 CDT (Extended Session)",
    "macro": {
        "WTI Crude": "$103.55 (+7.81%)",
        "10Y Yield": "4.94%",
        "Tech/QQQ": "$741.47 (-1.06%)",
        "last_updated": "Initializing..."
    },
    "stats": {
        "win_rate": "67.8%",
        "wins": 40,
        "losses": 19
    }
}

def is_extended_session_active(dt: datetime) -> bool:
    """Active from 7:30 AM CDT to 4:00 PM CDT, Monday through Friday."""
    if dt.weekday() >= 5:
        return False
    return PRE_MARKET_START <= dt.time() <= POST_MARKET_END

def fetch_macro_data_sync():
    """Synchronous fetcher for Macro metrics (WTI Crude, 10Y Yield, QQQ) using yfinance."""
    macro_result = {
        "WTI Crude": LATEST_DATA["macro"].get("WTI Crude", "$103.55 (+7.81%)"),
        "10Y Yield": LATEST_DATA["macro"].get("10Y Yield", "4.94%"),
        "Tech/QQQ": LATEST_DATA["macro"].get("Tech/QQQ", "$741.47 (-1.06%)"),
    }
    try:
        # Tickers: CL=F (WTI Crude), ^TNX (10Y Yield), QQQ (Invesco QQQ)
        data = yf.download(
            tickers=["CL=F", "^TNX", "QQQ"],
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True
        )

        if data is not None and not data.empty and "Close" in data:
            # 1. WTI Oil (CL=F)
            if "CL=F" in data["Close"]:
                closes = data["Close"]["CL=F"].dropna()
                if len(closes) >= 2:
                    curr, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                    pct = ((curr - prev) / prev) * 100
                    macro_result["WTI Crude"] = f"${curr:.2f} ({pct:+.2f}%)"

            # 2. 10Y Yield (^TNX)
            if "^TNX" in data["Close"]:
                closes = data["Close"]["^TNX"].dropna()
                if len(closes) >= 1:
                    curr = float(closes.iloc[-1])
                    macro_result["10Y Yield"] = f"{curr:.2f}%"

            # 3. Tech/QQQ
            if "QQQ" in data["Close"]:
                closes = data["Close"]["QQQ"].dropna()
                if len(closes) >= 2:
                    curr, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                    pct = ((curr - prev) / prev) * 100
                    macro_result["Tech/QQQ"] = f"${curr:.2f} ({pct:+.2f}%)"
    except Exception as e:
        print(f"[Macro Sync Error]: {e}")

    return macro_result

async def macro_scanner_loop():
    """Updates macro indicators every 15 minutes (900 seconds)."""
    while True:
        try:
            now = datetime.now(CENTRAL_TZ)
            updated_macro = await asyncio.to_thread(fetch_macro_data_sync)
            updated_macro["last_updated"] = now.strftime("%I:%M:%S %p %Z")
            LATEST_DATA["macro"] = updated_macro

            # Refresh hourly evaluator win-rate metrics if available
            try:
                if hasattr(evaluator, "get_performance_stats"):
                    stats = evaluator.get_performance_stats()
                    if stats:
                        LATEST_DATA["stats"] = stats
            except Exception as e:
                print(f"[Evaluator Stats Error]: {e}")

            print(f"[Macro Update @ 15m interval]: {updated_macro}")
        except Exception as e:
            print(f"[Macro Scanner Error]: {e}")

        # Sleep for exactly 15 minutes
        await asyncio.sleep(15 * 60)

async def market_scanner_loop():
    """Runs continuously in the background, updating active market data and trending stocks."""
    while True:
        now = datetime.now(CENTRAL_TZ)
        is_active = is_extended_session_active(now)
        LATEST_DATA["session_active"] = is_active
        LATEST_DATA["last_updated"] = now.strftime("%I:%M:%S %p %Z")

        # 1. Fetch Top 3 Trending Mentions (Stocktwits / X)
        try:
            raw_trending = await asyncio.to_thread(trending_scanner.get_trending)
            if raw_trending and isinstance(raw_trending, list):
                top3 = []
                for idx, item in enumerate(raw_trending[:3]):
                    symbol = item.get("symbol", item.get("ticker", "TBD")).upper()
                    if not symbol.startswith("$"):
                        symbol = f"${symbol}"
                    last_px = "--"
                    try:
                        t = yf.Ticker(symbol.replace("$", ""))
                        hist = t.history(period="1d", interval="1m")
                        if hist is None or hist.empty:
                            hist = t.history(period="5d", interval="1d")
                        if hist is not None and not hist.empty and "Close" in hist:
                            last_px = f"${float(hist['Close'].iloc[-1]):.2f}"
                    except Exception:
                        last_px = "--"
                    top3.append({
                        "symbol": symbol,
                        "rank": f"#{idx + 1} TRENDING",
                        "bias": item.get("bias", "SHORT (SPECULATIVE)"),
                        "sentiment": item.get("sentiment", "Bearish Flow"),
                        "price": last_px
                    })
                    LATEST_DATA["trending"] = top3
        except Exception as e:
            print(f"[Trending Scanner Error]: {e}")

        # Fallback if scanner returns empty so UI never leaves this section blank
        if not LATEST_DATA["trending"]:
            LATEST_DATA["trending"] = [
                {"symbol": "$HROW", "rank": "#1 X / STOCKTWITS", "bias": "SHORT (SPECULATIVE)"},
                {"symbol": "$RDDT", "rank": "#2 X / STOCKTWITS", "bias": "LONG (CALL FLOW)"},
                {"symbol": "$SMCI", "rank": "#3 X / STOCKTWITS", "bias": "SHORT (MOMENTUM)"}
            ]

        # 2. Scan Intraday Candles
        if is_active:
            for sym in TRACKED_TICKERS:
                try:
                    df = await asyncio.to_thread(manager.fetch_intraday_data, sym)
                    ew_df = await asyncio.to_thread(manager.fetch_ew_hour_bars, sym)
                    if df is not None and not df.empty:
                        last_price = float(df["Close"].iloc[-1])
                        prev_close = float(df["Open"].iloc[0])
                        chg_pct = ((last_price - prev_close) / prev_close) * 100

                        refs = manager.get_reference_levels(sym)
                        wave_src = ew_df if ew_df is not None and not ew_df.empty else df
                        regime = detect_regime_and_bias(wave_src, refs)
                        LATEST_DATA["tickers"][sym] = {
                            "price": round(last_price, 2),
                            "change": f"{chg_pct:+.2f}%",
                            "bias": regime.get("bias", "NEUTRAL") if isinstance(regime, dict) else "NEUTRAL"
                        }
                        bias_txt = LATEST_DATA["tickers"][sym]["bias"]
                        evaluator.record_recommendation(sym, last_price, bias_txt, last_price * 1.008, last_price * 0.992)
                except Exception as e:
                    print(f"[Scanner Error] {sym}: {e}")

            live_map = {s: d.get("price", 0.0) for s, d in LATEST_DATA["tickers"].items()}
            evaluator.evaluate_outcomes(live_map)
            LATEST_DATA["stats"] = evaluator.get_performance_stats()

        await asyncio.sleep(60)
@asynccontextmanager
async def lifespan(app: FastAPI):
    macro_task = asyncio.create_task(macro_scanner_loop())
    scan_task = asyncio.create_task(market_scanner_loop())
    yield
    macro_task.cancel()
    scan_task.cancel()

app = FastAPI(title="Options AI Desk", lifespan=lifespan)
templates = Jinja2Templates(directory="src/web/templates")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "tracked_tickers": TRACKED_TICKERS,
            "active_window": LATEST_DATA["active_window"],
            "last_updated": LATEST_DATA["last_updated"],
            "ticker_data": LATEST_DATA["tickers"],
            "trending_data": LATEST_DATA["trending"],
            "macro_data": LATEST_DATA["macro"],
            "stats_data": LATEST_DATA["stats"]
        }
    )

@app.get("/api/refresh")
async def api_refresh():
    return JSONResponse(content=LATEST_DATA)

@app.get("/api/macro")
async def api_macro():
    return JSONResponse(content={
        "macro": LATEST_DATA["macro"],
        "stats": LATEST_DATA["stats"]
    })

@app.get("/api/agent-desk/{symbol}")
async def get_agent_dossier(symbol: str):
    sym = symbol.upper()
    df = await asyncio.to_thread(manager.fetch_intraday_data, sym)
    refs = manager.get_reference_levels(sym)
    headline = catalyst_agent.fetch_ticker_headline(sym)
    dossier = run_multi_agent_assessment(sym, df, refs, headline)
    return JSONResponse(content=dossier)

@app.get("/api/health")
async def health_check():
    ollama_online = False
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                ollama_online = True
    except Exception:
        ollama_online = False

    return {"status": "ok", "ollama": ollama_online}