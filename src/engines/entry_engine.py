"""
ANGEL-X Entry Engine
Generates entry signals based on Greeks + Momentum + OI confirmation
Entry trigger: Acceleration + Commitment + Participation all align
"""

import logging
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class EntrySignal(Enum):
    """Entry signal types"""
    NO_SIGNAL = "NO_SIGNAL"
    CALL_BUY = "CALL_BUY"
    PUT_BUY = "PUT_BUY"


@dataclass
class EntryContext:
    """Complete entry context with all signals"""
    signal: EntrySignal
    option_type: str  # CE or PE
    strike: int
    entry_price: float
    entry_delta: float
    entry_gamma: float
    entry_theta: float
    entry_vega: float
    entry_iv: float
    reason_tags: List[str]
    confidence: float


class EntryEngine:
    """
    ANGEL-X Entry Engine
    Entry: Acceleration + Commitment + Participation ALL align
    """
    
    def __init__(self, bias_engine, trap_detection_engine):
        """Initialize entry engine"""
        self.bias_engine = bias_engine
        self.trap_detection_engine = trap_detection_engine
        self.last_entry_context = None
        self.entry_history = []
        self.momentum_count = 0
        logger.info("EntryEngine (ANGEL-X) initialized")
    
    def check_entry_signal(
        self,
        bias_state: str,
        bias_confidence: float,
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
        prev_iv: float,
        bid: float,
        ask: float,
        selected_strike: int,
        current_spread_percent: float
    ) -> Optional[EntryContext]:
        """Check if entry conditions are met - ALL must align"""
        
        # Prerequisite 1: Bias permission
        if bias_state == "NO_TRADE":
            return None
        
        # Prerequisite 2: Spread acceptable
        if current_spread_percent > config.MAX_SPREAD_PERCENT:
            return None
        
        # Prerequisite 3: Data valid
        if bid <= 0 or ask <= 0 or current_ltp <= 0:
            return None
        
        entry_signals = []
        confidence_score = 0.0
        
        # Signal 1: LTP rising
        if current_ltp > prev_ltp:
            entry_signals.append('ltp_rising')
            confidence_score += 15
        else:
            return None
        
        # Signal 2: Volume rising
        if current_volume > prev_volume:
            entry_signals.append('volume_rising')
            confidence_score += 15
        else:
            return None
        
        # Signal 3: OI rising
        if current_oi_change > 0:
            entry_signals.append('oi_rising')
            confidence_score += 15
        else:
            return None
        
        # Signal 4: Gamma rising
        if current_gamma > prev_gamma and current_gamma > config.IDEAL_GAMMA_MIN:
            entry_signals.append('gamma_rising')
            confidence_score += 15
        else:
            return None
        
        # Signal 5: Delta power zone
        if bias_state == "BULLISH":
            delta_valid = current_delta >= config.IDEAL_DELTA_CALL[0]
            option_type = "CE"
        else:
            delta_valid = current_delta <= config.IDEAL_DELTA_PUT[1]
            option_type = "PE"
        
        if delta_valid:
            entry_signals.append('delta_power_zone')
            confidence_score += 20
        else:
            return None
        
        # Rejection rules
        if self._should_reject_entry(current_oi, current_ltp, prev_ltp, current_iv, prev_iv, current_spread_percent, current_delta, prev_delta):
            return None
        
        # Trap check
        trap_signal = self.trap_detection_engine.update_price_data(current_ltp, bid, ask, current_volume, current_oi, current_oi_change, current_delta, current_iv)
        if self.trap_detection_engine.should_skip_entry(trap_signal):
            return None
        
        confidence_score += bias_confidence * 0.2
        
        entry_context = EntryContext(
            signal=EntrySignal.CALL_BUY if option_type == "CE" else EntrySignal.PUT_BUY,
            option_type=option_type,
            strike=selected_strike,
            entry_price=current_ltp,
            entry_delta=current_delta,
            entry_gamma=current_gamma,
            entry_theta=0,
            entry_vega=0,
            entry_iv=current_iv,
            reason_tags=entry_signals,
            confidence=min(confidence_score, 100.0)
        )
        
        logger.info(f"ENTRY: {option_type} {selected_strike} @ ₹{current_ltp:.2f} | Conf: {confidence_score:.0f}%")
        self.last_entry_context = entry_context
        self.entry_history.append(entry_context)
        
        return entry_context
    
    def _should_reject_entry(self, current_oi, current_ltp, prev_ltp, current_iv, prev_iv, current_spread_percent, current_delta, prev_delta) -> bool:
        """Entry rejection rules"""
        price_move = abs(current_ltp - prev_ltp)
        if price_move < config.REJECT_OI_FLAT_THRESHOLD:
            return True
        
        if prev_iv > 0:
            iv_change_pct = ((current_iv - prev_iv) / prev_iv) * 100
            if iv_change_pct < config.REJECT_IV_DROP_PERCENT:
                return True
        
        if current_spread_percent > config.REJECT_SPREAD_WIDENING:
            return True
        
        delta_change = abs(current_delta - prev_delta)
        if delta_change > config.REJECT_DELTA_SPIKE_COLLAPSE:
            return True
        
        return False
    
    def validate_entry_quality(self, context: EntryContext) -> bool:
        """Validate entry quality"""
        if context.confidence < 60:
            return False
        if len(context.reason_tags) < 4:
            return False
        if abs(context.entry_delta) < 0.45:
            return False
        return context.entry_gamma >= config.IDEAL_GAMMA_MIN
