"""
TEST SECTOR BREAKOUT SCANNER (KEYBOARD SHORTCUT EXPORT)
==================================================================================
1. Native Export: Uses Ctrl + Alt + S to force native TradingView chart downloads.
2. Embeds: URL wrapped in < > to permanently kill the ugly black preview card.
3. Deep-Links: iOS-compatible raw URL for flawless deep-linking.
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

# Fetch Secrets
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_SECTOR_WEBHOOK")
TV_USERNAME = os.environ.get("TV_USERNAME")
TV_PASSWORD = os.environ.get("TV_PASSWORD")

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
    # NATIVE EXPORT: Uses Ctrl+Alt+S to bypass UI clicks and get a clean chart
    # -----------------------------------------------------------------------
    try:
        print("   -> Triggering native export via Ctrl+Alt+S shortcut...")
        page.wait_for_timeout(2000) # Ensure chart is fully loaded before snap
        
        # Intercept the exact moment TradingView creates the download file
        with page.expect_download(timeout=15000) as download_info:
            page.keyboard.press("Control+Alt+s")
            
        download_info.value.save_as(screenshot_path)
        print("   -> Successfully downloaded pristine native chart.")
        
    except Exception as e:
        print(f"   -> Shortcut failed, falling back to standard screenshot: {e}")
        page.screenshot(path=screenshot_path)

    return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    if not DISCORD_WEBHOOK_URL: return
    formatted_symbol = tv_symbol.replace(":", "%3A")
    
    # Wrapped in < > blocks the black preview card
    tv_link = f"<https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1W>"

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

    discord_message = f"{title}\n\n**TECHNICAL**\n{body}\n**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n📊 **Interactive Chart:** {tv_link}"

    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/png")}
        try: 
            requests.post(DISCORD_WEBHOOK_URL, data={"content": discord_message}, files=files, timeout=25)
        except Exception as e: 
            print(f"[-] Exception during Discord webhook POST: {e}")

    if os.path.exists(image_path): os.remove(image_path)

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
        if not (post_ath["Close"] > lifetime_high).any(): is_multi_year_squeeze = True

    is_momentum = not is_multi_year_squeeze
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
    is_friday = True 
    qualified = []
    for i, idx in enumerate(SECTOR_INDICES, 1):
        exchange, symbol = idx["tv"].split(":")
        df = fetch_tv_data(exchange, symbol)
        if df is None: continue
        res, reason = analyze_sector(idx, df, is_friday)
        if res: qualified.append(res)

    if qualified:
        print(f"\n[!] Initializing Visual Engine for {len(qualified)} index(es)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", accept_downloads=True)
            page = context.new_page()
            stealth_sync(page)
            automate_tv_login(page)
            
            for q in sorted(qualified, key=lambda x: x["distance_pct"]):
                try:
                    screenshot_path = capture_breakout_chart(page, q['tv_symbol'], timeframe="1W")
                    send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
                except Exception as e:
                    print(f"[-] Failed to deliver chart for {q['name']}: {e}")
            browser.close()

if __name__ == "__main__":
    run_scan()
