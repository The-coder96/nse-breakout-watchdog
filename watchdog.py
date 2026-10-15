"""
LIVE INTRADAY BREAKOUT WATCHDOG (STOCKS & SECTORS)
==================================================================================
Reads watchlist.json and checks live prices.
Alerts Discord immediately if a Stock OR Sector crosses its multi-year ATH.
Routes to separate webhooks based on item type and includes clickable dual links (App + Web).
"""

import os
import json
import traceback
import requests
import yfinance as yf
from tvDatafeed import TvDatafeed, Interval

PROJECT_NAME = "NSE Breakout Watchdog"

# Webhooks Configuration
DISCORD_STOCK_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
DISCORD_SECTOR_WEBHOOK = os.environ.get("DISCORD_SECTOR_WEBHOOK")
DISCORD_BUG_WEBHOOK = os.environ.get("DISCORD_BUG_WEBHOOK")
WATCHLIST_FILE = "watchlist.json"

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

try:
    tv = TvDatafeed()
except Exception as e:
    print(f"[-] Failed to initialize TradingView feed in Watchdog: {e}")
    tv = None

def send_alert(item, live_price):
    target_webhook = DISCORD_STOCK_WEBHOOK if item["item_type"] == "STOCK" else DISCORD_SECTOR_WEBHOOK
    
    if not target_webhook:
        print(f"[-] Webhook missing for {item['item_type']}")
        return
    
    symbol = item["symbol"]
    target = float(item["target"])
    tv_symbol = item.get("tv_symbol", "")
    
    # Generate Dual Link (Web + Native App Protocol)
    formatted_symbol = tv_symbol.replace(":", "%3A")
    tv_web_url = f"https://www.tradingview.com/chart/?symbol={formatted_symbol}&interval=1D"
    tv_app_url = f"tradingview://chart?symbol={formatted_symbol}&interval=1D"
    
    if item["item_type"] == "SECTOR":
        title = f"🚀 **LIVE SECTOR BREAKOUT TRIGGERED!**"
        desc = f"**{symbol}** Index has just crossed its Absolute Ceiling of {target:.2f}!"
    else:
        title = f"🚨 **LIVE STOCK BREAKOUT TRIGGERED!**"
        desc = f"**{symbol}** has just crossed its Lifetime High of ₹{target:.2f}!"

    payload = {
        "content": (
            f"{title}\n"
            f"{desc}\n\n"
            f"• **Current Live Price:** ₹{live_price:.2f}\n"
            f"• **Breakout Target:** ₹{target:.2f}\n"
            f"• **Status:** Active Intraday Breakout\n\n"
            f"📊 **Live Chart:**\n"
            f"🌐 [Open in Web Browser]({tv_web_url}) | 📱 [Open in TV App]({tv_app_url})"
        )
    }
    
    try:
        res = requests.post(target_webhook, json=payload, timeout=10)
        if res.status_code in [200, 204]:
            print(f"[+] Alert sent for {symbol}")
        else:
            send_error_to_discord(f"Webhook returned status {res.status_code}: {res.text}", context=f"Alert Delivery ({symbol})")
    except Exception as e:
        print(f"[-] Alert failed for {symbol}: {e}")
        send_error_to_discord(traceback.format_exc(), context=f"Alert Delivery ({symbol})")

def get_live_sector_price(tv_symbol):
    if not tv: return None
    try:
        exchange, symbol = tv_symbol.split(":")
        df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=2)
        if df is not None and not df.empty:
            return float(df['close'].iloc[-1])
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
                    # Primary fast method
                    live_price = float(tk.fast_info['lastPrice'])
                except Exception:
                    # Bulletproof fallback in case yfinance fast_info fails
                    df = tk.history(period="1d")
                    if not df.empty:
                        live_price = float(df['Close'].iloc[-1])

            if live_price is not None:
                print(f"Checking {item.get('item_type', 'STOCK')} {symbol} -> LTP: {live_price:.2f} | Target: {target:.2f}")

                if live_price >= target and target > 0:
                    send_alert(item, live_price)
                else:
                    remaining_items.append(item)
            else:
                print(f"[-] Could not fetch live price for {symbol}")
                remaining_items.append(item)
                
        except Exception as e:
            print(f"Error checking {symbol}: {e}")
            remaining_items.append(item)

    # Overwrite watchlist, dropping only the ones that triggered an alert
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(remaining_items, f, indent=4)
    except Exception as e:
        send_error_to_discord(traceback.format_exc(), context="Saving watchlist.json")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        crit_err = traceback.format_exc()
        print("CRITICAL WATCHDOG CRASH:\n", crit_err)
        send_error_to_discord(crit_err, context="Watchdog Main Execution")
        sys.exit(1)
