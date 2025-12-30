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
            
            # Extract Greeks data from response
            # OpenAlgo response format: {'status': 'success', 'data': {'greeks': {...}, 'quote': {...}}}
            data = response.get('data', {})
            greeks_data = data.get('greeks', {}) or response.get('greeks', {})
            quote_data = data.get('quote', {}) or response.get('quote', {})
            
            # Fallback: if greeks directly in response
            if not greeks_data:
                greeks_data = {
                    'delta': response.get('delta', 0.0),
                    'gamma': response.get('gamma', 0.0),
                    'theta': response.get('theta', 0.0),
                    'vega': response.get('vega', 0.0),
                    'rho': response.get('rho', 0.0),
                    'iv': response.get('iv', 0.0)
                }
            
            if not quote_data:
                quote_data = {
                    'ltp': response.get('ltp', 0.0),
                    'bid': response.get('bid', 0.0),
                    'ask': response.get('ask', 0.0),
                    'volume': response.get('volume', 0),
                    'oi': response.get('oi', 0),
                    'oi_change': response.get('oi_change', 0.0)
                }
            
            # Create snapshot with proper data extraction
            snapshot = GreeksSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                delta=float(greeks_data.get('delta', 0.0)) if greeks_data.get('delta') else 0.0,
                gamma=float(greeks_data.get('gamma', 0.0)) if greeks_data.get('gamma') else 0.0,
                theta=float(greeks_data.get('theta', 0.0)) if greeks_data.get('theta') else 0.0,
                vega=float(greeks_data.get('vega', 0.0)) if greeks_data.get('vega') else 0.0,
                iv=float(greeks_data.get('iv', 0.0)) if greeks_data.get('iv') else 0.0,
                ltp=float(quote_data.get('ltp', 0.0)) if quote_data.get('ltp') else 0.0,
                bid=float(quote_data.get('bid', 0.0)) if quote_data.get('bid') else 0.0,
                ask=float(quote_data.get('ask', 0.0)) if quote_data.get('ask') else 0.0,
                volume=int(quote_data.get('volume', 0)) if quote_data.get('volume') else 0,
                oi=int(quote_data.get('oi', 0)) if quote_data.get('oi') else 0,
                oi_change=float(quote_data.get('oi_change', 0.0)) if quote_data.get('oi_change') else 0.0
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
    
    # ============================================================================
    # GREEKS VALIDATION & ANALYSIS ENHANCEMENTS
    # ============================================================================
    
    def validate_option_health(self, greeks: GreeksSnapshot) -> Dict[str, bool]:
        """
        Validate Greeks health for trading
        
        Returns dict with validation results:
        - 'delta_ok': Delta within acceptable range
        - 'gamma_ok': Gamma is positive
        - 'theta_ok': Theta decay acceptable
        - 'vega_ok': Vega not too high
        - 'liquidity_ok': Volume/OI sufficient
        - 'spread_ok': Bid-ask spread reasonable
        """
        if not greeks:
            return {k: False for k in ['delta_ok', 'gamma_ok', 'theta_ok', 'vega_ok', 'liquidity_ok', 'spread_ok']}
        
        # Delta validation (0.2 to 0.8 for scalping)
        delta_ok = 0.2 <= abs(greeks.delta) <= 0.8
        
        # Gamma validation (positive, >= 0.001)
        gamma_ok = greeks.gamma > 0.0008
        
        # Theta validation (not too negative)
        theta_ok = greeks.theta > -100  # Avoid extreme theta decay
        
        # Vega validation (not too high for short-term scalp)
        vega_ok = greeks.vega < 50  # Limit vega exposure
        
        # Liquidity validation (volume + OI)
        liquidity_ok = (greeks.volume >= getattr(config, 'MIN_VOLUME_THRESHOLD', 100) or 
                        greeks.oi >= getattr(config, 'MIN_OI_THRESHOLD', 1000))
        
        # Spread validation
        if greeks.ltp > 0:
            spread_pct = ((greeks.ask - greeks.bid) / greeks.ltp * 100) if greeks.ask > greeks.bid else 100
            spread_ok = spread_pct <= getattr(config, 'MAX_SPREAD_PERCENT', 2.0)
        else:
            spread_ok = False
        
        return {
            'delta_ok': delta_ok,
            'gamma_ok': gamma_ok,
            'theta_ok': theta_ok,
            'vega_ok': vega_ok,
            'liquidity_ok': liquidity_ok,
            'spread_ok': spread_ok
        }
    
    def get_greeks_quality_score(self, greeks: GreeksSnapshot) -> float:
        """
        Calculate option quality score (0-100)
        Higher score = better option for trading
        """
        if not greeks:
            return 0.0
        
        score = 0.0
        
        # Delta score (0-25): prefer 0.3-0.7
        delta_abs = abs(greeks.delta)
        if 0.3 <= delta_abs <= 0.7:
            score += 25
        elif 0.2 <= delta_abs <= 0.8:
            score += 15
        elif delta_abs > 0:
            score += 5
        
        # Gamma score (0-25): higher is better
        if greeks.gamma > 0.003:
            score += 25
        elif greeks.gamma > 0.001:
            score += 15
        elif greeks.gamma > 0:
            score += 5
        
        # Theta score (0-20): moderate decay
        theta_abs = abs(greeks.theta)
        if 5 <= theta_abs <= 50:
            score += 20
        elif 1 <= theta_abs <= 100:
            score += 10
        elif theta_abs > 0:
            score += 5
        
        # Vega score (0-15): low vega exposure
        if greeks.vega < 10:
            score += 15
        elif greeks.vega < 30:
            score += 10
        elif greeks.vega < 50:
            score += 5
        
        # Liquidity score (0-15)
        if greeks.volume >= 1000 or greeks.oi >= 10000:
            score += 15
        elif greeks.volume >= 100 or greeks.oi >= 1000:
            score += 10
        elif greeks.volume > 0 or greeks.oi > 0:
            score += 5
        
        return min(100.0, score)
    
    def compare_greeks_change(self, current: Optional[GreeksSnapshot], 
                              prev: Optional[GreeksSnapshot]) -> Dict[str, float]:
        """
        Compare current vs previous Greeks
        
        Returns:
        - 'delta_change': Change in delta
        - 'gamma_change': Change in gamma
        - 'theta_change': Change in theta
        - 'vega_change': Change in vega
        - 'oi_change_pct': OI change percentage
        """
        if not current or not prev:
            return {}
        
        return {
            'delta_change': current.delta - prev.delta,
            'gamma_change': current.gamma - prev.gamma,
            'theta_change': current.theta - prev.theta,
            'vega_change': current.vega - prev.vega,
            'oi_change_pct': ((current.oi - prev.oi) / prev.oi * 100) if prev.oi > 0 else 0,
            'price_change': current.ltp - prev.ltp
        }
    
    def get_entry_greeks_signal(self, greeks: GreeksSnapshot, option_type: str = "CE") -> Dict[str, bool]:
        """
        Generate entry signal based on Greeks
        
        Args:
            greeks: Greeks snapshot
            option_type: "CE" or "PE"
            
        Returns:
            {'delta_signal': bool, 'gamma_signal': bool, 'entry_ready': bool}
        """
        if not greeks or greeks.ltp == 0:
            return {'delta_signal': False, 'gamma_signal': False, 'entry_ready': False}
        
        # For CE: prefer positive delta rising
        # For PE: prefer negative delta falling
        if option_type == "CE":
            delta_signal = 0.3 <= greeks.delta <= 0.8  # Positive delta preferred
        else:  # PE
            delta_signal = -0.8 <= greeks.delta <= -0.3  # Negative delta preferred
        
        # Gamma should be positive and reasonable
        gamma_signal = 0.0008 <= greeks.gamma <= 0.01
        
        # Entry ready if both delta and gamma are good
        entry_ready = delta_signal and gamma_signal
        
        return {
            'delta_signal': delta_signal,
            'gamma_signal': gamma_signal,
            'entry_ready': entry_ready,
            'quality_score': self.get_greeks_quality_score(greeks)
        }
    
    def get_rolling_iv_trend(self, symbol: str, window: int = 5) -> Optional[str]:
        """
        Determine IV trend (RISING, FALLING, STABLE)
        
        Note: Requires historical tracking of IV changes
        """
        with self.data_lock:
            current = self.current_greeks.get(symbol)
            prev = self.prev_greeks.get(symbol)
        
        if not current or not prev or current.iv == 0:
            return None
        
        iv_change = current.iv - prev.iv
        
        if iv_change > 1.0:
            return "RISING"
        elif iv_change < -1.0:
            return "FALLING"
        else:
            return "STABLE"


