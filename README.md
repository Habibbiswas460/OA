# ANGEL-X: Professional Options Scalping Strategy

> **Greeks-Based Momentum Scalping for NIFTY/BANKNIFTY Weekly Options**  
> Auto-Expiry Detection | Risk-First Position Sizing | Time-Based Exits

---

## 📋 Overview

ANGEL-X is a professional-grade options scalping strategy designed for 1-5 minute trades on NIFTY/BANKNIFTY weekly options. The system features:

- ✅ **Auto-Expiry Detection** from OpenAlgo API
- ✅ **Greeks-Based Market Analysis** (Delta, Gamma, Theta, Vega)
- ✅ **9-Layer Architecture** for robust trading
- ✅ **Risk-First Position Sizing** (1-5% per trade)
- ✅ **Time-Based Exits** on expiry day (max 5 minutes)
- ✅ **Trap Detection Engine** for OI/IV/Spread patterns
- ✅ **Comprehensive Trade Logging** with analytics

---

## 📁 Project Structure

```
OA/
├── main.py                        # Strategy orchestrator (entry point)
│
├── src/                           # Source code
│   ├── __init__.py
│   ├── config.py                  # 13 sections of configuration
│   │
│   ├── core/                      # Core trading modules
│   │   ├── __init__.py
│   │   ├── trade_manager.py       # Trade lifecycle management
│   │   ├── order_manager.py       # OpenAlgo API wrapper
│   │   ├── position_sizing.py     # Risk-first sizing
│   │   ├── expiry_manager.py      # Auto-expiry detection
│   │   └── risk_manager.py        # Daily limits & kill-switch
│   │
│   ├── engines/                   # Analysis engines
│   │   ├── __init__.py
│   │   ├── bias_engine.py         # Market state (Greeks-based)
│   │   ├── entry_engine.py        # Momentum confirmation
│   │   ├── strike_selection_engine.py  # Option health scoring
│   │   └── trap_detection_engine.py    # Trap pattern detection
│   │
│   └── utils/                     # Utilities
│       ├── __init__.py
│       ├── logger.py              # Centralized logging
│       ├── data_feed.py           # WebSocket data ingestion
│       ├── trade_journal.py       # Comprehensive logging
│       ├── market_data.py         # Market data structures
│       └── options_helper.py      # Utility functions
│
├── docs/                          # Documentation
│   ├── QUICK_START_EXPIRY_TRADING.md
│   ├── CODE_CHANGES_SUMMARY.md
│   ├── EXPIRY_ARCHITECTURE_DIAGRAM.md
│   ├── EXPIRY_IMPLEMENTATION_VERIFICATION.md
│   ├── PROJECT_COMPLETE_SUMMARY.md
│   ├── DOCUMENTATION_INDEX.md
│   ├── START_HERE.md
│   └── INTEGRATION_GUIDE.md
│
├── logs/                          # Log files (auto-generated)
├── journal/                       # Trade journals (auto-generated)
├── venv/                          # Virtual environment
├── requirements.txt               # Python dependencies
├── .gitignore
└── README.md                      # This file
```

---

## 🏗️ Architecture: 9-Layer System

### **Layer 1-2: Data Ingestion & Normalization**
- `data_feed.py` - WebSocket connection to OpenAlgo
- `market_data.py` - Data structures for LTP, Greeks, OI

### **Layer 3: Market State Engine**
- `bias_engine.py` - Greeks-based market bias (BULLISH/BEARISH/NO_TRADE)
- Analyzes Delta, Gamma, OI alignment for directional bias

### **Layer 4: Option Selection Engine**
- `strike_selection_engine.py` - ATM ±5 strikes health scoring
- Filters by Greeks (Delta 0.45-0.65), liquidity, spread (<1%)

### **Layer 5: Entry Engine**
- `entry_engine.py` - 5-signal momentum confirmation
- LTP↑, Volume↑, OI↑, Gamma↑, Delta in power zone

### **Layer 6: Position Sizing Engine**
- `position_sizing.py` - Risk-first sizing (1-5% per trade)
- Auto-adjusts based on expiry rules (30% on expiry day)

