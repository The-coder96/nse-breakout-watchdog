"""
TEST SECTOR BREAKOUT SCANNER (iOS APP DEEP-LINK FIX)
==================================================================================
1. Deep-Links: Removed < > brackets to restore native Apple iOS Universal Links.
2. Embeds: Injected Discord API "flags: 4" to suppress the giant TradingView card.
3. Visual: Uses the native TradingView Camera button for 100% clean charts.
"""

import os
import time
import sys
import json
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
    {"name": "CNXIT", "tv": "NSE:CNXIT"} # Trimmed list for faster testing
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
        print("⚠️ No credentials found in secrets. Proceeding anonymously.")
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
        except:
            pass 
        
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
        print("   -> Hitting ENTER to submit form...")
        pass_input.press("Enter")
        
        print("⏳ Waiting 12 seconds for authentication & Cloudflare checks to clear...")
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
        for _ in range(6): page.keyboard.press("Control+ArrowDown"); page.wait_for_timeout(200)

    try:
        print("   -> Utilizing TradingView native camera export...")
        camera_btn = page.locator('button[id="header-toolbar-screenshot"], [data-name="header-toolbar-screenshot"]').first
        camera_btn.click(timeout=5000)
        page.wait_for_timeout(1000)
        
        with page.expect_download(timeout=10000) as download_info:
            page.locator('[data-name="save-chart-image"], span:has-text("Download image")').first.click(timeout=5000)
        
        download_info.value.save_as(screenshot_path)
        print("   -> Successfully exported pristine chart image.")
        
    except Exception as e:
        print(f"   -> Camera export failed, utilizing aggressive UI-hide fallback... ({e})")
        try:
            page.evaluate('''
                const hide = (sel) => { document.querySelectorAll(sel).forEach(el => el.style.display = 'none'); };
                hide('[class*="layout__area--left"]'); hide('[class*="layout__area--top"]');
                hide('[class*="layout__area--right"]'); hide('.widgetbar-wrap');
                hide('[class*="layout__area--bottom"]'); hide('#overlap-manager-root');
            ''')
            page.wait_for_timeout(1000)
        except: pass
        page.screenshot(path=screenshot_path)

    return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    if not DISCORD_WEBHOOK_URL: return
    formatted_symbol = tv_symbol.replace(":", "%3A")
    
    # -----------------------------------------------------------------------
    # 1. RAW, NAKED URL (No < >) so Apple iOS recognizes it as an App Link
    # -----------------------------------------------------------------------
    tv_link = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1W"

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
        
        # -----------------------------------------------------------------------
        # 2. DISCORD "FLAGS: 4" to suppress giant URL previews while keeping the image
        # -----------------------------------------------------------------------
        payload = {
            "content": f"{title}\n\n**TECHNICAL**\n{body}\n**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n📊 **Interactive Chart:** {tv_link}",
            "flags": 4 
        }
        
        try: 
            requests.post(DISCORD_WEBHOOK_URL, data={"payload_json": json.dumps(payload)}, files=files, timeout=25)
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
    total_indices = len(SECTOR_INDICES)

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
