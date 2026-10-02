"""
STRICT Multi-Year Breakout Scanner (10% GAP) + INSTITUTIONAL DISCORD ALERTS
==================================================================================
1. True Lifetime High: Absolute highest price ever traded (max of High).
2. Virgin Ceiling Rule (Age): MUST be >= 2.0 years old.
3. Integrity Rule: No daily close above this ceiling since established.
4. Squeeze Rule (Proximity): Current price between 0.00% and 10.00% below ATH.
5. Fundamental Rule: Must have POSITIVE Net Income & > ₹10Cr Revenue.
6. Visual Engine: '5Y' Zoom + Extra Zoom + Native TV Camera Snapshot.
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
from playwright.sync_api import sync_playwright

warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

# ==============================================================================
# SECURE DISCORD WEBHOOK CONFIGURATION
# ==============================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

# ==============================================================================
# WATCHLIST PERSISTENCE FOR INTRADAY WATCHDOG
# ==============================================================================
def save_watchlist(qualified_stocks):
    """Saves qualified breakout candidates to watchlist.json for watchdog.py."""
    watchlist = []
    for q in qualified_stocks:
        watchlist.append({
            "symbol": q["symbol"],
            "tv_symbol": q["tv_symbol"],
            "yf_symbol": tv_to_yf(q["tv_symbol"]),
            "target": round(float(q["lifetime_high"]), 2),
            "current_price": round(float(q["current_price"]), 2),
            "distance_pct": round(float(q["distance_pct"]), 2),
            "lh_date": q["lh_date"]
        })

    with open("watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=4)
    print(f"\n[+] Saved {len(watchlist)} candidate(s) to watchlist.json for tomorrow's watchdog.")


# ==============================================================================
# VISUAL CAPTURE & DISCORD DELIVERY ENGINE
# ==============================================================================

def capture_breakout_chart(tv_symbol, timeframe="1W"):
    """Takes a snapshot using TV's Native Camera with multi-year zoom."""
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

        # 1. Clear common popups
        for selector in [
            'button[aria-label="Close dialog"]',
            'button:has-text("Accept all")',
            'button[aria-label="Close"]',
        ]:
            try:
                page.locator(selector).click(timeout=1500)
            except Exception:
                pass

        # 2. Multi-Year Zoom Framing (5Y + Extra Zoom)
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

        # 3. Strip UI clutter
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

        # 4. Native TradingView Snapshot Export
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
    """Uploads the weekly chart screenshot and structured institutional metrics to Discord."""
    if not DISCORD_WEBHOOK_URL:
        print("[-] Error: DISCORD_WEBHOOK secret is missing.")
        return

    print(f"📤 Uploading {tv_symbol} alert to Discord...")
    
    # Convert Operating Cash Flow to Crores for clean display
    ocf_cr = q.get('ocf', 0) / 10000000

    with open(image_path, "rb") as f:
        files = {"file": (image_path, f, "image/png")}
        payload = {
            "content": (
                f"🚨 **MULTI-YEAR SQUEEZE DETECTED: {q['symbol']}**\n\n"
                f"**TECHNICAL**\n"
                f"• Current Price: ₹{q['current_price']:.2f}\n"
                f"• Lifetime High: ₹{q['lifetime_high']:.2f} (Established: {q['lh_date']})\n"
                f"• Ceiling Age: {q['age_years']:.2f} Y\n"
                f"• Squeeze Gap: {q['distance_pct']:.2f}%\n\n"
                f"**FUNDAMENTAL QUALITY**\n"
                f"• Revenue Growth: {q['rev_growth']:.2f}%\n"
                f"• PAT Growth: {q['pat_growth']:.2f}%\n"
                f"• ROCE: {q['roce']:.2f}%\n"
                f"• Debt/Equity: {q['de']:.2f}\n"
                f"• Operating Cash Flow: ₹{ocf_cr:,.2f} Cr\n"
                f"• Promoter Holding / Pledge: {q['promoter']:.2f}% / N/A\n\n"
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

def send_empty_alert_to_discord():
    """Sends a notification when 0 stocks pass the filter."""
    if not DISCORD_WEBHOOK_URL:
        print("[-] Error: DISCORD_WEBHOOK secret is missing.")
        return

    payload = {
        "content": "📊 **Daily Lifetime High Scanner Complete**\n0 stocks currently meet the strict ≥2Y age, ≤10% proximity, and profitability criteria today."
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("\n[+] Successfully delivered zero-result payload to Discord.")
    except Exception as e:
        print(f"\n[-] Exception during Discord webhook POST: {e}")

def process_alerts(qualified_stocks):
    """Loops through shortlisted stocks, captures charts, and posts to Discord."""
    print(f"\n[!] Initializing Visual Engine for {len(qualified_stocks)} stock(s)...")
    for q in sorted(qualified_stocks, key=lambda x: x["distance_pct"]):
        try:
            screenshot_path = capture_breakout_chart(q['tv_symbol'], timeframe="1W")
            send_breakout_to_discord(q['tv_symbol'], screenshot_path, q)
        except Exception as e:
            print(f"[-] Failed to generate or send chart for {q['symbol']}: {e}")

# ==============================================================================
# QUANTITATIVE SCANNER LOGIC (10% GAP + 6 FUNDAMENTAL FIELDS)
# ==============================================================================

def fetch_tv_candidates(limit_size):
    try:
        count, df = (
            Query()
            .set_markets("india")
            .select(
                "name", "close", "volume", "market_cap_basic", "High.All", 
                "net_income", "total_revenue",
                "total_revenue_yoy_growth", 
                "net_income_yoy_growth", 
                "return_on_capital_employed", 
                "debt_to_equity", 
                "cash_n_operating_activities", 
                "promoters_hold_pct"
            )
            .where(
                col("exchange").isin(["NSE"]),
                col("type").isin(["stock"]),
                col("close") > 50,
                col("volume") > 50000,
                col("net_income") > 0,              
                col("total_revenue") > 100000000    
            )
            .order_by("market_cap_basic", ascending=False)
            .limit(limit_size)
            .get_scanner_data()
        )
        if df is None or df.empty:
            return []

        candidates = []
        for _, row in df.iterrows():
            tv_sym = str(row.get("ticker", ""))
            name = str(row.get("name", ""))
            close = float(row.get("close", 0) or 0)
            high_all = float(row.get("High.All", 0) or 0)

            if "RR" in name or "INVIT" in name or name in ["NHIT", "VERTIS", "KRT", "EMBASSY"]:
                continue

            if close <= 0 or high_all <= 0:
                continue

            raw_dist_pct = ((high_all - close) / high_all) * 100.0

            if raw_dist_pct <= 15.0:
                candidates.append({
                    "tv_symbol": tv_sym,
                    "name": name,
                    "close": close,
                    "rev_growth": float(row.get("total_revenue_yoy_growth", 0) or 0),
                    "pat_growth": float(row.get("net_income_yoy_growth", 0) or 0),
                    "roce": float(row.get("return_on_capital_employed", 0) or 0),
                    "de": float(row.get("debt_to_equity", 0) or 0),
                    "ocf": float(row.get("cash_n_operating_activities", 0) or 0),
                    "promoter": float(row.get("promoters_hold_pct", 0) or 0)
                })
        return candidates
    except Exception as e:
        print(f"TV Fetch failed: {e}")
        return []

def tv_to_yf(tv_symbol):
    raw = tv_symbol.split(':')[-1].strip()
    normalized = raw.replace('_', '-')
    return f"{normalized}.NS"

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

def analyze_strict(c, df):
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

    distance_pct = ((lifetime_high - current_price) / lifetime_high) * 100.0

    if not (0.00 <= distance_pct <= 10.00):
        return None

    post_ath = df.loc[lh_idx:]
    if (post_ath["Close"] > lifetime_high).any():
        return None

    return {
        "symbol": c["name"],
        "tv_symbol": c["tv_symbol"],
        "current_price": current_price,
        "lifetime_high": lifetime_high,
        "lh_date": lh_date.strftime("%d-%b-%Y"),
        "age_years": age_years,
        "distance_pct": distance_pct,
        "rev_growth": c.get("rev_growth", 0),
        "pat_growth": c.get("pat_growth", 0),
        "roce": c.get("roce", 0),
        "de": c.get("de", 0),
        "ocf": c.get("ocf", 0),
        "promoter": c.get("promoter", 0)
    }

def print_results(qualified, universe_name):
    print("\n" + "="*85)
    print(f"STRICT MULTI-YEAR BREAKOUT SETUP(S) FOUND IN {universe_name} (GAP <= 10%)")
    print("="*85)
    print(f"{'SYMBOL':<15} {'PRICE':<10} {'ATH':<12} {'ATH DATE':<15} {'AGE':<10} {'GAP %':<10}")
    print("-" * 85)
    for q in sorted(qualified, key=lambda x: x["distance_pct"]):
        print(f"{q['symbol']:<15} {q['current_price']:<10.2f} {q['lifetime_high']:<12.2f} {q['lh_date']:<15} {q['age_years']:<5.2f}Y    {q['distance_pct']:.2f}%")
    print("="*85 + "\n")

def run_scan():
    print("Initializing Strict Multi-Year Proximity Scanner (Expanded to 10% Gap + Fundamentals)...")

    print("\n[Pass 1] Scanning Top 500 NSE stocks by Market Cap...")
    candidates = fetch_tv_candidates(500)
    print(f"Prefilter complete. Testing {len(candidates)} candidates deeply via yfinance...")

    qualified = []
    for c in candidates:
        time.sleep(0.1)
        df = fetch_yf(tv_to_yf(c["tv_symbol"]))
        res = analyze_strict(c, df)
        if res:
            qualified.append(res)

    if qualified:
        print_results(qualified, "TOP 500")
        process_alerts(qualified)
        save_watchlist(qualified)
        return

    print("\n[0 Stocks Qualified in Top 500]")
    print("Expanding scan to ENTIRE liquid NSE market (Vol > 50k, Close > 50)...")

    candidates_all = fetch_tv_candidates(5000)
    print(f"Prefilter complete. Testing {len(candidates_all)} candidates deeply via yfinance...")

    qualified_all = []
    for i, c in enumerate(candidates_all):
        if i % 50 == 0 and i > 0:
            print(f"...processed {i}/{len(candidates_all)} candidates...")

        df = fetch_yf(tv_to_yf(c["tv_symbol"]))
        res = analyze_strict(c, df)
        if res:
            qualified_all.append(res)

    if qualified_all:
        print_results(qualified_all, "ENTIRE MARKET")
        process_alerts(qualified_all)
        save_watchlist(qualified_all)
    else:
        print("\n0 stocks qualified in the entire market.")
        send_empty_alert_to_discord()
        save_watchlist([])

if __name__ == "__main__":
    run_scan()