### **Layer 7: Execution Engine**
- `order_manager.py` - OpenAlgo API integration
- Order placement, modification, cancellation

### **Layer 8: Trade Management Engine**
- `trade_manager.py` - Greek-based exits
- Delta weakness, Gamma rollover, Theta damage, IV crush

### **Layer 9: Daily Risk & Kill-Switch**
- `risk_manager.py` - Daily loss limits (3% max)
- Max 5 trades/day, consecutive loss cooldown

---

## 🎯 Key Features

### 1. **Auto-Expiry Detection** (NEW)
```python
ExpiryManager
├─ fetch_available_expiries()  # From OpenAlgo API
├─ select_nearest_weekly_expiry()
├─ apply_expiry_rules()        # Position size reduction
└─ build_order_symbol()        # NIFTY18800CE06FEB2025
```

**Expiry-Day Rules:**
- Position size: **30%** of normal (70% reduction!)
- Risk: **0.5%** per trade (vs 2% normal)
- Hard SL: **3%** (vs 6-8% normal)
- Max duration: **5 minutes** (hard stop)

### 2. **Greeks-Based Bias Engine**
```python
BiasEngine
├─ Delta ≥ 0.45 + Gamma↑ → BULLISH (CALL permission)
├─ Delta ≤ -0.45 + Gamma↑ → BEARISH (PUT permission)
└─ OI↑ but LTP flat → NO_TRADE (trap detected)
```

### 3. **Risk-First Position Sizing**
```python
PositionSizing
├─ Calculate from hard SL (6-8%)
├─ Risk per trade: 1-5% of capital
└─ Auto-adjust for expiry (30%-100%)
```

### 4. **Time-Based Exits** (Expiry Protection)
```python
TradeManager
├─ Track time_in_trade_sec
├─ Expiry day: Exit at 5 min (even if loss)
└─ Opportunistic: Exit at 20s + profit target
```

### 5. **Trap Detection**
```python
TrapDetectionEngine
├─ OI↑ but premium flat → OI trap
├─ IV↑ but price choppy → IV trap
└─ Spread >1.5% → Liquidity trap
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone repository
cd /home/lora/projects/OA

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac
# venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Edit `src/config.py`:

```python
# OpenAlgo API Configuration
OPENALGO_API_KEY = "your_api_key_here"
OPENALGO_HOST = "http://16.16.70.80:5000"
OPENALGO_WS_URL = "ws://16.16.70.80:8765"

# Primary Trading Symbol
PRIMARY_UNDERLYING = "NIFTY"  # or "BANKNIFTY"

# Capital & Risk
CAPITAL = 100000
RISK_PER_TRADE_OPTIMAL = 0.02  # 2% per trade
MAX_DAILY_LOSS_PERCENT = 0.03  # 3% daily loss limit
```

### 3. Run Strategy

```bash
# From project root
python main.py
```

### 4. Test Mode (Recommended First)

```python
# In src/config.py
PAPER_TRADING = True   # Paper trading mode
DRY_RUN = True         # No actual orders
ANALYZER_MODE = True   # OpenAlgo analyzer mode
```

---

## 📊 Configuration Guide

### Trading Parameters
```python
# Time Windows
TRADING_SESSION_START = "09:15"
TRADING_SESSION_END = "15:30"
NO_TRADE_LAST_MINUTES = 45  # Avoid expiry chaos

# Greeks Thresholds
IDEAL_DELTA_CALL = (0.45, 0.65)
IDEAL_GAMMA_MIN = 0.002
IDEAL_THETA_MAX = -0.05

