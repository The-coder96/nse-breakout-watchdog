"""
LIVE INTRADAY BREAKOUT WATCHDOG (STOCKS & SECTORS)
==================================================================================
Reads watchlist.json and checks live prices.
If a Stock OR Sector crosses its multi-year ATH:
1. Launches Playwright (only on trigger) and logs into TradingView.
2. Captures a crisp native TradingView 1W chart snapshot (Ctrl+Alt+S -> Camera -> Clean DOM fallback).
3. Sends the alert + attached PNG chart + clean embed-free link to the routed Discord webhook.
4. Clears triggered symbols from both watchlist.json and alert_history.json.
"""

import os
import sys
import json
import warnings
import traceback
import requests
import yfinance as yf
from tvDatafeed import TvDatafeed, Interval
from playwright.sync_api import sync_playwright

warnings.filterwarnings("ignore")
PROJECT_NAME = "NSE Breakout Watchdog"

# ==============================================================================
# SECURE DISCORD WEBHOOK & AUTH CONFIGURATION
# ==============================================================================
DISCORD_STOCK_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
DISCORD_SECTOR_WEBHOOK = os.environ.get("DISCORD_SECTOR_WEBHOOK")
DISCORD_BUG_WEBHOOK = os.environ.get("DISCORD_BUG_WEBHOOK")
TV_USERNAME = os.environ.get("TV_USERNAME")
TV_PASSWORD = os.environ.get("TV_PASSWORD")
WATCHLIST_FILE = "watchlist.json"
ALERT_HISTORY_FILE = "alert_history.json"

# ==============================================================================
# 🚨 DISCORD UNIVERSAL ERROR REPORTER
# ==============================================================================
def send_error_to_discord(error_msg, context="Watchdog"):
    if not DISCORD_BUG_WEBHOOK:
        print(f"[-] DISCORD_BUG_WEBHOOK not configured. Suppressing bug report for: {context}")
        return

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
# ALERT HISTORY CLEANUP ON LIVE BREAKOUT
# ==============================================================================
def clear_from_alert_history(tv_symbols):
    if not tv_symbols or not os.path.exists(ALERT_HISTORY_FILE):
        return

    try:
        with open(ALERT_HISTORY_FILE, "r") as f:
            history = json.load(f)

        if not isinstance(history, dict):
            return

        removed = []
        for tv_sym in tv_symbols:
            if tv_sym in history:
                del history[tv_sym]
                removed.append(tv_sym)

        if removed:
            with open(ALERT_HISTORY_FILE, "w") as f:
                json.dump(history, f, indent=4)
            print(f"[+] Cleared {len(removed)} broken-out symbol(s) from {ALERT_HISTORY_FILE}: {', '.join(removed)}")
    except Exception as e:
        print(f"[-] Failed to update {ALERT_HISTORY_FILE}: {e}")
        send_error_to_discord(traceback.format_exc(), context="Updating alert_history.json")

try:
    tv = TvDatafeed()
except Exception as e:
    print(f"[-] Failed to initialize TradingView feed in Watchdog: {e}")
    tv = None

# ==============================================================================
# PLAYWRIGHT VISUAL ENGINE (MATCHES test.py)
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
        send_error_to_discord(error_details, context="Watchdog TV Login")

def capture_breakout_chart(page, tv_symbol, timeframe="1W"):
    print(f"📸 Generating weekly chart snapshot for {tv_symbol}...")
    formatted_symbol = tv_symbol.replace(":", "%3A")
    url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval={timeframe}&theme=light"
    screenshot_path = f"{tv_symbol.replace(':', '_')}_breakout.png"

    page.goto(url, timeout=60000)
    page.wait_for_timeout(6000)

    for selector in ['button[aria-label="Close dialog"]', 'button:has-text("Accept all")', 'button[aria-label="Close"]']:
        try:
            page.locator(selector).click(timeout=1500)
        except Exception:
            pass

    # 5Y base + 2x zoom-out keeps multi-year peaks (e.g., 2021) framed alongside current price
    try:
        page.get_by_text("5Y", exact=True).click(timeout=3000)
        page.wait_for_timeout(1500)
        page.keyboard.type("1W", delay=100)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2500)
        for _ in range(2):
            page.keyboard.press("Control+ArrowDown")
            page.wait_for_timeout(200)
        for _ in range(3):
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(100)
    except Exception:
        for _ in range(4):
            page.keyboard.press("Control+ArrowDown")
            page.wait_for_timeout(150)

    # Center click for 1440x810 viewport before triggering native chart export
    page.mouse.click(720, 405)
    page.wait_for_timeout(1000)
    native_success = False

    # Attempt 1: Native Ctrl+Alt+S chart export
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

    # Attempt 2: Native Camera toolbar button
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

    # Attempt 3: Edge-to-edge DOM cleanup fallback
    if not native_success:
        try:
            page.evaluate('''
                const leftBar = document.querySelector('[class*="layout__area--left"]'); if (leftBar) leftBar.style.display = 'none';
                const topBar = document.querySelector('[class*="layout__area--top"]'); if (topBar) topBar.style.display = 'none';
                const rightBar = document.querySelector('[class*="layout__area--right"]'); if (rightBar) rightBar.style.display = 'none';
                const bottomWidget = document.querySelector('[data-name="bottom-widget-bar"]'); if (bottomWidget) bottomWidget.style.display = 'none';
            ''')
            page.wait_for_timeout(800)
        except Exception:
            pass
        page.screenshot(path=screenshot_path)

    return screenshot_path

