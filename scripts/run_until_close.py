#!/usr/bin/env python3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import os
import signal

WORKDIR = Path('/home/lora/projects/OA')
LOGDIR = WORKDIR / 'logs'
LOGDIR.mkdir(exist_ok=True)


def market_close_dt(today_tz):
    # NSE market close 15:30 IST
    return today_tz.replace(hour=15, minute=30, second=0, microsecond=0)


def now_ist():
    return datetime.now(ZoneInfo('Asia/Kolkata'))


def seconds_until_close():
    now = now_ist()
    close = market_close_dt(now)
    if now >= close:
        # If past close, run 10 minutes for cleanup
        return 600
    return (close - now).total_seconds()


def start_bot():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = LOGDIR / f'live_run_{ts}.log'
    py = sys.executable or 'python3'
    cmd = [py, 'main.py']
    f = open(log_path, 'w')
    proc = subprocess.Popen(cmd, cwd=WORKDIR, stdout=f, stderr=subprocess.STDOUT)
    with open('/tmp/bot_pid.txt', 'w') as pf:
        pf.write(str(proc.pid))
    print(f"Started bot PID {proc.pid}, logging to {log_path}")
    return proc, log_path


def graceful_stop(pid):
    try:
        print(f"Sending SIGINT to PID {pid} for graceful stop...")
        os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
        print("Process already stopped.")


def parse_summary(log_path):
    summary = {
        'websocket_reconnects': 0,
        'rest_fallbacks': 0,
        'alerts': 0,
        'last_ltp': None
    }
    try:
        with open(log_path, 'r') as f:
            for line in f:
                if 'Re-subscribing to' in line and 'symbols' in line:
                    summary['websocket_reconnects'] += 1
                if 'REST API polling started as fallback' in line:
                    summary['rest_fallbacks'] += 1
                if 'Alerts:' in line:
                    try:
                        summary['alerts'] = int(line.strip().split('Alerts:')[-1].strip())
                    except:
                        pass
                if 'NIFTY' in line and '[' in line and 'REST_POLLING' in line:
                    # Try to capture last LTP
                    parts = line.strip().split(':')
                    if len(parts) >= 2:
                        try:
                            summary['last_ltp'] = float(parts[1].split()[0])
                        except:
                            pass
    except Exception as e:
        print(f"Error parsing summary: {e}")
    return summary


def write_close_report(log_path, summary):
    report_path = LOGDIR / f"close_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_path, 'w') as r:
        r.write("# Market Close Report\n\n")
        r.write(f"- Log file: {log_path}\n")
        r.write(f"- Time: {now_ist().strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        r.write(f"- WebSocket reconnects: {summary['websocket_reconnects']}\n")
        r.write(f"- REST fallbacks: {summary['rest_fallbacks']}\n")
        r.write(f"- Alerts: {summary['alerts']}\n")
        r.write(f"- Last LTP (if parsed): {summary['last_ltp']}\n")
    print(f"Wrote close report: {report_path}")
    return report_path


def main():
    proc, log_path = start_bot()
    secs = int(seconds_until_close())
    print(f"Running until market close (~{secs} seconds)...")
    try:
        # Sleep in intervals to print checkpoints
        remaining = secs
        while remaining > 0:
            step = min(300, remaining)  # 5 min steps
            time.sleep(step)
            remaining -= step
            print(f"...still running, {remaining} seconds to close")
    finally:
        graceful_stop(proc.pid)
        # Give time to flush logs
        time.sleep(10)
        # Parse and write report
        summary = parse_summary(log_path)
        write_close_report(log_path, summary)
        print("Done.")


if __name__ == '__main__':
    main()
