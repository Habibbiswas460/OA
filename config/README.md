# Configuration Setup

## Quick Start

1. **Copy the example configuration:**
   ```bash
   cp config.example.py config.py
   ```

2. **Edit `config.py` with your credentials:**
   ```python
   OPENALGO_API_KEY = "your_actual_api_key_here"
   OPENALGO_HOST = "http://your_server:5000"
   OPENALGO_WS_URL = "ws://your_server:8765"
   OPENALGO_CLIENT_ID = "your_client_id"
   ```

3. **Review and adjust trading parameters:**
   - Capital and risk limits
   - Trading hours
   - Greeks thresholds
   - Position sizing rules

## Files

- **config.example.py** - Example configuration (safe to commit)
- **config.py** - Your actual configuration (DO NOT commit - contains API keys)
- **config.py is git-ignored** for security

## Important Notes

⚠️ **Security**:
- Never commit `config.py` to version control
- It contains sensitive API keys and credentials
- Always use `config.example.py` as template

✅ **Best Practice**:
```bash
# Set restrictive permissions
chmod 600 config.py
```

## Configuration Sections

1. **Logging** - Log levels and file settings
2. **OpenAlgo API** - API credentials and endpoints
3. **Symbols** - Trading instruments (NIFTY/BANKNIFTY)
4. **Time Windows** - Trading hours and restrictions
5. **Market Context** - IV and volatility thresholds
6. **Bias Engine** - Greeks-based bias thresholds
7. **Strike Selection** - Option health criteria
8. **Entry Engine** - Entry signal conditions
9. **Position Sizing** - Risk and capital management
10. **Execution** - Order placement rules
11. **Trade Management** - Exit triggers and Greeks-based stops
12. **Trap Detection** - Pattern detection settings
13. **Daily Risk** - Kill-switch and daily limits

## Environment Variables (Optional)

For additional security, use environment variables:

```python
import os

OPENALGO_API_KEY = os.getenv('OPENALGO_API_KEY', 'fallback_value')
OPENALGO_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5000')
```

Then set in your environment:
```bash
export OPENALGO_API_KEY="your_key_here"
export OPENALGO_HOST="http://your_server:5000"
```
