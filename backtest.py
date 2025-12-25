"""
ANGEL-X Backtesting System
Test ANGEL-X strategy with historical data

Simulates real trading conditions:
- Historical price data
- Greek values simulation
- Trade execution with slippage
- Risk management rules
- Exit conditions (Greek-based)

Usage:
    python backtest.py --start 2024-01-01 --end 2024-12-31 --capital 100000
"""

import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional
import json

# Configuration
from config import config

# Strategy components
from src.engines.bias_engine import BiasEngine, BiasState
from src.engines.entry_engine import EntryEngine, EntrySignal
from src.engines.strike_selection_engine import StrikeSelectionEngine
from src.engines.trap_detection_engine import TrapDetectionEngine
from src.core.position_sizing import PositionSizing
from src.core.trade_manager import Trade


class BacktestMarketData:
    """Simulated market data for backtesting"""
    
    def __init__(self, data_file: Optional[str] = None):
        """Initialize with historical data"""
        self.data = None
        self.current_idx = 0
        
        if data_file:
            self.load_from_file(data_file)
        else:
            self.generate_sample_data()
    
    def load_from_file(self, file_path: str, timestamp_col: Optional[str] = None, date_col: Optional[str] = None, time_col: Optional[str] = None):
        """Load historical data from CSV with flexible schema"""
        print(f"📊 Loading historical data from {file_path}...")
        df = pd.read_csv(file_path)

        # Normalize column names to lowercase
        df.columns = [str(c).strip().lower() for c in df.columns]

        # Determine timestamp
        ts_col = (timestamp_col.lower() if timestamp_col else None)
        dt_col = (date_col.lower() if date_col else None)
        tm_col = (time_col.lower() if time_col else None)

        # Auto-detect if not provided
        if not ts_col:
            for cand in ['timestamp', 'datetime', 'date_time', 'ts']:
                if cand in df.columns:
                    ts_col = cand
                    break

        if ts_col and ts_col in df.columns:
            df['timestamp'] = pd.to_datetime(df[ts_col])
        else:
            # Try combining date + time
            if not dt_col:
                for cand in ['date']:
                    if cand in df.columns:
                        dt_col = cand
                        break
            if not tm_col:
                for cand in ['time']:
                    if cand in df.columns:
                        tm_col = cand
                        break

            if dt_col and tm_col and dt_col in df.columns and tm_col in df.columns:
                df['timestamp'] = pd.to_datetime(df[dt_col].astype(str) + ' ' + df[tm_col].astype(str))
            else:
                raise ValueError("Unable to determine timestamp column. Provide --timestamp-col or --date-col and --time-col.")

        # Map OHLCV columns (support common variants)
        col_map = {
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'volume': None,
        }

        for key in list(col_map.keys()):
            if key in df.columns:
                col_map[key] = key
        # Try alternate names
        alternates = {
            'open': ['o', 'opn'],
            'high': ['h', 'hi'],
            'low': ['l', 'lo'],
            'close': ['c', 'cls', 'price'],
            'volume': ['vol', 'qty']
        }
        for k, alts in alternates.items():
            if col_map[k] is None:
                for cand in alts:
                    if cand in df.columns:
                        col_map[k] = cand
                        break

        # If any OHLC missing, try to synthesize from close
        base_close = col_map['close']
        if base_close is None:
            raise ValueError("CSV must include a close/price column.")
        for k in ['open', 'high', 'low']:
            if col_map[k] is None:
                df[k] = df[base_close]
                col_map[k] = k
        if col_map['volume'] is None:
            df['volume'] = 0
            col_map['volume'] = 'volume'

        # Build normalized DataFrame
        self.data = df[['timestamp', col_map['open'], col_map['high'], col_map['low'], col_map['close'], col_map['volume']]].copy()
        self.data.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

        # Coerce numeric types
        for c in ['open', 'high', 'low', 'close', 'volume']:
            self.data[c] = pd.to_numeric(self.data[c], errors='coerce')

        # Drop rows with missing timestamp or close
        self.data = self.data.dropna(subset=['timestamp', 'close'])

        # Sort by time
        self.data = self.data.sort_values('timestamp').reset_index(drop=True)
        print(f"   Loaded {len(self.data)} candles")
    
    def generate_sample_data(self, days: int = 30):
        """Generate sample NIFTY data for testing"""
        print(f"📊 Generating sample data for {days} days...")
        
        # Start from 30 days ago
        start_date = datetime.now() - timedelta(days=days)
        
        # Generate 1-minute candles for trading hours (9:15 AM - 3:30 PM)
        timestamps = []
        current = start_date.replace(hour=9, minute=15, second=0)
        
        while current < datetime.now():
            # Only during trading hours
            if time(9, 15) <= current.time() <= time(15, 30):
                timestamps.append(current)
                current += timedelta(minutes=1)
            else:
                # Skip to next day
                current = (current + timedelta(days=1)).replace(hour=9, minute=15)
        
        # Base NIFTY price around 22000
        base_price = 22000
        
        data = []
        prev_close = base_price
        
        for ts in timestamps:
            # Random walk with trend
            change = np.random.randn() * 20  # ±20 points volatility
            trend = 5 if np.random.random() > 0.5 else -5  # Small trend
            
            open_price = prev_close + change
            high = open_price + abs(np.random.randn() * 15)
            low = open_price - abs(np.random.randn() * 15)
            close = (high + low) / 2 + trend
            
            volume = int(1000000 + np.random.randn() * 200000)
            
            data.append({
                'timestamp': ts,
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })
            
            prev_close = close
        
        self.data = pd.DataFrame(data)
        print(f"   Generated {len(self.data)} candles")
    
    def get_next_candle(self) -> Optional[Dict]:
        """Get next candle for simulation"""
        if self.current_idx >= len(self.data):
            return None
        
        candle = self.data.iloc[self.current_idx].to_dict()
        self.current_idx += 1
        return candle
    
    def get_lookback_candles(self, n: int) -> pd.DataFrame:
        """Get last N candles for analysis"""
        start = max(0, self.current_idx - n)
        return self.data.iloc[start:self.current_idx]
    
    def reset(self):
        """Reset to beginning"""
        self.current_idx = 0


