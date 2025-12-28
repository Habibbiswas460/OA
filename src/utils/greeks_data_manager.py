"""
Greeks & OI Data Manager
Handles real-time Greeks and OI data fetching with rate limiting and caching
Designed to minimize API calls while maintaining data freshness
"""

import time
from threading import Lock, Thread
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from collections import defaultdict

from config import config
from src.utils.logger import StrategyLogger
from src.utils.options_helper import OptionsHelper

logger = StrategyLogger.get_logger(__name__)


@dataclass
class GreeksSnapshot:
    """Greeks data snapshot for a specific symbol at a point in time"""
    symbol: str
    timestamp: datetime
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float
    ltp: float
    bid: float
    ask: float
    volume: int
    oi: int
    oi_change: float
    
    def is_stale(self, max_age_seconds: int = 10) -> bool:
        """Check if data is stale"""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > max_age_seconds


@dataclass
class OptionChainSnapshot:
    """Option chain snapshot with multiple strikes"""
    underlying: str
    expiry_date: str
    timestamp: datetime
    strikes: Dict[str, Dict]  # strike_symbol -> data
    atm_strike: float
    
    def is_stale(self, max_age_seconds: int = 30) -> bool:
        """Check if chain data is stale"""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > max_age_seconds


class GreeksDataManager:
    """
    Manages real-time Greeks and OI data with intelligent caching and rate limiting
    
    Architecture:
    1. Active symbol tracking - only fetch for symbols we're monitoring
    2. Tiered caching - fast memory cache with TTL
    3. Batch fetching - get option chain once, extract multiple strikes
    4. Rate limiting - respect API limits
    5. Fallback - use last known values if API fails
    """
    
    def __init__(self):
        """Initialize Greeks data manager"""
        self.options_helper = OptionsHelper()
        
        # State management
        self.data_lock = Lock()
        self.active_symbols = set()  # Symbols we're actively tracking
        self.greeks_cache: Dict[str, GreeksSnapshot] = {}
        self.chain_cache: Dict[str, OptionChainSnapshot] = {}
        
        # Rolling state for delta tracking
        self.prev_greeks: Dict[str, GreeksSnapshot] = {}
        self.current_greeks: Dict[str, GreeksSnapshot] = {}
        
        # Rate limiting
        self.last_api_call = defaultdict(float)
        self.api_call_count = defaultdict(int)
        self.min_call_interval = getattr(config, 'GREEKS_API_MIN_INTERVAL', 1)
        
        # Background refresh
        self.refresh_thread = None
        self.refresh_running = False
        self.refresh_interval = getattr(config, 'GREEKS_REFRESH_INTERVAL', 5)
        
        # Performance tracking
        self.api_calls_total = 0
        self.cache_hits = 0
        self.cache_misses = 0
        
        logger.info("GreeksDataManager initialized")
    
    def start_background_refresh(self):
        """Start background thread for periodic data refresh"""
        if self.refresh_running:
            logger.warning("Background refresh already running")
            return
        
        self.refresh_running = True
        self.refresh_thread = Thread(target=self._refresh_loop, daemon=True)
        self.refresh_thread.start()
        logger.info(f"Started background Greeks refresh (interval: {self.refresh_interval}s)")
    
    def stop_background_refresh(self):
        """Stop background refresh thread"""
        self.refresh_running = False
        if self.refresh_thread:
            self.refresh_thread.join(timeout=5)
        logger.info("Stopped background Greeks refresh")
    
    def _refresh_loop(self):
        """Background loop for periodic data refresh"""
        while self.refresh_running:
            try:
                # Refresh all active symbols
                with self.data_lock:
                    active_symbols_copy = self.active_symbols.copy()
                
                for symbol in active_symbols_copy:
                    try:
                        self._fetch_greeks_for_symbol(symbol, force=False)
                    except Exception as e:
                        logger.error(f"Error refreshing Greeks for {symbol}: {e}")
                
                time.sleep(self.refresh_interval)
                
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")
                time.sleep(5)
    
    def track_symbol(self, symbol: str):
        """Add symbol to active tracking list"""
        with self.data_lock:
            if symbol not in self.active_symbols:
                self.active_symbols.add(symbol)
                logger.info(f"Now tracking Greeks for: {symbol}")
    
    def untrack_symbol(self, symbol: str):
        """Remove symbol from active tracking"""
        with self.data_lock:
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
                logger.info(f"Stopped tracking Greeks for: {symbol}")
    
    def get_greeks(self, symbol: str, exchange: str = "NFO", 
                   underlying_symbol: Optional[str] = None, 
                   underlying_exchange: Optional[str] = None,
                   force_refresh: bool = False) -> Optional[GreeksSnapshot]:
        """
        Get Greeks data for a symbol
        
        Args:
            symbol: Option symbol
            exchange: Option exchange
            underlying_symbol: Underlying symbol (for Greeks calculation)
            underlying_exchange: Underlying exchange
            force_refresh: Force API call even if cache is fresh
            
        Returns:
            GreeksSnapshot or None if fetch fails
        """
        # Check cache first
        if not force_refresh:
            with self.data_lock:
                if symbol in self.greeks_cache:
                    cached = self.greeks_cache[symbol]
                    if not cached.is_stale(max_age_seconds=getattr(config, 'GREEKS_CACHE_TTL', 10)):
                        self.cache_hits += 1
                        return cached
        
        # Cache miss or stale - fetch from API
        self.cache_misses += 1
        return self._fetch_greeks_for_symbol(symbol, exchange, underlying_symbol, underlying_exchange)
    
    def _fetch_greeks_for_symbol(self, symbol: str, exchange: str = "NFO",
                                  underlying_symbol: Optional[str] = None,
                                  underlying_exchange: Optional[str] = None,
                                  force: bool = True) -> Optional[GreeksSnapshot]:
        """Fetch Greeks from API with rate limiting"""
        
        # Rate limiting check
        now = time.time()
        last_call = self.last_api_call.get(symbol, 0)
        
        if not force and (now - last_call) < self.min_call_interval:
            # Too soon, return cached if available
            with self.data_lock:
                return self.greeks_cache.get(symbol)
        
        try:
            # Call API
            self.last_api_call[symbol] = now
            self.api_calls_total += 1
            self.api_call_count[symbol] += 1
            
            response = self.options_helper.get_option_greeks(
                symbol=symbol,
                exchange=exchange,
                underlying_symbol=underlying_symbol or config.PRIMARY_UNDERLYING,
                underlying_exchange=underlying_exchange or config.UNDERLYING_EXCHANGE
            )
            
            if not response or response.get('status') != 'success':
                logger.warning(f"Failed to fetch Greeks for {symbol}")
                # Return cached value if available
                with self.data_lock:
                    return self.greeks_cache.get(symbol)
            
            data = response.get('data', {})
            greeks_data = data.get('greeks', {})
            quote_data = data.get('quote', {})
            
            # Create snapshot
            snapshot = GreeksSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                delta=greeks_data.get('delta', 0.0),
                gamma=greeks_data.get('gamma', 0.0),
                theta=greeks_data.get('theta', 0.0),
                vega=greeks_data.get('vega', 0.0),
                iv=greeks_data.get('iv', 0.0),
                ltp=quote_data.get('ltp', 0.0),
                bid=quote_data.get('bid', 0.0),
                ask=quote_data.get('ask', 0.0),
                volume=quote_data.get('volume', 0),
                oi=quote_data.get('oi', 0),
                oi_change=quote_data.get('oi_change', 0.0)
            )
            
            # Update cache and rolling state
            with self.data_lock:
                # Move current to prev
                if symbol in self.current_greeks:
                    self.prev_greeks[symbol] = self.current_greeks[symbol]
                
                # Update current
                self.current_greeks[symbol] = snapshot
                self.greeks_cache[symbol] = snapshot
            
            logger.debug(f"Fetched Greeks for {symbol}: Delta={snapshot.delta:.4f}, Gamma={snapshot.gamma:.4f}, IV={snapshot.iv:.2f}")
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error fetching Greeks for {symbol}: {e}")
            # Return last known value if available
            with self.data_lock:
                return self.greeks_cache.get(symbol)
    
    def get_option_chain_data(self, underlying: str, expiry_date: str, 
                              exchange: Optional[str] = None, 
                              strike_count: int = 5,
                              force_refresh: bool = False) -> Optional[OptionChainSnapshot]:
        """
        Get option chain data (more efficient than individual Greeks calls)
        
        Args:
            underlying: Underlying symbol
            expiry_date: Expiry date
            exchange: Exchange
            strike_count: Number of strikes around ATM
            force_refresh: Force API call
            
        Returns:
            OptionChainSnapshot or None
        """
        cache_key = f"{underlying}_{expiry_date}"
        
        # Check cache
        if not force_refresh:
            with self.data_lock:
                if cache_key in self.chain_cache:
                    cached = self.chain_cache[cache_key]
                    if not cached.is_stale(max_age_seconds=getattr(config, 'CHAIN_CACHE_TTL', 30)):
                        self.cache_hits += 1
                        return cached
        
        # Fetch from API
        self.cache_misses += 1
        return self._fetch_option_chain(underlying, expiry_date, exchange, strike_count)
    
    def _fetch_option_chain(self, underlying: str, expiry_date: str,
                            exchange: Optional[str] = None, strike_count: int = 5) -> Optional[OptionChainSnapshot]:
        """Fetch option chain from API"""
        
        try:
            self.api_calls_total += 1
            
            response = self.options_helper.get_option_chain(
                underlying=underlying,
                expiry_date=expiry_date,
                exchange=exchange or config.UNDERLYING_EXCHANGE,
                strike_count=strike_count
            )
            
            if not response or response.get('status') != 'success':
                logger.warning(f"Failed to fetch option chain for {underlying}")
                return None
            
            data = response.get('data', {})
            
            snapshot = OptionChainSnapshot(
                underlying=underlying,
                expiry_date=expiry_date,
                timestamp=datetime.now(),
                strikes=data.get('strikes', {}),
                atm_strike=data.get('atm_strike', 0.0)
            )
            
            # Cache it
            cache_key = f"{underlying}_{expiry_date}"
            with self.data_lock:
                self.chain_cache[cache_key] = snapshot
            
            logger.info(f"Fetched option chain for {underlying} ({len(snapshot.strikes)} strikes)")
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            return None
    
    def get_rolling_greeks(self, symbol: str) -> Tuple[Optional[GreeksSnapshot], Optional[GreeksSnapshot]]:
        """
        Get current and previous Greeks for delta tracking
        
        Returns:
            (current_snapshot, prev_snapshot) or (None, None)
        """
        with self.data_lock:
            current = self.current_greeks.get(symbol)
            prev = self.prev_greeks.get(symbol)
            return current, prev
    
    def get_stats(self) -> Dict:
        """Get performance statistics"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'api_calls_total': self.api_calls_total,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': hit_rate,
            'active_symbols': len(self.active_symbols),
            'cached_symbols': len(self.greeks_cache)
        }
    
    def clear_stale_cache(self):
        """Remove stale entries from cache"""
        with self.data_lock:
            # Clear stale Greeks
            stale_symbols = [
                symbol for symbol, snapshot in self.greeks_cache.items()
                if snapshot.is_stale(max_age_seconds=60)
            ]
            for symbol in stale_symbols:
                del self.greeks_cache[symbol]
            
            # Clear stale chains
            stale_chains = [
                key for key, snapshot in self.chain_cache.items()
                if snapshot.is_stale(max_age_seconds=120)
            ]
            for key in stale_chains:
                del self.chain_cache[key]
            
            if stale_symbols or stale_chains:
                logger.debug(f"Cleared {len(stale_symbols)} stale Greeks, {len(stale_chains)} stale chains")
