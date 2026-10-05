"""
UNIFIED SECTOR SCANNER (5:15 PM DAILY)
==================================================================================
1. Mon-Thu Rule: Alerts ONLY on 5 to 10 Year Virgin Ceilings within a 5% Gap.
2. Friday Rule: Alerts on 5 to 10 Year Squeezes AND Absolute ATH Momentum.
3. Live Price: Reads the active market price without dropping the current day.
"""

import os
import time
import sys
import warnings
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from playwright.sync_api import sync_playwright

warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

# ==============================================================================
# SECURE DISCORD WEBHOOK CONFIGURATION
# ==============================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_SECTOR_WEBHOOK")

# ==============================================================================
# CORRECTED INDEX UNIVERSE MAPPING FOR YAHOO FINANCE
# ==============================================================================
SECTOR_INDICES = [
    {"name": "NIFTY 50", "tv": "NSE:NIFTY", "yf": "^NSEI"},
    {"name": "BANKNIFTY", "tv": "NSE:BANKNIFTY", "yf": "^NSEBANK"},
    {"name": "SENSEX", "tv": "BSE:SENSEX", "yf": "^BSESN"},
    {"name": "CNXIT", "tv": "NSE:CNXIT", "yf": "^CNXIT"},
    {"name": "CNXAUTO", "tv": "NSE:CNXAUTO", "yf": "^CNXAUTO"},
    {"name": "CNXFMCG", "tv": "NSE:CNXFMCG", "yf": "^CNXFMCG"},
    {"name": "CNXPHARMA", "tv": "NSE:CNXPHARMA", "yf": "^CNXPHARMA"},
    {"name": "NIFTY_HEALTHCARE", "tv": "NSE:NIFTY_HEALTHCARE", "yf": "NIFTY_HEALTHCARE.NS"}, 
    {"name": "CNXMETAL", "tv": "NSE:CNXMETAL", "yf": "^CNXMETAL"},
    {"name": "CNXREALTY", "tv": "NSE:CNXREALTY", "yf": "^CNXREALTY"},
    {"name": "CNXENERGY", "tv": "NSE:CNXENERGY", "yf": "^CNXENERGY"},
    {"name": "CNXINFRA", "tv": "NSE:CNXINFRA", "yf": "^CNXINFRA"},
    {"name": "CNXMEDIA", "tv": "NSE:CNXMEDIA", "yf": "^CNXMEDIA"},
    {"name": "CNXFINANCE", "tv": "NSE:CNXFINANCE", "yf": "NIFTY_FIN_SERVICE.NS"},
    {"name": "CNXPSE", "tv": "NSE:CNXPSE", "yf": "^CNXPSE"},
    {"name": "CNXPSUBANK", "tv": "NSE:CNXPSUBANK", "yf": "^CNXPSUBANK"},
    {"name": "NIFTYPVTBANK", "tv": "NSE:NIFTYPVTBANK", "yf": "NIFTY_PVT_BANK.NS"},
    {"name": "CNXCONSUMPTION", "tv": "NSE:CNXCONSUMPTION", "yf": "^CNXCONSUM"},
    {"name": "CNXCOMMODITIES", "tv": "NSE:CNXCOMMODITIES", "yf": "^CNXCMDT"},
    {"name": "CNXMIDCAP", "tv": "NSE:CNXMIDCAP", "yf": "NIFTY_MIDCAP_100.NS"},
    {"name": "CNXSMLLCAP", "tv": "NSE:CNXSMALLCAP", "yf": "NIFTY_SMLCAP_100.NS"},
    {"name": "CNX500", "tv": "NSE:CNX500", "yf": "^CRSLDX"}
]

# ==============================================================================
# VISUAL CAPTURE & DISCORD ENGINE
# ==============================================================================