class BacktestGreeksSimulator:
    """Simulate Greeks for option prices"""
    
    @staticmethod
    def calculate_greeks(spot: float, strike: int, time_to_expiry_days: int,
                        option_type: str = 'CE') -> Dict:
        """
        Simplified Greeks calculation
        Real backtesting should use proper Black-Scholes
        """
        # Moneyness
        moneyness = (spot - strike) / strike
        
        # Time decay factor
        time_factor = max(0.1, time_to_expiry_days / 7.0)
        
        # Simplified calculations (approximations)
        if option_type == 'CE':
            # Call option
            if moneyness > 0:  # ITM
                delta = 0.7 + (moneyness * 20)
                premium = max(spot - strike, 0) + (time_factor * 50)
            elif moneyness > -0.01:  # ATM
                delta = 0.5
                premium = time_factor * 100
            else:  # OTM
                delta = 0.2 + (abs(moneyness) * 10)
                premium = time_factor * 30
        else:
            # Put option (mirror)
            if moneyness < 0:  # ITM
                delta = -0.7 - (abs(moneyness) * 20)
                premium = max(strike - spot, 0) + (time_factor * 50)
            elif moneyness < 0.01:  # ATM
                delta = -0.5
                premium = time_factor * 100
            else:  # OTM
                delta = -0.2 - (moneyness * 10)
                premium = time_factor * 30
        
        # Other Greeks (simplified)
        gamma = 0.05 * time_factor
        theta = -premium / (time_to_expiry_days + 1)  # Daily decay
        vega = premium * 0.1
        iv = 15 + np.random.randn() * 3  # IV around 15%
        
        return {
            'premium': round(premium, 2),
            'delta': round(delta, 4),
            'gamma': round(gamma, 4),
            'theta': round(theta, 2),
            'vega': round(vega, 2),
            'iv': round(iv, 2)
        }


