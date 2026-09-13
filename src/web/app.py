import os
import asyncio
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

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
from src.signals.agent_optimizer import run_agentic_retrospective

CENTRAL_TZ = ZoneInfo("America/Chicago")
MEMORY_FILE = "obsidian_vault/Daily_Runs/agent_memory_state.md"

SESSION_START = dtime(8, 0)
SESSION_END = dtime(15, 30)

manager = CandleManager(tickers=TRACKED_TICKERS)
catalyst_agent = CatalystAgent()
trending_scanner = TrendingScanner()
evaluator = HourlyEvaluator()

def is_market_session_active(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    return SESSION_START <= dt.time() <= SESSION_END

def load_memory_state() -> str:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                for header in ["# 🧠 AI Agent Learning & Memory State", "# ?? AI Agent Learning & Memory State"]:
                    content = content.replace(header, "")
                content = content.strip()
                if content:
                    return content
        except Exception:
            pass
    return "Initial run: Waiting for next market session to calibrate triggers."

async def background_audit_loop():
    last_retrospective_date = None
    while True:
        try:
            now = datetime.now(CENTRAL_TZ)
            today_str = now.strftime("%Y-%m-%d")

            if is_market_session_active(now):
                snapshot = manager.fetch_realtime_snapshot()
                live_map = {sym: data.get("price", 0.0) for sym, data in snapshot.items()}
                evaluator.evaluate_outcomes(live_map)

            if now.weekday() < 5 and now.time() >= dtime(15, 35) and last_retrospective_date != today_str:
                print(f"[{now.strftime('%H%M')} CDT] Triggering daily retrospective loop...")
                run_agentic_retrospective()
                last_retrospective_date = today_str

        except Exception as e:
            print(f"[Background Loop Warning] {e}")
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background_audit_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="src/web/templates")

def process_card_metrics(sym: str, headline: str = ""):
    now = datetime.now(CENTRAL_TZ)
    df = manager.fetch_intraday_data(sym)
    refs = manager.get_reference_levels(sym)
    analysis = detect_regime_and_bias(df, refs)

    price_val = analysis.get("current_price", 0.0)
    bias = analysis.get("options_bias", "Stay Out / Iron Condor")
    bull_trig = analysis.get("bull_trigger", price_val * 1.01)
    bear_trig = analysis.get("bear_trigger", price_val * 0.99)
    recommendation = analysis.get("recommendation", "HOLD / NEUTRAL")
    ew_phase = analysis.get("elliott_phase", "Consolidation")
    fib_info = analysis.get("fib_level", "N/A")
    trail_info = analysis.get("trailing_target", "N/A")

    if price_val > 0.0 and is_market_session_active(now):
        evaluator.record_recommendation(sym, price_val, bias, bull_trig, bear_trig)

    return {
        "symbol": sym,
        "price": f"${price_val:,.2f}" if price_val > 0 else "Active",
        "regime": analysis.get("regime", "Expanding (Trend)"),
        "options_bias": bias,
        "recommendation": recommendation,
        "elliott_phase": ew_phase,
        "fib_level": fib_info,
        "trailing_target": trail_info,
        "catalyst": f"[{ew_phase} | {fib_info}]" + (f" | {headline}" if headline else ""),
        "risk": f"Bull: >${bull_trig:,.2f} | Bear: <${bear_trig:,.2f} | {trail_info}"
    }

def build_desk_state():
    now = datetime.now(CENTRAL_TZ)
    session_active = is_market_session_active(now)

    try:
        macro = catalyst_agent.fetch_macro_catalysts()
    except Exception:
        macro = {
            "WTI Crude": "$103.55 (+7.81%)",
            "10Y Yield": "4.94%",
            "Tech/QQQ": "$708.69 (-1.06%)"
        }

    cards = [process_card_metrics(sym, catalyst_agent.fetch_ticker_headline(sym)) for sym in TRACKED_TICKERS]

    trending_cards = []
    for item in trending_scanner.fetch_top_options_trending(limit=3):
        sym = item["symbol"]
        cd = process_card_metrics(sym, f"Rank #{item['rank']} on Social ({item['watchlist_count']:,} watchers)")
        cd["social_rank"] = item["rank"]
        trending_cards.append(cd)

    stats = evaluator.get_stats()
    memory_text = load_memory_state()

    if not session_active:
        memory_text = f"⏸️ [SESSION STANDBY] Active Window: 08:00 - 15:30 CDT.\n{memory_text}"

    return {
        "macro": macro,
        "cards": cards,
        "trending_cards": trending_cards,
        "stats": stats,
        "memory": memory_text,
        "session_active": session_active
    }

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    state = build_desk_state()
    return templates.TemplateResponse(request=request, name="index.html", context=state)

@app.get("/api/refresh")
async def api_refresh():
    return JSONResponse(content=build_desk_state())

@app.get("/api/agent-desk/{symbol}")
async def get_agent_dossier(symbol: str):
    sym = symbol.upper()
    df = manager.fetch_intraday_data(sym)
    refs = manager.get_reference_levels(sym)
    headline = catalyst_agent.fetch_ticker_headline(sym)
    dossier = run_multi_agent_assessment(sym, df, refs, headline)
    return JSONResponse(content=dossier)