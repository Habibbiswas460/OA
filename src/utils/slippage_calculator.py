"""
Slippage and Fees Calculator
Models realistic market impact and costs for options trading
"""

from typing import Dict, Optional
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class SlippageCalculator:
    """
    Calculate realistic slippage and brokerage fees
    
    Based on:
    - Spread width (volatile vs stable markets)
    - Quantity traded (larger orders = more slippage)
    - Market conditions (VIX, liquidity)
    - Broker fees (Angel, Zerodha, Fyers)
    """
    
    # Broker fee structures (per contract, options)
    BROKER_FEES = {
        'angel': {
            'commission_percent': 0.0,  # Angel charges flat fee, not percent
            'flat_fee_per_lot': 20,     # ₹20 per lot
            'gst_percent': 18,          # GST on brokerage
            'exchange_turnover_charge': 0.00015,  # 0.015% turnover charge
            'ssi_charge': 0.0001,       # 0.01% SSI charge
        },
        'zerodha': {
            'commission_percent': 0.0,
            'flat_fee_per_lot': 20,
            'gst_percent': 18,
            'exchange_turnover_charge': 0.00015,
            'ssi_charge': 0.0001,
        },
        'fyers': {
            'commission_percent': 0.0,
            'flat_fee_per_lot': 15,     # Slightly cheaper
            'gst_percent': 18,
            'exchange_turnover_charge': 0.00015,
            'ssi_charge': 0.0001,
        }
    }
    
    def __init__(self, broker: str = 'angel'):
        """
        Initialize slippage calculator
        
        Args:
            broker: Broker name (angel, zerodha, fyers)
        """
        self.broker = broker.lower()
        self.fees = self.BROKER_FEES.get(self.broker, self.BROKER_FEES['angel'])
        logger.info(f"SlippageCalculator initialized for {self.broker}")
    
    def calculate_entry_slippage(self, 
                                  ltp: float,
                                  bid: float,
                                  ask: float,
                                  quantity: int,
                                  volatility: str = 'normal') -> Dict:
        """
        Calculate slippage for ENTRY (buying at ask)
        
        Args:
            ltp: Last Traded Price
            bid: Bid price
            ask: Ask price
            quantity: Order quantity (75 = 1 lot for NIFTY options)
            volatility: 'low', 'normal', 'high'
        
        Returns:
            {
                'slippage_amount': float,
                'slippage_percent': float,
                'effective_price': float,
                'mid_price': float
            }
        """
        spread = ask - bid
        spread_percent = (spread / ltp * 100) if ltp > 0 else 0
        mid_price = (bid + ask) / 2
        
        # Slippage model based on spread and volatility
        slippage_multiplier = {
            'low': 0.25,        # We get 25% of half-spread
            'normal': 0.50,     # We get 50% of half-spread  
            'high': 1.0         # We get full half-spread (worst case)
        }.get(volatility, 0.50)
        
        # Slippage in rupees
        slippage_amount = (spread / 2) * slippage_multiplier
        
        # For large orders, additional slippage (market impact)
        if quantity > 150:  # More than 2 lots
            market_impact = (quantity / 150 - 1) * 0.05  # 5% additional per lot
            slippage_amount *= (1 + market_impact)
        
        effective_price = ask + slippage_amount
        slippage_percent = (slippage_amount / ltp * 100) if ltp > 0 else 0
        
        logger.debug(f"Entry Slippage: LTP={ltp:.2f}, Spread={spread:.2f} ({spread_percent:.2f}%), "
                    f"Slippage={slippage_amount:.2f} ({slippage_percent:.2f}%)")
        
        return {
            'slippage_amount': slippage_amount,
            'slippage_percent': slippage_percent,
            'effective_price': effective_price,
            'mid_price': mid_price,
            'spread_width': spread,
            'spread_percent': spread_percent
        }
    
    def calculate_exit_slippage(self,
                                ltp: float,
                                bid: float,
                                ask: float,
                                quantity: int,
                                volatility: str = 'normal') -> Dict:
        """
        Calculate slippage for EXIT (selling at bid)
        
        Args:
            ltp: Last Traded Price
            bid: Bid price
            ask: Ask price
            quantity: Order quantity
            volatility: Market volatility level
        
        Returns:
            Slippage details dictionary
        """
        spread = ask - bid
        spread_percent = (spread / ltp * 100) if ltp > 0 else 0
        mid_price = (bid + ask) / 2
        
        # Exit slippage (selling at bid - adverse)
        slippage_multiplier = {
            'low': 0.25,
            'normal': 0.50,
            'high': 1.0
        }.get(volatility, 0.50)
        
        slippage_amount = (spread / 2) * slippage_multiplier
        
        # Market impact for large orders
        if quantity > 150:
            market_impact = (quantity / 150 - 1) * 0.05
            slippage_amount *= (1 + market_impact)
        
        effective_price = bid - slippage_amount
        slippage_percent = (slippage_amount / ltp * 100) if ltp > 0 else 0
        
        logger.debug(f"Exit Slippage: LTP={ltp:.2f}, Spread={spread:.2f} ({spread_percent:.2f}%), "
                    f"Slippage={slippage_amount:.2f} ({slippage_percent:.2f}%)")
        
        return {
            'slippage_amount': slippage_amount,
            'slippage_percent': slippage_percent,
            'effective_price': effective_price,
            'mid_price': mid_price,
            'spread_width': spread,
            'spread_percent': spread_percent
        }
    
    def calculate_brokerage_and_taxes(self,
                                     entry_price: float,
                                     exit_price: float,
                                     quantity: int) -> Dict:
        """
        Calculate total brokerage and tax costs
        
        Args:
            entry_price: Entry price per contract
            exit_price: Exit price per contract
            quantity: Number of contracts
        
        Returns:
            {
                'entry_brokerage': float,
                'exit_brokerage': float,
                'total_brokerage': float,
                'gst': float,
                'turnover_charge': float,
                'ssi_charge': float,
                'total_cost': float
            }
        """
        lots = quantity / 75  # NIFTY option lot = 75 qty
        
        # Flat fee per lot
        flat_fee = self.fees['flat_fee_per_lot'] * lots
        
        # Entry and exit transactions (both ways)
        entry_turnover = entry_price * quantity
        exit_turnover = exit_price * quantity
        total_turnover = entry_turnover + exit_turnover
        
        # Turnover charges
        turnover_charge = total_turnover * self.fees['exchange_turnover_charge']
        
        # SSI charge (Securities transaction tax for options)
        ssi_charge = total_turnover * self.fees['ssi_charge']
        
        # GST on brokerage (only on flat fee, not on turnover charges)
        brokerage_before_gst = flat_fee * 2  # Both entry and exit
        gst = brokerage_before_gst * (self.fees['gst_percent'] / 100)
        
        total_cost = brokerage_before_gst + gst + turnover_charge + ssi_charge
        
        logger.debug(f"Brokerage Breakdown (qty={quantity}, lots={lots:.2f}):")
        logger.debug(f"  Flat Fee: ₹{flat_fee*2:.2f}")
        logger.debug(f"  GST (18%): ₹{gst:.2f}")
        logger.debug(f"  Turnover Charge: ₹{turnover_charge:.2f}")
        logger.debug(f"  SSI Charge: ₹{ssi_charge:.2f}")
        logger.debug(f"  Total: ₹{total_cost:.2f}")
        
        return {
            'entry_brokerage': flat_fee,
            'exit_brokerage': flat_fee,
            'total_brokerage': flat_fee * 2,
            'gst': gst,
            'turnover_charge': turnover_charge,
            'ssi_charge': ssi_charge,
            'total_cost': total_cost,
            'cost_per_contract': total_cost / quantity if quantity > 0 else 0
        }
    
    def calculate_realistic_pnl(self,
                               entry_price: float,
                               exit_price: float,
                               quantity: int,
                               entry_slippage: float = 0.0,
                               exit_slippage: float = 0.0) -> Dict:
        """
        Calculate P&L accounting for slippage and fees
        
        Args:
            entry_price: Entry price (LTP, not effective)
            exit_price: Exit price (LTP, not effective)
            quantity: Number of contracts
            entry_slippage: Slippage amount on entry
            exit_slippage: Slippage amount on exit
        
        Returns:
            {
                'gross_pnl': float,         # Without costs
                'slippage_cost': float,     # Total slippage impact
                'brokerage_cost': float,    # All fees
                'net_pnl': float,          # After all costs
                'net_pnl_percent': float,
                'breakeven_price': float   # Price needed to breakeven
            }
        """
        # Gross P&L (price difference only)
        price_diff = exit_price - entry_price
        gross_pnl = price_diff * quantity
        
        # Slippage costs (both entry and exit)
        slippage_cost = (entry_slippage + exit_slippage) * quantity
        
        # Brokerage costs
        fees_detail = self.calculate_brokerage_and_taxes(entry_price, exit_price, quantity)
        brokerage_cost = fees_detail['total_cost']
        
        # Net P&L
        net_pnl = gross_pnl - slippage_cost - brokerage_cost
        
        # Net P&L %
        capital_at_risk = entry_price * quantity
        net_pnl_percent = (net_pnl / capital_at_risk * 100) if capital_at_risk > 0 else 0
        
        # Breakeven price (what exit price needed to make 0 P&L)
        total_costs_per_contract = (slippage_cost + brokerage_cost) / quantity if quantity > 0 else 0
        breakeven_price = entry_price + total_costs_per_contract
        
        logger.info(f"Realistic P&L Calculation:")
        logger.info(f"  Gross P&L: ₹{gross_pnl:.2f}")
        logger.info(f"  Slippage Cost: ₹{slippage_cost:.2f}")
        logger.info(f"  Brokerage Cost: ₹{brokerage_cost:.2f}")
        logger.info(f"  Net P&L: ₹{net_pnl:.2f} ({net_pnl_percent:.2f}%)")
        logger.info(f"  Breakeven Price: ₹{breakeven_price:.2f}")
        
        return {
            'gross_pnl': gross_pnl,
            'slippage_cost': slippage_cost,
            'brokerage_cost': brokerage_cost,
            'net_pnl': net_pnl,
            'net_pnl_percent': net_pnl_percent,
            'breakeven_price': breakeven_price,
            **fees_detail
        }
