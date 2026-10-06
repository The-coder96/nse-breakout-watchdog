"""
TEST SECTOR BREAKOUT SCANNER (WIDGET ENGINE + DEEP LINKS)
==================================================================================
1. Gap Range: 8.00% for testing.
2. Friday Mode: Hardcoded to True.
3. Feature Test: Clickable TradingView URL (www subdomain for mobile app deep-linking).
4. Visual Engine: Migrated to TradingView Widget API to bypass "Account Frozen" IP bans.
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

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_SECTOR_WEBHOOK")

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

def capture_breakout_chart(tv_symbol, timeframe="1W"):
    print(f"📸 Generating weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    
    # -----------------------------------------------------------------------
    # FIX 2: Uses the Embed API to bypass "Account Frozen" and IP bans
    # -----------------------------------------------------------------------
    url = f"https://s.tradingview.com/widgetembed/?frameElementId=tradingview_1&symbol={formatted_symbol}&interval={timeframe}&theme=light&style=1&timezone=Asia%2FKolkata"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_weekly.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        # Added a realistic User-Agent to act like a real PC
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        page.goto(url, timeout=60000)
        page.wait_for_timeout(4000) # Give candles time to load

        try:
            # Click the chart and zoom out slightly
            page.click("body")
            page.wait_for_timeout(500)
            for _ in range(5):
                page.keyboard.press("Control+ArrowDown")
                page.wait_for_timeout(200)
            for _ in range(3):
                page.keyboard.press("ArrowLeft")
                page.wait_for_timeout(100)
        except Exception:
            pass

        # Clean native screenshot of the widget
        page.screenshot(path=screenshot_path)
        browser.close()
        return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    if not DISCORD_WEBHOOK_URL: return

    formatted_symbol = tv_symbol.replace(":", "%3A")
    
    # -----------------------------------------------------------------------
    # FIX 1: URL reset to 'www.' so the iOS/Android TradingView App catches it
    # -----------------------------------------------------------------------
    tv_link = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}"

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
        
        # Wrapped the URL in < > to hide the massive preview card, keeping only the clickable text
        payload = {
            "content": f"{title}\n\n**TECHNICAL**\n{body}\n**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n🔎 **[Click here for detailed analysis](<{tv_link}>)**"
        }
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files, timeout=25)
        except Exception as e:
            print(f"[-] Exception during Discord webhook POST: {e}")

    if os.path.exists(image_path):
        os.remove(image_path)

def analyze_sector(index_data, df, is_friday):
    if df is None or len(df) < 250: return None, "Insufficient data (< 250 bars)"

    ist_now = datetime.now(tz=IST)
    today = ist_now.date()

    current_price = float(df["Close"].iloc[-1])
    lifetime_high = float(df["High"].max())
    lh_idx = df["High"].idxmax()
    lh_date = lh_idx.date()
    age_years = (today - lh_date).days / 365.25
    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    if not (0.00 <= distance_pct <= 8.00):
        return None, f"Gap ({distance_pct:.2f}%) exceeds 8.00% range"

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
    else:
        if age_years < 1.0: return None, f"Ceiling too recent ({age_years:.2f}Y) — Mon-Thu requires 1-10Y"
        elif age_years > 10.0: return None, f"Ceiling too old ({age_years:.2f}Y) — exceeds 10-year limit"
        else: return None, "Integrity broken (close found above ceiling)"

    return {
        "name": index_data["name"], "tv_symbol": index_data["tv"], "current_price": current_price,
        "lifetime_high": lifetime_high, "lh_date": lh_date.strftime("%d-%b-%Y"),
        "age_years": age_years, "distance_pct": distance_pct, "type": alert_type
    }, "Qualified"

def run_scan():
    ist_now = datetime.now(tz=IST)
    is_friday = True  # TEST OVERRIDE
    total_indices = len(SECTOR_INDICES)

    print("=" * 80)
    print(f"SECTOR SCANNER EXECUTION: {ist_now.strftime('%d-%b-%Y %I:%M %p IST')}")
    print("Mode: TEST FORCED FRIDAY MODE (8% Gap + Momentum ATH Enabled)")
    print("=" * 80)

    qualified = []
    thrown_out_count = 0
    failed_fetch_count = 0

    for i, idx in enumerate(SECTOR_INDICES, 1):
        exchange, symbol = idx["tv"].split(":")
        df = fetch_tv_data(exchange, symbol)
        if df is None:
            failed_fetch_count += 1
            print(f"[{i:02d}/{total_indices:02d}] ⚠️ SKIPPED    : {idx['name']:<18} | Data fetch failed")
            continue

        res, reason = analyze_sector(idx, df, is_friday)
        if res:
            qualified.append(res)
            print(f"[{i:02d}/{total_indices:02d}] ✅ SHORTLISTED: {idx['name']:<18} | {res['type']} (Gap: {res['distance_pct']:.2f}%, Age: {res['age_years']:.2f}Y)")
        else:
            thrown_out_count += 1
            print(f"[{i:02d}/{total_indices:02d}] ❌ THROWN OUT : {idx['name']:<18} | {reason}")

    if qualified:
        print(f"\n[!] Initializing Visual Engine for {len(qualified)} index(es)...")
        for q in sorted(qualified, key=lambda x: x["distance_pct"]):
            try:
                screenshot_path = capture_breakout_chart(q['tv_symbol'], timeframe="1W")
                send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
            except Exception as e:
                print(f"[-] Failed to deliver chart for {q['name']}: {e}")
    else:
        print("\n0 sector indices met alert criteria today.")

if __name__ == "__main__":
    run_scan()
