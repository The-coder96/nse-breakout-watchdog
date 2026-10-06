"""
UNIFIED SECTOR SCANNER (TRADINGVIEW ENGINE)
==================================================================================
1. Universe: All 29 Sector & Thematic Indices.
2. Mon-Thu Rule: Alerts ONLY on 1 to 10 Year Virgin Ceilings within a 5% Gap.
3. Friday Rule: Alerts on 1 to 10 Year Squeezes AND Absolute ATH Momentum.
4. Data Engine: Uses tvDatafeed (TradingView) to bypass Yahoo Finance failures.
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

warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

# ==============================================================================
# SECURE DISCORD WEBHOOK CONFIGURATION
# ==============================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_SECTOR_WEBHOOK")

# ==============================================================================
# UNIFIED TRADINGVIEW INDEX UNIVERSE (29 INDICES)
# ==============================================================================
SECTOR_INDICES = [
    {"name": "NIFTY 50", "tv": "NSE:NIFTY"},
    {"name": "BANKNIFTY", "tv": "NSE:BANKNIFTY"},
    {"name": "SENSEX", "tv": "BSE:SENSEX"},
    {"name": "CNX500", "tv": "NSE:CNX500"},
    {"name": "CNXMIDCAP", "tv": "NSE:CNXMIDCAP"},
    {"name": "CNXSMLLCAP", "tv": "NSE:CNXSMALLCAP"},
    {"name": "CNXIT", "tv": "NSE:CNXIT"},
    {"name": "CNXAUTO", "tv": "NSE:CNXAUTO"},
    {"name": "CNXFMCG", "tv": "NSE:CNXFMCG"},
    {"name": "CNXPHARMA", "tv": "NSE:CNXPHARMA"},
    {"name": "CNXMETAL", "tv": "NSE:CNXMETAL"},
    {"name": "CNXREALTY", "tv": "NSE:CNXREALTY"},
    {"name": "CNXENERGY", "tv": "NSE:CNXENERGY"},
    {"name": "CNXINFRA", "tv": "NSE:CNXINFRA"},
    {"name": "CNXMEDIA", "tv": "NSE:CNXMEDIA"},
    {"name": "CNXFINANCE", "tv": "NSE:CNXFINANCE"},
    {"name": "CNXPSE", "tv": "NSE:CNXPSE"},
    {"name": "CNXPSUBANK", "tv": "NSE:CNXPSUBANK"},
    {"name": "NIFTYPVTBANK", "tv": "NSE:NIFTYPVTBANK"},
    {"name": "CNXCONSUMPTION", "tv": "NSE:CNXCONSUMPTION"},
    {"name": "CNXCOMMODITIES", "tv": "NSE:CNXCOMMODITIES"},
    {"name": "CNXSERVICE", "tv": "NSE:CNXSERVICE"},
    {"name": "NIFTY_HEALTHCARE", "tv": "NSE:NIFTY_HEALTHCARE"},
    {"name": "NIFTY_IND_TOURISM", "tv": "NSE:NIFTY_IND_TOURISM"},
    {"name": "NIFTY_IND_DEFENCE", "tv": "NSE:NIFTY_IND_DEFENCE"},
    {"name": "NIFTY_OIL_AND_GAS", "tv": "NSE:NIFTY_OIL_AND_GAS"},
    {"name": "NIFTY_RURAL", "tv": "NSE:NIFTY_RURAL"},
    {"name": "NIFTY_EV", "tv": "NSE:NIFTY_EV"},
    {"name": "NIFTY_CONSR_DURBL", "tv": "NSE:NIFTY_CONSR_DURBL"}
]

# ==============================================================================
# TRADINGVIEW DATA ENGINE
# ==============================================================================

# Initialize Guest Connection to TradingView Data Servers
try:
    tv = TvDatafeed()
except Exception as e:
    print(f"[-] Failed to initialize TradingView feed: {e}")
    sys.exit(1)

def fetch_tv_data(exchange, symbol):
    for attempt in range(1, 4):
        try:
            # Fetch roughly 12 years of daily data (3000 bars)
            df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=3000)
            if df is not None and not df.empty:
                # Format to match standard OHLC logic
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                df.dropna(subset=["Close", "High"], inplace=True)
                return df
        except:
            time.sleep(1)
    return None

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

def analyze_sector(index_data, df, is_friday):
    # Minimum 1 year of data required (approx 250 bars)
    if df is None or len(df) < 250:
        return None, f"Insufficient data (< 250 bars)"

    ist_now = datetime.now(tz=IST)
    today = ist_now.date()

    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    lh_date = lh_idx.date()

    age_days = (today - lh_date).days
    age_years = age_days / 365.25

    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    if not (0.00 <= distance_pct <= 8.00):
        return None, f"Gap ({distance_pct:.2f}%) exceeds 8.00% range"

    # Condition 1: STRICT 1-to-10 Year Squeeze (Applies Mon-Fri)
    is_multi_year_squeeze = False
    if 1.0 <= age_years <= 10.0:
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
        if age_years < 1.0:
            return None, f"Ceiling too recent ({age_years:.2f}Y) — Mon-Thu requires 1-10Y"
        elif age_years > 10.0:
            return None, f"Ceiling too old ({age_years:.2f}Y) — exceeds 10-year limit"
        else:
            return None, "Integrity broken (close found above ceiling)"

    return {
        "name": index_data["name"],
        "tv_symbol": index_data["tv"],
        "current_price": current_price,
        "lifetime_high": lifetime_high,
        "lh_date": lh_date.strftime("%d-%b-%Y"),
        "age_years": age_years,
        "distance_pct": distance_pct,
        "type": alert_type
    }, "Qualified"

def run_scan():
    ist_now = datetime.now(tz=IST)
    is_friday = (ist_now.weekday() == 4)
    total_indices = len(SECTOR_INDICES)

    print("=" * 80)
    print(f"SECTOR SCANNER EXECUTION: {ist_now.strftime('%d-%b-%Y %I:%M %p IST')}")
    print(f"Mode: {'FRIDAY FULL SCAN (1-10Y Squeeze + Momentum ATH)' if is_friday else 'MON-THU STRICT SCAN (1-10Y Squeeze Only)'}")
    print("=" * 80)

    qualified = []
    thrown_out_count = 0
    failed_fetch_count = 0

    for i, idx in enumerate(SECTOR_INDICES, 1):
        # Split TradingView symbol (e.g. "NSE:CNXAUTO") into Exchange and Symbol for the TV Feed
        exchange, symbol = idx["tv"].split(":")
        
        df = fetch_tv_data(exchange, symbol)
        if df is None:
            failed_fetch_count += 1
            print(f"[{i:02d}/{total_indices:02d}] ⚠️ SKIPPED    : {idx['name']:<18} | TradingView Data Fetch Failed")
            continue

        res, reason = analyze_sector(idx, df, is_friday)
        if res:
            qualified.append(res)
            print(f"[{i:02d}/{total_indices:02d}] ✅ SHORTLISTED: {idx['name']:<18} | {res['type']} (Gap: {res['distance_pct']:.2f}%, Age: {res['age_years']:.2f}Y)")
        else:
            thrown_out_count += 1
            print(f"[{i:02d}/{total_indices:02d}] ❌ THROWN OUT : {idx['name']:<18} | {reason}")

    successfully_scanned = total_indices - failed_fetch_count

    print("\n" + "=" * 80)
    print("FINAL SCAN AUDIT REPORT")
    print("=" * 80)
    print(f"• Total Indices Processed : {total_indices}/{total_indices}")
    print(f"• Successfully Downloaded : {successfully_scanned}/{total_indices}")
    print(f"• Data Download Failures  : {failed_fetch_count}")
    print(f"• Thrown Out (Filtered)   : {thrown_out_count}")
    print(f"• Shortlisted for Discord : {len(qualified)}")
    print("=" * 80 + "\n")

    if qualified:
        print(f"[!] Initializing Visual Engine for {len(qualified)} index(es)...")
        for q in sorted(qualified, key=lambda x: x["distance_pct"]):
            try:
                screenshot_path = capture_breakout_chart(q['tv_symbol'], timeframe="1W")
                send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
            except Exception as e:
                print(f"[-] Failed to deliver chart for {q['name']}: {e}")
    else:
        print("0 sector indices met alert criteria today.")

if __name__ == "__main__":
    run_scan()