class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(self, initial_capital: float = 100000, risk_per_trade: float = 0.04, sl_percent: float = 0.10, daily_kill_pct: float = 0.05, target_percent: float = 0.12):
        """Initialize backtesting engine"""
        print("\n" + "="*80)
        print("ANGEL-X BACKTESTING ENGINE (OPTIMIZED)")
        print("="*80)
        
        self.initial_capital = initial_capital
        self.capital = initial_capital
        
        # User-configurable risk settings
        self.risk_per_trade = risk_per_trade  # e.g., 0.04 for 4%
        self.sl_percent = sl_percent          # e.g., 0.10 for 10% SL on premium
        self.target_percent = target_percent  # e.g., 0.12 for 12% target
        
        # Market data
        self.market_data = BacktestMarketData()
        self.greeks_simulator = BacktestGreeksSimulator()
        
        # Strategy components
        self.bias_engine = BiasEngine()
        # Enable trap detection in backtest
        self.trap_detection = TrapDetectionEngine()
        self.entry_engine = EntryEngine(self.bias_engine, self.trap_detection)
        self.position_sizing = PositionSizing()
        
        # Trade tracking
        self.trades: List[Trade] = []
        self.current_position: Optional[Trade] = None
        
        # Statistics
        self.stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'current_drawdown': 0,
            'peak_capital': initial_capital,
            'avg_win': 0,
            'avg_loss': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_fees': 0,
            'trades_skipped_daily_limit': 0
        }
        
        # Expiry tracking (weekly)
        self.current_expiry_date = None
        self.days_to_expiry = 5
        
        # Risk management - IMPROVED
        self.daily_kill_pct = daily_kill_pct  # e.g., 0.05 for 5% daily kill
        self.consecutive_losses = 0
        self.consecutive_wins = 0

        # Per-day tracking for kill-switch
        self.current_day: Optional[datetime] = None
        self.day_start_capital: float = self.capital
        self.day_loss_limit_amount: float = self.day_start_capital * self.daily_kill_pct
        self.day_kill_active: bool = False
        
        print(f"✅ Initial Capital: ₹{initial_capital:,.2f}")
        print(f"✅ Risk per trade:  {self.risk_per_trade*100:.1f}%")
        print(f"✅ Stop-loss:       {self.sl_percent*100:.1f}% of premium")
        print(f"✅ Target:          {self.target_percent*100:.1f}% of premium")
        print(f"✅ Daily Kill-Switch: {self.daily_kill_pct*100:.1f}% of day start capital")
        print(f"✅ Risk Management: Consecutive loss tracking")
        print("="*80)
    
    def is_trading_hours(self, timestamp: datetime) -> bool:
        """Check if within trading hours"""
        t = timestamp.time()
        
        # Session hours
        if not (time(9, 15) <= t <= time(15, 30)):
            return False
        
        # No trade zone (opening)
        if time(9, 15) <= t <= time(9, 20):
            return False
        
        # No trade zone (closing)
        if t >= time(14, 45):
            return False
        
        return True
    
    def update_expiry(self, current_date: datetime):
        """Update days to expiry (weekly cycle)"""
        weekday = current_date.weekday()  # 0=Monday, 3=Thursday
        
        # Assuming weekly expiry on Thursday
        if weekday < 3:  # Monday to Wednesday
            self.days_to_expiry = 3 - weekday
        elif weekday == 3:  # Thursday (expiry day)
            self.days_to_expiry = 0
        else:  # Friday (new cycle starts)
            self.days_to_expiry = 5
        
        # Avoid expiry day trading
        if self.days_to_expiry == 0:
            return False
        
        return True
    
    def calculate_slippage(self, price: float, is_entry: bool = True) -> float:
        """Add realistic slippage"""
        # Entry: slightly worse price, Exit: slightly worse price
        slippage_pct = 0.0005  # 0.05% slippage
        
        if is_entry:
            return price * (1 + slippage_pct)
        else:
            return price * (1 - slippage_pct)
    
    def calculate_fees(self, quantity: int, price: float) -> float:
        """Calculate transaction fees"""
        # Simplified fee: 0.05% of trade value
        trade_value = quantity * price
        return trade_value * 0.0005
    
    def check_entry_conditions(self, candle: Dict) -> Optional[Dict]:
        """Check if entry conditions are met with time filters and quality checks"""
        spot = candle['close']
        timestamp = candle['timestamp']
        
        # Not in general trading hours
        if not self.is_trading_hours(timestamp):
            return None

        # Time-window filters
        t = timestamp.time()
        in_primary_window = (t >= time(14, 0)) and (t <= time(14, 30))  # Reduced from 14:45 to 14:30
        in_secondary_window = (t >= time(9, 25)) and (t <= time(10, 0))
        in_avoid_window_1 = (t >= time(10, 0)) and (t <= time(11, 0))
        in_avoid_window_2 = (t >= time(12, 0)) and (t <= time(13, 30))

        # Avoid worst hours completely
        if in_avoid_window_1 or in_avoid_window_2:
            return None

        # Only allow primary and secondary windows
        if not (in_primary_window or in_secondary_window):
            return None
        
        # Already in position
        if self.current_position:
            return None
        
        # Daily kill-switch check (per-day 5% default)
        day_loss = self.day_start_capital - self.capital
        if self.day_kill_active or (day_loss >= self.day_loss_limit_amount):
            self.day_kill_active = True
            self.stats['trades_skipped_daily_limit'] += 1
            return None
        
        # Update bias (simplified for backtesting)
        lookback = self.market_data.get_lookback_candles(20)
        if len(lookback) < 10:
            return None
        
        # Trend detection with momentum
        recent_high = lookback['high'].tail(5).max()
        recent_low = lookback['low'].tail(5).min()
        prev_high = lookback['high'].tail(10).head(5).max()
        prev_low = lookback['low'].tail(10).head(5).min()
        
        price_range = recent_high - recent_low
        
        if price_range == 0:
            return None
        
        # Current price position in range
        price_position = (spot - recent_low) / price_range
        
        # Bias by price position
        if price_position > 0.60:  # Upper 40% - Bullish signal
            bias_state = BiasState.BULLISH
        elif price_position < 0.40:  # Lower 40% - Bearish signal
            bias_state = BiasState.BEARISH
        else:
            return None  # Neutral zone - NO TRADE
        
        # Determine option type
        option_type = 'CE' if bias_state == BiasState.BULLISH else 'PE'
        
        # Both windows require HH/LL confirmation (momentum filter)
        if in_secondary_window or in_primary_window:
            if option_type == 'CE' and not (recent_high > prev_high):
                return None
            if option_type == 'PE' and not (recent_low < prev_low):
                return None
        
        # Select strike (ATM for simplicity)
        strike = round(spot / 100) * 100  # Round to nearest 100
        
        # Calculate Greeks
        greeks = self.greeks_simulator.calculate_greeks(
            spot, strike, self.days_to_expiry, option_type
        )
        
        # Greeks filters
        # Base thresholds
        delta_min = 0.33
        iv_min = 10

        # Secondary window: tighten thresholds
        if in_secondary_window:
            delta_min = 0.40
            iv_min = 15

        # (If avoid windows ever enabled, keep stricter delta)
        if in_avoid_window_1 or in_avoid_window_2:
            delta_min = max(delta_min, 0.40)

        if greeks['premium'] < 50 or abs(greeks['delta']) < delta_min:
            return None

        # IV filter: window-aware
        if greeks['iv'] < iv_min:
            return None

        # Simple spread/liquidity check: skip if simulated spread > 1%
        simulated_spread_pct = (price_range / max(spot, 1e-6))
        if simulated_spread_pct > 0.01:
            return None
        
        return {
            'spot': spot,
            'strike': strike,
            'option_type': option_type,
            'entry_price': greeks['premium'],
            'entry_delta': greeks['delta'],
            'entry_gamma': greeks['gamma'],
            'entry_theta': greeks['theta'],
            'entry_iv': greeks['iv'],
            'timestamp': timestamp
        }
    
    def enter_trade(self, entry_signal: Dict):
        """Enter a new trade - Time-aware risk and fixed SL"""
        ts = entry_signal['timestamp']
        t = ts.time()
        in_primary_window = (t >= time(14, 0)) and (t <= time(14, 45))
        in_secondary_window = (t >= time(9, 25)) and (t <= time(10, 0))
        in_avoid_window_1 = (t >= time(10, 0)) and (t <= time(11, 0))
        in_avoid_window_2 = (t >= time(12, 0)) and (t <= time(13, 30))

        # Hour-based dynamic position sizing
        if in_secondary_window:
            risk_pct = self.risk_per_trade  # 4% for best-performing 09:25-10:00 window
        elif in_primary_window:
            risk_pct = self.risk_per_trade * 0.625  # 2.5% for break-even 14:00-14:30 window
        else:
            risk_pct = 0.02  # Fallback for any edge cases
        risk_amount = self.capital * risk_pct
        
        # Stop-loss distance based on premium percentage (e.g., 10%)
        sl_distance = entry_signal['entry_price'] * self.sl_percent
        
        # Quantity calculation
        quantity = min(
            int(risk_amount / sl_distance),
            config.MINIMUM_LOT_SIZE * 2  # Max 2 lots
        )
        quantity = max(quantity, config.MINIMUM_LOT_SIZE)  # Min 1 lot
        
        # Apply slippage
        actual_entry_price = self.calculate_slippage(entry_signal['entry_price'], is_entry=True)
        
        # Calculate fees
        fees = self.calculate_fees(quantity, actual_entry_price)
        self.stats['total_fees'] += fees
        
        # SL and Target
        sl_price = actual_entry_price * (1 - self.sl_percent)  # e.g., 10% SL
        target_price = actual_entry_price * (1 + self.target_percent)  # Configurable target
        
        # Create trade
        trade_id = f"BT_{entry_signal['timestamp'].strftime('%Y%m%d_%H%M%S')}"
        
        self.current_position = Trade(
            trade_id=trade_id,
            entry_time=entry_signal['timestamp'],
            exit_time=None,
            option_type=entry_signal['option_type'],
            strike=entry_signal['strike'],
            entry_price=actual_entry_price,
            current_price=actual_entry_price,
            quantity=quantity,
            entry_delta=entry_signal['entry_delta'],
            entry_gamma=entry_signal['entry_gamma'],
            entry_theta=entry_signal['entry_theta'],
            entry_iv=entry_signal['entry_iv'],
            sl_price=sl_price,
            target_price=target_price,
            status='OPEN',
            exit_reason=None,
            pnl=0,
            pnl_percent=0,
            time_in_trade_sec=0
        )
        
        print(f"\n📈 ENTRY: {trade_id}")
        print(f"   {entry_signal['option_type']} {entry_signal['strike']} @ ₹{actual_entry_price:.2f}")
        print(f"   Qty: {quantity} | Risk: {risk_pct*100:.1f}% | SL: ₹{sl_price:.2f} | Target: ₹{target_price:.2f}")
    
    def check_exit_conditions(self, candle: Dict) -> Optional[str]:
        """Check if exit conditions are met - IMPROVED: Tighter exits"""
        if not self.current_position:
            return None
        
        spot = candle['close']
        
        # Recalculate Greeks
        greeks = self.greeks_simulator.calculate_greeks(
            spot, 
            self.current_position.strike,
            self.days_to_expiry,
            self.current_position.option_type
        )
        
        current_price = greeks['premium']
        
        # Update current price
        self.current_position.current_price = current_price
        
        # Calculate PnL
        pnl = (current_price - self.current_position.entry_price) * self.current_position.quantity
        pnl_pct = ((current_price - self.current_position.entry_price) / self.current_position.entry_price) * 100
        
        # Hard SL - exit immediately
        if current_price <= self.current_position.sl_price:
            return 'SL_HIT'
        
        # Target - take profit
        if current_price >= self.current_position.target_price:
            return 'TARGET_HIT'
        
        # IMPROVED: Better Greek-based exits with optimal thresholds
        # Delta weakness (18% degradation from entry)
        delta_change = abs(greeks['delta'] - self.current_position.entry_delta) / abs(self.current_position.entry_delta)
        if delta_change > 0.18:
            return 'DELTA_WEAKNESS'
        
        # Gamma rollover (peak passed significantly)
        if greeks['gamma'] < self.current_position.entry_gamma * 0.75:
            return 'GAMMA_ROLLOVER'
        
        # Time limit: 25 minutes (good balance for scalping)
        time_in_trade = (candle['timestamp'] - self.current_position.entry_time).seconds
        if time_in_trade > 1500:  # 25 minutes
            return 'TIME_LIMIT'
        
        return None
    
    def exit_trade(self, candle: Dict, exit_reason: str):
        """Exit current position - IMPROVED: Track consecutive wins/losses"""
        if not self.current_position:
            return
        
        # Apply slippage
        exit_price = self.calculate_slippage(self.current_position.current_price, is_entry=False)
        
        # Calculate fees
        fees = self.calculate_fees(self.current_position.quantity, exit_price)
        self.stats['total_fees'] += fees
        
        # Calculate final PnL
        pnl = (exit_price - self.current_position.entry_price) * self.current_position.quantity
        pnl -= fees  # Deduct fees
        
        pnl_pct = ((exit_price - self.current_position.entry_price) / self.current_position.entry_price) * 100
        
        # Update trade
        self.current_position.exit_time = candle['timestamp']
        self.current_position.current_price = exit_price
        self.current_position.pnl = pnl
        self.current_position.pnl_percent = pnl_pct
        self.current_position.exit_reason = exit_reason
        self.current_position.time_in_trade_sec = (
            self.current_position.exit_time - self.current_position.entry_time
        ).seconds
        
        if pnl > 0:
            self.current_position.status = 'CLOSED_PROFIT'
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.current_position.status = 'CLOSED_LOSS'
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        
        # Update capital
        self.capital += pnl
        
        # Update statistics
        self.stats['total_trades'] += 1
        self.stats['total_pnl'] += pnl
        
        if pnl > 0:
            self.stats['winning_trades'] += 1
        else:
            self.stats['losing_trades'] += 1
        
        # Drawdown
        if self.capital > self.stats['peak_capital']:
            self.stats['peak_capital'] = self.capital
            self.stats['current_drawdown'] = 0
        else:
            self.stats['current_drawdown'] = self.stats['peak_capital'] - self.capital
            self.stats['max_drawdown'] = max(
                self.stats['max_drawdown'],
                self.stats['current_drawdown']
            )
        
        # Save trade
        self.trades.append(self.current_position)
        
        print(f"\n📉 EXIT: {self.current_position.trade_id}")
        print(f"   Reason: {exit_reason}")
        print(f"   Exit Price: ₹{exit_price:.2f}")
        print(f"   P&L: ₹{pnl:.2f} ({pnl_pct:.2f}%)")
        print(f"   Capital: ₹{self.capital:,.2f}")
        
        self.current_position = None
    
    def run(self):
        """Run backtest simulation"""
        print("\n🚀 Starting backtest...\n")
        
        self.market_data.reset()
        
        while True:
            candle = self.market_data.get_next_candle()
            if not candle:
                break

            # Day boundary handling for daily kill-switch
            candle_day = candle['timestamp'].date()
            if (self.current_day is None) or (candle_day != self.current_day):
                self.current_day = candle_day
                self.day_start_capital = self.capital
                self.day_loss_limit_amount = self.day_start_capital * self.daily_kill_pct
                self.day_kill_active = False
            
            # Update expiry tracking
            if not self.update_expiry(candle['timestamp']):
                continue  # Skip expiry day
            
            # Check exit first (if in position)
            if self.current_position:
                exit_reason = self.check_exit_conditions(candle)
                if exit_reason:
                    self.exit_trade(candle, exit_reason)
            
            # Check entry (if no position)
            if not self.current_position:
                entry_signal = self.check_entry_conditions(candle)
                if entry_signal:
                    self.enter_trade(entry_signal)
        
        # Close any open position at end
        if self.current_position:
            last_candle = self.market_data.data.iloc[-1].to_dict()
            self.exit_trade(last_candle, 'BACKTEST_END')
        
        self.calculate_final_statistics()
        self.print_results()
    
    def calculate_final_statistics(self):
        """Calculate final statistics"""
        if self.stats['total_trades'] == 0:
            return
        
        # Win rate
        self.stats['win_rate'] = (
            self.stats['winning_trades'] / self.stats['total_trades']
        ) * 100
        
        # Average win/loss
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        losses = [t.pnl for t in self.trades if t.pnl < 0]
        
        self.stats['avg_win'] = np.mean(wins) if wins else 0
        self.stats['avg_loss'] = np.mean(losses) if losses else 0
        
        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        
        self.stats['profit_factor'] = (
            total_wins / total_losses if total_losses > 0 else 0
        )
    
    def print_results(self):
        """Print backtest results"""
        print("\n" + "="*80)
        print("BACKTEST RESULTS")
        print("="*80)
        
        print(f"\n💰 FINANCIAL SUMMARY")
        print(f"   Initial Capital:    ₹{self.initial_capital:,.2f}")
        print(f"   Final Capital:      ₹{self.capital:,.2f}")
        print(f"   Total P&L:          ₹{self.stats['total_pnl']:,.2f}")
        print(f"   Total Fees:         ₹{self.stats['total_fees']:,.2f}")
        print(f"   Return:             {(self.capital / self.initial_capital - 1) * 100:.2f}%")
        
        print(f"\n📊 TRADE STATISTICS")
        print(f"   Total Trades:       {self.stats['total_trades']}")
        print(f"   Winning Trades:     {self.stats['winning_trades']}")
        print(f"   Losing Trades:      {self.stats['losing_trades']}")
        print(f"   Win Rate:           {self.stats['win_rate']:.2f}%")
        
        print(f"\n📈 PERFORMANCE METRICS")
        print(f"   Average Win:        ₹{self.stats['avg_win']:.2f}")
        print(f"   Average Loss:       ₹{self.stats['avg_loss']:.2f}")
        print(f"   Profit Factor:      {self.stats['profit_factor']:.2f}")
        print(f"   Max Drawdown:       ₹{self.stats['max_drawdown']:,.2f}")
        
        # Risk-adjusted metrics
        if self.stats['total_trades'] > 0:
            avg_pnl = self.stats['total_pnl'] / self.stats['total_trades']
            pnl_std = np.std([t.pnl for t in self.trades]) if len(self.trades) > 1 else 0
            
            sharpe = (avg_pnl / pnl_std) if pnl_std > 0 else 0
            
            print(f"\n🎯 RISK-ADJUSTED METRICS")
            print(f"   Sharpe Ratio:       {sharpe:.2f}")
            print(f"   Avg PnL per Trade:  ₹{avg_pnl:.2f}")
            print(f"   PnL Std Dev:        ₹{pnl_std:.2f}")
        
        print("\n" + "="*80)
        
        # Export results
        self.export_results()
    
    def export_results(self):
        """Export results to files"""
        # Trade log CSV
        if self.trades:
            trades_df = pd.DataFrame([
                {
                    'trade_id': t.trade_id,
                    'entry_time': t.entry_time,
                    'exit_time': t.exit_time,
                    'option_type': t.option_type,
                    'strike': t.strike,
                    'entry_price': t.entry_price,
                    'exit_price': t.current_price,
                    'quantity': t.quantity,
                    'pnl': t.pnl,
                    'pnl_percent': t.pnl_percent,
                    'exit_reason': t.exit_reason,
                    'time_in_trade_sec': t.time_in_trade_sec
                }
                for t in self.trades
            ])
            
            csv_path = f"backtest_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trades_df.to_csv(csv_path, index=False)
            print(f"\n✅ Trade log exported: {csv_path}")
        
        # Summary JSON
        summary = {
            'backtest_date': datetime.now().isoformat(),
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'statistics': self.stats
        }
        
        json_path = f"backtest_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"✅ Summary exported: {json_path}")


