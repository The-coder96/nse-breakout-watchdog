"""
UNIFIED BREAKOUT SCANNER (STOCKS & SECTORS) + HYBRID DISCORD ALERTS
==================================================================================
1. Stocks: Multi-Year Breakout (2Y+ Age, <= 5% Gap, Verified Full Fundamentals).
2. Sectors: 1-10Y Squeezes (Mon-Fri) + ATH Momentum (Fridays ONLY) (<= 5% Gap).
3. Hybrid Alerting:
   - Day 1 (New Entry): Full Fundamentals + Native Playwright Weekly Chart.
   - Day 2+ / Re-entry: Compact Daily Squeeze Radar (text-only, closest to ATH first).
4. Optimization: Playwright launches ONLY when new Day 1 chart alerts exist.
5. Error Shield: Universal Bug Reporter routed to DISCORD_BUG_WEBHOOK.
6. Execution: Silent exit on 0-candidate days (no Discord spam).
"""

import os
import time
import sys
import json
import warnings
import traceback
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, col
from tvDatafeed import TvDatafeed, Interval
from playwright.sync_api import sync_playwright

warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
PROJECT_NAME = "NSE Breakout Watchdog"

# ==============================================================================
# HYBRID RADAR SETTINGS (EASY TOGGLES)
# ==============================================================================
ALERT_HISTORY_FILE = "alert_history.json"
CLICKABLE_RADAR_LINKS = True   # True: ticker name opens TradingView | False: pure plain text
ALERT_RESET_DAYS = 90          # Fresh Day 1 chart after 90 days; set to None for permanent text-only until breakout

# ==============================================================================
# SECURE DISCORD WEBHOOK & AUTH CONFIGURATION
# ==============================================================================
DISCORD_STOCK_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
DISCORD_SECTOR_WEBHOOK = os.environ.get("DISCORD_SECTOR_WEBHOOK")
DISCORD_BUG_WEBHOOK = os.environ.get("DISCORD_BUG_WEBHOOK")
TV_USERNAME = os.environ.get("TV_USERNAME")
TV_PASSWORD = os.environ.get("TV_PASSWORD")

# ==============================================================================
# 🚨 DISCORD UNIVERSAL ERROR REPORTER
# ==============================================================================
def send_error_to_discord(error_msg, context=""):
    if not DISCORD_BUG_WEBHOOK:
        print(f"[-] DISCORD_BUG_WEBHOOK not configured. Suppressing bug report for: {context}")
        return

    tag = f"🚨 [{PROJECT_NAME} Error]"
    if context:
        tag = f"🚨 [{PROJECT_NAME} Error - {context}]"

    trace_text = str(error_msg).strip()
    if len(trace_text) > 1800:
        trace_text = trace_text[-1800:]

    discord_message = f"{tag}\n```\n{trace_text}\n```"

    try:
        requests.post(DISCORD_BUG_WEBHOOK, json={"content": discord_message}, timeout=10)
    except Exception as e:
        print(f"[-] Failed to push bug report to Discord: {e}")