# ==============================================================================
# DISCORD ALERT DELIVERY
# ==============================================================================
def send_alert(item, live_price, image_path=None):
    target_webhook = DISCORD_STOCK_WEBHOOK if item["item_type"] == "STOCK" else DISCORD_SECTOR_WEBHOOK

    if not target_webhook:
        print(f"[-] Webhook missing for {item['item_type']}")
        return

    symbol = item["symbol"]
    target = float(item["target"])
    tv_symbol = item.get("tv_symbol", "")

    # <url> suppresses Discord's generic link preview while keeping the clickable blue link
    formatted_symbol = tv_symbol.replace(":", "%3A")
    tv_link = f"<https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1W>"

    if item["item_type"] == "SECTOR":
        title = f"🚀 **LIVE SECTOR BREAKOUT TRIGGERED: {symbol}**"
        body = (
            f"• Current Level: {live_price:.2f}\n"
            f"• Breakout Target (Absolute Ceiling): {target:.2f}\n"
            f"• Status: Active Intraday Breakout\n"
        )
    else:
        title = f"🚨 **LIVE STOCK BREAKOUT TRIGGERED: {symbol}**"
        body = (
            f"• Current Price: ₹{live_price:.2f}\n"
            f"• Breakout Target (Lifetime High): ₹{target:.2f}\n"
            f"• Status: Active Intraday Breakout\n"
        )

    content_text = (
        f"{title}\n\n"
        f"**TECHNICAL**\n{body}\n"
        f"**CHART**\n*Attached: Weekly (1W) timeframe chart.*\n\n"
        f"📊 **Interactive Chart:** {tv_link}"
    )

    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                files = {"file": (os.path.basename(image_path), f, "image/png")}
                res = requests.post(target_webhook, data={"content": content_text}, files=files, timeout=25)
        else:
            res = requests.post(target_webhook, json={"content": content_text}, timeout=10)

        if res.status_code in [200, 204]:
            print(f"[+] Alert sent for {symbol}")
        else:
            send_error_to_discord(f"Webhook returned status {res.status_code}: {res.text}", context=f"Alert Delivery ({symbol})")
    except Exception as e:
        print(f"[-] Alert failed for {symbol}: {e}")
        send_error_to_discord(traceback.format_exc(), context=f"Alert Delivery ({symbol})")
    finally:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)

# ==============================================================================
# LIVE PRICE CHECKER
# ==============================================================================
def get_live_sector_price(tv_symbol):
    if not tv or ":" not in tv_symbol:
        return None
    try:
        exchange, symbol = tv_symbol.split(":", 1)
        df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=2)
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None

def main():
    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist.json found. Exiting.")
        return

    try:
        with open(WATCHLIST_FILE, "r") as f:
            watchlist = json.load(f)
    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"Error reading watchlist: {e}")
        send_error_to_discord(err_msg, context="Reading watchlist.json")
        return

    if not watchlist:
        print("Watchlist is empty. Exiting.")
        return

    triggered_items = []
    remaining_items = []

    for item in watchlist:
        symbol = item.get("symbol", "Unknown")
        target = float(item.get("target", 0))
        live_price = None

        try:
            if item.get("item_type") == "SECTOR":
                live_price = get_live_sector_price(item.get("tv_symbol", ""))
            else:
                yf_symbol = item.get("yf_symbol") or f"{symbol}.NS"
                tk = yf.Ticker(yf_symbol)
                try:
                    live_price = float(tk.fast_info["lastPrice"])
                except Exception:
                    df = tk.history(period="1d", auto_adjust=False)
                    if not df.empty:
                        live_price = float(df["Close"].iloc[-1])

            if live_price is not None:
                print(f"Checking {item.get('item_type', 'STOCK')} {symbol} -> LTP: {live_price:.2f} | Target: {target:.2f}")

                if live_price >= target and target > 0:
                    triggered_items.append((item, live_price))
                else:
                    remaining_items.append(item)
            else:
                print(f"[-] Could not fetch live price for {symbol}")
                remaining_items.append(item)

        except Exception as e:
            print(f"Error checking {symbol}: {e}")
            remaining_items.append(item)

    # Only spin up Playwright when at least 1 breakout actually triggers
    if triggered_items:
        print(f"\n[!] Initializing Visual Engine for {len(triggered_items)} live breakout(s)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 810},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()

            automate_tv_login(page)

            for item, live_price in triggered_items:
                screenshot_path = None
                try:
                    screenshot_path = capture_breakout_chart(page, item["tv_symbol"], timeframe="1W")
                except Exception as e:
                    error_trace = traceback.format_exc()
                    print(f"[-] Failed to capture chart for {item['symbol']}: {e}")
                    send_error_to_discord(error_trace, context=f"Watchdog Chart Snapshot ({item['symbol']})")

                send_alert(item, live_price, screenshot_path)

            browser.close()

        clear_from_alert_history([item.get("tv_symbol") for item, _ in triggered_items if item.get("tv_symbol")])

    # Overwrite watchlist, dropping only the items that triggered an alert
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(remaining_items, f, indent=4)
    except Exception:
        send_error_to_discord(traceback.format_exc(), context="Saving watchlist.json")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        crit_err = traceback.format_exc()
        print("CRITICAL WATCHDOG CRASH:\n", crit_err)
        send_error_to_discord(crit_err, context="Watchdog Main Execution")
        sys.exit(1)
