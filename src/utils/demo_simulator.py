"""
Demo Data Simulator - Generates realistic market data for testing
Provides synthetic NIFTY ticks with realistic Greeks, OI, volume patterns
"""

import time
import math
import random
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class DemoTick:
    """Synthetic market tick data"""
    timestamp: datetime
    symbol: str
    ltp: float
    bid: float
    ask: float
    high: float
    low: float
    open: float
    close: float
    volume: int
    oi: int
    source: str = "DEMO"


class DemoDataSimulator:
    """
    Generates realistic NIFTY price movement with Greeks patterns
    Simulates realistic market microstructure for testing
    """
    
    def __init__(self, start_price=25900, volatility=0.15):
        """
        Initialize simulator
        
        Args:
            start_price: Starting NIFTY price
            volatility: Daily volatility (15% = typical)
        """
        self.start_price = start_price
        self.current_price = start_price
        self.volatility = volatility
        self.tick_count = 0
        
        # Market microstructure
        self.bid_ask_spread = 5  # NIFTY typical spread
        self.volume_base = 500000
        self.oi_base = 1000000
        
        # Bias patterns
        self.bias_state = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL
        self.trend_direction = 1  # 1 = up, -1 = down
        self.trend_strength = random.uniform(0.3, 0.8)
        
        # Greeks state
        self.atm_delta = 0.5
        self.atm_gamma = 0.003
        self.atm_theta = -0.02
        self.atm_vega = 25.0
        
    def generate_tick(self) -> DemoTick:
        """Generate next realistic market tick"""
        self.tick_count += 1
        current_time = datetime.now()
        
        # Brownian motion with trend + mean reversion
        dt = 1/252/6.5/60  # 1 minute in annual terms
        dW = random.gauss(0, 1)
        
        # Trend component (changes bias state occasionally)
        if self.tick_count % 300 == 0:  # Every 5 minutes
            self.trend_direction = random.choice([1, -1])
            self.trend_strength = random.uniform(0.2, 0.7)
            new_bias = random.choice(["BULLISH", "BEARISH", "NEUTRAL"])
            if new_bias != self.bias_state:
                self.bias_state = new_bias
        
        trend_component = self.trend_direction * self.trend_strength * 0.01
        
        # Price update (GBM)
        price_change = (trend_component + self.volatility * math.sqrt(dt) * dW) * self.current_price
        self.current_price += price_change
        
        # Realistic bounds
        self.current_price = max(25500, min(26500, self.current_price))
        
        # Market microstructure
        bid = self.current_price - self.bid_ask_spread / 2
        ask = self.current_price + self.bid_ask_spread / 2
        ltp = (bid + ask) / 2
        
        # OHLC
        if self.tick_count % 60 == 1:  # New candle
            self.candle_open = ltp
            self.candle_high = ltp
            self.candle_low = ltp
        else:
            self.candle_high = max(self.candle_high, ltp)
            self.candle_low = min(self.candle_low, ltp)
        
        # Volume/OI patterns
        volume_noise = random.uniform(0.7, 1.3)
        volume = int(self.volume_base * volume_noise)
        
        # OI increases with rising price (momentum)
        price_momentum = (ltp - self.start_price) / self.start_price
        oi_factor = 1 + price_momentum * 0.5
        oi = int(self.oi_base * oi_factor * random.uniform(0.9, 1.1))
        
        # Greeks update
        self._update_greeks(ltp)
        
        return DemoTick(
            timestamp=current_time,
            symbol="NIFTY",
            ltp=ltp,
            bid=bid,
            ask=ask,
            high=self.candle_high,
            low=self.candle_low,
            open=self.candle_open,
            close=ltp,
            volume=volume,
            oi=oi
        )
    
    def _update_greeks(self, spot_price: float):
        """Update synthetic Greeks based on spot price"""
        # Delta: moves with spot
        price_change_percent = (spot_price - self.start_price) / self.start_price
        self.atm_delta = 0.5 + price_change_percent * 0.1
        self.atm_delta = max(0.3, min(0.7, self.atm_delta))
        
        # Gamma: peaks at ATM, decreases away
        gamma_factor = max(0, 1 - abs(price_change_percent * 2))
        self.atm_gamma = 0.003 * gamma_factor
        
        # Theta: negative, increases with time decay
        self.atm_theta = -0.02 - (self.tick_count / 1000) * 0.001
        
        # Vega: volatility sensitivity
        self.atm_vega = 25 + random.uniform(-2, 2)
    
    def get_greeks(self, strike: int, option_type: str = "CE") -> Dict:
        """Get synthetic Greeks for given strike"""
        atm_strike = 25950
        strike_diff = strike - atm_strike
        
        # Adjust delta based on strike
        if option_type == "CE":
            delta = self.atm_delta - (strike_diff / 1000)
        else:  # PE
            delta = -(1 - self.atm_delta) - (strike_diff / 1000)
        
        delta = max(-1, min(1, delta))
        
        return {
            'delta': delta,
            'gamma': max(0, self.atm_gamma - abs(strike_diff) / 10000),
            'theta': self.atm_theta,
            'vega': self.atm_vega,
            'iv': 15.0 + random.uniform(-2, 2),
            'option_price': max(1, 100 + strike_diff * -0.1)
        }
    
    def get_bias_state(self) -> str:
        """Get current market bias"""
        return self.bias_state
    
    def get_price_history(self, count: int = 20) -> List[float]:
        """Get recent price history for indicator calculation"""
        return [self.current_price * (1 + random.uniform(-0.01, 0.01)) for _ in range(count)]


# Global simulator instance
_demo_simulator = None


def get_demo_simulator() -> DemoDataSimulator:
    """Get or create global demo simulator"""
    global _demo_simulator
    if _demo_simulator is None:
        _demo_simulator = DemoDataSimulator()
    return _demo_simulator


def reset_demo_simulator():
    """Reset simulator for new test session"""
    global _demo_simulator
    _demo_simulator = None
