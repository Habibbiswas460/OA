"""
ANGEL-X Entry Engine
Generates entry signals based on Greeks + Momentum + OI confirmation
Entry trigger: Acceleration + Commitment + Participation all align
"""

import logging
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
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
    
    def select_dynamic_strike(self, base_strike: int, option_type: str, 
                             current_ltp: float, ltp_history: List[float]) -> int:
        """
        Dynamically select strike - ATM by default, but shift to ITM/OTM if no movement
        
        Args:
            base_strike: Base ATM strike
            option_type: CE or PE
            current_ltp: Current LTP
            ltp_history: History of LTP values for movement detection
            
        Returns:
            Selected strike (ATM, ITM±50, or OTM±50)
        """
        if len(ltp_history) < 5:
            return base_strike  # Not enough data
        
        # Check for ATM movement (variance in recent prices)
        recent_ltp = ltp_history[-5:]
        ltp_range = max(recent_ltp) - min(recent_ltp)
        ltp_avg = sum(recent_ltp) / len(recent_ltp)
        movement_percent = (ltp_range / ltp_avg) * 100 if ltp_avg > 0 else 0
        
        logger.info(f"Movement check: Range={ltp_range:.2f}, % = {movement_percent:.2f}%")
        
        # If ATM showing good movement (>0.5%), stay with ATM
        if movement_percent > getattr(config, 'MIN_ATM_MOVEMENT_PERCENT', 0.5):
            logger.info(f"✓ ATM strike {base_strike} has good movement ({movement_percent:.2f}%)")
            return base_strike
        
        # Low movement - shift to ITM/OTM
        logger.info(f"⚠ ATM strike {base_strike} has low movement ({movement_percent:.2f}%) - considering shift")
        
        # Determine shift direction based on option type and price trend
        recent_avg = sum(ltp_history[-3:]) / 3
        curr_vs_avg = current_ltp - recent_avg
        
        if option_type == "CE":
            # For CE: if price trending up, go OTM; if trending down, go ITM
            if curr_vs_avg > 0:
                new_strike = base_strike + 50
                logger.info(f"→ Price trending UP: CE shift to OTM +50 ({new_strike})")
            else:
                new_strike = base_strike - 50
                logger.info(f"→ Price trending DOWN: CE shift to ITM -50 ({new_strike})")
        else:  # PE
            # For PE: if price trending up, go ITM; if trending down, go OTM
            if curr_vs_avg > 0:
                new_strike = base_strike - 50
                logger.info(f"→ Price trending UP: PE shift to ITM -50 ({new_strike})")
            else:
                new_strike = base_strike + 50
                logger.info(f"→ Price trending DOWN: PE shift to OTM +50 ({new_strike})")
        
        return new_strike
    
    def validate_greeks_for_entry(self, greeks_snapshot, option_type: str) -> Dict:
        """
        Validate Greeks health for entry using relaxed validation for expiry day
        
        Args:
            greeks_snapshot: GreeksSnapshot object
            option_type: "CE" or "PE"
            
        Returns:
            {
                'is_valid': bool,
                'quality_score': float (0-100),
                'health_checks': {check_name: bool},
                'reason': str
            }
        """
        if not greeks_snapshot:
            return {
                'is_valid': False,
                'quality_score': 0.0,
                'health_checks': {},
                'reason': 'No Greeks data available'
            }
        
        # Import here to avoid circular dependency
        from src.utils.greeks_data_manager import GreeksDataManager
        
        # Use existing GreeksDataManager methods
        health_checks = {
            'delta_ok': False,
            'gamma_ok': False,
            'theta_ok': False,
            'vega_ok': False,
            'ltp_exists': False,  # Just check LTP exists
            'spread_ok': False
        }
        
        # Validate delta based on option type (relaxed range for scalping)
        if option_type == "CE":
            health_checks['delta_ok'] = 0.1 <= abs(greeks_snapshot.delta) <= 0.9
        else:  # PE
            health_checks['delta_ok'] = -0.9 <= greeks_snapshot.delta <= -0.1
        
        # Gamma check: just needs to be positive
        health_checks['gamma_ok'] = greeks_snapshot.gamma > 0.0001
        
        # Theta check: scalping has high theta decay, allow it
        health_checks['theta_ok'] = True  # Don't check theta for scalping
        
        # Vega check: not too high for scalping
        health_checks['vega_ok'] = greeks_snapshot.vega < 100
        
        # LTP exists check (for expiry day with 0 OI)
        health_checks['ltp_exists'] = greeks_snapshot.ltp > 0
        
        # Spread check
        if greeks_snapshot.ltp > 0 and greeks_snapshot.ask > greeks_snapshot.bid:
            spread_pct = ((greeks_snapshot.ask - greeks_snapshot.bid) / greeks_snapshot.ltp * 100)
            health_checks['spread_ok'] = spread_pct <= getattr(config, 'MAX_SPREAD_PERCENT', 5.0)  # Relaxed
        else:
            health_checks['spread_ok'] = greeks_snapshot.ltp > 0  # Okay if price exists
        
        # Calculate quality score
        quality_score = sum([20 if v else 0 for v in health_checks.values()])
        
        # Check minimum health requirements (relaxed: only 3 of 6 needed)
        healthy_checks = sum(health_checks.values())
        is_valid = healthy_checks >= 3  # Much more relaxed
        
        reason = "Greeks health OK" if is_valid else f"Only {healthy_checks}/6 health checks passed"
        
        return {
            'is_valid': is_valid,
            'quality_score': quality_score,
            'health_checks': health_checks,
            'reason': reason,
            'details': {
                'delta': greeks_snapshot.delta,
                'gamma': greeks_snapshot.gamma,
                'theta': greeks_snapshot.theta,
                'vega': greeks_snapshot.vega,
                'iv': greeks_snapshot.iv,
                'spread_pct': ((greeks_snapshot.ask - greeks_snapshot.bid) / greeks_snapshot.ltp * 100) if greeks_snapshot.ltp > 0 else 0
            }
        }
    
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
        current_spread_percent: float,
        greeks_snapshot=None
    ) -> Optional[EntryContext]:
        """Check if entry conditions are met - configurable signal alignment with Greeks validation"""
        
        # Log prerequisites being checked
        logger.info(f"  📋 Entry prerequisites check:")
        logger.info(f"    Bias: {bias_state} (NO_TRADE={bias_state == 'NO_TRADE'})")
        logger.info(f"    Spread: {current_spread_percent:.2f}% vs MAX={config.MAX_SPREAD_PERCENT}%")
        logger.info(f"    Data: bid={bid}, ask={ask}, ltp={current_ltp}")
        
        # Prerequisite 1: Bias permission
        if bias_state == "NO_TRADE":
            logger.info(f"    ❌ Entry rejected: bias_state=NO_TRADE")
            return None
        
        # Prerequisite 2: Spread acceptable
        if current_spread_percent > config.MAX_SPREAD_PERCENT:
            logger.info(f"    ❌ Entry rejected: spread {current_spread_percent:.2f}% > {config.MAX_SPREAD_PERCENT}%")
            return None
        
        # Prerequisite 3: Data valid
        if bid <= 0 or ask <= 0 or current_ltp <= 0:
            logger.info(f"    ❌ Entry rejected: invalid price data")
            return None
        
        logger.info(f"    ✅ All prerequisites passed")
        
        entry_signals = []
        confidence_score = 0.0
        signal_count = 0
        
        # Determine option type early for Greeks validation
        option_type = "CE" if bias_state == "BULLISH" else "PE"
        
        # NEW: Validate Greeks health if available
        if greeks_snapshot:
            greeks_validation = self.validate_greeks_for_entry(greeks_snapshot, option_type)
            if not greeks_validation['is_valid']:
                logger.info(f"🚫 Entry rejected by Greeks validation: {greeks_validation['reason']}")
                logger.debug(f"Health checks: {greeks_validation['health_checks']}")
                return None
            # Add Greeks quality as confidence boost
            confidence_score += greeks_validation['quality_score'] * 0.3
        
        # Signal 1: LTP rising (always required)
        logger.info(f"  ✓ Signal 1 (LTP): {prev_ltp:.2f} → {current_ltp:.2f} rising? {current_ltp > prev_ltp}")
        if current_ltp > prev_ltp:
            entry_signals.append('ltp_rising')
            confidence_score += 20
            signal_count += 1
            logger.info(f"    ✅ LTP rising - score now {confidence_score:.0f}%, signal_count={signal_count}")
        
        # Signal 2: Volume rising (configurable)
        logger.info(f"  ✓ Signal 2 (Volume): {prev_volume} → {current_volume} rising? {current_volume > prev_volume} (required={config.ENTRY_VOLUME_RISING})")
        if config.ENTRY_VOLUME_RISING and current_volume > prev_volume:
            entry_signals.append('volume_rising')
            confidence_score += 15
            signal_count += 1
            logger.info(f"    ✅ Volume rising - score now {confidence_score:.0f}%, signal_count={signal_count}")
        elif not config.ENTRY_VOLUME_RISING:
            signal_count += 1  # Don't require it
            logger.info(f"    ⊗ Volume not required - signal_count={signal_count}")
        else:
            logger.info(f"    ❌ Volume not rising and required")
        
        # Signal 3: OI analysis (improved) - RELAXED FOR EXPIRY DAY
        # On expiry day, OI will be 0, so accept any positive OI or allow zero with price movement
        min_oi_threshold = getattr(config, 'MIN_OI_FOR_ENTRY', 1)  # Very low for expiry
        oi_is_healthy = current_oi >= min_oi_threshold
        oi_is_rising = current_oi_change > getattr(config, 'MIN_OI_CHANGE_FOR_ENTRY', 0)
        logger.info(f"  ✓ Signal 3 (OI): {current_oi} (healthy={oi_is_healthy}), Δ={current_oi_change} (rising={oi_is_rising})")
        
        if config.ENTRY_OI_RISING:
            if oi_is_rising:
                entry_signals.append('oi_rising')
                confidence_score += 10
                signal_count += 1
                logger.info(f"    ✅ OI rising - score now {confidence_score:.0f}%, signal_count={signal_count}")
            else:
                # On expiry day, OI won't rise - just count it as valid
                signal_count += 1
                logger.info(f"    ⊗ OI not rising but counted for expiry - signal_count={signal_count}")
        else:
            # OI rising not required - count signal if price is moving or OI exists
            signal_count += 1  # Always count for expiry scalping
            logger.info(f"    ⊗ OI rising not required - signal_count={signal_count}")

        
        # Signal 4: Gamma rising (configurable)
        logger.info(f"  ✓ Signal 4 (Gamma): {prev_gamma:.6f} → {current_gamma:.6f} rising? {current_gamma > prev_gamma} (required={config.ENTRY_GAMMA_RISING})")
        if config.ENTRY_GAMMA_RISING and current_gamma > prev_gamma and current_gamma > config.IDEAL_GAMMA_MIN:
            entry_signals.append('gamma_rising')
            confidence_score += 15
            signal_count += 1
            logger.info(f"    ✅ Gamma rising - score now {confidence_score:.0f}%, signal_count={signal_count}")
        elif not config.ENTRY_GAMMA_RISING:
            signal_count += 1  # Don't require it
            logger.info(f"    ⊗ Gamma not required - signal_count={signal_count}")
        else:
            logger.info(f"    ❌ Gamma not rising and required")
        
        # Check signal count requirement
        logger.info(f"  📊 Signal Count Check: {signal_count} vs {getattr(config, 'ENTRY_SIGNALS_REQUIRED_COUNT', 2)} required")
        if signal_count < getattr(config, 'ENTRY_SIGNALS_REQUIRED_COUNT', 2):
            logger.info(f"🚫 Entry rejected: {signal_count} signals < {getattr(config, 'ENTRY_SIGNALS_REQUIRED_COUNT', 2)} required | Confidence: {confidence_score:.0f}%")
            return None
        logger.info(f"  ✅ Signal count passed")
        
        # Check confidence threshold
        logger.info(f"  💪 Confidence Check: {confidence_score:.0f}% vs {getattr(config, 'ENTRY_MIN_CONFIDENCE', 40.0)}% minimum")
        if confidence_score < getattr(config, 'ENTRY_MIN_CONFIDENCE', 40.0):
            logger.info(f"🚫 Entry rejected: confidence {confidence_score:.0f}% < {getattr(config, 'ENTRY_MIN_CONFIDENCE', 40.0)}% (signals: {signal_count})")
            return None
        logger.info(f"  ✅ Confidence check passed")
        
        # Signal 5: Delta power zone
        logger.info(f"  🎯 Bias: {bias_state} | Current Delta: {current_delta:.4f}")
        if bias_state == "BULLISH":
            delta_valid = current_delta >= config.IDEAL_DELTA_CALL[0]
            option_type = "CE"
            logger.info(f"    Call check: {current_delta:.4f} >= {config.IDEAL_DELTA_CALL[0]} ? {delta_valid}")
        else:  # BEARISH / PE
            # For PE: delta range is (-0.65, -0.45), so delta should be between these
            # This means: -0.65 <= delta <= -0.45
            delta_valid = config.IDEAL_DELTA_PUT[0] <= current_delta <= config.IDEAL_DELTA_PUT[1]
            option_type = "PE"
            logger.info(f"    Put check: {config.IDEAL_DELTA_PUT[0]} <= {current_delta:.4f} <= {config.IDEAL_DELTA_PUT[1]} ? {delta_valid}")
        
        if delta_valid:
            entry_signals.append('delta_power_zone')
            confidence_score += 20
            logger.info(f"    ✅ Delta power zone valid - score now {confidence_score:.0f}%")
        else:
            logger.info(f"    ❌ Delta out of range - REJECTING ENTRY")
            return None
        
        # Rejection rules
        logger.info(f"  🚨 Checking rejection rules...")
        if self._should_reject_entry(current_oi, current_ltp, prev_ltp, current_iv, prev_iv, current_spread_percent, current_delta, prev_delta):
            logger.info(f"    ❌ Rejected by rejection rules")
            return None
        logger.info(f"    ✅ No rejection rule triggered")
        
        # Trap check
        logger.info(f"  🪤 Checking trap detection...")
        trap_signal = self.trap_detection_engine.update_price_data(current_ltp, bid, ask, current_volume, current_oi, current_oi_change, current_delta, current_iv)
        logger.info(f"    Trap signal: {trap_signal}")
        if self.trap_detection_engine.should_skip_entry(trap_signal):
            logger.info(f"    ❌ Trap detected - SKIPPING ENTRY")
            return None
        logger.info(f"    ✅ No trap - safe to enter")
        
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
        """Validate entry quality - RELAXED FOR EXPIRY DAY"""
        if context.confidence < 15:  # VERY RELAXED for expiry
            return False
        # Don't check reason_tags count - can be just 1-2 on expiry
        if abs(context.entry_delta) < 0.1:  # RELAXED - even small delta ok for scalping
            return False
        # Don't check gamma on expiry day
        return True  # If we got here, entry is good enough