def main():
    """Main backtest runner"""
    parser = argparse.ArgumentParser(description='ANGEL-X Backtesting')
    parser.add_argument('--capital', type=float, default=100000,
                       help='Initial capital (default: 100000)')
    parser.add_argument('--days', type=int, default=30,
                       help='Number of days to backtest (default: 30)')
    parser.add_argument('--data', type=str, default=None,
                       help='Path to historical data CSV')
    parser.add_argument('--timestamp-col', type=str, default=None,
                       help='Timestamp column name if not "timestamp"')
    parser.add_argument('--date-col', type=str, default=None,
                       help='Date column name when separate date/time')
    parser.add_argument('--time-col', type=str, default=None,
                       help='Time column name when separate date/time')
    parser.add_argument('--risk', type=float, default=0.04,
                       help='Risk per trade as fraction (e.g., 0.04 for 4%)')
    parser.add_argument('--sl', type=float, default=0.10,
                       help='Stop-loss percent of premium as fraction (e.g., 0.10 for 10%)')
    parser.add_argument('--daily-kill', type=float, default=0.05,
                       help='Daily kill-switch percent as fraction (e.g., 0.05 for 5%)')
    parser.add_argument('--target', type=float, default=0.12,
                       help='Target profit percent as fraction (e.g., 0.12 for 12%)')
    
    args = parser.parse_args()
    
    # Create backtest engine with requested risk settings
    engine = BacktestEngine(initial_capital=args.capital, risk_per_trade=args.risk, sl_percent=args.sl, daily_kill_pct=args.daily_kill, target_percent=args.target)
    
    # Load/generate data
    if args.data:
        engine.market_data.load_from_file(
            args.data,
            timestamp_col=args.timestamp_col,
            date_col=args.date_col,
            time_col=args.time_col,
        )
    else:
        engine.market_data.generate_sample_data(days=args.days)
    
    # Run backtest
    engine.run()


if __name__ == '__main__':
    main()
