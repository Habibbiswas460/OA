import argparse
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime


def fetch(symbol: str, interval: str, period: str, outfile: str):
    print(f"Downloading {symbol} interval={interval} period={period}...")
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(interval=interval, period=period, prepost=False)
        if df.empty:
            print("No data returned. Try a different interval/period or symbol.")
            sys.exit(1)
        df = df.reset_index()  # bring DatetimeIndex to a column
        # Normalize columns
        # yfinance uses 'Datetime' column name after reset_index()
        # Also columns: Open, High, Low, Close, Volume
        # Ensure standard lowercase names expected by backtester
        col_map = {
            'Datetime': 'timestamp',
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }
        df_ren = {}
        for c in df.columns:
            target = col_map.get(c, c.lower())
            df_ren[c] = target
        df = df.rename(columns=df_ren)

        # Keep required columns
        needed = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for n in needed:
            if n not in df.columns:
                raise ValueError(f"Missing column after normalization: {n}")
        out_df = df[needed].copy()

        # Ensure timestamp is ISO-like string for pandas parser
        out_df['timestamp'] = pd.to_datetime(out_df['timestamp'])
        out_df = out_df.sort_values('timestamp')

        out_df.to_csv(outfile, index=False)
        print(f"Saved {len(out_df)} rows to {outfile}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch NIFTY historical OHLCV to CSV via yfinance')
    parser.add_argument('--symbol', type=str, default='^NSEI', help='Yahoo Finance symbol (default: ^NSEI for NIFTY 50 index)')
    parser.add_argument('--interval', type=str, default='5m', help='Data interval (e.g., 1m, 5m, 15m, 60m, 1d)')
    parser.add_argument('--period', type=str, default='30d', help='Lookback period (e.g., 7d for 1m data, 30d for 5m)')
    parser.add_argument('--out', type=str, default='data/nifty_5m_30d.csv', help='Output CSV path')
    args = parser.parse_args()

    fetch(args.symbol, args.interval, args.period, args.out)