# Risk Management
MAX_CONCURRENT_POSITIONS = 1  # Scalp style
MAX_TRADES_PER_DAY = 5
CONSECUTIVE_LOSS_LIMIT = 2
```

---

## 🎯 Features

### ✅ **Core Features**
- Auto-expiry detection from OpenAlgo API
- Greeks-based market analysis (Delta, Gamma, Theta, Vega)
- 9-layer professional architecture
- Risk-first position sizing (1-5% per trade)
- Time-based exits on expiry day (max 5 minutes)
- Trap detection for OI/IV/Spread patterns
- Comprehensive trade logging with analytics

### ✅ **Risk Management**
- Daily loss limits (3% max)
- Daily profit targets
- Max trades per day (5)
- Consecutive loss cooldown (2 losses)
- Position size limits
- Time-based controls

### ✅ **Expiry Protection**
- **Expiry day**: 30% position, 0.5% risk, 5 min max
- **Last day**: 50% position, 1% risk, 10 min max
- **Expiry week**: 70% position, 1.5% risk, 15 min max
- **Normal**: 100% position, 2% risk

---

## 📚 Documentation

All documentation is in the `docs/` folder:

### Quick Reference
- **START_HERE.md** - 5-minute overview
- **QUICK_START_EXPIRY_TRADING.md** - Expiry trading guide
- **DOCUMENTATION_INDEX.md** - Complete documentation index

### Technical Details
- **EXPIRY_ARCHITECTURE_DIAGRAM.md** - System flow diagrams
- **CODE_CHANGES_SUMMARY.md** - What changed in the code
- **EXPIRY_IMPLEMENTATION_VERIFICATION.md** - Verification checklist
- **PROJECT_COMPLETE_SUMMARY.md** - Complete project overview

---

## 📝 Logging & Monitoring

### Log Files (auto-generated in `logs/`)
```
logs/
├── strategy_2025-12-25.log    # Main strategy log
├── trades_2025-12-25.log      # Trade-specific log
└── errors_2025-12-25.log      # Error log
```

### Trade Journal (auto-generated in `journal/`)
```
journal/
├── trades_2025-12-25.csv      # CSV format
└── trades_2025-12-25.json     # JSON format
```

### What's Logged
- Entry/exit prices and reasons
- Entry/exit Greeks (Delta, Gamma, Theta, Vega, IV)
- Trade duration and P&L
- Position sizing details
- Exit trigger reasons (time-based, Greek-based, SL)
- Trap detection events

---

## 🔧 Customization

### 1. Modify Bias Logic
Edit `src/engines/bias_engine.py`:
```python
def update_with_greeks_data(self, ...):
    # Add your custom bias calculation
    # Modify Delta/Gamma thresholds
    # Add new indicators
```

### 2. Add Entry Filters
Edit `src/engines/entry_engine.py`:
```python
def check_entry_signal(self, ...):
    # Add custom entry conditions
    # Modify confirmation logic
```

### 3. Adjust Position Sizing
Edit `src/core/position_sizing.py`:
```python
def calculate_position_size(self, ...):
    # Modify sizing algorithm
    # Add custom risk calculations
```

---

## ⚠️ Important Notes

### Safety First
1. ✅ **Test First**: Always test with `DRY_RUN = True` and `PAPER_TRADING = True`
2. ✅ **Check API Keys**: Ensure OpenAlgo credentials are correct
3. ✅ **Monitor Risk**: Watch daily P&L and position sizing
4. ✅ **Review Logs**: Check `logs/` directory regularly
5. ✅ **Paper Trade**: Use paper trading mode before going live

### Expiry Day Caution
- On expiry day, position size is **automatically reduced to 30%**
- Max trade duration is **5 minutes** (hard stop)
- Risk is capped at **0.5%** per trade
- System exits immediately if time limit exceeded

---

## 🔒 Security Best Practices

```python
# NEVER commit API keys to git
# Use environment variables or secure config

# In src/config.py
import os
OPENALGO_API_KEY = os.getenv('OPENALGO_API_KEY', 'your_key_here')
```

- Don't commit API keys to version control
- Restrict file permissions: `chmod 600 src/config.py`
- Use `.gitignore` for sensitive files
- Enable 2FA on broker account

---

## 📊 Performance Monitoring

### Real-Time Stats
The strategy tracks and displays:
```
Total Trades: 42
Win Rate: 65.5%
Daily P&L: ₹8,450
Active Positions: 0
Daily Trades: 4/5
Risk Exposure: 2.3%
```

### Post-Trade Analytics
Review in `journal/` folder:
- CSV format for Excel/Pandas analysis
- JSON format for custom processing
- Tagged exit reasons for pattern analysis

---

## 🛠️ Troubleshooting

### WebSocket Connection Issues
```bash
# Check logs
tail -f logs/strategy_2025-12-25.log

