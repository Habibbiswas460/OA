# Test Suite - ANGEL-X OpenAlgo Integration

All test files for ANGEL-X trading strategy.

## 📁 Test Files

### 1. **test_openalgo_integration.py** ⭐
Complete OpenAlgo API integration test with 7 steps:
- ✅ Fetch option chain
- ✅ Resolve symbols (CE/PE)
- ✅ Fetch Greeks (Delta, Gamma, Theta, Vega, IV)
- ✅ Fetch real-time quotes
- ✅ Execute single-leg order
- ✅ Execute multi-leg order
- ✅ Print execution summary

**Status: ✅ PASSING (100% success rate)**

### 2. **test_data_feed.py**
Tests data feed connectivity and tick reception.

### 3. **analyze_1hour_test.py**
Tests 1-hour candle analysis and signal generation.

### 4. **test_orders.py**
Tests order placement and management.

## 🚀 Running Tests

### Run All Tests (from project root):
```bash
source venv/bin/activate
python -m pytest tests/ -v
```

### Run Individual Tests:

**OpenAlgo Integration Test:**
```bash
source venv/bin/activate
python tests/test_openalgo_integration.py
```

**Data Feed Test:**
```bash
source venv/bin/activate
python tests/test_data_feed.py
```

## ✅ Latest Test Results

**test_openalgo_integration.py** (Dec 29, 2025 19:52):
```
Mode: ANALYZE
Total Orders: 3
Successful: 3 ✅
Failed: 0 ❌
Success Rate: 100.0%
```

**All APIs Working:**
- ✅ optionchain → ATM Strike: 25950.0
- ✅ optionsymbol → Symbol resolved
- ✅ optiongreeks → Greeks fetched
- ✅ quotes → LTP: ₹25942.10
- ✅ optionsorder → Order ID: 25122973207109
- ✅ optionsmultiorder → 2 legs executed

## 📋 Test Environment

**Required:**
- Virtual environment activated (`source venv/bin/activate`)
- OpenAlgo library installed (`pip install openalgo`)
- Config file with valid API key (`config/config.py`)

**Configuration:**
- OpenAlgo Host: http://habiqx.cc:5000
- API Key: Configured in config/config.py
- Mode: ANALYZE (safe testing with real API data)

## 🎯 Next Steps

1. All integration tests passing ✅
2. Ready for paper trading validation
3. After paper trading → Move to LIVE mode

**Note:** Always test in ANALYZE mode first before LIVE trading!
