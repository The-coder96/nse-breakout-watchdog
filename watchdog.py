"""
LIVE INTRADAY BREAKOUT WATCHDOG (STOCKS & SECTORS)
==================================================================================
Reads watchlist.json and checks live prices.
Alerts Discord immediately if a Stock OR Sector crosses its multi-year ATH.
Routes to separate webhooks based on item type.
"""

import os
import json
import requests
import yfinance as yf
from tvDatafeed import TvDatafeed, Interval

# Split Routing Webhooks
DISCORD_STOCK_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
DISCORD_SECTOR_WEBHOOK = os.environ.get("DISCORD_SECTOR_WEBHOOK")
WATCHLIST_FILE = "watchlist.json"

try:
    tv = TvDatafeed()
except Exception as e:
    print(f"[-] Failed to initialize TradingView feed in Watchdog: {e}")
    tv = None

def send_alert(item, live_price):
    # Route to the correct webhook based on item type
    target_webhook = DISCORD_STOCK_WEBHOOK if item["item_type"] == "STOCK" else DISCORD_SECTOR_WEBHOOK
    
    if not target_webhook:
        print(f"[-] Webhook missing for {item['item_type']}")
        return
    
    symbol = item["symbol"]
    target = float(item["target"])
    
    if item["item_type"] == "SECTOR":
        title = f"🚀 **LIVE SECTOR BREAKOUT TRIGGERED!**"
        desc = f"**{symbol}** Index has just crossed its Absolute Ceiling of {target:.2f}!"
    else:
        title = f"🚨 **LIVE STOCK BREAKOUT TRIGGERED!**"
        desc = f"**{symbol}** has just crossed its Lifetime High of ₹{target:.2f}!"

    payload = {
        "content": (
            f"{title}\n"
            f"{desc}\n"
            f"• **Current Live Price:** {live_price:.2f}\n"
            f"• **Status:** Active Intraday Breakout"
        )
    }
    
    try:
        # Pushes to the strictly routed channel
        requests.post(target_webhook, json=payload, timeout=10)
        print(f"[+] Alert sent for {symbol}")
    except Exception as e:
        print(f"[-] Alert failed for {symbol}: {e}")

def get_live_sector_price(tv_symbol):
    if not tv: return None
    try:
        exchange, symbol = tv_symbol.split(":")
        df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=2)
        if df is not None and not df.empty:
            return float(df['close'].iloc[-1])
    except: pass
    return None

def main():
    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist.json found. Exiting.")
        return

    try:
        with open(WATCHLIST_FILE, "r") as f:
            watchlist = json.load(f)
    except Exception as e:
        print(f"Error reading watchlist: {e}")
        return

    if not watchlist:
        print("Watchlist is empty. Exiting.")
        return

    remaining_items = []

    for item in watchlist:
        symbol = item["symbol"]
        target = float(item["target"])
        live_price = None

        try:
            # Route data engine based on item type
            if item.get("item_type") == "SECTOR":
                live_price = get_live_sector_price(item["tv_symbol"])
            else:
                tk = yf.Ticker(item["yf_symbol"])
                live_price = float(tk.fast_info['lastPrice'])

            if live_price is not None:
                print(f"Checking {item['item_type']} {symbol} -> LTP: {live_price:.2f} | Target: {target:.2f}")

                if live_price >= target:
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
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(remaining_items, f, indent=4)

if __name__ == "__main__":
    main()
