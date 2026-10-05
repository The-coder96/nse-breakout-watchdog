"""
ISOLATED TEST: Multi-Year Breakout Scanner for Indices/Sectors
==================================================================================
1. Hardcoded Index Universe: Scans predefined NSE/BSE sector indices.
2. True Lifetime High: Absolute highest price ever traded (max of High).
3. Virgin Ceiling Rule (Age): MUST be >= 2.0 years old.
4. Integrity Rule: No daily close above this ceiling since established.
5. Squeeze Rule (Proximity): Current price between 0.00% and 10.00% below ATH.
6. Visual Engine: '5Y' Zoom + Extra Zoom + Native TV Camera Snapshot.
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
# INDEX UNIVERSE MAPPING (TradingView Format -> Yahoo Finance Format)
# ==============================================================================
SECTOR_INDICES = [
    {"name": "NIFTY 50", "tv": "NSE:NIFTY", "yf": "^NSEI"},
    {"name": "BANKNIFTY", "tv": "NSE:BANKNIFTY", "yf": "^NSEBANK"},
    {"name": "SENSEX", "tv": "BSE:SENSEX", "yf": "^BSESN"},
    {"name": "CNXIT", "tv": "NSE:CNXIT", "yf": "^CNXIT"},
    {"name": "CNXAUTO", "tv": "NSE:CNXAUTO", "yf": "^CNXAUTO"},
    {"name": "CNXFMCG", "tv": "NSE:CNXFMCG", "yf": "^CNXFMCG"},
    {"name": "CNXPHARMA", "tv": "NSE:CNXPHARMA", "yf": "^CNXPHARMA"},
    {"name": "CNXMETAL", "tv": "NSE:CNXMETAL", "yf": "^CNXMETAL"},
    {"name": "CNXREALTY", "tv": "NSE:CNXREALTY", "yf": "^CNXREALTY"},
    {"name": "CNXENERGY", "tv": "NSE:CNXENERGY", "yf": "^CNXENERGY"},
    {"name": "CNXINFRA", "tv": "NSE:CNXINFRA", "yf": "^CNXINFRA"},
    {"name": "CNXMEDIA", "tv": "NSE:CNXMEDIA", "yf": "^CNXMEDIA"},
    {"name": "CNXFINANCE", "tv": "NSE:CNXFINANCE", "yf": "^CNXFINANCE"},
    {"name": "CNXPSE", "tv": "NSE:CNXPSE", "yf": "^CNXPSE"},
    {"name": "CNXPSUBANK", "tv": "NSE:CNXPSUBANK", "yf": "^CNXPSUBANK"},
    {"name": "NIFTYPVTBANK", "tv": "NSE:NIFTYPVTBANK", "yf": "^NIFTYPVTBANK"},
    {"name": "CNXCONSUMPTION", "tv": "NSE:CNXCONSUMPTION", "yf": "^CNXCONSUMPTION"},
    {"name": "CNXCOMMODITIES", "tv": "NSE:CNXCOMMODITIES", "yf": "^CNXCOMMODITIES"},
    {"name": "CNXMIDCAP", "tv": "NSE:CNXMIDCAP", "yf": "^CNXMIDCAP"},
    {"name": "CNXSMLLCAP", "tv": "NSE:CNXSMALLCAP", "yf": "^CNXSMALLCAP"},
    {"name": "CNX500", "tv": "NSE:CNX500", "yf": "^CRSLDX"}
]

# ==============================================================================
# VISUAL CAPTURE & DISCORD ENGINE (Purely Technical)
# ==============================================================================

def capture_breakout_chart(tv_symbol, timeframe="1W"):
    print(f"📸 Generating weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval={timeframe}&theme=light"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_weekly.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
        page = context.new_page()

        page.goto(url, timeout=60000)
        page.wait_for_timeout(5000)

        for selector in [
            'button[aria-label="Close dialog"]',
            'button:has-text("Accept all")',
            'button[aria-label="Close"]',
        ]:
            try:
                page.locator(selector).click(timeout=1500)
            except Exception:
                pass

        try:
            page.get_by_text("5Y", exact=True).click(timeout=3000)
            page.wait_for_timeout(1000)
            page.keyboard.type("1W", delay=100)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            for _ in range(2):
                page.keyboard.press("Control+ArrowDown")
                page.wait_for_timeout(200)
            for _ in range(3):
                page.keyboard.press("ArrowLeft")
                page.wait_for_timeout(100)
        except Exception:
            for _ in range(6):
                page.keyboard.press("Control+ArrowDown")
                page.wait_for_timeout(200)

        try:
            page.evaluate('''
                const leftBar = document.querySelector('[class*="layout__area--left"]');
                if (leftBar) leftBar.style.display = 'none';
                const topBar = document.querySelector('[class*="layout__area--top"]');
                if (topBar) topBar.style.display = 'none';
                const rightBar = document.querySelector('[class*="layout__area--right"]');
                if (rightBar) rightBar.style.display = 'none';
                const bottomArea = document.querySelector('[class*="layout__area--bottom"]');
                if (bottomArea) bottomArea.style.display = 'none';
                const bottomWidget = document.querySelector('[data-name="bottom-widget-bar"]');
                if (bottomWidget) bottomWidget.style.display = 'none';
            ''')
            page.wait_for_timeout(1000)
        except Exception:
            pass

        try:
            print("   -> Triggering Native TradingView 'Take a snapshot' (Camera)...")
            camera_btn = page.locator('button[id="header-toolbar-screenshot"], [data-name="header-toolbar-screenshot"], button[aria-label="Take a snapshot"]').first
            camera_btn.click(timeout=5000)
            page.wait_for_timeout(1000)

            with page.expect_download(timeout=10000) as download_info:
                page.locator('[data-name="save-chart-image"], span:has-text("Download image"), div:has-text("Download image")').first.click(timeout=5000)

            download = download_info.value
            download.save_as(screenshot_path)
            print("   -> Native snapshot downloaded via UI click!")
        except Exception:
            print("   -> UI Camera click failed. Trying keyboard shortcut (Ctrl+Alt+S)...")
            try:
                with page.expect_download(timeout=10000) as download_info:
                    page.keyboard.press("Control+Alt+s")
                download = download_info.value
                download.save_as(screenshot_path)
                print("   -> Native snapshot downloaded via shortcut!")
            except Exception:
                print("   -> Shortcut failed. Falling back to manual browser screenshot...")
                page.screenshot(path=screenshot_path)

        browser.close()
        return screenshot_path

def send_breakout_to_discord(tv_symbol, image_path, q):
    if not DISCORD_WEBHOOK_URL:
        print("[-] Error: DISCORD_SECTOR_WEBHOOK URL is missing from environment variables.")
        return

    print(f"📤 Uploading {tv_symbol} alert to Discord...")
    
    with open(image_path, "rb") as f:
        files = {"file": (image_path, f, "image/png")}
        payload = {
            "content": (
                f"🚨 **SECTOR SQUEEZE DETECTED: {q['name']}**\n\n"
                f"**TECHNICAL**\n"
                f"• Current Level: {q['current_price']:.2f}\n"
                f"• Lifetime High: {q['lifetime_high']:.2f} (Established: {q['lh_date']})\n"
                f"• Ceiling Age: {q['age_years']:.2f} Y\n"
                f"• Squeeze Gap: {q['distance_pct']:.2f}%\n\n"
                f"**CHART**\n"
                f"*Attached: Weekly (1W) timeframe chart.*"
            )
        }
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files, timeout=25)
            if response.status_code in (200, 204):
                print(f"[+] Successfully delivered {tv_symbol} payload to Discord.")
            else:
                print(f"[-] Failed to send alert. Status Code: {response.status_code}")
        except Exception as e:
            print(f"[-] Exception during Discord webhook POST: {e}")

    if os.path.exists(image_path):
        os.remove(image_path)

# ==============================================================================
# TECHNICAL SCANNER LOGIC
# ==============================================================================

def fetch_yf(yf_symbol):
    for attempt in range(1, 4):
        try:
            raw = yf.download(yf_symbol, period="max", auto_adjust=True, progress=False, timeout=10)
            if raw is None or raw.empty:
                return None

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
            df = raw[needed].copy()
            df.dropna(subset=["Close", "High"], inplace=True)
            df.sort_index(inplace=True)

            if df.empty:
                return None

            return df
        except Exception:
            time.sleep(1)
    return None

def analyze_strict(index_data, df):
    if df is None or len(df) < 500:
        return None

    ist_now = datetime.now(tz=IST)
    today = ist_now.date()

    if df.index[-1].date() == today and ist_now.time() < datetime.strptime("15:30", "%H:%M").time():
        df = df.iloc[:-1]

    if len(df) < 500:
        return None

    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    lh_date = lh_idx.date()

    age_days = (today - lh_date).days
    age_years = age_days / 365.25

    if age_years < 2.0:
        return None

    # 10% Squeeze gap
    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    if not (0.00 <= distance_pct <= 10.00):
        return None

    post_ath = df.loc[lh_idx:]
    if (post_ath["Close"] > lifetime_high).any():
        return None

    return {
        "name": index_data["name"],
        "tv_symbol": index_data["tv"],
        "current_price": current_price,
        "lifetime_high": lifetime_high,
        "lh_date": lh_date.strftime("%d-%b-%Y"),
        "age_years": age_years,
        "distance_pct": distance_pct
    }

def print_results(qualified):
    print("\n" + "="*85)
    print(f"SECTOR BREAKOUT SETUP(S) FOUND (GAP <= 10%)")
    print("="*85)
    print(f"{'INDEX':<20} {'LEVEL':<10} {'ATH':<12} {'ATH DATE':<15} {'AGE':<10} {'GAP %':<10}")
    print("-" * 85)
    for q in sorted(qualified, key=lambda x: x["distance_pct"]):
        print(f"{q['name']:<20} {q['current_price']:<10.2f} {q['lifetime_high']:<12.2f} {q['lh_date']:<15} {q['age_years']:<5.2f}Y    {q['distance_pct']:.2f}%")
    print("="*85 + "\n")

def run_scan():
    print("Initializing Sector Index Breakout Tester...")
    print(f"Scanning {len(SECTOR_INDICES)} Major Indices...")

    qualified = []
    for idx in SECTOR_INDICES:
        time.sleep(0.1)
        df = fetch_yf(idx["yf"])
        res = analyze_strict(idx, df)
        if res:
            qualified.append(res)
        else:
            print(f"   -> {idx['name']} did not meet 2Y Age + 10% Proximity rules.")

    if qualified:
        print_results(qualified)
        print(f"\n[!] Initializing Visual Engine for {len(qualified)} index(es)...")
        for q in sorted(qualified, key=lambda x: x["distance_pct"]):
            try:
                screenshot_path = capture_breakout_chart(q['tv_symbol'], timeframe="1W")
                send_breakout_to_discord(q['tv_symbol'], screenshot_path, q)
            except Exception as e:
                print(f"[-] Failed to generate chart for {q['name']}: {e}")
    else:
        print("\n0 sector indices are currently squeezing within 10% of a 2+ Year High.")

if __name__ == "__main__":
    run_scan()
