"""
ANGEL-X Trap Detection Engine
Identifies market traps and fake moves to protect against losses
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class TrapType(Enum):
    """Types of market traps detected"""
    OI_NO_PREMIUM_RISE = "OI increasing but premium not rising"
    PREMIUM_NO_OI = "Premium rising but OI decreasing (short covering)"
    OI_SPIKE_NO_FOLLOW = "OI spike with no price follow-through"
    IV_DROP_CRUSH = "IV dropping sharply (premium melt)"
    IV_CHOPPY_UNDERLYING = "High IV with choppy underlying movement"
    SPREAD_WIDENING = "Spread suddenly widening"
    LIQUIDITY_EVAPORATION = "Volume/OI vanishing suddenly"
    DELTA_SPIKE_COLLAPSE = "Delta spikes then collapses (fake move)"


@dataclass
class TrapSignal:
    """Trap detection signal"""
    trap_type: TrapType
    severity: float  # 0-100
    description: str
    timestamp: datetime
    data_snapshot: dict


class TrapDetectionEngine:
    """
    Detects market traps and operator/retail manipulation patterns
    Prevents entering false moves
    """
    
    def __init__(self):
        """Initialize trap detection engine"""
        self.oi_history = []  # Track OI changes
        self.premium_history = []  # Track premium changes
        self.iv_history = []  # Track IV changes
        self.spread_history = []  # Track spread changes
        self.delta_history = []  # Track delta changes
        self.volume_history = []  # Track volume
        
        self.detected_traps = []
        self.trap_cooldown_until = None
        
        logger.info("TrapDetectionEngine initialized")
    
    def update_price_data(
        self,
        ltp: float,
        bid: float,
        ask: float,
        volume: int,
        oi: int,
        oi_change: float,
        delta: float,
        iv: float
    ) -> Optional[TrapSignal]:
        """
        Update trap detector with latest price data
        Returns TrapSignal if trap detected
        """
        timestamp = datetime.now()
        spread = (ask - bid) if (ask > 0 and bid > 0) else 0
        spread_percent = (spread / ltp * 100) if ltp > 0 else 0
        
        # Store history (keep last 50 candles)
        self.oi_history.append({'oi': oi, 'oi_change': oi_change, 'timestamp': timestamp})
        self.premium_history.append({'ltp': ltp, 'timestamp': timestamp})
        self.iv_history.append({'iv': iv, 'timestamp': timestamp})
        self.spread_history.append({'spread': spread, 'spread_pct': spread_percent, 'timestamp': timestamp})
        self.delta_history.append({'delta': delta, 'timestamp': timestamp})
        self.volume_history.append({'volume': volume, 'timestamp': timestamp})
        
        if len(self.oi_history) > 50:
            self.oi_history = self.oi_history[-50:]
        if len(self.premium_history) > 50:
            self.premium_history = self.premium_history[-50:]
        if len(self.iv_history) > 50:
            self.iv_history = self.iv_history[-50:]
        if len(self.spread_history) > 50:
            self.spread_history = self.spread_history[-50:]
        if len(self.delta_history) > 50:
            self.delta_history = self.delta_history[-50:]
        if len(self.volume_history) > 50:
            self.volume_history = self.volume_history[-50:]
        
        # Check for traps
        trap_signal = None
        
        if config.DETECT_OI_TRAP_NO_PREMIUM_RISE:
            trap_signal = self._detect_oi_no_premium_trap()
        
        if not trap_signal and config.DETECT_OI_TRAP_PREMIUM_RISE_NO_OI:
            trap_signal = self._detect_premium_no_oi_trap()
        
        if not trap_signal and config.DETECT_OI_TRAP_SPIKE_NO_FOLLOW:
            trap_signal = self._detect_oi_spike_no_follow_trap()
        
        if not trap_signal and config.DETECT_IV_TRAP_SUDDEN_DROP:
            trap_signal = self._detect_iv_crush_trap(iv)
        
        if not trap_signal and config.DETECT_IV_TRAP_CHOPPY_UNDERLYING:
            trap_signal = self._detect_choppy_underlying_trap()
        
        if not trap_signal and config.DETECT_SPREAD_TRAP_WIDE_ENTRY:
            trap_signal = self._detect_spread_widening_trap(spread_percent)
        
        if not trap_signal and config.DETECT_LIQUIDITY_DROP:
            trap_signal = self._detect_liquidity_evaporation_trap(volume)
        
        # Delta spike collapse detection (entry time critical)
        delta_spike_trap = self._detect_delta_spike_collapse_trap(delta)
        if delta_spike_trap:
            trap_signal = delta_spike_trap
        
        if trap_signal:
            self.detected_traps.append(trap_signal)
            logger.warning(f"TRAP DETECTED: {trap_signal.trap_type.value} (severity: {trap_signal.severity:.1f})")
        
        return trap_signal
    
    def _detect_oi_no_premium_trap(self) -> Optional[TrapSignal]:
        """OI increasing but premium not moving"""
        if len(self.oi_history) < 5:
            return None
        
        recent_oi = self.oi_history[-5:]
        recent_premium = self.premium_history[-5:]
        
        # Check if OI rising
        oi_trend = recent_oi[-1]['oi'] - recent_oi[0]['oi']
        
        # Check if premium flat
        premium_trend = recent_premium[-1]['ltp'] - recent_premium[0]['ltp']
        premium_volatility = max([p['ltp'] for p in recent_premium]) - min([p['ltp'] for p in recent_premium])
        
        if oi_trend > 0 and premium_volatility < 1:  # OI rising, premium almost flat
            severity = min(abs(oi_trend) / 100 * 100, 80)  # Cap at 80
            
            return TrapSignal(
                trap_type=TrapType.OI_NO_PREMIUM_RISE,
                severity=severity,
                description=f"OI +{oi_trend:.0f} but premium movement < ₹1",
                timestamp=datetime.now(),
                data_snapshot={'oi_trend': oi_trend, 'premium_move': premium_trend}
            )
        
        return None
    
    def _detect_premium_no_oi_trap(self) -> Optional[TrapSignal]:
        """Premium rising but OI decreasing (short covering / pullback)"""
        if len(self.oi_history) < 5:
            return None
        
        recent_oi = self.oi_history[-5:]
        recent_premium = self.premium_history[-5:]
        
        # OI declining
        oi_trend = recent_oi[-1]['oi'] - recent_oi[0]['oi']
        
        # Premium rising
        premium_trend = recent_premium[-1]['ltp'] - recent_premium[0]['ltp']
        
        if oi_trend < -50 and premium_trend > 2:  # OI falling, premium up
            severity = min(abs(oi_trend) / 50, 70)
            
            return TrapSignal(
                trap_type=TrapType.PREMIUM_NO_OI,
                severity=severity,
                description=f"Premium +₹{premium_trend:.1f} but OI falling ({oi_trend:.0f})",
                timestamp=datetime.now(),
                data_snapshot={'oi_trend': oi_trend, 'premium_move': premium_trend}
            )
        
        return None
    
    def _detect_oi_spike_no_follow_trap(self) -> Optional[TrapSignal]:
        """OI spike with no price follow-through (operator manipulation)"""
        if len(self.oi_history) < 10:
            return None
        
        recent_oi = self.oi_history[-10:]
        recent_premium = self.premium_history[-10:]
        
        # Find spike point (OI jumps significantly)
        oi_values = [o['oi'] for o in recent_oi]
        max_oi_change = max(oi_values[i+1] - oi_values[i] for i in range(len(oi_values)-1))
        
        if max_oi_change > 200:  # Significant OI spike
            # Check if premium followed
            premium_move = recent_premium[-1]['ltp'] - recent_premium[-5]['ltp'] if len(recent_premium) >= 5 else 0
            
            if abs(premium_move) < 1:  # No premium follow-through
                severity = min(max_oi_change / 200 * 75, 85)
                
                return TrapSignal(
                    trap_type=TrapType.OI_SPIKE_NO_FOLLOW,
                    severity=severity,
                    description=f"OI spike +{max_oi_change:.0f} but no premium continuation",
                    timestamp=datetime.now(),
                    data_snapshot={'oi_spike': max_oi_change, 'premium_follow': premium_move}
                )
        
        return None
    
    def _detect_iv_crush_trap(self, current_iv: float) -> Optional[TrapSignal]:
        """IV dropping sharply (premium will melt)"""
        if len(self.iv_history) < 5:
            return None
        
        recent_iv = self.iv_history[-5:]
        premium_recent = self.premium_history[-5:]
        
        # IV drop percent
        iv_change_percent = ((current_iv - recent_iv[0]['iv']) / recent_iv[0]['iv'] * 100) if recent_iv[0]['iv'] > 0 else 0
        
        # Premium movement
        premium_move = premium_recent[-1]['ltp'] - premium_recent[0]['ltp']
        
        if iv_change_percent < config.EXIT_IV_CRUSH_PERCENT and abs(premium_move) < 1:
            severity = min(abs(iv_change_percent), 85)
            
            return TrapSignal(
                trap_type=TrapType.IV_DROP_CRUSH,
                severity=severity,
                description=f"IV dropping {iv_change_percent:.1f}% with flat premium (crush risk)",
                timestamp=datetime.now(),
                data_snapshot={'iv_change_pct': iv_change_percent, 'premium_move': premium_move}
            )
        
        return None
    
    def _detect_choppy_underlying_trap(self) -> Optional[TrapSignal]:
        """High IV with choppy (sideways) underlying movement"""
        if len(self.iv_history) < 10:
            return None
        
        recent_iv = self.iv_history[-10:]
        recent_premium = self.premium_history[-10:]
        
        avg_iv = sum(i['iv'] for i in recent_iv) / len(recent_iv)
        
        # Check for choppiness (many reversals in premium)
        premium_values = [p['ltp'] for p in recent_premium]
        reversals = 0
        for i in range(1, len(premium_values) - 1):
            if (premium_values[i] > premium_values[i-1] and premium_values[i] > premium_values[i+1]) or \
               (premium_values[i] < premium_values[i-1] and premium_values[i] < premium_values[i+1]):
                reversals += 1
        
        choppiness_ratio = reversals / len(premium_values)
        
        if avg_iv > config.IV_EXTREMELY_HIGH_THRESHOLD and choppiness_ratio > 0.5:
            severity = min(choppiness_ratio * 100, 70)
            
            return TrapSignal(
                trap_type=TrapType.IV_CHOPPY_UNDERLYING,
                severity=severity,
                description=f"High IV ({avg_iv:.1f}) + choppy price action",
                timestamp=datetime.now(),
                data_snapshot={'avg_iv': avg_iv, 'choppiness': choppiness_ratio}
            )
        
        return None
    
    def _detect_spread_widening_trap(self, current_spread_pct: float) -> Optional[TrapSignal]:
        """Spread suddenly widening (liquidity trap)"""
        if len(self.spread_history) < 5:
            return None
        
        recent_spreads = self.spread_history[-5:]
        
        # Check if spread widened significantly
        prev_avg_spread = sum(s['spread_pct'] for s in recent_spreads[:-2]) / max(len(recent_spreads[:-2]), 1)
        spread_widening = current_spread_pct - prev_avg_spread
        
        if spread_widening > 0.5:  # Spread increased by >0.5%
            severity = min(spread_widening * 50, 75)
            
            return TrapSignal(
                trap_type=TrapType.SPREAD_WIDENING,
                severity=severity,
                description=f"Spread widened from {prev_avg_spread:.2f}% to {current_spread_pct:.2f}%",
                timestamp=datetime.now(),
                data_snapshot={'spread_widening_pct': spread_widening, 'current_spread': current_spread_pct}
            )
        
        return None
    
    def _detect_liquidity_evaporation_trap(self, current_volume: int) -> Optional[TrapSignal]:
        """Volume/OI suddenly vanishing"""
        if len(self.volume_history) < 5:
            return None
        
        recent_volumes = self.volume_history[-5:]
        avg_volume = sum(v['volume'] for v in recent_volumes[:-1]) / max(len(recent_volumes[:-1]), 1)
        
        volume_drop_pct = ((avg_volume - current_volume) / avg_volume * 100) if avg_volume > 0 else 0
        
        if volume_drop_pct > 50:  # Volume dropped >50%
            severity = min(volume_drop_pct / 2, 80)
            
            return TrapSignal(
                trap_type=TrapType.LIQUIDITY_EVAPORATION,
                severity=severity,
                description=f"Volume dropped {volume_drop_pct:.1f}% (from {avg_volume:.0f} to {current_volume})",
                timestamp=datetime.now(),
                data_snapshot={'volume_drop_pct': volume_drop_pct, 'current_volume': current_volume}
            )
        
        return None
    
    def _detect_delta_spike_collapse_trap(self, current_delta: float) -> Optional[TrapSignal]:
        """Delta spikes then collapses (fake move, entry time critical)"""
        if len(self.delta_history) < 3:
            return None
        
        recent_deltas = self.delta_history[-3:]
        
        # Check for spike then collapse pattern
        if len(recent_deltas) >= 3:
            prev_delta = recent_deltas[0]['delta']
            spike_delta = recent_deltas[1]['delta']
            current = recent_deltas[2]['delta']
            
            # Spike up then collapse
            if abs(spike_delta - prev_delta) > 0.15 and abs(current - spike_delta) > 0.10:
                severity = min(abs(spike_delta - prev_delta) * 100, 75)
                
                return TrapSignal(
                    trap_type=TrapType.DELTA_SPIKE_COLLAPSE,
                    severity=severity,
                    description=f"Delta spike ({prev_delta:.2f}→{spike_delta:.2f}→{current:.2f}), possible fake move",
                    timestamp=datetime.now(),
                    data_snapshot={'prev': prev_delta, 'spike': spike_delta, 'current': current}
                )
        
        return None
    
    def is_trap_active(self) -> bool:
        """Check if any trap is currently active with high severity"""
        if not self.detected_traps:
            return False
        
        recent_trap = self.detected_traps[-1]
        
        # Trap is active if detected within last 10 seconds and severity >50
        if (datetime.now() - recent_trap.timestamp).total_seconds() < 10 and recent_trap.severity > 50:
            return True
        
        return False
    
    def get_recent_traps(self, seconds: int = 30) -> List[TrapSignal]:
        """Get traps detected in recent N seconds"""
        cutoff_time = datetime.now() - timedelta(seconds=seconds)
        return [t for t in self.detected_traps if t.timestamp > cutoff_time]
    
    def clear_old_traps(self):
        """Clear trap records older than 60 seconds"""
        cutoff_time = datetime.now() - timedelta(seconds=60)
        self.detected_traps = [t for t in self.detected_traps if t.timestamp > cutoff_time]
    
    def should_skip_entry(self, trap_signal: Optional[TrapSignal]) -> bool:
        """
        Determine if entry should be skipped due to trap detection
        """
        if trap_signal is None:
            return False
        
        # High severity traps = skip
        if trap_signal.severity > 70:
            logger.warning(f"SKIPPING ENTRY due to high-severity trap: {trap_signal.description}")
            return True
        
        # Medium severity traps with recent history = skip
        if trap_signal.severity > 50:
            recent_traps = self.get_recent_traps(seconds=5)
            if len(recent_traps) > 0:
                logger.warning(f"SKIPPING ENTRY: Multiple trap signals in recent history")
                return True
        
        return False
