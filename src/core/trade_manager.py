"""
ANGEL-X Trade Manager
Greek-based exits: Delta weakness, Gamma rollover, Theta damage, IV crush, OI-Price mismatch
"When Gamma peaks, don't hope - exit"
"""

import logging
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from config import config
from src.utils.logger import StrategyLogger
from src.core.order_manager import OrderManager
from src.utils.slippage_calculator import SlippageCalculator

logger = StrategyLogger.get_logger(__name__)


@dataclass
class Trade:
    """Trade object"""
    trade_id: str
    entry_time: datetime
    exit_time: Optional[datetime]
    option_type: str
    strike: int
    entry_price: float
    current_price: float
    quantity: int
    entry_delta: float
    entry_gamma: float
    entry_theta: float
    entry_iv: float
    sl_price: float
    target_price: float
    status: str  # OPEN, CLOSED_PROFIT, CLOSED_LOSS, CLOSED_SL
    exit_reason: Optional[str]
    pnl: float
    pnl_percent: float
    time_in_trade_sec: int = 0  # Added for expiry-day management
    # Realistic costs
    entry_slippage: float = 0.0  # Slippage on entry in rupees
    exit_slippage: float = 0.0   # Slippage on exit in rupees
    brokerage_cost: float = 0.0  # Total brokerage + taxes
    net_pnl: float = 0.0         # P&L after costs
    net_pnl_percent: float = 0.0 # P&L % after costs

