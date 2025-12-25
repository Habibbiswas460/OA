"""
ANGEL-X Strike Selection Engine
Responsible for scanning and selecting optimal strikes for scalping
Based on Greeks health, liquidity, and spread filters
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class OptionType(Enum):
    """Option type"""
    CALL = "CE"
    PUT = "PE"


@dataclass
class OptionStrike:
    """Option strike data with Greeks"""
    symbol: str
    strike: int
    option_type: OptionType
    ltp: float
    bid: float
    ask: float
    bid_qty: int
    ask_qty: int
    volume: int
    oi: int
    oi_change: float
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float
    underlying_price: float
    timestamp: datetime
    
    @property
    def spread_percent(self) -> float:
        """Calculate spread percentage"""
        if self.ltp <= 0:
            return 999.0
        return ((self.ask - self.bid) / self.ltp) * 100
    
    @property
    def is_healthy_spread(self) -> bool:
        """Check if spread is acceptable"""
        return self.spread_percent <= config.MAX_SPREAD_PERCENT
    
    @property
    def is_liquid(self) -> bool:
        """Check if strike is liquid enough"""
        return (self.volume >= config.MIN_VOLUME_THRESHOLD and 
                self.oi >= config.MIN_OI_THRESHOLD and
                self.bid > 0 and self.ask > 0)
    
    @property
    def greeks_health_score(self) -> float:
        """Score Greeks health (0-100)"""
        score = 0.0
        
        # Delta score (0-25 points)
        if self.option_type == OptionType.CALL:
            if config.IDEAL_DELTA_CALL[0] <= abs(self.delta) <= config.IDEAL_DELTA_CALL[1]:
                score += 25
            elif abs(self.delta) > config.IDEAL_DELTA_CALL[0]:
                score += 15
        else:  # PUT
            if config.IDEAL_DELTA_PUT[0] <= self.delta <= config.IDEAL_DELTA_PUT[1]:
                score += 25
            elif self.delta < config.IDEAL_DELTA_PUT[0]:
                score += 15
        
        # Gamma score (0-25 points)
        if self.gamma >= config.IDEAL_GAMMA_MIN:
            score += 25
        elif self.gamma > 0:
            score += 15
        
        # Theta score (0-25 points) - lower is better
        if abs(self.theta) <= config.IDEAL_THETA_MAX:
            score += 25
        elif abs(self.theta) < config.IDEAL_THETA_MAX * 2:
            score += 15
        
        # Vega score (0-25 points)
        if self.vega >= config.IDEAL_VEGA_MIN:
            score += 25
        elif self.vega > 0:
            score += 15
        
        return score


class StrikeSelectionEngine:
    """
    Strike Selection Engine for ANGEL-X
    
    Scans available strikes and selects best option for scalping
    based on Greeks health, liquidity, and spread
    """
    
    def __init__(self):
        """Initialize strike selection engine"""
        self.last_selected_call = None
        self.last_selected_put = None
        self.last_scan_time = None
        logger.info("StrikeSelectionEngine initialized")
    
    def scan_and_select_best_strike(
        self,
        available_strikes: List[OptionStrike],
        bias: str,
        current_underlying_price: float
    ) -> Optional[OptionStrike]:
        """
        Scan available strikes and select best based on bias
        
        Args:
            available_strikes: List of OptionStrike objects for all strikes
            bias: 'BULLISH' | 'BEARISH' | 'NO_TRADE'
            current_underlying_price: Current underlying LTP
            
        Returns:
            Best OptionStrike object or None if no suitable strike found
        """
        
        if not available_strikes or bias == 'NO_TRADE':
            return None
        
        self.last_scan_time = datetime.now()
        
        # Filter by option type based on bias
        if bias == 'BULLISH':
            candidates = [s for s in available_strikes if s.option_type == OptionType.CALL]
        else:  # BEARISH
            candidates = [s for s in available_strikes if s.option_type == OptionType.PUT]
        
        if not candidates:
            logger.warning(f"No {bias} candidates found in available strikes")
            return None
        
        # Apply filters
        filtered = self._apply_health_filters(candidates)
        
        if not filtered:
            logger.debug(f"No strikes passed health filters for {bias} bias")
            return None
        
        # Score and rank remaining strikes
        scored = self._score_strikes(filtered)
        
        if not scored:
            return None
        
        # Select best strike
        best_strike = max(scored, key=lambda x: x[1])
        selected = best_strike[0]
        
        logger.info(
            f"Selected {selected.option_type.value} strike: "
            f"Strike={selected.strike}, Delta={selected.delta:.2f}, "
            f"Gamma={selected.gamma:.4f}, Spread={selected.spread_percent:.2f}%, "
            f"Score={best_strike[1]:.1f}"
        )
        
        if bias == 'BULLISH':
            self.last_selected_call = selected
        else:
            self.last_selected_put = selected
        
        return selected
    
    def _apply_health_filters(self, strikes: List[OptionStrike]) -> List[OptionStrike]:
        """Apply mandatory health filters"""
        filtered = []
        
        for strike in strikes:
            # Liquidity check
            if not strike.is_liquid:
                continue
            
            # Spread check
            if not strike.is_healthy_spread:
                continue
            
            # Price check (must be meaningful)
            if strike.ltp <= 0:
                continue
            
            # Greeks presence check
            if strike.delta == 0 or strike.gamma == 0:
                continue
            
            # OI change indicator check
            if strike.oi_change is None:
                strike.oi_change = 0
            
            filtered.append(strike)
        
        return filtered
    
    def _score_strikes(self, strikes: List[OptionStrike]) -> List[tuple]:
        """Score strikes and return ranked list"""
        scored = []
        
        for strike in strikes:
            score = 0.0
            
            # Greeks health score (40 points)
            greeks_score = strike.greeks_health_score
            score += (greeks_score / 100) * 40
            
            # Liquidity score (30 points)
            volume_score = min(strike.volume / 200, 1.0) * 15
            oi_score = min(strike.oi / 500, 1.0) * 15
            score += volume_score + oi_score
            
            # Spread score (20 points)
            spread_score = max(0, 1.0 - (strike.spread_percent / config.MAX_SPREAD_PERCENT)) * 20
            score += spread_score
            
            # OI momentum score (10 points)
            if strike.oi_change > 0:
                oi_momentum = min(strike.oi_change / 100, 1.0) * 10
                score += oi_momentum
            
            scored.append((strike, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def validate_selection_quality(self, selected: OptionStrike, bias: str) -> bool:
        """
        Validate if selected strike meets minimum quality standards
        
        Returns:
            True if selection quality is good, False otherwise
        """
        # Check liquidity
        if not selected.is_liquid:
            logger.warning(f"Selected strike fails liquidity check: Volume={selected.volume}, OI={selected.oi}")
            return False
        
        # Check spread
        if not selected.is_healthy_spread:
            logger.warning(f"Selected strike spread too wide: {selected.spread_percent:.2f}%")
            return False
        
        # Check Greeks are meaningful
        if abs(selected.delta) < 0.40:
            logger.warning(f"Selected strike delta too weak: {selected.delta:.2f}")
            return False
        
        if selected.gamma < config.IDEAL_GAMMA_MIN:
            logger.warning(f"Selected strike gamma too low: {selected.gamma:.4f}")
            return False
        
        # Check Greeks health score
        health_score = selected.greeks_health_score
        if health_score < 50:
            logger.warning(f"Selected strike health score too low: {health_score:.1f}")
            return False
        
        logger.info(f"Strike validation passed - Health Score: {health_score:.1f}")
        return True
    
    def get_alternative_strikes(
        self,
        strikes: List[OptionStrike],
        exclude_strike: Optional[OptionStrike] = None,
        option_type: Optional[OptionType] = None,
        count: int = 3
    ) -> List[OptionStrike]:
        """
        Get alternative strike options for diversification
        
        Args:
            strikes: Available strikes
            exclude_strike: Strike to exclude (usually current selection)
            option_type: Filter by CALL or PUT
            count: Number of alternatives to return
            
        Returns:
            List of alternative OptionStrike objects
        """
        candidates = strikes.copy()
        
        # Filter by option type if specified
        if option_type:
            candidates = [s for s in candidates if s.option_type == option_type]
        
        # Exclude current strike
        if exclude_strike:
            candidates = [s for s in candidates if s.strike != exclude_strike.strike]
        
        # Apply health filters
        candidates = self._apply_health_filters(candidates)
        
        # Score and rank
        scored = self._score_strikes(candidates)
        
        # Return top N
        return [s[0] for s in scored[:count]]
    
    def is_strike_still_valid(self, strike: OptionStrike) -> bool:
        """
        Check if previously selected strike is still valid for trading
        (liquidity, spread, Greeks not degraded)
        """
        if not strike.is_liquid:
            return False
        
        if not strike.is_healthy_spread:
            return False
        
        # If Greeks degraded significantly, mark invalid
        if abs(strike.delta) < 0.30:
            return False
        
        return True
    
    def scan_strikes_for_bias(
        self,
        call_strikes: List[OptionStrike],
        put_strikes: List[OptionStrike],
        bias: str
    ) -> Optional[OptionStrike]:
        """
        Simple wrapper: scan appropriate strikes based on bias
        """
        if bias == 'BULLISH':
            return self.scan_and_select_best_strike(call_strikes, bias, 0.0)
        elif bias == 'BEARISH':
            return self.scan_and_select_best_strike(put_strikes, bias, 0.0)
        else:
            return None