# ==============================================================================
# ALERT HISTORY MEMORY MANAGEMENT
# ==============================================================================
def load_alert_history():
    if not os.path.exists(ALERT_HISTORY_FILE):
        return {}
    try:
        with open(ALERT_HISTORY_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[-] Failed to read {ALERT_HISTORY_FILE}: {e}")
        send_error_to_discord(traceback.format_exc(), context="Reading alert_history.json")
        return {}

def save_alert_history(history):
    try:
        with open(ALERT_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
        print(f"[+] Saved {len(history)} tracked record(s) to {ALERT_HISTORY_FILE}.")
    except Exception as e:
        print(f"[-] Failed to write {ALERT_HISTORY_FILE}: {e}")
        send_error_to_discord(traceback.format_exc(), context="Saving alert_history.json")

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
        except Exception:
            pass

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
        error_details = traceback.format_exc()
        print(f"⚠️ Login sequence failed: {e}")
        send_error_to_discord(error_details, context="TradingView Login")

def capture_breakout_chart(page, tv_symbol, timeframe="1W"):
    print(f"📸 Generating weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval={timeframe}&theme=light"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_weekly.png"

    page.goto(url, timeout=60000)
    page.wait_for_timeout(6000)

    for selector in ['button[aria-label="Close dialog"]', 'button:has-text("Accept all")', 'button[aria-label="Close"]']:
        try:
            page.locator(selector).click(timeout=1500)
        except Exception:
            pass

    try:
        page.get_by_text("5Y", exact=True).click(timeout=3000)
        page.wait_for_timeout(1000)
        page.keyboard.type("1W", delay=100)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)
        for _ in range(2):
            page.keyboard.press("Control+ArrowDown")
            page.wait_for_timeout(200)
        for _ in range(3):
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(100)
    except Exception:
        pass

    page.mouse.click(960, 540)
    page.wait_for_timeout(1000)
    native_success = False

    try:
        with page.expect_download(timeout=6000) as download_info:
            page.keyboard.down("Control")
            page.keyboard.down("Alt")
            page.keyboard.press("s")
            page.keyboard.up("Alt")
            page.keyboard.up("Control")

        download_info.value.save_as(screenshot_path)
        native_success = True
    except Exception:
        pass

    if not native_success:
        try:
            camera_btn = page.locator('button[id="header-toolbar-screenshot"], [data-name="header-toolbar-screenshot"]').first
            camera_btn.click(timeout=5000)
            page.wait_for_selector('[data-name="save-chart-image"]', state="visible", timeout=3000)

            with page.expect_download(timeout=6000) as download_info:
                page.locator('[data-name="save-chart-image"]').click()

            download_info.value.save_as(screenshot_path)
            native_success = True
        except Exception:
            pass

    if not native_success:
        try:
            page.evaluate('''
                const rightArea = document.querySelector('[class*="layout__area--right"]');
                if (rightArea) rightArea.style.display = 'none';
            ''')
            page.wait_for_timeout(500)
        except Exception:
            pass
        page.screenshot(path=screenshot_path)

    return screenshot_path

def send_alert_to_discord(tv_symbol, image_path, q):
    target_webhook = DISCORD_STOCK_WEBHOOK if q["item_type"] == "STOCK" else DISCORD_SECTOR_WEBHOOK
    if not target_webhook:
        if os.path.exists(image_path):
            os.remove(image_path)
        return False

    # <url> format: Suppresses the bulky embed preview and allows 1-click direct browser redirect
    formatted_symbol = tv_symbol.replace(":", "%3A")
    tv_link = f"<https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1W>"

    if q["item_type"] == "STOCK":
        rev_cr = q.get('total_revenue', 0) / 10000000
        ni_cr = q.get('net_income', 0) / 10000000
        ebitda_cr = q.get('ebitda', 0) / 10000000
        eps_val = q.get('eps', 0)

        title = f"🚨 **MULTI-YEAR SQUEEZE DETECTED: {q['symbol']}**"
        body = (
            f"• Current Price: ₹{q['current_price']:.2f}\n"
            f"• Lifetime High: ₹{q['lifetime_high']:.2f} (Hit: {q['lh_date']})\n"
            f"• Ceiling Age: {q['age_years']:.2f} Y\n"
            f"• Squeeze Gap: {q['distance_pct']:.2f}%\n\n"
            f"**VERIFIED FUNDAMENTALS (Latest)**\n"
            f"• Total Revenue: ₹{rev_cr:,.2f} Cr\n"
            f"• Net Income (PAT): ₹{ni_cr:,.2f} Cr\n"
            f"• EBITDA: ₹{ebitda_cr:,.2f} Cr\n"
            f"• EPS: ₹{eps_val:.2f}\n"
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

    sent_ok = False
    try:
        with open(image_path, "rb") as f:
            files = {"file": (os.path.basename(image_path), f, "image/png")}
            payload = {
                "content": (
                    f"{title}\n\n"
                    f"**TECHNICAL**\n{body}\n"
                    f"**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n"
                    f"📊 **Interactive Chart:** {tv_link}"
                )
            }
            res = requests.post(target_webhook, data=payload, files=files, timeout=25)
            if res.status_code in [200, 204]:
                sent_ok = True
                print(f"[+] Sent Day 1 full alert for {q['symbol']}")
            else:
                send_error_to_discord(
                    f"Webhook returned status {res.status_code} for {q['symbol']}: {res.text}",
                    context="Discord POST Delivery"
                )
    except Exception as e:
        send_error_to_discord(f"Failed to post alert payload for {q['symbol']}: {e}", context="Discord POST Delivery")
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)

    return sent_ok

def send_daily_radar_to_discord(radar_items, item_type):
    if not radar_items:
        return

    target_webhook = DISCORD_STOCK_WEBHOOK if item_type == "STOCK" else DISCORD_SECTOR_WEBHOOK
    if not target_webhook:
        print(f"[-] Webhook missing for {item_type} daily radar.")
        return

    sorted_items = sorted(radar_items, key=lambda x: x["distance_pct"])
    label = "STOCKS" if item_type == "STOCK" else "SECTORS"
    header = f"📋 **DAILY SQUEEZE RADAR — {label} ({len(sorted_items)} Armed)**\n"

    lines = []
    for idx, q in enumerate(sorted_items, start=1):
        formatted_symbol = q["tv_symbol"].replace(":", "%3A")
        tv_url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1W"

        if CLICKABLE_RADAR_LINKS:
            name_str = f"**[{q['symbol']}](<{tv_url}>)**"
        else:
            name_str = f"**{q['symbol']}**"

        if item_type == "STOCK":
            price_str = f"₹{q['current_price']:,.2f}"
            ath_str = f"₹{q['lifetime_high']:,.2f}"
        else:
            price_str = f"{q['current_price']:,.2f}"
            ath_str = f"{q['lifetime_high']:,.2f}"

        if q.get("is_reentry"):
            line = f"{idx}. {name_str} — {price_str} | **{q['distance_pct']:.2f}% away** *(Re-entered)* | ATH: {ath_str}"
        else:
            day_num = q.get("days_in_zone", 2)
            line = f"{idx}. {name_str} — {price_str} | **{q['distance_pct']:.2f}% away** | ATH: {ath_str} | Day {day_num}"

        lines.append(line)

    # Auto-chunk if a big bull market puts 20+ items in the list (Discord 2000-char limit)
    chunks = []
    current_msg = header
    for line in lines:
        if len(current_msg) + len(line) + 1 > 1900:
            chunks.append(current_msg.rstrip())
            current_msg = line + "\n"
        else:
            current_msg += line + "\n"
    if current_msg.strip():
        chunks.append(current_msg.rstrip())

    for msg in chunks:
        try:
            res = requests.post(target_webhook, json={"content": msg}, timeout=15)
            if res.status_code in [200, 204]:
                print(f"[+] Sent {label} Daily Squeeze Radar ({len(sorted_items)} item(s)).")
            else:
                send_error_to_discord(
                    f"Radar webhook returned {res.status_code}: {res.text}",
                    context=f"Daily Radar ({label})"
                )
        except Exception as e:
            send_error_to_discord(f"Failed to send {label} Daily Radar: {e}", context=f"Daily Radar ({label})")

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
                    "tv_symbol": str(row.get("ticker", "")),
                    "name": name,
                    "close": close,
                    "total_revenue": float(row.get("total_revenue", 0) or 0),
                    "net_income": float(row.get("net_income", 0) or 0),
                    "ebitda": float(row.get("ebitda", 0) or 0),
                    "eps": float(row.get("basic_eps_net_income", 0) or 0)
                })
        return candidates
    except Exception as e:
        send_error_to_discord(traceback.format_exc(), context="TV Screener Query")
        return []

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

    # 5.00% Limit for Stocks (2+ Year ATH Age)
    if age_years < 2.0 or not (0.00 <= distance_pct <= 5.00): return None
    if (df.loc[lh_idx:]["Close"] > lifetime_high).any(): return None

    return {
        "symbol": c["name"],
        "tv_symbol": c["tv_symbol"],
        "current_price": current_price,
        "lifetime_high": lifetime_high,
        "lh_date": lh_idx.date().strftime("%d-%b-%Y"),
        "age_years": age_years,
        "distance_pct": distance_pct,
        "total_revenue": c.get("total_revenue", 0),
        "net_income": c.get("net_income", 0),
        "ebitda": c.get("ebitda", 0),
        "eps": c.get("eps", 0),
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

    # 5.00% Limit for Sectors
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

def run_scan():
    all_qualified = []
    today_date = datetime.now(tz=IST).date()
    today_str = today_date.strftime("%Y-%m-%d")
    history = load_alert_history()

    print("\n[Pass 1] Scanning Top 500 NSE stocks by Market Cap...")
    stock_cands = fetch_tv_candidates(500)
    for c in stock_cands:
        try:
            ticker = yf.Ticker(tv_to_yf(c["tv_symbol"]))

            # FIX: auto_adjust=False stops yfinance from adjusting historical peaks for dividend stocks
            df = ticker.history(period="max", auto_adjust=False)

            if df is not None and not df.empty:
                res = analyze_stock(c, df)
                if res: all_qualified.append(res)
        except Exception as e:
            print(f"[-] Data error for {c['name']}: {e}")

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
            except Exception:
                pass

    # Partition qualified candidates into Day 1 (Full Chart) vs Day 2+/Re-entry (Compact Radar)
    qualified_keys = set()
    new_full_alerts = []
    radar_stocks = []
    radar_sectors = []

    for q in sorted(all_qualified, key=lambda x: x["distance_pct"]):
        key = q["tv_symbol"]
        qualified_keys.add(key)
        record = history.get(key)

        needs_full_chart = True
        if record and record.get("first_alert_date"):
            try:
                first_dt = datetime.strptime(record["first_alert_date"], "%Y-%m-%d").date()
                days_since_chart = (today_date - first_dt).days
                if ALERT_RESET_DAYS is None or days_since_chart < ALERT_RESET_DAYS:
                    needs_full_chart = False
            except Exception:
                needs_full_chart = True

        if needs_full_chart:
            new_full_alerts.append(q)
        else:
            was_active = record.get("active", False)
            last_seen = record.get("last_seen_date", "")

            if not was_active:
                # Re-entered the 5% zone after dropping below it
                days_in_zone = 1
                is_reentry = True
            elif last_seen == today_str:
                # Same-day manual re-run safeguard (do not double-count day)
                days_in_zone = int(record.get("days_in_zone", 1))
                is_reentry = bool(record.get("reentered_today", False))
            else:
                days_in_zone = int(record.get("days_in_zone", 1)) + 1
                is_reentry = False

            record["symbol"] = q["symbol"]
            record["item_type"] = q["item_type"]
            record["last_seen_date"] = today_str
            record["days_in_zone"] = days_in_zone
            record["active"] = True
            record["reentered_today"] = is_reentry
            record["ath_target"] = round(float(q["lifetime_high"]), 2)
            history[key] = record

            q["days_in_zone"] = days_in_zone
            q["is_reentry"] = is_reentry

            if q["item_type"] == "STOCK":
                radar_stocks.append(q)
            else:
                radar_sectors.append(q)

    # Mark dropped-out symbols as inactive and prune expired inactive entries
    expired_keys = []
    for key, record in history.items():
        if key not in qualified_keys:
            record["active"] = False
            record["reentered_today"] = False
            if ALERT_RESET_DAYS is not None and record.get("first_alert_date"):
                try:
                    first_dt = datetime.strptime(record["first_alert_date"], "%Y-%m-%d").date()
                    if (today_date - first_dt).days >= ALERT_RESET_DAYS:
                        expired_keys.append(key)
                except Exception:
                    pass
    for key in expired_keys:
        del history[key]

    # 1. Process brand-new Day 1 alerts (Playwright launches ONLY if needed)
    if new_full_alerts:
        print(f"\n[!] Initializing Visual Engine for {len(new_full_alerts)} NEW Day 1 item(s)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()

            automate_tv_login(page)

            for q in new_full_alerts:
                try:
                    screenshot_path = capture_breakout_chart(page, q['tv_symbol'], timeframe="1W")
                    sent_ok = send_alert_to_discord(q['tv_symbol'], screenshot_path, q)
                    if sent_ok:
                        history[q["tv_symbol"]] = {
                            "symbol": q["symbol"],
                            "item_type": q["item_type"],
                            "first_alert_date": today_str,
                            "last_seen_date": today_str,
                            "days_in_zone": 1,
                            "active": True,
                            "reentered_today": False,
                            "ath_target": round(float(q["lifetime_high"]), 2)
                        }
                except Exception as e:
                    error_trace = traceback.format_exc()
                    print(f"[-] Failed to generate or send chart for {q['symbol']}: {e}")
                    send_error_to_discord(error_trace, context=f"Chart Snapshot ({q['symbol']})")

            browser.close()
    else:
        print("\n[*] No new Day 1 entries today. Skipping Playwright visual engine.")

    # 2. Send compact Daily Squeeze Radar for ongoing / re-entered items
    if radar_stocks:
        send_daily_radar_to_discord(radar_stocks, "STOCK")
    if radar_sectors:
        send_daily_radar_to_discord(radar_sectors, "SECTOR")

    # 3. Always update watchlist.json and alert_history.json
    if not all_qualified:
        print("\n0 Stocks and 0 Sectors met criteria today. Silent exit (no Discord post).")

    save_watchlist(all_qualified)
    save_alert_history(history)

if __name__ == "__main__":
    try:
        run_scan()
    except Exception as e:
        crit_err = traceback.format_exc()
        print("CRITICAL CRASH:\n", crit_err)
        send_error_to_discord(crit_err, context="Main Scanner Execution")
        sys.exit(1)
