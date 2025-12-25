# Local Network Optimization Guide

## Overview
The ANGEL-X strategy has been optimized for local network resilience to handle common connectivity issues that may arise when running on a local machine.

## Optimizations Implemented

### 1. **WebSocket Auto-Reconnection** (`src/utils/data_feed.py`)
- **Auto-reconnect enabled** with configurable retry attempts
- **Health check loop** monitors WebSocket connection every 30 seconds
- **Tick timeout detection** alerts if no data received for 60+ seconds
- **Automatic re-subscription** to symbols after reconnection
- **Configurable delays** between reconnection attempts

**Config Parameters:**
```python
WEBSOCKET_RECONNECT_ENABLED = True
WEBSOCKET_MAX_RECONNECT_ATTEMPTS = 5
WEBSOCKET_RECONNECT_DELAY = 2  # seconds
WEBSOCKET_PING_INTERVAL = 30  # seconds
WEBSOCKET_TICK_TIMEOUT = 60  # seconds
```

### 2. **API Call Retry Logic** (`src/core/order_manager.py`)
- **Automatic retry** on connection errors and timeouts
- **Configurable timeout** for API requests (15 seconds default)
- **Exponential backoff** between retries
- **Error tracking** for health monitoring

**Config Parameters:**
```python
API_REQUEST_TIMEOUT = 15  # seconds
API_RETRY_ATTEMPTS = 3  # number of retries
API_RETRY_DELAY = 1  # seconds between retries
```

### 3. **Network Health Monitoring** (`src/utils/network_resilience.py`)
- **Real-time monitoring** of API calls and WebSocket ticks
- **Health status tracking** including error rates
- **Alert generation** for connectivity issues
- **Automatic logging** of network events

**Monitoring Metrics:**
- API call count and error rate
- WebSocket reconnection count
- Time since last tick received
- Active alerts and recent issues

### 4. **Graceful Degradation**
- Strategy **continues operating** during brief connectivity interruptions
- **No manual intervention** required for temporary network issues
- **Automatic recovery** once connection restored
- **Clear logging** of all connection events

## Monitoring Health During Live Trading

### Check Network Status in Logs
The strategy logs network events at startup:
```
[INFO] Network monitoring started - monitoring connectivity and data flow
[INFO] WebSocket connected successfully
[INFO] Subscribed to LTP: 1 symbols
```

### Watch for These Warnings
- `WebSocket disconnected, attempting reconnect...` → Connection lost, auto-reconnecting
- `No ticks for XXs` → Data flow interrupted, checking connection
- `API error rate high: X%` → Many API failures, check network quality

### Monitor Health at Shutdown
When strategy stops, summary is printed:
```
Network Health Summary:
  API Calls: 1234
  API Errors: 5 (0.4%)
  WebSocket Reconnects: 0
  Alerts: 0
```

## Troubleshooting Common Issues

### Issue: "WebSocket connection failed"
**Cause:** Network unavailable or OpenAlgo server unreachable
**Solution:**
1. Check internet connection: `ping 16.16.70.80`
2. Check OpenAlgo server status: `curl http://16.16.70.80:5000`
3. Verify API credentials in `config/config.py`

### Issue: "Max reconnection attempts exceeded"
**Cause:** Persistent network or server issues
**Solution:**
1. Wait 2-3 minutes for network recovery
2. Restart the strategy: `python main.py`
3. Check OpenAlgo server logs

### Issue: "No ticks for 60+ seconds"
**Cause:** WebSocket connection alive but not receiving data
**Solution:**
1. Check subscription: Strategy auto-resubscribes on reconnect
2. Wait 1-2 minutes for data to resume
3. If persists, restart strategy

### Issue: "API error rate high"
**Cause:** Multiple API call failures (order placement, expiry check, etc.)
**Solution:**
1. Check internet connection quality
2. Reduce network load (close other apps)
3. Check OpenAlgo server performance

## Configuration Tuning

### For More Aggressive Reconnection (Fast Recovery)
```python
# In config/config.py
WEBSOCKET_RECONNECT_DELAY = 1  # Try faster
WEBSOCKET_MAX_RECONNECT_ATTEMPTS = 10  # Try more times
```

### For More Conservative Approach (Fewer Retries)
```python
# In config/config.py
WEBSOCKET_RECONNECT_DELAY = 5  # Wait longer
WEBSOCKET_MAX_RECONNECT_ATTEMPTS = 3  # Try fewer times
```

### For High-Latency Networks
```python
# In config/config.py
API_REQUEST_TIMEOUT = 30  # Increase timeout
WEBSOCKET_TICK_TIMEOUT = 120  # More patience for ticks
```

## Network Best Practices for Tomorrow (Dec 26)

1. **Run on Stable Connection**
   - Use WiFi 5GHz or wired Ethernet
   - Close other bandwidth-heavy applications
   - Disable VPN if possible (unless required)

2. **Monitor First Hour**
   - Keep terminal visible during 09:15-10:00
   - Watch for any reconnection messages
   - Have phone ready to restart if needed

3. **Check Logs Regularly**
   - `tail -f logs/angel_x_*.log` to watch real-time logs
   - Look for error patterns
   - Note any repeated issues

4. **Have Fallback Plan**
   - If strategy doesn't connect by 09:20, restart it
   - If frequent disconnects occur, switch to wired connection
   - If continues, manually pause and investigate

## Technical Details

### Connection Flow
```
1. Strategy start
   ↓
2. Network monitor starts (health checking)
   ↓
3. WebSocket connect (with retry logic)
   ↓
4. Subscribe to NIFTY LTP
   ↓
5. Health check loop monitors connection every 30s
   ↓
6. If disconnected: Auto-reconnect + resubscribe
   ↓
7. Strategy continues trading once reconnected
```

### Error Handling Hierarchy
```
Transient Error (timeout)
  ↓ Retry with backoff
  ↓ Success → Continue
  ↓ Failure after max retries → Log alert

Connection Error (disconnected)
  ↓ Trigger auto-reconnect
  ↓ Success → Resubscribe
  ↓ Failure → Log alert + continue monitoring

Persistent Error (server down)
  ↓ Keep retrying
  ↓ Alert user in logs
  ↓ Manual intervention needed
```

## Logs Location
All events logged to: `./logs/angel_x_YYYY-MM-DD.log`

Key sections to review:
- `[DataFeed]` - WebSocket connection events
- `[OrderManager]` - API call retries and results
- `[NetworkMonitor]` - Network health alerts

---

**Ready for live trading tomorrow!** Strategy is now resilient to common local network issues. 🚀
