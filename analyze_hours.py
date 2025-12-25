import argparse
import pandas as pd
from collections import Counter


def analyze_hours(trades_csv: str):
    df = pd.read_csv(trades_csv, parse_dates=['entry_time', 'exit_time'])
    if 'pnl' not in df.columns:
        raise ValueError('Trades CSV must include a pnl column')

    # Hour-of-day by exit time
    df['exit_hour'] = df['exit_time'].dt.hour

    # Aggregate PnL by hour
    pnl_by_hour = df.groupby('exit_hour')['pnl'].sum().sort_values()

    # Exit reasons count by hour
    reason_by_hour = (
        df.groupby(['exit_hour', 'exit_reason'])['trade_id']
          .count()
          .reset_index()
          .pivot(index='exit_hour', columns='exit_reason', values='trade_id')
          .fillna(0)
    )

    print('\n=== Hour-wise PnL (Exit Hour) ===')
    for hour, pnl in pnl_by_hour.items():
        print(f"{hour:02d}:00 -> PnL: ₹{pnl:,.2f}")

    print('\n=== Exit Reason Counts by Hour ===')
    # Ensure consistent ordering
    columns = sorted(reason_by_hour.columns.tolist())
    for hour in reason_by_hour.index:
        counts = {col: int(reason_by_hour.loc[hour, col]) for col in columns}
        counts_str = ', '.join([f"{k}: {v}" for k, v in counts.items() if v > 0])
        print(f"{hour:02d}:00 -> {counts_str if counts_str else 'No exits'}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze trades CSV for hour-wise performance')
    parser.add_argument('--trades', type=str, required=True, help='Path to backtest trades CSV')
    args = parser.parse_args()

    analyze_hours(args.trades)
