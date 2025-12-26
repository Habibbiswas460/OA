# ANGEL-X Quick Start Guide

## TL;DR

```bash
cd /home/lora/projects/OA
source venv/bin/activate
python3 main.py
```

Run indefinitely. Press Ctrl+C to stop. All trades logged to `journal/`.

---

## What Just Happened

✅ **ANGEL-X is now fully integrated with OpenAlgo SDK** and tested end-to-end.

### Key Features
- **Single-leg options orders** via `optionsorder()`
- **Multi-leg orders** (straddle/strangle) via `optionsmultiorder()`
- **Symbol resolution** via `optionsymbol()` with fallback
- **Intent & outcome logging** for every order attempt
- **WebSocket + REST fallback** for data reliability
- **Paper trading mode** (safe for testing)

### All Tests Pass ✅
```
✅ Logger proxies working
✅ Single order placed: PAPER_1766757583_4291
✅ Multi-leg order placed: PAPER_1766757583_2585
✅ Symbol resolved: NIFTY30DEC25ATMCE
✅ TradeManager multi-leg placed: PAPER_1766757583_3897
✅ Offsets computed correctly
✅ Config flags readable
```

---

## Enable Multi-Leg (Straddle)

Edit `config/config.py`:
```python
USE_MULTILEG_STRATEGY = True
MULTILEG_STRATEGY_TYPE = "STRADDLE"
```

Then run `main.py`. Entries will place straddle orders instead of single legs.

---

## Run Until Market Close

```bash
python3 scripts/run_until_close.py
```

Auto-stops at 15:30 IST. Outputs:
- `logs/live_run_YYYYMMDD_HHMMSS.log`
- `logs/close_report_*.md` (summary)

---

## Check Logs

```bash
# Strategy logs
tail -f logs/strategy_$(date +%Y-%m-%d).log

# Live run logs
tail -f logs/live_run_*.log

# Tick data (once REST fallback starts)
head -20 ticks/ticks_$(date +%Y%m%d).csv
```

---

## Validate Everything

```bash
python3 scripts/validate_all.py
```

Should show:
```
✅ ALL VALIDATION TESTS PASSED
```

---

## Key Configuration Flags

- `PAPER_TRADING = True` → Simulated orders (safe)
- `ANALYZER_MODE = False` → Live data feed
- `USE_OPENALGO_OPTIONS_API = True` → Use optionsorder
- `USE_MULTILEG_STRATEGY = False` → Enable for straddle/strangle
- `MULTILEG_STRATEGY_TYPE = "STRADDLE"` → Type of multi-leg

---

## Monitoring

### Entry Signals
Check logs for:
```
OPTIONSORDER_INTENT  → Order about to be placed
OPTIONSORDER_PLACED  → Order success
MULTIORDER_PLACED    → Multi-leg success
```

### Data Health
Check logs for:
```
WebSocket connected
✅ REST API polling started as fallback
Subscribed to LTP: 1 symbols
```

---

## Common Commands

| Command | What It Does |
|---------|---|
| `python3 main.py` | Run strategy live |
| `python3 scripts/run_until_close.py` | Run until market close |
| `python3 scripts/test_orders.py` | Test order placement |
| `python3 scripts/validate_all.py` | Validate all components |
| `tail -f logs/strategy_*.log` | Watch live logs |

---

## Go Live Checklist

Before flipping `PAPER_TRADING = False`:

- [ ] WebSocket is receiving ticks (check logs)
- [ ] REST fallback works (verify in logs)
- [ ] Single-leg orders succeed (run test_orders.py)
- [ ] Multi-leg orders succeed (run test_orders.py)
- [ ] Entry conditions trigger (run with DEMO_MODE=False)
- [ ] Risk limits respected (check config)
- [ ] Kill-switch enabled (MAX_DAILY_LOSS_AMOUNT set)

---

## Troubleshooting

### No Ticks Received
**Check:** `logs/live_run_*.log` for "REST API polling started"  
**Fix:** Broker WebSocket likely in analyzer mode. Contact admin.

### Order Placement Fails
**Check:** `logs/strategy_*.log` for `OPTIONSORDER_REJECTED` events  
**Fix:** Verify OpenAlgo API key and host in config.

### Strategy Stuck
**Check:** `logs/strategy_*.log` for errors  
**Fix:** Press Ctrl+C to stop; fix the error; restart.

---

## Support

- 📖 Full documentation: [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)
- 🔍 Detailed report: [FINAL_REPORT.md](FINAL_REPORT.md)
- 📋 OpenAlgo API: http://16.16.70.80:5000

---

**You're all set. Happy trading!** 🚀
