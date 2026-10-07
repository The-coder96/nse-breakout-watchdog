"""
UNIFIED BREAKOUT SCANNER (STOCKS & SECTORS) + DISCORD ALERTS
==================================================================================
1. Stocks: Multi-Year Breakout (2Y+ Age, <= 7% Gap, +Net Income, >10Cr Rev).
2. Sectors: 1-10Y Squeezes (Mon-Fri) + ATH Momentum (Fridays) (<= 5% Gap).
3. Data Engines: yfinance for Stocks, tvDatafeed for Sectors.
4. Routing: Automatically splits alerts to separate Discord channels.
5. Visuals: Human-emulated login + Ctrl+Alt+S Native Chart Exports + iOS Links.
"""

import os
import time
import sys
import json
import warnings
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, col
from tvDatafeed import TvDatafeed, Interval
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

# ==============================================================================
# SECURE DISCORD WEBHOOK & AUTH CONFIGURATION
# ==============================================================================
DISCORD_STOCK_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
DISCORD_SECTOR_WEBHOOK = os.environ.get("DISCORD_SECTOR_WEBHOOK")
TV_USERNAME = os.environ.get("TV_USERNAME")
TV_PASSWORD = os.environ.get("TV_PASSWORD")

# ==============================================================================
# SECTOR UNIVERSE (29 INDICES)
# ==============================================================================
SECTOR_INDICES = [
    {"name": "NIFTY 50", "tv": "NSE:NIFTY"}, {"name": "BANKNIFTY", "tv": "NSE:BANKNIFTY"},
    {"name": "SENSEX", "tv": "BSE:SENSEX"}, {"name": "CNX500", "tv": "NSE:CNX500"},
    {"name": "CNXMIDCAP", "tv": "NSE:CNXMIDCAP"}, {"name": "CNXSMLLCAP", "tv": "NSE:CNXSMALLCAP"},
    {"name": "CNXIT", "tv": "NSE:CNXIT"}, {"name": "CNXAUTO", "tv": "NSE:CNXAUTO"},
    {"name": "CNXFMCG", "tv": "NSE:CNXFMCG"}, {"name": "CNXPHARMA", "tv": "NSE:CNXPHARMA"},
    {"name": "CNXMETAL", "tv": "NSE:CNXMETAL"}, {"name": "CNXREALTY", "tv": "NSE:CNXREALTY"},
    {"name": "CNXENERGY", "tv": "NSE:CNXENERGY"}, {"name": "CNXINFRA", "tv": "NSE:CNXINFRA"},
    {"name": "CNXMEDIA", "tv": "NSE:CNXMEDIA"}, {"name": "CNXFINANCE", "tv": "NSE:CNXFINANCE"},
    {"name": "CNXPSE", "tv": "NSE:CNXPSE"}, {"name": "CNXPSUBANK", "tv": "NSE:CNXPSUBANK"},
    {"name": "NIFTYPVTBANK", "tv": "NSE:NIFTYPVTBANK"}, {"name": "CNXCONSUMPTION", "tv": "NSE:CNXCONSUMPTION"},
    {"name": "CNXCOMMODITIES", "tv": "NSE:CNXCOMMODITIES"}, {"name": "CNXSERVICE", "tv": "NSE:CNXSERVICE"},
    {"name": "NIFTY_HEALTHCARE", "tv": "NSE:NIFTY_HEALTHCARE"}, {"name": "NIFTY_IND_TOURISM", "tv": "NSE:NIFTY_IND_TOURISM"},
    {"name": "NIFTY_IND_DEFENCE", "tv": "NSE:NIFTY_IND_DEFENCE"}, {"name": "NIFTY_OIL_AND_GAS", "tv": "NSE:NIFTY_OIL_AND_GAS"},
    {"name": "NIFTY_RURAL", "tv": "NSE:NIFTY_RURAL"}, {"name": "NIFTY_EV", "tv": "NSE:NIFTY_EV"},
    {"name": "NIFTY_CONSR_DURBL", "tv": "NSE:NIFTY_CONSR_DURBL"}
]

try:
    tv = TvDatafeed()
except Exception as e:
    print(f"[-] Failed to initialize TradingView feed: {e}")
    tv = None

