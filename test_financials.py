import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
from tradingview_screener import Query, col
import pandas as pd

# Expand terminal output width for GitHub Actions console
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

SYMBOL_NSE = "NAZARA.NS"
SYMBOL_TV = "NAZARA"

def run_yfinance_test():
    print("=" * 85)
    print(f"TEST 1: Fetching Multi-Year Financial Statements via yfinance ({SYMBOL_NSE})")
    print("=" * 85)

    try:
        tk = yf.Ticker(SYMBOL_NSE)
        fin = tk.financials  # Annual Income Statement

        if fin is not None and not fin.empty:
            # Desired rows that typically match TradingView's fundamental view
            desired_rows = [
                "Total Revenue",
                "Operating Revenue",
                "Gross Profit",
                "Operating Expense",
                "Operating Income",
                "Pretax Income",
                "Tax Provision",
                "Net Income Common Stockholders",
                "Diluted EPS",
                "EBITDA",
                "EBIT"
            ]
            
            # Filter available rows to keep the console clean
            available_rows = [row for row in desired_rows if row in fin.index]
            summary_table = fin.loc[available_rows]

            # Convert dates to years (e.g., 2024, 2023)
            summary_table.columns = [col.strftime("%Y") if hasattr(col, "strftime") else str(col) for col in summary_table.columns]

            # Display raw table in Crores (INR Cr = Value / 10,000,000)
            print("\n--- Annual Income Statement (Values in INR Crores) ---")
            print((summary_table / 1e7).round(2))
        else:
            print("[-] No financial statement data returned by yfinance.")
    except Exception as e:
        print(f"[-] yfinance error: {e}")

def run_tradingview_test():
    print("\n" + "=" * 85)
    print(f"TEST 2: Fetching Screener Fundamentals via TradingView Backend ({SYMBOL_TV})")
    print("=" * 85)

    try:
        # Query fundamental metrics directly from TV's screener database
        count, df = (
            Query()
            .set_markets("india")
            .select(
                "name",
                "close",
                "total_revenue",          # Total Revenue
                "gross_profit_fq",        # Recent Gross Profit
                "net_income",             # Net Income
                "ebitda",                 # EBITDA
                "basic_eps_net_income",   # EPS
                "return_on_equity",       # ROE
                "debt_to_equity"          # D/E ratio
            )
            .where(
                col("exchange").isin(["NSE"]),
                col("name") == SYMBOL_TV
            )
            .get_scanner_data()
        )

        if df is not None and not df.empty:
            print("\n--- TradingView Screener Live Fundamental Fields ---")
            for column in df.columns:
                val = df[column].iloc[0]
                print(f"• {column:<25}: {val}")
        else:
            print("[-] No screener data returned by TradingView.")
    except Exception as e:
        print(f"[-] tradingview-screener error: {e}")

if __name__ == "__main__":
    run_yfinance_test()
    run_tradingview_test()