def capture_breakout_chart(tv_symbol, timeframe="1W"):
    print(f"📸 Generating weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval={timeframe}&theme=light"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_weekly.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
        page = context.new_page()

        page.goto(url, timeout=60000)
        page.wait_for_timeout(5000)

        for selector in ['button[aria-label="Close dialog"]', 'button:has-text("Accept all")', 'button[aria-label="Close"]']:
            try: page.locator(selector).click(timeout=1500)
            except: pass

        try:
            page.get_by_text("5Y", exact=True).click(timeout=3000)
            page.wait_for_timeout(1000)
            page.keyboard.type("1W", delay=100)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            for _ in range(2): page.keyboard.press("Control+ArrowDown"); page.wait_for_timeout(200)
            for _ in range(3): page.keyboard.press("ArrowLeft"); page.wait_for_timeout(100)
        except Exception:
            for _ in range(6): page.keyboard.press("Control+ArrowDown"); page.wait_for_timeout(200)

        try:
            page.evaluate('''
                const hide = (selector) => { const el = document.querySelector(selector); if (el) el.style.display = 'none'; };
                hide('[class*="layout__area--left"]'); hide('[class*="layout__area--top"]');
                hide('[class*="layout__area--right"]'); hide('[class*="layout__area--bottom"]');
                hide('[data-name="bottom-widget-bar"]');
            ''')
            page.wait_for_timeout(1000)
        except: pass

        try:
            camera_btn = page.locator('button[id="header-toolbar-screenshot"], [data-name="header-toolbar-screenshot"]').first
            camera_btn.click(timeout=5000)
            page.wait_for_timeout(1000)
            with page.expect_download(timeout=10000) as download_info:
                page.locator('[data-name="save-chart-image"], span:has-text("Download image")').first.click(timeout=5000)
            download_info.value.save_as(screenshot_path)
        except Exception:
            try:
                with page.expect_download(timeout=10000) as download_info:
                    page.keyboard.press("Control+Alt+s")
                download_info.value.save_as(screenshot_path)
            except Exception:
                page.screenshot(path=screenshot_path)

        browser.close()
        return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    if not DISCORD_WEBHOOK_URL: return
    
    if q["type"] == "SQUEEZE":
        title = f"🚨 **5-10 YEAR SECTOR SQUEEZE DETECTED: {q['name']}**"
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
            "content": f"{title}\n\n**TECHNICAL**\n{body}\n**CHART**\n*Attached: Weekly (1W) timeframe chart.*"
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files, timeout=25)
        except Exception as e:
            print(f"[-] Exception during Discord webhook POST: {e}")

    if os.path.exists(image_path):
        os.remove(image_path)

# ==============================================================================
# CORE SCANNER LOGIC
# ==============================================================================

def fetch_yf(yf_symbol):
    for attempt in range(1, 4):
        try:
            raw = yf.download(yf_symbol, period="max", auto_adjust=True, progress=False, timeout=10)
            if raw is None or raw.empty: return None
            if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
            needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
            df = raw[needed].copy()
            df.dropna(subset=["Close", "High"], inplace=True)
            df.sort_index(inplace=True)
            if not df.empty: return df
        except: time.sleep(1)
    return None

def analyze_sector(index_data, df, is_friday):
    if df is None or len(df) < 500: return None

    ist_now = datetime.now(tz=IST)
    today = ist_now.date()

    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    lh_date = lh_idx.date()

    age_days = (today - lh_date).days
    age_years = age_days / 365.25

    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    if not (0.00 <= distance_pct <= 5.00):
        return None

    # Condition 1: STRICT 5-to-10 Year Squeeze (Applies Mon-Fri)
    is_multi_year_squeeze = False
    if 5.0 <= age_years <= 10.0:  # <--- UPDATED: Cap maximum ceiling age at 10 years
        post_ath = df.loc[lh_idx:]
        if not (post_ath["Close"] > lifetime_high).any():
            is_multi_year_squeeze = True

    # Condition 2: Absolute Momentum (Applies ONLY on Fridays)
    is_momentum = False
    if not is_multi_year_squeeze:
        is_momentum = True

    # Routing
    if is_multi_year_squeeze:
        alert_type = "SQUEEZE"
    elif is_momentum and is_friday:
        alert_type = "MOMENTUM"
    else:
        return None

    return {
        "name": index_data["name"],
        "tv_symbol": index_data["tv"],
        "current_price": current_price,
        "lifetime_high": lifetime_high,
        "lh_date": lh_date.strftime("%d-%b-%Y"),
        "age_years": age_years,
        "distance_pct": distance_pct,
        "type": alert_type
    }

def run_scan():
    ist_now = datetime.now(tz=IST)
    is_friday = (ist_now.weekday() == 4)  # 4 = Friday in Python

    print(f"Initializing Unified Sector Scanner at {ist_now.strftime('%I:%M %p IST')}...")
    if is_friday:
        print("==> TODAY IS FRIDAY: Scanning for 5-10 Year Squeezes AND Absolute Momentum (ATH).")
    else:
        print("==> TODAY IS MON-THU: Scanning ONLY for 5-10 Year Squeezes.")

    qualified = []
    for idx in SECTOR_INDICES:
        df = fetch_yf(idx["yf"])
        res = analyze_sector(idx, df, is_friday)
        if res:
            qualified.append(res)

    if qualified:
        print(f"\n[!] Initializing Visual Engine for {len(qualified)} index(es)...")
        for q in sorted(qualified, key=lambda x: x["distance_pct"]):
            try:
                screenshot_path = capture_breakout_chart(q['tv_symbol'], timeframe="1W")
                send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
            except Exception as e:
                print(f"[-] Failed: {e}")
    else:
        print("\n0 sector indices meet today's criteria.")

if __name__ == "__main__":
    run_scan()
