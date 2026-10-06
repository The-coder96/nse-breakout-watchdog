"""
TEST SECTOR BREAKOUT SCANNER (PLAYWRIGHT STEALTH ENGINE)
==================================================================================
1. Links: Uses RAW URLs wrapped in < > to bypass Discord popups and embeds.
2. Visual Engine: Scrapes the live TradingView chart.
3. Bot Bypass: Uses playwright-stealth to mask the headless browser fingerprint.
"""

import os
import time
import sys
import warnings
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_SECTOR_WEBHOOK")

SECTOR_INDICES = [
    {"name": "NIFTY 50", "tv": "NSE:NIFTY"}, {"name": "BANKNIFTY", "tv": "NSE:BANKNIFTY"},
    {"name": "SENSEX", "tv": "BSE:SENSEX"}, {"name": "CNX500", "tv": "NSE:CNX500"},
    {"name": "CNXMIDCAP", "tv": "NSE:CNXMIDCAP"}, {"name": "CNXSMLLCAP", "tv": "NSE:CNXSMALLCAP"},
    {"name": "CNXIT", "tv": "NSE:CNXIT"}
]

try:
    tv = TvDatafeed()
except Exception as e:
    print(f"[-] Failed to initialize TradingView feed: {e}")
    sys.exit(1)

def fetch_tv_data(exchange, symbol):
    for attempt in range(1, 4):
        try:
            df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=3000)
            if df is not None and not df.empty:
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
                df.dropna(subset=["Close", "High"], inplace=True)
                return df
        except Exception:
            time.sleep(1)
    return None

def capture_breakout_chart(tv_symbol, timeframe="1W"):
    print(f"📸 Generating stealth weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    url = f"https://in.tradingview.com/chart/?symbol={formatted_symbol}&interval={timeframe}&theme=light"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_weekly.png"

    with sync_playwright() as p:
        # Launching with standard Chrome arguments to look normal
        browser = p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # INJECT STEALTH TO BYPASS CLOUDFLARE/BOT DETECTION
        stealth_sync(page)
        
        page.goto(url, timeout=60000)
        page.wait_for_timeout(6000) # Give extra time to bypass Cloudflare checks

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
            for _ in range(6): page.keyboard.press("Control+ArrowDown"); page.wait_for_timeout(200)

        try:
            page.evaluate('''
                const hide = (selector) => { const el = document.querySelector(selector); if (el) el.style.display = 'none'; };
                hide('[class*="layout__area--left"]'); hide('[class*="layout__area--top"]');
                hide('[class*="layout__area--right"]'); hide('[class*="layout__area--bottom"]');
                hide('[data-name="bottom-widget-bar"]');
                hide('#overlap-manager-root'); 
            ''')
            page.wait_for_timeout(1000)
        except: pass

        page.screenshot(path=screenshot_path)
        browser.close()
        return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    if not DISCORD_WEBHOOK_URL: return

    formatted_symbol = tv_symbol.replace(":", "%3A")
    
    # RAW URL formatted to prevent Embed card, while avoiding "Leaving Discord" warning
    tv_link = f"<https://in.tradingview.com/chart/?symbol={formatted_symbol}>"

    if q["type"] == "SQUEEZE":
        title = f"🚨 **1-10 YEAR SECTOR SQUEEZE DETECTED: {q['name']}**"
        body = (
            f"• Current Level: {q['current_price']:.2f}\n"
            f"• Multi-Year Ceiling: {q['lifetime_high']:.2f} (Hit: {q['lh_date']})\n"
            f"• Ceiling Age: {q['age_years']:.2f} Y\n"
            f"• Squeeze Gap: {q['distance_pct']:.2f}%\n"
        )
    else:
        title = f"🚀 **SECTOR AT ABSOLUTE ALL-TIME HIGH: {q['name']}**"
        body = (
            f"• Current Level: {q['current_price']:.2f}\n"
            f"• Absolute Max High: {q['lifetime_high']:.2f} (Hit: {q['lh_date']})\n"
            f"• Proximity to Max High: {q['distance_pct']:.2f}%\n"
        )

    with open(image_path, "rb") as f:
        files = {"file": (image_path, f, "image/png")}
        payload = {
            "content": f"{title}\n\n**TECHNICAL**\n{body}\n**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n📊 **Interactive Chart:** {tv_link}"
        }
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files, timeout=25)
        except Exception as e:
            print(f"[-] Exception during Discord webhook POST: {e}")

    if os.path.exists(image_path):
        os.remove(image_path)

def analyze_sector(index_data, df, is_friday):
    if df is None or len(df) < 250: return None, "Insufficient data"
    ist_now = datetime.now(tz=IST)
    today = ist_now.date()
    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    lh_date = lh_idx.date()
    age_years = (today - lh_date).days / 365.25
    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    if not (0.00 <= distance_pct <= 8.00): return None, f"Gap ({distance_pct:.2f}%) exceeds 8.00%"

    is_multi_year_squeeze = False
    if 1.0 <= age_years <= 10.0:
        post_ath = df.loc[lh_idx:]
        if not (post_ath["Close"] > lifetime_high).any():
            is_multi_year_squeeze = True

    is_momentum = False
    if not is_multi_year_squeeze:
        is_momentum = True

    if is_multi_year_squeeze: alert_type = "SQUEEZE"
    elif is_momentum and is_friday: alert_type = "MOMENTUM"
    else: return None, "Filtered by Age/Condition"

    return {
        "name": index_data["name"], "tv_symbol": index_data["tv"], "current_price": current_price,
        "lifetime_high": lifetime_high, "lh_date": lh_date.strftime("%d-%b-%Y"),
        "age_years": age_years, "distance_pct": distance_pct, "type": alert_type
    }, "Qualified"

def run_scan():
    ist_now = datetime.now(tz=IST)
    is_friday = True  # TEST OVERRIDE
    total_indices = len(SECTOR_INDICES)

    qualified = []
    for i, idx in enumerate(SECTOR_INDICES, 1):
        exchange, symbol = idx["tv"].split(":")
        df = fetch_tv_data(exchange, symbol)
        if df is None: continue
        res, reason = analyze_sector(idx, df, is_friday)
        if res: qualified.append(res)

    if qualified:
        for q in sorted(qualified, key=lambda x: x["distance_pct"]):
            try:
                screenshot_path = capture_breakout_chart(q['tv_symbol'], timeframe="1W")
                send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
            except Exception as e:
                print(f"[-] Failed to deliver chart for {q['name']}: {e}")

if __name__ == "__main__":
    run_scan()
