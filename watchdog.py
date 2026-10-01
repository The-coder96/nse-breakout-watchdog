import os
import json
import requests
import yfinance as yf

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
WATCHLIST_FILE = "watchlist.json"

def send_alert(symbol, target, live_price):
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK secret not found.")
        return
    payload = {
        "content": (
            f"🚨 **LIVE BREAKOUT TRIGGERED!**\n"
            f"**{symbol}** has crossed its Lifetime High of ₹{target:.2f}!\n"
            f"• **Current Live Price:** ₹{live_price:.2f}\n"
            f"• **Status:** Active Breakout"
        )
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f"[+] Alert sent for {symbol}")
    except Exception as e:
        print(f"[-] Alert failed for {symbol}: {e}")

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

    remaining_stocks = []

    for stock in watchlist:
        symbol = stock["symbol"]
        target = float(stock["target"])
        yf_symbol = stock.get("yf_symbol", f"{symbol}.NS")

        try:
            tk = yf.Ticker(yf_symbol)
            live_price = float(tk.fast_info['lastPrice'])
            print(f"Checking {symbol} -> LTP: ₹{live_price:.2f} | Target: ₹{target:.2f}")

            if live_price >= target:
                send_alert(symbol, target, live_price)
            else:
                remaining_stocks.append(stock)
        except Exception as e:
            print(f"Error checking {symbol}: {e}")
            remaining_stocks.append(stock)

    with open(WATCHLIST_FILE, "w") as f:
        json.dump(remaining_stocks, f, indent=4)

if __name__ == "__main__":
    main()
