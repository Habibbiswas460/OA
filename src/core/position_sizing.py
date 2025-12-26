"""
ANGEL-X Position Sizing Engine
Risk-first positioning: Capital × Risk% → Auto lot sizing
Hard SL: 6-8% premium, SL > 10% required → Trade skipped
"""

import logging
from dataclasses import dataclass
from typing import Optional
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


@dataclass
class PositionSize:
    """Position sizing result"""
    quantity: int  # Number of units
    lot_size: int  # Quantity per lot
    num_lots: float
    capital_allocated: float
    max_loss_amount: float
    hard_sl_percent: float
    hard_sl_price: float
    target_price: float
    risk_reward_ratio: float
    sizing_valid: bool
    rejection_reason: Optional[str] = None


class PositionSizing:
    """
    ANGEL-X Position Sizing Engine
    
    Rule-based, risk-first position sizing
    Input: Entry price, Risk%, SL% → Output: Qty
    
    Non-negotiable rules:
    - Risk: 1-5% per trade only
    - SL: 6-8% typical, >10% → SKIP
    - No averaging
    - No SL widening
    """
    
    def __init__(self):
        """Initialize position sizing"""
        self.capital = config.CAPITAL
        self.min_lot_size = config.MINIMUM_LOT_SIZE
        logger.info(f"PositionSizing initialized - Capital: ₹{self.capital}")
    
    def calculate_position_size(
        self,
        entry_price: float,
        hard_sl_price: float,
        target_price: float,
        risk_percent: Optional[float] = None,
        selected_sl_percent: Optional[float] = None,
        expiry_rules: Optional[dict] = None
    ) -> PositionSize:
        """
        Calculate optimal position size based on risk parameters
        
        Args:
            entry_price: Entry premium
            hard_sl_price: Stop loss price
            target_price: Take profit price
            risk_percent: Risk % (1-5%, default 2%)
            selected_sl_percent: SL as % of premium (optional override)
            expiry_rules: Expiry-adjusted rules dict (optional)
        
        Returns:
            PositionSize object with qty, risk, SL details
        """
        
        # Apply expiry rules if provided
        if expiry_rules:
            risk_percent = expiry_rules.get('risk_percent', None)
        
        # Default risk percentage (config already in integer percentage form)
        if risk_percent is None:
            risk_percent = config.RISK_PER_TRADE_OPTIMAL
        
        # Validate risk bounds (config values already in percentage form)
        if risk_percent < config.RISK_PER_TRADE_MIN:
            risk_percent = config.RISK_PER_TRADE_MIN
        if risk_percent > config.RISK_PER_TRADE_MAX:
            risk_percent = config.RISK_PER_TRADE_MAX
        
        # Convert to decimal for calculations
        risk_decimal = risk_percent / 100
        
        # Calculate SL percent
        if hard_sl_price > 0:
            sl_percent = abs((hard_sl_price - entry_price) / entry_price * 100)
        else:
            sl_percent = config.HARD_SL_PERCENT_MIN
        
        # Hard SL validation
        if sl_percent > config.HARD_SL_PERCENT_EXCEED_SKIP:
            logger.warning(f"SL too wide ({sl_percent:.2f}%), trade SKIPPED")
            return PositionSize(
                quantity=0,
                lot_size=self.min_lot_size,
                num_lots=0,
                capital_allocated=0,
                max_loss_amount=0,
                hard_sl_percent=sl_percent,
                hard_sl_price=hard_sl_price,
                target_price=target_price,
                risk_reward_ratio=0,
                sizing_valid=False,
                rejection_reason=f"SL too wide: {sl_percent:.2f}% (max {config.HARD_SL_PERCENT_EXCEED_SKIP}%)"
            )
        
        # Calculate max loss allowed
        max_loss_allowed = self.capital * risk_decimal
        
        # Calculate qty needed for this risk level
        loss_per_unit = abs(entry_price - hard_sl_price)
        
        if loss_per_unit <= 0:
            return PositionSize(
                quantity=0,
                lot_size=self.min_lot_size,
                num_lots=0,
                capital_allocated=0,
                max_loss_amount=0,
                hard_sl_percent=0,
                hard_sl_price=hard_sl_price,
                target_price=target_price,
                risk_reward_ratio=0,
                sizing_valid=False,
                rejection_reason="Invalid SL calculation"
            )
        
        # Quantity = max_loss / loss_per_unit
        raw_qty = max_loss_allowed / loss_per_unit
        
        # Round to lot size
        num_lots = int(raw_qty / self.min_lot_size)
        
        if num_lots < 1:
            # Can't even buy 1 lot with this risk
            return PositionSize(
                quantity=0,
                lot_size=self.min_lot_size,
                num_lots=0,
                capital_allocated=0,
                max_loss_amount=0,
                hard_sl_percent=sl_percent,
                hard_sl_price=hard_sl_price,
                target_price=target_price,
                risk_reward_ratio=0,
                sizing_valid=False,
                rejection_reason=f"Insufficient capital for 1 lot ({self.min_lot_size} units) with {risk_percent:.1f}% risk"
            )
        
        # Final quantity
        final_qty = num_lots * self.min_lot_size
        
        # Cap at max position size
        if final_qty > config.MAX_POSITION_SIZE:
            final_qty = config.MAX_POSITION_SIZE
            num_lots = final_qty / self.min_lot_size
        
        # Calculate actual risk
        actual_max_loss = final_qty * loss_per_unit
        actual_risk_percent = (actual_max_loss / self.capital) * 100
        
        # Capital allocation
        capital_allocated = entry_price * final_qty
        
        # Risk/Reward ratio
        profit_per_unit = abs(target_price - entry_price) if target_price > 0 else 0
        total_profit = final_qty * profit_per_unit
        risk_reward_ratio = total_profit / actual_max_loss if actual_max_loss > 0 else 0
        
        logger.info(
            f"Position Sizing: {final_qty} units ({num_lots:.1f} lots) | "
            f"Risk: ₹{actual_max_loss:.2f} ({actual_risk_percent:.2f}%) | "
            f"Target: ₹{total_profit:.2f} | RR: {risk_reward_ratio:.2f}"
        )
        
        return PositionSize(
            quantity=final_qty,
            lot_size=self.min_lot_size,
            num_lots=num_lots,
            capital_allocated=capital_allocated,
            max_loss_amount=actual_max_loss,
            hard_sl_percent=sl_percent,
            hard_sl_price=hard_sl_price,
            target_price=target_price,
            risk_reward_ratio=risk_reward_ratio,
            sizing_valid=True
        )
    
    def get_recommendation(
        self,
        entry_price: float,
        stop_loss_percent: float,
        risk_percent: float = None,
        expiry_rules: Optional[dict] = None
    ) -> dict:
        """
        Get quick sizing recommendation
        
        Returns dict with qty, risk, target
        """
        # Use default if not provided
        if risk_percent is None:
            risk_percent = config.RISK_PER_TRADE_OPTIMAL
        sl_price = entry_price * (1 - stop_loss_percent / 100)
        target_price = entry_price * (1 + 2 * stop_loss_percent / 100)  # 1:2 RR assumption
        
        sizing = self.calculate_position_size(entry_price, sl_price, target_price, risk_percent, expiry_rules=expiry_rules)
        
        if not sizing.sizing_valid:
            return {'error': sizing.rejection_reason}
        
        return {
            'quantity': sizing.quantity,
            'entry': entry_price,
            'sl': sizing.hard_sl_price,
            'target': sizing.target_price,
            'max_loss': sizing.max_loss_amount,
            'expected_profit': sizing.target_price * sizing.quantity - entry_price * sizing.quantity,
            'risk_reward': sizing.risk_reward_ratio
        }
