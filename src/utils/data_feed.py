"""
Data Feed Module
Handles WebSocket connections, LTP updates, quote data, and market depth using OpenAlgo
Optimized for local network resilience with auto-reconnection and retry logic
"""

import json
import time
from threading import Thread, Lock, Event
from datetime import datetime
from openalgo import api
from config import config
from src.utils.logger import StrategyLogger
logger = StrategyLogger.get_logger(__name__)


class DataFeed:
    """Manages real-time market data feed via WebSocket"""
    
    # Reconnection parameters
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_DELAY = 2  # seconds
    PING_INTERVAL = 30  # seconds
    PING_TIMEOUT = 5  # seconds
    
    def __init__(self):
        self.ws = None
        self.connected = False
        self.subscribed_symbols = set()
        self.subscribed_instruments = []  # Store for re-subscription
        
        # Thread-safe data storage
        self.data_lock = Lock()
        self.ltp_data = {}
        self.quote_data = {}
        self.depth_data = {}
        self.tick_data = []
        
        # Callbacks
        self.on_tick_callbacks = []
        self.on_quote_callbacks = []
        self.on_depth_callbacks = []
        
        # Reconnection state
        self.reconnect_thread = None
        self.stop_reconnect = Event()
        self.last_tick_received = time.time()
        
        logger.info("DataFeed initialized with auto-reconnection support")
    
    def connect(self, retry_count=0):
        """Establish WebSocket connection using OpenAlgo with retry logic"""
        try:
            if retry_count > self.MAX_RECONNECT_ATTEMPTS:
                logger.error("Max reconnection attempts exceeded")
                return False
            
            logger.info(f"Connecting to WebSocket (attempt {retry_count + 1}/{self.MAX_RECONNECT_ATTEMPTS})...")
            
            # Initialize OpenAlgo client with WebSocket
            self.client = api(
                api_key=config.OPENALGO_API_KEY,
                host=config.OPENALGO_HOST,
                ws_url=config.OPENALGO_WS_URL
            )
            
            # Connect to WebSocket (OpenAlgo connect() doesn't accept timeout parameter)
            self.client.connect()
            self.connected = True
            self.stop_reconnect.clear()
            
            logger.info("WebSocket connected successfully")
            
            # Start health check thread
            if self.reconnect_thread is None or not self.reconnect_thread.is_alive():
                self.reconnect_thread = Thread(
                    target=self._health_check_loop,
                    daemon=True,
                    name="WebSocket-HealthCheck"
                )
                self.reconnect_thread.start()
            
            return True
            
        except TimeoutError:
            logger.warning(f"Connection timeout (attempt {retry_count + 1})")
            time.sleep(self.RECONNECT_DELAY)
            return self.connect(retry_count + 1)
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e} (attempt {retry_count + 1})")
            time.sleep(self.RECONNECT_DELAY)
            return self.connect(retry_count + 1)
    
    def _health_check_loop(self):
        """Periodically check WebSocket health and reconnect if needed"""
        while not self.stop_reconnect.is_set():
            try:
                time.sleep(self.PING_INTERVAL)
                
                if not self.connected:
                    logger.warning("WebSocket disconnected, attempting reconnect...")
                    self.reconnect()
                
                # Check if ticks are being received
                time_since_last_tick = time.time() - self.last_tick_received
                if time_since_last_tick > 60 and self.subscribed_symbols:
                    logger.warning(f"No ticks for {time_since_last_tick:.0f}s, checking connection...")
                    if not self._is_connection_alive():
                        logger.warning("Connection appears dead, reconnecting...")
                        self.reconnect()
                        
            except Exception as e:
                logger.error(f"Health check error: {e}")
                time.sleep(self.RECONNECT_DELAY)
    
    def _is_connection_alive(self):
        """Check if WebSocket connection is alive"""
        try:
            if not hasattr(self, 'client') or not self.client:
                return False
            # Try to access a simple method to verify connection
            return getattr(self.client, '_connected', False)
        except:
            return False
    
    def reconnect(self):
        """Attempt to reconnect to WebSocket"""
        try:
            logger.info("Attempting to reconnect...")
            self.disconnect()
            time.sleep(self.RECONNECT_DELAY)
            
            if self.connect():
                # Re-subscribe to all previously subscribed symbols
                if self.subscribed_symbols:
                    logger.info(f"Re-subscribing to {len(self.subscribed_symbols)} symbols...")
                    self._resubscribe_all()
                return True
            else:
                logger.error("Reconnection failed")
                return False
                
        except Exception as e:
            logger.error(f"Reconnection error: {e}")
            return False
    
    def _resubscribe_all(self):
        """Re-subscribe to all previously subscribed symbols"""
        try:
            if not self.subscribed_instruments:
                logger.warning("No instruments to re-subscribe")
                return
            
            logger.info(f"Re-subscribing to {len(self.subscribed_instruments)} instruments...")
            
            # Re-subscribe to LTP for stored instruments
            success = self.subscribe_ltp(self.subscribed_instruments, retry_count=0)
            if success:
                logger.info("Re-subscription successful")
            else:
                logger.warning("Re-subscription failed")
                
        except Exception as e:
            logger.error(f"Re-subscription error: {e}")
    
    def disconnect(self):
        """Close WebSocket connection gracefully"""
        try:
            self.stop_reconnect.set()
            
            if hasattr(self, 'client') and self.client:
                self.client.disconnect()
            self.connected = False
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
    
    def subscribe_ltp(self, instruments, callback=None, retry_count=0):
        """
        Subscribe to LTP updates with retry logic
        
        Args:
            instruments: List of dicts [{'exchange': 'NSE', 'symbol': 'RELIANCE'}, ...]
            callback: Callback function for LTP updates
            retry_count: Internal retry counter
        """
        try:
            if not self.connected:
                logger.warning("Not connected, attempting to connect first...")
                if not self.connect():
                    return False
            
            if callback:
                self.on_tick_callbacks.append(callback)
            
            self.client.subscribe_ltp(
                instruments,
                on_data_received=self._process_tick
            )
            
            # Store instruments for re-subscription after reconnect
            self.subscribed_instruments = instruments
            
            for inst in instruments:
                self.subscribed_symbols.add(f"{inst['exchange']}:{inst['symbol']}")
            
            logger.info(f"Subscribed to LTP: {len(instruments)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"LTP subscription failed: {e}")
            if retry_count < 3:
                logger.info(f"Retrying LTP subscription (attempt {retry_count + 1}/3)...")
                time.sleep(self.RECONNECT_DELAY)
                return self.subscribe_ltp(instruments, callback, retry_count + 1)
            return False
    
    def subscribe_quote(self, instruments, callback=None):
        """Subscribe to quote updates"""
        try:
            if callback:
                self.on_quote_callbacks.append(callback)
            
            self.client.subscribe_quote(
                instruments,
                on_data_received=self._process_tick
            )
            
            logger.info(f"Subscribed to quotes: {len(instruments)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"Quote subscription failed: {e}")
            return False
    
    def subscribe_depth(self, instruments, callback=None):
        """Subscribe to market depth updates"""
        try:
            if callback:
                self.on_depth_callbacks.append(callback)
            
            self.client.subscribe_depth(
                instruments,
                on_data_received=self._process_tick
            )
            
            logger.info(f"Subscribed to depth: {len(instruments)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"Depth subscription failed: {e}")
            return False
    
    def unsubscribe_ltp(self, instruments):
        """Unsubscribe from LTP updates"""
        try:
            self.client.unsubscribe_ltp(instruments)
            
            for inst in instruments:
                self.subscribed_symbols.discard(f"{inst['exchange']}:{inst['symbol']}")
            
            logger.info(f"Unsubscribed from LTP: {len(instruments)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"LTP unsubscription failed: {e}")
            return False
    
    def unsubscribe_quote(self, instruments):
        """Unsubscribe from quote updates"""
        try:
            self.client.unsubscribe_quote(instruments)
            logger.info(f"Unsubscribed from quotes: {len(instruments)} symbols")
            return True
        except Exception as e:
            logger.error(f"Quote unsubscription failed: {e}")
            return False
    
    def unsubscribe_depth(self, instruments):
        """Unsubscribe from depth updates"""
        try:
            self.client.unsubscribe_depth(instruments)
            logger.info(f"Unsubscribed from depth: {len(instruments)} symbols")
            return True
        except Exception as e:
            logger.error(f"Depth unsubscription failed: {e}")
            return False
    
    def _on_connect(self, ws, response):
        """WebSocket connection callback"""
        logger.info("WebSocket connection established")
        self.connected = True
    
    def _on_message(self, ws, message):
        """WebSocket message callback"""
        try:
            data = json.loads(message)
            self._process_tick(data)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _on_error(self, ws, error):
        """WebSocket error callback"""
        logger.error(f"WebSocket error: {error}")
    
    def _on_close(self, ws):
        """WebSocket close callback"""
        logger.warning("WebSocket connection closed")
        self.connected = False
        
        if config.WEBSOCKET_ENABLED:
            logger.info(f"Reconnecting in {config.WEBSOCKET_RECONNECT_DELAY} seconds...")
            time.sleep(config.WEBSOCKET_RECONNECT_DELAY)
            self.connect()
    
    def _process_tick(self, tick):
        """Process incoming tick data"""
        try:
            symbol = tick.get('symbol')
            if not symbol:
                return
            
            with self.data_lock:
                # Update LTP
                if 'ltp' in tick:
                    self.ltp_data[symbol] = {
                        'price': tick['ltp'],
                        'timestamp': datetime.now()
                    }
                
                # Update quote
                if 'bid' in tick or 'ask' in tick:
                    self.quote_data[symbol] = {
                        'bid': tick.get('bid'),
                        'ask': tick.get('ask'),
                        'bid_qty': tick.get('bid_qty'),
                        'ask_qty': tick.get('ask_qty'),
                        'timestamp': datetime.now()
                    }
                
                # Update depth
                if 'depth' in tick:
                    self.depth_data[symbol] = tick['depth']
                
                # Store tick
                self.tick_data.append(tick)
                if len(self.tick_data) > 1000:  # Keep last 1000 ticks
                    self.tick_data = self.tick_data[-1000:]
            
            # Call registered callbacks
            self._trigger_callbacks(tick)
            
            logger.log_market_data(f"{symbol}: {tick.get('ltp')}")
            
        except Exception as e:
            logger.error(f"Error processing tick: {e}")
    
    def _trigger_callbacks(self, tick):
        """Trigger registered callbacks"""
        try:
            for callback in self.on_tick_callbacks:
                callback(tick)
            
            if 'bid' in tick or 'ask' in tick:
                for callback in self.on_quote_callbacks:
                    callback(tick)
            
            if 'depth' in tick:
                for callback in self.on_depth_callbacks:
                    callback(tick)
                    
        except Exception as e:
            logger.error(f"Error triggering callbacks: {e}")
    
    def register_callback(self, callback_type, callback_func):
        """Register callback function for data updates"""
        if callback_type == 'tick':
            self.on_tick_callbacks.append(callback_func)
        elif callback_type == 'quote':
            self.on_quote_callbacks.append(callback_func)
        elif callback_type == 'depth':
            self.on_depth_callbacks.append(callback_func)
        else:
            logger.warning(f"Unknown callback type: {callback_type}")
    
    def get_ltp(self, symbol):
        """Get last traded price for symbol"""
        with self.data_lock:
            return self.ltp_data.get(symbol, {}).get('price')
    
    def get_quote(self, symbol):
        """Get quote data for symbol"""
        with self.data_lock:
            return self.quote_data.get(symbol)
    
    def get_depth(self, symbol):
        """Get market depth for symbol"""
        with self.data_lock:
            return self.depth_data.get(symbol)
    
    def is_connected(self):
        """Check if WebSocket is connected"""
        return self.connected