class TradeManager:
    """
    ANGEL-X Trade Manager
    
    Manages trade lifecycle with Greek-based exits
    
    Exit triggers (all edge-gone):
    1. Hard SL: Premium falls to SL → exit immediately
    2. Delta weakness: Delta degrades 15%+ → exit
    3. Gamma rollover: Gamma stops rising → exit
    4. Theta damage: Flat price + theta eating → exit
    5. IV crush: IV drops >5% + price stalls → exit
    6. OI-Price mismatch: OI↑ but price flat → exit
    """
    
    def __init__(self):
        """Initialize trade manager"""
        self.active_trades: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.trade_counter = 0
        # Local order manager for multi-leg operations
        self._order_manager = OrderManager()
        
        logger.info("TradeManager (ANGEL-X) initialized")
    
    def enter_trade(
        self,
        option_type: str,
        strike: int,
        entry_price: float,
        quantity: int,
        entry_delta: float,
        entry_gamma: float,
        entry_theta: float,
        entry_iv: float,
        sl_price: float,
        target_price: float
    ) -> Trade:
        """
        Enter a new trade
        
        Returns:
            Trade object for tracking
        """
        self.trade_counter += 1
        trade_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.trade_counter:03d}"
        
        trade = Trade(
            trade_id=trade_id,
            entry_time=datetime.now(),
            exit_time=None,
            option_type=option_type,
            strike=strike,
            entry_price=entry_price,
            current_price=entry_price,
            quantity=quantity,
            entry_delta=entry_delta,
            entry_gamma=entry_gamma,
            entry_theta=entry_theta,
            entry_iv=entry_iv,
            sl_price=sl_price,
            target_price=target_price,
            status="OPEN",
            exit_reason=None,
            pnl=0.0,
            pnl_percent=0.0
        )
        
        self.active_trades.append(trade)
        logger.info(f"Trade opened: {trade_id} | {option_type} {strike} @ ₹{entry_price:.2f} | SL: ₹{sl_price:.2f}")
        
        return trade

    def enter_multi_leg_order(
        self,
        underlying: str,
        legs: List[dict],
        expiry_date: Optional[str] = None
    ) -> Optional[dict]:
        """Place a multi-leg options order via OpenAlgo.

        Args:
            underlying: Underlying symbol (e.g., NIFTY)
            legs: List of leg dicts (offset/option_type/action/quantity [and optional pricetype/product/splitsize])
            expiry_date: Common expiry in DDMMMYY (if not per-leg)

        Returns:
            Order response dict or None
        """
        try:
            intent = {
                'type': 'MULTI_LEG_INTENT',
                'underlying': underlying,
                'expiry_date': expiry_date,
                'legs': legs
            }
            logger.log_order(intent)
            resp = self._order_manager.place_options_multi_order(
                strategy=config.STRATEGY_NAME,
                underlying=underlying,
                legs=legs,
                expiry_date=expiry_date
            )
            if resp and resp.get('status') == 'success':
                # Validate multi-order results
                results = resp.get('results')
                if not results or len(results) == 0:
                    if config.PAPER_TRADING:
                        # In paper mode, synthesize per-leg success entries to avoid noisy failures
                        resp['results'] = [
                            {
                                'status': 'success',
                                'orderid': resp.get('orderid'),
                                'leg': leg
                            }
                            for leg in legs
                        ]
                        logger.info("Synthesized multi-order results for paper trading mode")
                    else:
                        logger.error(f"⚠️ Multi-order success but NO RESULTS. Response: {resp}")
                        logger.log_order({'type': 'MULTI_LEG_NO_RESULTS', 'response': resp})
                        return None  # Treat as failure despite success status
                logger.log_order({'type': 'MULTI_LEG_PLACED', 'response': resp})
            else:
                logger.log_order({'type': 'MULTI_LEG_REJECTED', 'response': resp})
            return resp
        except Exception as e:
            logger.error(f"Error in enter_multi_leg_order: {e}")
            return None
    
    def update_trade(
        self,
        trade: Trade,
        current_price: float,
        current_delta: float,
        current_gamma: float,
        current_theta: float,
        current_iv: float,
        current_oi: int,
        prev_oi: int,
        prev_price: float,
        expiry_rules: Optional[dict] = None
    ) -> Optional[str]:
        """
        Update trade with latest data and check exit triggers
        
        Args:
            expiry_rules: Expiry-adjusted rules for strict exits on expiry day
        
        Returns:
            Exit reason if trade should be exited, None otherwise
        """
        
        # Update current price and Greeks
        trade.current_price = current_price
        trade.pnl = (current_price - trade.entry_price) * trade.quantity
        trade.pnl_percent = ((current_price - trade.entry_price) / trade.entry_price * 100) if trade.entry_price > 0 else 0
        
        # Calculate realistic P&L with slippage and fees
        if getattr(config, 'USE_REALISTIC_SLIPPAGE', False) or getattr(config, 'USE_REALISTIC_FEES', False):
            slippage_calc = SlippageCalculator(broker=getattr(config, 'BROKER_NAME', 'angel'))
            
            # Calculate costs (use bid/ask if available, else assume spread of 0.1%)
            bid_price = current_price * 0.9995  # Conservative estimate
            ask_price = current_price * 1.0005
            
            exit_slippage_info = slippage_calc.calculate_exit_slippage(
                ltp=current_price,
                bid=bid_price,
                ask=ask_price,
                quantity=trade.quantity,
                volatility=getattr(config, 'EXIT_SLIPPAGE_VOLATILITY', 'normal')
            )
            
            # For entry, use historical slippage if tracked, else estimate
            entry_slippage = getattr(trade, 'entry_slippage', 0.0)
            exit_slippage = exit_slippage_info['slippage_amount']
            
            # Calculate realistic P&L
            pnl_detail = slippage_calc.calculate_realistic_pnl(
                entry_price=trade.entry_price,
                exit_price=current_price,
                quantity=trade.quantity,
                entry_slippage=entry_slippage,
                exit_slippage=exit_slippage
            )
            
            trade.exit_slippage = exit_slippage
            trade.brokerage_cost = pnl_detail['total_cost']
            trade.net_pnl = pnl_detail['net_pnl']
            trade.net_pnl_percent = pnl_detail['net_pnl_percent']
        
        # Update time in trade
        trade.time_in_trade_sec = int((datetime.now() - trade.entry_time).total_seconds())
        
        # Check exit triggers (with expiry rules if applicable)
        exit_reason = self._check_exit_triggers(
            trade, current_price, current_delta, current_gamma, current_theta, current_iv, current_oi, prev_oi, prev_price, expiry_rules
        )
        
        return exit_reason
    
    def _check_exit_triggers(
        self, trade, current_price, current_delta, current_gamma, current_theta, current_iv, current_oi, prev_oi, prev_price, expiry_rules: Optional[dict] = None
    ) -> Optional[str]:
        """Check all exit trigger rules"""
        
        # EXPIRY-DAY TIME-BASED EXIT (highest priority)
        if expiry_rules:
            min_time = expiry_rules.get('min_time_in_trade', 20)
            max_time = expiry_rules.get('max_time_in_trade', 300)
            
            # If time exceeded max, exit immediately (even if loss)
            if trade.time_in_trade_sec > max_time:
                if trade.pnl > 0:
                    return "expiry_time_based_profit_exit"
                else:
                    return "expiry_time_forced_exit_loss"
            
            # If min time passed and profit is hit, exit
            if trade.time_in_trade_sec > min_time and trade.pnl > 0:
                profit_target = trade.entry_price * (1 + config.ENTRY_PROFIT_TARGET_PERCENT / 100)
                if current_price >= profit_target:
                    return "expiry_time_based_target"
        
        # Trigger 1: Hard SL (absolute)
        if current_price <= trade.sl_price:
            return "hard_sl_hit"
        
        # Trigger 2: Target hit
        if current_price >= trade.target_price:
            return "target_hit"
        
        # Trigger 3: Delta weakness
        delta_degradation = abs(current_delta) / abs(trade.entry_delta) if trade.entry_delta != 0 else 1.0
        if delta_degradation < (1.0 - config.EXIT_DELTA_WEAKNESS_PERCENT / 100):
            return "delta_weakness"
        
        # Trigger 4: Gamma rollover
        if config.EXIT_GAMMA_ROLLOVER and current_gamma <= trade.entry_gamma * 0.8:
            return "gamma_rollover"
        
        # Trigger 5: Theta damage (time decay eating profit)
        if config.EXIT_THETA_DAMAGE_THRESHOLD:
            price_change = abs(current_price - trade.entry_price)
            if price_change < 0.5 and current_theta < trade.entry_theta:
                return "theta_damage"
        
        # Trigger 6: IV crush
        if config.EXIT_IV_CRUSH_PERCENT:
            iv_change_pct = ((current_iv - trade.entry_iv) / trade.entry_iv * 100) if trade.entry_iv > 0 else 0
            price_change = abs(current_price - trade.entry_price)
            if iv_change_pct < config.EXIT_IV_CRUSH_PERCENT and price_change < 1.0:
                return "iv_crush"
        
        # Trigger 7: OI-Price mismatch
        if config.EXIT_OI_PRICE_MISMATCH:
            oi_change = current_oi - prev_oi
            if oi_change > 100 and abs(current_price - prev_price) < 0.5:
                return "oi_price_mismatch"
        
        return None
    
    def exit_trade(self, trade: Trade, exit_reason: str) -> Trade:
        """
        Exit a trade
        
        Returns:
            Updated Trade object with exit details
        """
        trade.exit_time = datetime.now()
        trade.exit_reason = exit_reason
        
        if trade.pnl > 0:
            trade.status = "CLOSED_PROFIT"
        elif trade.pnl < 0:
            trade.status = "CLOSED_LOSS"
        else:
            trade.status = "CLOSED"
        
        self.active_trades.remove(trade)
        self.closed_trades.append(trade)
        
        duration = (trade.exit_time - trade.entry_time).total_seconds()
        
        logger.info(
            f"Trade closed: {trade.trade_id} | Exit: {exit_reason} | "
            f"PnL: ₹{trade.pnl:.2f} ({trade.pnl_percent:+.2f}%) | Duration: {duration:.0f}s"
        )
        
        return trade
    
    def get_active_trades(self) -> List[Trade]:
        """Get active trades"""
        return self.active_trades.copy()
    
    def get_closed_trades(self) -> List[Trade]:
        """Get closed trades"""
        return self.closed_trades.copy()
    
    def get_trade_statistics(self) -> dict:
        """Get trading statistics"""
        all_trades = self.closed_trades
        
        if not all_trades:
            return {
                'total': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0
            }
        
        total = len(all_trades)
        wins = sum(1 for t in all_trades if t.pnl > 0)
        losses = sum(1 for t in all_trades if t.pnl < 0)
        win_rate = (wins / total * 100) if total > 0 else 0
        total_pnl = sum(t.pnl for t in all_trades)
        avg_pnl = total_pnl / total if total > 0 else 0
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl
        }
