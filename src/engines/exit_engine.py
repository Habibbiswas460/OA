"""
ANGEL-X Exit Engine
Handles exit strategies: target-based, time-based, stop-loss-based
Optimized for scalping (1-5 minute holds)
"""

import logging
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class ExitSignal(Enum):
    """Exit signal types"""
    NO_EXIT = "NO_EXIT"
    PROFIT_TARGET = "PROFIT_TARGET"
    TIME_STOP = "TIME_STOP"
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    BREAKEVEN = "BREAKEVEN"


@dataclass
class ExitContext:
    """Exit decision context"""
    signal: ExitSignal
    exit_price: float
    exit_pnl: float
    exit_pnl_percent: float
    exit_reason: str
    hold_seconds: int
    confidence: float


class ExitEngine:
    """
    ANGEL-X Exit Engine
    
    Exit Strategy:
    1. Quick profit exit (1-1.5% profit)
    2. Time-based exit (5-10 minutes max)
    3. Stop loss (0.5% loss)
    4. Breakeven recovery
    """
    
    def __init__(self):
        """Initialize exit engine"""
        # Get config values with defaults for scalping
        self.profit_target_percent = getattr(config, 'EXIT_PROFIT_TARGET_PERCENT', 1.0)
        self.stop_loss_percent = getattr(config, 'EXIT_STOP_LOSS_PERCENT', 0.5)
        self.max_hold_seconds = getattr(config, 'EXIT_MAX_HOLD_SECONDS', 300)  # 5 minutes
        self.breakeven_recovery_percent = getattr(config, 'EXIT_BREAKEVEN_RECOVERY_PERCENT', 0.2)
        self.trailing_stop_percent = getattr(config, 'EXIT_TRAILING_STOP_PERCENT', 0.3)
        
        # State tracking
        self.entry_price = None
        self.entry_time = None
        self.highest_price = None
        self.lowest_price = None
        
        logger.info("ExitEngine initialized")
    
    def set_entry(self, entry_price: float, entry_time: datetime):
        """Record entry for tracking"""
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.highest_price = entry_price
        self.lowest_price = entry_price
    
    def check_exit(self, current_price: float, current_time: datetime = None) -> Optional[ExitContext]:
        """
        Check if exit conditions are met
        
        Args:
            current_price: Current option price
            current_time: Current time (defaults to now)
            
        Returns:
            ExitContext if exit condition met, None otherwise
        """
        if not self.entry_price or not self.entry_time:
            return None
        
        if current_time is None:
            current_time = datetime.now()
        
        # Update highest/lowest
        self.highest_price = max(self.highest_price, current_price)
        self.lowest_price = min(self.lowest_price, current_price)
        
        # Calculate metrics
        pnl = current_price - self.entry_price
        pnl_percent = (pnl / self.entry_price * 100) if self.entry_price > 0 else 0
        hold_seconds = (current_time - self.entry_time).total_seconds()
        
        # Exit Priority: SL > Breakeven > Profit Target > Time Exit
        
        # 1. Stop Loss - HIGHEST PRIORITY
        if pnl_percent <= -self.stop_loss_percent:
            return ExitContext(
                signal=ExitSignal.STOP_LOSS,
                exit_price=current_price,
                exit_pnl=pnl,
                exit_pnl_percent=pnl_percent,
                exit_reason=f"Stop Loss triggered ({pnl_percent:.2f}%)",
                hold_seconds=int(hold_seconds),
                confidence=95.0
            )
        
        # 2. Profit Target - SECOND PRIORITY
        if pnl_percent >= self.profit_target_percent:
            return ExitContext(
                signal=ExitSignal.PROFIT_TARGET,
                exit_price=current_price,
                exit_pnl=pnl,
                exit_pnl_percent=pnl_percent,
                exit_reason=f"Profit target reached ({pnl_percent:.2f}%)",
                hold_seconds=int(hold_seconds),
                confidence=95.0
            )
        
        # 3. Breakeven Recovery - recovering from small loss
        if pnl_percent < 0 and pnl_percent >= -self.breakeven_recovery_percent:
            if pnl_percent >= 0:  # Recovered to breakeven or better
                return ExitContext(
                    signal=ExitSignal.BREAKEVEN,
                    exit_price=current_price,
                    exit_pnl=pnl,
                    exit_pnl_percent=pnl_percent,
                    exit_reason=f"Breakeven recovery ({pnl_percent:.2f}%)",
                    hold_seconds=int(hold_seconds),
                    confidence=75.0
                )
        
        # 4. Trailing Stop - exit if price falls from high
        drawdown_from_high = ((self.highest_price - current_price) / self.highest_price * 100) if self.highest_price > 0 else 0
        if self.highest_price > self.entry_price and drawdown_from_high >= self.trailing_stop_percent:
            return ExitContext(
                signal=ExitSignal.TRAILING_STOP,
                exit_price=current_price,
                exit_pnl=pnl,
                exit_pnl_percent=pnl_percent,
                exit_reason=f"Trailing stop ({drawdown_from_high:.2f}% from high)",
                hold_seconds=int(hold_seconds),
                confidence=80.0
            )
        
        # 5. Time-Based Exit - exit after max hold time
        if hold_seconds >= self.max_hold_seconds:
            return ExitContext(
                signal=ExitSignal.TIME_STOP,
                exit_price=current_price,
                exit_pnl=pnl,
                exit_pnl_percent=pnl_percent,
                exit_reason=f"Time limit reached ({hold_seconds}s)",
                hold_seconds=int(hold_seconds),
                confidence=85.0
            )
        
        # No exit condition met
        return None
    
    def get_status(self) -> dict:
        """Get current exit strategy status"""
        return {
            'entry_price': self.entry_price,
            'entry_time': self.entry_time,
            'highest_price': self.highest_price,
            'lowest_price': self.lowest_price,
            'profit_target': self.profit_target_percent,
            'stop_loss': self.stop_loss_percent,
            'max_hold_seconds': self.max_hold_seconds
        }