# Verify credentials
# Check src/config.py → OPENALGO_API_KEY, OPENALGO_HOST
```

### Orders Not Placing
Check:
- [ ] `DRY_RUN = False` in config
- [ ] Trading hours (09:15 - 15:30)
- [ ] Daily loss limit not exceeded
- [ ] Max trades/day not reached
- [ ] Risk manager allowing trades

### Import Errors After Reorganization
```bash
# Run from project root
cd /home/lora/projects/OA
python src/main.py

# If still errors, check Python path
export PYTHONPATH="${PYTHONPATH}:/home/lora/projects/OA"
```

### Expiry Detection Not Working
```bash
# Check logs for expiry manager
grep "Expiry" logs/strategy_*.log

# Verify OpenAlgo API access
# Check OPENALGO_HOST and OPENALGO_API_KEY
```

---

## 📈 Next Steps

### 1. Initial Testing (Week 1)
- [ ] Run in `DRY_RUN` mode for 3-5 days
- [ ] Review all log files
- [ ] Check trade journal entries
- [ ] Verify position sizing logic
- [ ] Test expiry day behavior (if applicable)

### 2. Paper Trading (Week 2-3)
- [ ] Enable `PAPER_TRADING = True`
- [ ] Monitor for 2 weeks
- [ ] Analyze win rate and P&L
- [ ] Fine-tune parameters if needed
- [ ] Test consecutive loss handling

### 3. Live Trading (Week 4+)
- [ ] Start with minimum capital
- [ ] Trade only 1-2 contracts
- [ ] Monitor closely for first week
- [ ] Gradually increase position size
- [ ] Keep detailed notes

---

## 🔧 Advanced Configuration

### Custom Greeks Thresholds
```python
# In src/config.py

# For aggressive scalping
IDEAL_DELTA_CALL = (0.50, 0.70)
IDEAL_GAMMA_MIN = 0.003
ENTRY_PROFIT_TARGET_PERCENT = 5.0  # Faster exits

# For conservative trading
IDEAL_DELTA_CALL = (0.40, 0.60)
RISK_PER_TRADE_OPTIMAL = 0.01  # 1% risk
MAX_TRADES_PER_DAY = 3
```

### Custom Time Windows
```python
# Avoid specific times
NO_TRADE_WINDOWS = [
    ("09:15", "09:25"),  # Opening volatility
    ("14:45", "15:30")   # Closing volatility
]
```

---

## 📚 Further Reading

### Documentation (in `docs/` folder)
1. **START_HERE.md** - Quick 5-minute overview
2. **DOCUMENTATION_INDEX.md** - Full documentation guide
3. **EXPIRY_ARCHITECTURE_DIAGRAM.md** - System flow charts

### OpenAlgo Integration
- OpenAlgo API documentation
- WebSocket protocol details
- Symbol format specifications

### Options Trading
- Greeks fundamentals (Delta, Gamma, Theta, Vega)
- Options pricing and IV
- Position sizing for options

---

## 🤝 Support & Community

### Getting Help
1. Check `docs/` folder for detailed guides
2. Review `logs/` for error messages
3. Enable DEBUG logging for troubleshooting
4. Consult OpenAlgo documentation

### Reporting Issues
Include:
- Error message from logs
- Configuration (hide API keys!)
- Steps to reproduce
- Expected vs actual behavior

---

## 📄 License & Disclaimer

### License
This project is provided as-is for educational purposes.

### Disclaimer
⚠️ **TRADING INVOLVES SUBSTANTIAL RISK OF LOSS**

- This software is for educational purposes only
- Not financial advice or trading recommendation
- Test thoroughly before using with real money
- Authors are not responsible for any trading losses
- Options trading is highly risky and not suitable for everyone
- Past performance does not guarantee future results

**USE AT YOUR OWN RISK**

---

## 📞 Contact

For issues or questions related to this implementation, refer to the documentation in `docs/` folder.

---

**Built with ❤️ for Professional Options Scalpers**

*ANGEL-X v1.0.0 - Greeks-Based Momentum Scalping System*