# ==============================================================================
# WATCHLIST PERSISTENCE
# ==============================================================================
def save_watchlist(qualified_items):
    watchlist = []
    for q in qualified_items:
        item_data = {
            "symbol": q["symbol"],
            "tv_symbol": q["tv_symbol"],
            "yf_symbol": tv_to_yf(q["tv_symbol"]) if q["item_type"] == "STOCK" else None,
            "target": round(float(q["lifetime_high"]), 2),
            "current_price": round(float(q["current_price"]), 2),
            "distance_pct": round(float(q["distance_pct"]), 2),
            "lh_date": q["lh_date"],
            "item_type": q["item_type"]
        }
        watchlist.append(item_data)

    with open("watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=4)
    print(f"\n[+] Saved {len(watchlist)} candidate(s) to watchlist.json for watchdog.")

# ==============================================================================
# VISUAL & DISCORD ENGINE
# ==============================================================================
def automate_tv_login(page):
    if not TV_USERNAME or not TV_PASSWORD:
        return

    print("🔑 Attempting live TradingView login via human-emulation...")
    try:
        page.goto("https://www.tradingview.com/", timeout=60000)
        page.wait_for_timeout(4000)
        
        page.locator('.tv-header__user-menu-button--anonymous').click(timeout=10000)
        page.wait_for_timeout(1500)
        
        page.locator('button[data-name="header-user-menu-sign-in"]').click(timeout=10000)
        page.wait_for_timeout(3000)
        
        try:
            page.locator('span:has-text("Email")').first.click(timeout=5000)
            page.wait_for_timeout(2000)
        except: pass 
        
        print("   -> Typing credentials like a human...")
        user_input = page.locator('input[name="id_username"]')
        user_input.click()
        page.wait_for_timeout(400)
        user_input.press_sequentially(TV_USERNAME, delay=120)
        page.wait_for_timeout(800)
        
        pass_input = page.locator('input[name="id_password"]')
        pass_input.click()
        page.wait_for_timeout(400)
        pass_input.press_sequentially(TV_PASSWORD, delay=120)
        page.wait_for_timeout(1000)
        
        pass_input.press("Enter")
        page.wait_for_timeout(12000)
        print("✅ Login sequence completed.")
    except Exception as e:
        print(f"⚠️ Login sequence failed: {e}")

def capture_breakout_chart(page, tv_symbol, timeframe="1W"):
    print(f"📸 Generating weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval={timeframe}&theme=light"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_weekly.png"

    page.goto(url, timeout=60000)
    page.wait_for_timeout(6000)

    for selector in ['button[aria-label="Close dialog"]', 'button:has-text("Accept all")', 'button[aria-label="Close"]']:
        try: page.locator(selector).click(timeout=1500)
        except: pass

    try:
        page.get_by_text("5Y", exact=True).click(timeout=3000)
        page.wait_for_timeout(1000)
        page.keyboard.type("1W", delay=100)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000) 
        for _ in range(2): page.keyboard.press("Control+ArrowDown"); page.wait_for_timeout(200)
        for _ in range(3): page.keyboard.press("ArrowLeft"); page.wait_for_timeout(100)
    except:
        pass

    # -----------------------------------------------------------------------
    # DUAL-NATIVE EXPORT ENGINE
    # -----------------------------------------------------------------------
    page.mouse.click(960, 540) # Ensure chart canvas has focus
    page.wait_for_timeout(1000)
    
    native_success = False

    # ATTEMPT 1: Explicitly hold modifiers to force Linux to recognize Ctrl+Alt+S
    try:
        print("   -> Attempt 1: Triggering Ctrl+Alt+S shortcut...")
        with page.expect_download(timeout=6000) as download_info:
            page.keyboard.down("Control")
            page.keyboard.down("Alt")
            page.keyboard.press("s")
            page.keyboard.up("Alt")
            page.keyboard.up("Control")
            
        download_info.value.save_as(screenshot_path)
        print("   -> Success: Native chart downloaded via shortcut.")
        native_success = True
    except Exception as e:
        print(f"   -> Shortcut timeout on Linux server: {e}")

    # ATTEMPT 2: Native Camera Icon (Waits for animation before clicking)
    if not native_success:
        try:
            print("   -> Attempt 2: Clicking native Camera icon...")
            camera_btn = page.locator('button[id="header-toolbar-screenshot"], [data-name="header-toolbar-screenshot"]').first
            camera_btn.click(timeout=5000)
            
            page.wait_for_selector('[data-name="save-chart-image"]', state="visible", timeout=3000)
            
            with page.expect_download(timeout=6000) as download_info:
                page.locator('[data-name="save-chart-image"]').click()
                
            download_info.value.save_as(screenshot_path)
            print("   -> Success: Native chart downloaded via Camera menu.")
            native_success = True
        except Exception as e:
            print(f"   -> Camera menu failed: {e}")

    # ATTEMPT 3: Absolute Fallback (Strips right sidebar manually before screenshot)
    if not native_success:
        print("   -> Both native engines failed. Forcing clean fallback screenshot...")
        try:
            page.evaluate('''
                const rightArea = document.querySelector('[class*="layout__area--right"]');
                if (rightArea) rightArea.style.display = 'none';
            ''')
            page.wait_for_timeout(500)
        except: pass
        page.screenshot(path=screenshot_path)

    return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    target_webhook = DISCORD_STOCK_WEBHOOK if q["item_type"] == "STOCK" else DISCORD_SECTOR_WEBHOOK
    
    if not target_webhook:
        print(f"[-] Error: Webhook secret missing for {q['item_type']}")
        return

    formatted_symbol = tv_symbol.replace(":", "%3A")
    tv_link = f"<https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1W>"

    if q["item_type"] == "STOCK":
        rev_cr = q.get('total_revenue', 0) / 10000000
        ni_cr = q.get('net_income', 0) / 10000000
        title = f"🚨 **MULTI-YEAR SQUEEZE DETECTED: {q['symbol']}**"
        body = (
            f"• Current Price: ₹{q['current_price']:.2f}\n"
            f"• Lifetime High: ₹{q['lifetime_high']:.2f} (Hit: {q['lh_date']})\n"
            f"• Ceiling Age: {q['age_years']:.2f} Y\n"
            f"• Squeeze Gap: {q['distance_pct']:.2f}%\n\n"
            f"**FUNDAMENTALS**\n"
            f"• Total Revenue: ₹{rev_cr:,.2f} Cr\n"
            f"• Net Income: ₹{ni_cr:,.2f} Cr\n"
        )
    else:
        if q.get("alert_type") == "SQUEEZE":
            title = f"🚨 **1-10 YEAR SECTOR SQUEEZE: {q['symbol']}**"
        else:
            title = f"🚀 **SECTOR AT ABSOLUTE ALL-TIME HIGH: {q['symbol']}**"
            
        body = (
            f"• Current Level: {q['current_price']:.2f}\n"
            f"• Absolute Max High: {q['lifetime_high']:.2f} (Hit: {q['lh_date']})\n"
            f"• Ceiling Age: {q['age_years']:.2f} Y\n"
            f"• Proximity to Max High: {q['distance_pct']:.2f}%\n"
        )

    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/png")}
        payload = {"content": f"{title}\n\n**TECHNICAL**\n{body}\n**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n📊 **Interactive Chart:** {tv_link}"}
        
        try:
            requests.post(target_webhook, data=payload, files=files, timeout=25)
            print(f"[+] Successfully delivered {tv_symbol} payload to Discord.")
        except Exception as e:
            print(f"[-] Exception during Discord webhook POST: {e}")

    if os.path.exists(image_path):
        os.remove(image_path)

# ==============================================================================
# SCANNER LOGIC
# ==============================================================================
def tv_to_yf(tv_symbol):
    return f"{tv_symbol.split(':')[-1].strip().replace('_', '-')}.NS"

def fetch_tv_candidates(limit_size):
    try:
        count, df = (
            Query().set_markets("india")
            .select("name", "close", "volume", "market_cap_basic", "High.All", "total_revenue", "net_income", "ebitda", "basic_eps_net_income")
            .where(col("exchange").isin(["NSE"]), col("type").isin(["stock"]), col("close") > 50, col("volume") > 50000, col("net_income") > 0, col("total_revenue") > 100000000)
            .order_by("market_cap_basic", ascending=False).limit(limit_size).get_scanner_data()
        )
        candidates = []
        for _, row in df.iterrows():
            name = str(row.get("name", ""))
            close = float(row.get("close", 0) or 0)
            high_all = float(row.get("High.All", 0) or 0)
            if "RR" in name or "INVIT" in name or name in ["NHIT", "VERTIS", "KRT", "EMBASSY"]: continue
            if close > 0 and high_all > 0 and (((high_all - close) / high_all) * 100.0) <= 15.0:
                candidates.append({
                    "tv_symbol": str(row.get("ticker", "")), "name": name, "close": close,
                    "total_revenue": float(row.get("total_revenue", 0) or 0),
                    "net_income": float(row.get("net_income", 0) or 0)
                })
        return candidates
    except: return []

def analyze_stock(c, df):
    if df is None or len(df) < 500: return None
    ist_now = datetime.now(tz=IST)
    if df.index[-1].date() == ist_now.date() and ist_now.time() < datetime.strptime("15:30", "%H:%M").time():
        df = df.iloc[:-1]
    
    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    age_years = (ist_now.date() - lh_idx.date()).days / 365.25
    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    # -----------------------------------------------------------------------
    # Updated: Strict 7.00% Limit for Stocks 
    # -----------------------------------------------------------------------
    if age_years < 2.0 or not (0.00 <= distance_pct <= 7.00): return None
    if (df.loc[lh_idx:]["Close"] > lifetime_high).any(): return None

    return {
        "symbol": c["name"], "tv_symbol": c["tv_symbol"], "current_price": current_price,
        "lifetime_high": lifetime_high, "lh_date": lh_idx.date().strftime("%d-%b-%Y"),
        "age_years": age_years, "distance_pct": distance_pct,
        "total_revenue": c.get("total_revenue", 0), "net_income": c.get("net_income", 0),
        "item_type": "STOCK"
    }

def analyze_sector(idx, df, is_friday):
    if df is None or len(df) < 250: return None
    today = datetime.now(tz=IST).date()
    
    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    age_years = (today - lh_idx.date()).days / 365.25
    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    # Strict 5.00% Limit for Sectors
    if not (0.00 <= distance_pct <= 5.00): return None

    is_multi_year = (1.0 <= age_years <= 10.0) and not (df.loc[lh_idx:]["Close"] > lifetime_high).any()
    
    if is_multi_year: alert_type = "SQUEEZE"
    elif not is_multi_year and is_friday: alert_type = "MOMENTUM"
    else: return None

    return {
        "symbol": idx["name"], "tv_symbol": idx["tv"], "current_price": current_price,
        "lifetime_high": lifetime_high, "lh_date": lh_idx.date().strftime("%d-%b-%Y"),
        "age_years": age_years, "distance_pct": distance_pct, 
        "item_type": "SECTOR", "alert_type": alert_type
    }

# ==============================================================================
# MAIN EXECUTION PIPELINE
# ==============================================================================
def run_scan():
    all_qualified = []
    
    print("\n[Pass 1] Scanning Top 500 NSE stocks by Market Cap...")
    stock_cands = fetch_tv_candidates(500)
    for c in stock_cands:
        try:
            df = yf.download(tv_to_yf(c["tv_symbol"]), period="max", auto_adjust=True, progress=False, timeout=5)
            if df is not None and not df.empty:
                res = analyze_stock(c, df)
                if res: all_qualified.append(res)
        except: pass
    
    print("\n[Pass 2] Scanning 29 Sector & Thematic Indices via TradingView...")
    if tv:
        is_friday = (datetime.now(tz=IST).weekday() == 4)
        for idx in SECTOR_INDICES:
            exchange, symbol = idx["tv"].split(":")
            try:
                df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=3000)
                if df is not None and not df.empty:
                    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
                    res = analyze_sector(idx, df, is_friday)
                    if res: all_qualified.append(res)
            except: pass

    if all_qualified:
        print(f"\n[!] Initializing Visual Engine for {len(all_qualified)} item(s)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                accept_downloads=True 
            )
            page = context.new_page()
            stealth_sync(page)
            
            # Login once, use session for all charts
            automate_tv_login(page)

            for q in sorted(all_qualified, key=lambda x: x["distance_pct"]):
                try:
                    screenshot_path = capture_breakout_chart(page, q['tv_symbol'], timeframe="1W")
                    send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
                except Exception as e:
                    print(f"[-] Failed to generate or send chart for {q['symbol']}: {e}")
            
            browser.close()
            
        save_watchlist(all_qualified)
    else:
        print("\n0 Stocks and 0 Sectors met criteria today.")
        save_watchlist([])
        if DISCORD_STOCK_WEBHOOK:
            requests.post(DISCORD_STOCK_WEBHOOK, json={"content": "📊 **Daily Lifetime High Scanner Complete**\n0 equities or sectors met strict criteria today."}, timeout=10)

if __name__ == "__main__":
    run_scan()
