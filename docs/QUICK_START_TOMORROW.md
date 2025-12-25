# Quick Start Guide for Tomorrow (Dec 26, 2025)

## Status ✅
Your ANGEL-X strategy is **ready for live paper trading tomorrow**!

### What's Fixed
- ✅ OpenAlgo API compatibility (removed invalid `timeout` parameter)
- ✅ Graceful fallback to default expiries when API unavailable
- ✅ WebSocket auto-reconnection with health monitoring
- ✅ API call retry logic for resilience
- ✅ Network health tracking and alerts

---

## How to Run Tomorrow

### 1. **Start the Strategy** (09:15 IST, 5 min before market opens)
```bash
cd /home/lora/projects/OA
python main.py
```

**Expected output:**
```
2025-12-26 09:15:... INFO - ANGEL-X STRATEGY INITIALIZATION
2025-12-26 09:15:... INFO - NetworkMonitor initialized
...
2025-12-26 09:15:... INFO - WebSocket connected successfully
2025-12-26 09:15:... INFO - Subscribed to NIFTY LTP stream
2025-12-26 09:15:... INFO - Strategy started successfully
2025-12-26 09:15:... INFO - Entering main trading loop...
```

### 2. **Watch for These Success Indicators**
- ✅ "WebSocket connected successfully" → Connection alive
- ✅ "Subscribed to NIFTY LTP stream" → Ready for data
- ✅ "Strategy started successfully" → All engines running
- ✅ "Entering main trading loop..." → Trading active

### 3. **Monitor During 09:25-10:00 Window**
Strategy will:
- Monitor NIFTY LTP stream
- Update bias every 60 seconds
- Trigger entries when:
  - Delta ≥ 0.40
  - IV ≥ 15
  - Spread ≤ 1%
  - HH/LL momentum confirmed
- Exit at +10% profit or -10% loss

### 4. **Network Health Monitoring**
Watch logs for:
- **"No ticks for XXs"** → Data flow check
- **"Connection appears dead"** → Auto-reconnect triggered
- **"Reconnecting..."** → Network recovery in progress

All handled automatically! No manual intervention needed.

### 5. **Stop After 10:00 AM**
Press `Ctrl+C` after trading window closes
```
2025-12-26 10:00:... INFO - STRATEGY STOPPED - DAILY SUMMARY
```

---

## Configuration for Live Run

**Current settings (optimized):**
- **Instrument:** NIFTY only
- **Window:** 09:25–10:00 AM IST
- **Risk:** 4% per trade (₹4,000 on ₹100k capital)
- **SL:** 10% of premium
- **Target:** 10% of premium
- **Mode:** Paper trading (analyzer mode, no live broker)
- **Position:** Max 1 concurrent position

To modify before running:
```bash
# Edit config
nano /home/lora/projects/OA/config/config.py

# Then restart strategy
python main.py
```

---

## Network Resilience Features

**Built-in safeguards for local network:**

1. **WebSocket Auto-Reconnect** (every 2 seconds, max 5 attempts)
2. **API Retry Logic** (3 retries with 1-second delays)
3. **Health Monitoring** (checks every 30 seconds)
4. **Tick Timeout Alert** (alerts if no data for 60+ seconds)
5. **Auto Error Recovery** (continues trading through interruptions)

---

## Logs Location

**Real-time logs:**
```bash
# Watch logs live
tail -f /home/lora/projects/OA/logs/angel_x_*.log
```

**Log files are saved to:**
```
/home/lora/projects/OA/logs/angel_x_YYYY-MM-DD.HHmmss.log
```

**Key sections to review:**
- `[DataFeed]` - WebSocket events
- `[OrderManager]` - Order execution
- `[NetworkMonitor]` - Network health
- `[TradeManager]` - Trade P&L

---

## Troubleshooting

### Issue: "WebSocket connection failed"
**Action:** Check internet connection
```bash
ping 16.16.70.80
```

### Issue: "No ticks for 60+ seconds"
**Action:** Normal - strategy auto-reconnects. Wait 1-2 minutes.

### Issue: "Max reconnection attempts exceeded"
**Action:** Network issue persists. Restart strategy:
```bash
Ctrl+C
sleep 5
python main.py
```

### Issue: Strategy not trading during 09:25-10:00
**Action:** Check logs for entry condition details
```bash
grep "Entry" logs/angel_x_*.log | tail -20
```

---

## Demo Mode (for testing)

**To test without connectivity:**
```python
# Edit config/config.py
DEMO_MODE = True
DEMO_SKIP_WEBSOCKET = True

# Run
python main.py
```

---

## Performance Expectations

**Based on 60-day backtest:**
- Win Rate: 43.4%
- Return: +1.59%
- Max Drawdown: ₹11,747 (12%)
- Avg Trade Duration: 2-4 minutes
- Trades per session: 3-6 in morning window

---

## Safety Checklist Before Starting

- [ ] Internet connection stable (WiFi 5GHz or wired)
- [ ] Closed bandwidth-heavy apps
- [ ] Python environment activated: `source venv/bin/activate`
- [ ] Latest code pulled: `git pull origin main`
- [ ] Logs directory accessible: `./logs/`
- [ ] Capital set to ₹100k in config
- [ ] Paper trading enabled: `PAPER_TRADING = True`
- [ ] Watch this terminal during 09:15-10:00 IST

---

## Post-Trading Analysis

**After market closes (10:00+ AM):**

```bash
# Analyze hour-wise performance
python analyze_hours.py --trades journal/trades_$(date +%Y%m%d).csv

# View detailed trade journal
cat journal/trades_*.csv

# Check network health from logs
grep "Network Health" logs/angel_x_*.log
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python main.py` | Start strategy |
| `Ctrl+C` | Stop strategy gracefully |
| `tail -f logs/angel_x_*.log` | Watch live logs |
| `python analyze_hours.py --trades journal/trades_*.csv` | Analyze results |
| `git log --oneline -5` | View recent commits |
| `git push origin main` | Push day's results to GitHub |

---

## You're Ready! 🚀

Everything is configured and tested. The strategy will:
1. Connect to OpenAlgo analyzer mode ✅
2. Monitor NIFTY LTP in real-time ✅
3. Trade only during 09:25–10:00 window ✅
4. Auto-recover from network issues ✅
5. Journal all trades for analysis ✅

**See you tomorrow at 09:15 IST!**

Questions? Check the logs:
```bash
tail -100 logs/angel_x_*.log
```
