"""
ANGEL-X Bias Engine (Market State Engine)
Determines market permission: BULLISH (CALL trade ok) | BEARISH (PUT trade ok) | NO_TRADE
Based on: Delta, Gamma, OI, Volume, IV, Price action
"""

import time
from datetime import datetime
from threading import Thread, Lock
from enum import Enum
from typing import Dict
from dataclasses import dataclass
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class BiasState(Enum):
    """Market bias states"""
    BULLISH = "BULLISH"      # Delta ≥0.45, Gamma rising, OI↑+LTP↑, Vol↑
    BEARISH = "BEARISH"      # Delta ≤-0.45, Gamma rising, OI↑+LTP↑, Vol↑
    NO_TRADE = "NO_TRADE"    # Weak direction, flat gamma, mismatched OI
    UNKNOWN = "UNKNOWN"


@dataclass
class BiasMetrics:
    """Bias calculation metrics"""
    delta_signal: float
    gamma_signal: float
    oi_volume_align: float
    iv_environment: float
    market_structure: str
    confidence: float


class BiasEngine:
    """
    ANGEL-X Market State Engine (Bias Detection)
    
    Detects MARKET PERMISSION for trading, not entry signals.
    Bias is "gate keeper" - tells which side is allowed.
    """
    
    def __init__(self, data_feed=None):
        """Initialize bias engine"""
        self.data_feed = data_feed
        self.bias_lock = Lock()
        
        # Current state
        self.current_bias = BiasState.UNKNOWN
        self.bias_confidence = 0.0
        self.last_bias_update = None
        
        # Historical data for trend detection
        self.price_history = []  # [(timestamp, price), ...]
        self.delta_history = []  # [(timestamp, delta), ...]
        self.gamma_history = []  # [(timestamp, gamma), ...]
        self.oi_history = []     # [(timestamp, oi, oi_change), ...]
        self.volume_history = [] # [(timestamp, volume), ...]
        self.iv_history = []     # [(timestamp, iv), ...]
        
        # Keep last 100 candles
        self.max_history = 100
        
        # Bias metrics
        self.metrics = {
            'delta_signal': 0.0,
            'gamma_signal': 0.0,
            'oi_volume_align': 0.0,
            'iv_environment': 0.0,
            'market_structure': 'UNKNOWN',
            'confidence': 0.0
        }
        
        # Background update thread
        self.running = False
        self.update_thread = None
        
        logger.info("BiasEngine (ANGEL-X) initialized")
    
    def start(self):
        """Start background bias updates"""
        self.running = True
        self.update_thread = Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        logger.info("BiasEngine started")
    
    def stop(self):
        """Stop bias engine"""
        self.running = False
        if self.update_thread:
            self.update_thread.join()
        logger.info("BiasEngine stopped")
    
    def _update_loop(self):
        """Background loop for periodic bias updates"""
        while self.running:
            try:
                time.sleep(config.BIAS_UPDATE_INTERVAL)
            except Exception as e:
                logger.error(f"Error in bias update loop: {e}")
    
    def update_with_greeks_data(
        self,
        current_delta: float,
        prev_delta: float,
        current_gamma: float,
        prev_gamma: float,
        current_oi: int,
        current_oi_change: float,
        current_ltp: float,
        prev_ltp: float,
        current_volume: int,
        prev_volume: int,
        current_iv: float,
        prev_iv: float
    ):
        """
        Update bias with latest Greeks and market data
        
        Core ANGEL-X logic:
        - BULLISH: Delta ≥0.45 + Gamma rising + OI↑+LTP↑ + Volume↑
        - BEARISH: Delta ≤-0.45 + Gamma rising + OI↑+LTP↑ + Volume↑
        - NO_TRADE: Weak delta, flat gamma, OI-price mismatch, IV crushing
        """
        
        now = datetime.now()
        
        # Store history (keep last N candles)
        self.delta_history.append((now, current_delta))
        self.gamma_history.append((now, current_gamma))
        self.oi_history.append((now, current_oi, current_oi_change))
        self.price_history.append((now, current_ltp))
        self.volume_history.append((now, current_volume))
        self.iv_history.append((now, current_iv))
        
        # Trim history
        if len(self.delta_history) > self.max_history:
            self.delta_history = self.delta_history[-self.max_history:]
        if len(self.gamma_history) > self.max_history:
            self.gamma_history = self.gamma_history[-self.max_history:]
        if len(self.oi_history) > self.max_history:
            self.oi_history = self.oi_history[-self.max_history:]
        if len(self.price_history) > self.max_history:
            self.price_history = self.price_history[-self.max_history:]
        if len(self.volume_history) > self.max_history:
            self.volume_history = self.volume_history[-self.max_history:]
        if len(self.iv_history) > self.max_history:
            self.iv_history = self.iv_history[-self.max_history:]
        
        with self.bias_lock:
            # 1. Delta Signal Analysis
            delta_signal = self._analyze_delta_signal(current_delta)
            
            # 2. Gamma Momentum (is acceleration happening?)
            gamma_rising = self._is_gamma_rising(current_gamma, prev_gamma)
            
            # 3. OI + Volume + Price Alignment
            oi_vol_align = self._check_oi_volume_alignment(
                current_oi, current_oi_change, current_ltp, prev_ltp, 
                current_volume, prev_volume
            )
            
            # 4. IV Environment
            iv_health = self._check_iv_environment(current_iv, prev_iv)
            
            # 5. Market Structure (trend)
            market_structure = self._detect_market_structure()
            
            # Store metrics
            self.metrics = {
                'delta_signal': delta_signal,
                'gamma_signal': 1.0 if gamma_rising else 0.0,
                'oi_volume_align': oi_vol_align,
                'iv_environment': iv_health,
                'market_structure': market_structure,
                'confidence': 0.0
            }
            
            # Determine bias (rule-based)
            bias, confidence = self._determine_bias(
                delta_signal=delta_signal,
                gamma_rising=gamma_rising,
                oi_vol_align=oi_vol_align,
                iv_health=iv_health,
                market_structure=market_structure
            )
            
            self.current_bias = bias
            self.bias_confidence = confidence
            self.metrics['confidence'] = confidence
            self.last_bias_update = now
            
            logger.info(
                f"Bias: {bias.value} (confidence: {confidence:.0f}%) | "
                f"Δ: {delta_signal:+.2f}, Γ: {'↑' if gamma_rising else '→'}, "
                f"OI-V: {oi_vol_align:.2f}, IV: {iv_health:.2f}, Structure: {market_structure}"
            )
            
            return bias
    
    def _analyze_delta_signal(self, current_delta: float) -> float:
        """
        Analyze delta to determine directional signal
        
        Returns:
            +1 = Strong bullish (delta ≥ 0.45)
            0 = Weak/neutral (0.30-0.45)
            -1 = Strong bearish (delta ≤ -0.45)
        """
        if current_delta >= config.BULLISH_DELTA_MIN:
            return 1.0  # Strong bullish
        elif current_delta <= config.BEARISH_DELTA_MAX:
            return -1.0  # Strong bearish
        elif abs(current_delta) >= config.NO_TRADE_DELTA_WEAK:
            return 0.0  # Weak
        else:
            return 0.0  # Very weak, no permission
    
    def _is_gamma_rising(self, current_gamma: float, prev_gamma: float) -> bool:
        """
        Check if gamma is rising (acceleration continuing)
        
        Gamma rising = momentum continuing = edge alive
        Gamma flat/falling = momentum dying = no edge
        """
        if len(self.gamma_history) < 3:
            return False
        
        # Check last 3 gamma readings
        recent_gammas = [g[1] for g in self.gamma_history[-3:]]
        
        # Trend: should be rising or at least stable
        gamma_trend = recent_gammas[-1] - recent_gammas[0]
        
        # Gamma rising if change > threshold
        is_rising = gamma_trend > config.NO_TRADE_GAMMA_FLAT
        
        return is_rising
    
    def _check_oi_volume_alignment(
        self,
        current_oi: int,
        current_oi_change: float,
        current_ltp: float,
        prev_ltp: float,
        current_volume: int,
        prev_volume: int
    ) -> float:
        """
        Check if OI, Volume, and Price are moving together
        
        GOOD alignment (1.0):
            OI ↑ + LTP ↑ + Volume ↑ = Fresh accumulation
        
        BAD alignment (0.0):
            OI ↑ but LTP flat = Operator adjustment (trap)
            OI ↓ = Positions closing (move dying)
        """
        alignment_score = 0.0
        
        # OI movement
        oi_rising = current_oi_change > 0
        
        # Price movement
        ltp_rising = current_ltp > prev_ltp
        
        # Volume movement
        vol_rising = current_volume > prev_volume
        
        # Check alignment
        if oi_rising:
            if ltp_rising and vol_rising:
                alignment_score = 1.0  # Perfect alignment
            elif ltp_rising or vol_rising:
                alignment_score = 0.5  # Partial alignment
            else:
                alignment_score = -1.0  # OI trap (no price/vol follow)
        else:
            # OI not rising = positions closing or flat
            alignment_score = 0.0
        
        return alignment_score
    
    def _check_iv_environment(self, current_iv: float, prev_iv: float) -> float:
        """
        Check IV health
        
        GOOD (1.0): IV in safe zone, not crushing
        BAD (-1.0): IV collapsing, premium melt risk
        """
        # IV change percent
        iv_change_pct = ((current_iv - prev_iv) / prev_iv * 100) if prev_iv > 0 else 0
        
        # IV range check
        if config.IV_SAFE_ZONE[0] <= current_iv <= config.IV_SAFE_ZONE[1]:
            iv_health = 0.5  # Optimal zone
        elif current_iv < config.IV_EXTREMELY_LOW_THRESHOLD:
            iv_health = -0.5  # Too low, theta eats
        elif current_iv > config.IV_EXTREMELY_HIGH_THRESHOLD:
            iv_health = -0.3  # Too high, only scalp quick
        else:
            iv_health = 0.2  # Acceptable
        
        # IV crush (sharp drop) = danger
        if iv_change_pct < config.REJECT_IV_DROP_PERCENT:
            iv_health -= 0.5  # Penalize crush
        
        return max(-1.0, min(1.0, iv_health))
    
    def _detect_market_structure(self) -> str:
        """
        Detect micro-market structure for context
        
        HH-HL = Bullish (higher highs, higher lows)
        LL-LH = Bearish (lower lows, lower highs)
        SIDEWAYS = Choppy
        """
        if len(self.price_history) < 5:
            return "UNKNOWN"
        
        recent_prices = [p[1] for p in self.price_history[-5:]]
        
        # Find highs and lows in last 5 candles
        recent_high = max(recent_prices)
        recent_low = min(recent_prices)
        
        # Compare to prior period
        prior_prices = [p[1] for p in self.price_history[-10:-5]]
        if not prior_prices:
            return "UNKNOWN"
        
        prior_high = max(prior_prices)
        prior_low = min(prior_prices)
        
        # Detect pattern
        if recent_high > prior_high and recent_low > prior_low:
            return "HH-HL"  # Bullish
        elif recent_high < prior_high and recent_low < prior_low:
            return "LL-LH"  # Bearish
        else:
            return "SIDEWAYS"  # Choppy
    
    def _determine_bias(
        self,
        delta_signal: float,
        gamma_rising: bool,
        oi_vol_align: float,
        iv_health: float,
        market_structure: str
    ) -> tuple:
        """
        Main rule-based bias determination
        
        BULLISH: delta ≥0.45 + gamma rising + oi-vol aligned + iv ok
        BEARISH: delta ≤-0.45 + gamma rising + oi-vol aligned + iv ok
        NO_TRADE: anything else
        """
        
        confidence = 0.0
        bias = BiasState.NO_TRADE
        
        # BULLISH conditions
        if delta_signal > 0:  # Delta bullish
            if gamma_rising and oi_vol_align >= 0:  # Gamma + OI alignment
                if iv_health >= -0.3:  # IV not crushing
                    bias = BiasState.BULLISH
                    confidence = 85.0
                else:
                    bias = BiasState.BULLISH
                    confidence = 60.0  # IV concern but still bullish
            else:
                bias = BiasState.NO_TRADE
                confidence = 40.0
        
        # BEARISH conditions
        elif delta_signal < 0:  # Delta bearish
            if gamma_rising and oi_vol_align >= 0:  # Gamma + OI alignment
                if iv_health >= -0.3:  # IV not crushing
                    bias = BiasState.BEARISH
                    confidence = 85.0
                else:
                    bias = BiasState.BEARISH
                    confidence = 60.0  # IV concern but still bearish
            else:
                bias = BiasState.NO_TRADE
                confidence = 40.0
        
        # Weak delta = no permission
        else:
            bias = BiasState.NO_TRADE
            confidence = 20.0
        
        # Apply market structure modifier
        if market_structure == "SIDEWAYS":
            confidence *= 0.7  # Less confident in sideways
        
        return bias, confidence
    
    def get_bias(self) -> BiasState:
        """Get current bias state"""
        with self.bias_lock:
            return self.current_bias
    
    def get_confidence(self) -> float:
        """Get bias confidence (0-100)"""
        with self.bias_lock:
            return self.bias_confidence
    
    def get_metrics(self) -> Dict:
        """Get bias calculation metrics"""
        with self.bias_lock:
            return self.metrics.copy()
    
    def is_trade_allowed(self, desired_side: str) -> bool:
        """
        Check if trade is allowed based on current bias
        
        Args:
            desired_side: 'CALL' or 'PUT'
        
        Returns:
            True if side aligns with bias, False otherwise
        """
        bias = self.get_bias()
        
        if bias == BiasState.BULLISH:
            return desired_side.upper() == "CALL"
        elif bias == BiasState.BEARISH:
            return desired_side.upper() == "PUT"
        else:
            return False
