"""
ANGEL-X Main Strategy Orchestrator
Coordinates all 9 layers of ANGEL-X system
Optimized for local network with auto-reconnection and monitoring
"""

import signal
import time
import logging
from datetime import datetime, timedelta
from threading import Lock

# Configuration
from config import config

# Utils
from src.utils.logger import StrategyLogger
from src.utils.data_feed import DataFeed
from src.utils.trade_journal import TradeJournal
from src.utils.network_resilience import get_network_monitor

# Engines
from src.engines.bias_engine import BiasEngine, BiasState
from src.engines.strike_selection_engine import StrikeSelectionEngine
from src.engines.entry_engine import EntryEngine, EntrySignal
from src.engines.trap_detection_engine import TrapDetectionEngine

# Core
from src.core.position_sizing import PositionSizing
from src.core.order_manager import OrderManager, OrderAction, OrderType, ProductType
from src.core.trade_manager import TradeManager
from src.core.expiry_manager import ExpiryManager

logger = StrategyLogger.get_logger(__name__)


class AngelXStrategy:
    """
    ANGEL-X: Professional Options Scalping Strategy
    
    9-Layer Architecture:
    1. Data Ingestion (WebSocket)
    2. Data Normalization & Health Check
    3. Market State Engine (Bias)
    4. Option Selection Engine
    5. Entry Engine (Trigger)
    6. Position Sizing Engine (Risk)
    7. Execution Engine (Orders)
    8. Trade Management Engine (Greek exits)
    9. Daily Risk & Kill-Switch
    """
    
    def __init__(self):
        """Initialize ANGEL-X strategy"""
        logger.info("="*80)
        logger.info("ANGEL-X STRATEGY INITIALIZATION")
        logger.info("="*80)
        
        # Initialize network monitor for local network resilience
        self.network_monitor = get_network_monitor()
        self.network_monitor.start_monitoring()
        logger.info("Network monitor started - monitoring connectivity and data flow")
        
        # Initialize all components
        self.data_feed = DataFeed()
        self.bias_engine = BiasEngine()
        self.trap_detection = TrapDetectionEngine()
        self.strike_selection = StrikeSelectionEngine()
        self.entry_engine = EntryEngine(self.bias_engine, self.trap_detection)
        self.position_sizing = PositionSizing()
        self.order_manager = OrderManager()
        self.trade_manager = TradeManager()
        self.trade_journal = TradeJournal()
        
        # Expiry manager - auto-detect from OpenAlgo
        self.expiry_manager = ExpiryManager()
        self.expiry_manager.refresh_expiry_chain(config.PRIMARY_UNDERLYING)
        
        # Strategy state
        self.running = False
        self.state_lock = Lock()
        self.last_tick_time = None
        
        # Daily limits
        self.daily_start_time = datetime.now()
        self.daily_pnl = 0.0
        self.daily_trades = 0
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("All components initialized successfully")
        logger.info("="*80)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal")
        self.stop()
    
    def start(self):
        """Start the strategy"""
        try:
            logger.info("Starting ANGEL-X strategy...")
            
            # Check demo mode
            if config.DEMO_MODE:
                logger.info("=" * 80)
                logger.info("DEMO MODE ENABLED - Running in simulation")
                logger.info("=" * 80)
                if config.DEMO_SKIP_WEBSOCKET:
                    logger.info("WebSocket connection skipped in demo mode")
                    return True
            
            # Connect to data feed
            if config.WEBSOCKET_ENABLED and not config.DEMO_SKIP_WEBSOCKET:
                logger.info("Connecting to WebSocket...")
                if not self.data_feed.connect():
                    logger.error("Failed to connect to data feed")
                    if not config.DEMO_MODE:
                        return False
                    else:
                        logger.warning("Continuing in demo mode despite connection failure")
                        return True
                
                # Subscribe to LTP
                instruments = [{'exchange': config.UNDERLYING_EXCHANGE, 'symbol': config.PRIMARY_UNDERLYING}]
                self.data_feed.subscribe_ltp(instruments)
                
                logger.info(f"Subscribed to {config.PRIMARY_UNDERLYING} LTP stream")
            
            # Start bias engine
            self.bias_engine.start()
            
            # Set running flag
            self.running = True
            
            logger.info("Strategy started successfully")
            logger.info("="*80)
            
            # Main loop
            self._run_loop()
            
        except Exception as e:
            logger.error(f"Error starting strategy: {e}")
            self.stop()
            return False
    
    def _run_loop(self):
        """Main strategy loop"""
        logger.info("Entering main trading loop...")
        
        try:
            while self.running:
                try:
                    # Check daily limits
                    if not self._check_daily_limits():
                        logger.warning("Daily limits exceeded, stopping")
                        self.running = False
                        break
                    
                    # Check trading hours
                    if not self._is_trading_allowed():
                        time.sleep(5)
                        continue
                    
                    # Refresh expiry periodically (every 100 iterations)
                    if self.daily_trades % 100 == 0:
                        self.expiry_manager.refresh_expiry_chain(config.PRIMARY_UNDERLYING)
                        expiry_stats = self.expiry_manager.get_expiry_statistics()
                        logger.info(f"Expiry status: {expiry_stats}")
                    
                    # Get expiry rules
                    expiry_rules = self.expiry_manager.apply_expiry_rules()
                    
                    # Get latest market data
                    ltp = self.data_feed.get_ltp(config.PRIMARY_UNDERLYING)
                    if not ltp:
                        time.sleep(0.5)
                        continue
                    
                    # Update market state
                    bias_state = self.bias_engine.get_bias()
                    bias_confidence = self.bias_engine.get_confidence()
                    
                    # Check for entry opportunities
                    active_trades = self.trade_manager.get_active_trades()
                    
                    if len(active_trades) == 0:
                        # Look for entry
                        entry_context = self.entry_engine.check_entry_signal(
                            bias_state=bias_state.value,
                            bias_confidence=bias_confidence,
                            current_delta=0.5,  # Placeholder
                            prev_delta=0.45,
                            current_gamma=0.005,
                            prev_gamma=0.004,
                            current_oi=1000,
                            current_oi_change=100,
                            current_ltp=ltp,
                            prev_ltp=ltp * 0.99,
                            current_volume=500,
                            prev_volume=450,
                            current_iv=25.0,
                            prev_iv=24.5,
                            bid=ltp * 0.995,
                            ask=ltp * 1.005,
                            selected_strike=18800,
                            current_spread_percent=0.5
                        )
                        
                        if entry_context and entry_context.signal != EntrySignal.NO_SIGNAL:
                            # Validate entry quality
                            if self.entry_engine.validate_entry_quality(entry_context):
                                # Calculate position size
                                position = self.position_sizing.calculate_position_size(
                                    entry_price=entry_context.entry_price,
                                    hard_sl_price=entry_context.entry_price * 0.93,
                                    target_price=entry_context.entry_price * 1.07
                                )
                                
                                if position.sizing_valid:
                                    # Enter trade
                                    trade = self.trade_manager.enter_trade(
                                        option_type=entry_context.option_type,
                                        strike=entry_context.strike,
                                        entry_price=entry_context.entry_price,
                                        quantity=int(position.quantity * expiry_rules.get('max_position_size_factor', 1.0)),
                                        entry_delta=entry_context.entry_delta,
                                        entry_gamma=entry_context.entry_gamma,
                                        entry_theta=entry_context.entry_theta,
                                        entry_iv=entry_context.entry_iv,
                                        sl_price=position.hard_sl_price,
                                        target_price=position.target_price
                                    )
                                    
                                    # Build symbol using expiry manager
                                    order_symbol = self.expiry_manager.build_order_symbol(
                                        entry_context.strike,
                                        entry_context.option_type
                                    )
                                    
                                    # Place order
                                    order = self.order_manager.place_order(
                                        exchange=config.UNDERLYING_EXCHANGE,
                                        symbol=order_symbol,
                                        action=OrderAction.BUY,
                                        order_type=OrderType.LIMIT,
                                        price=entry_context.entry_price,
                                        quantity=int(position.quantity * expiry_rules.get('max_position_size_factor', 1.0)),
                                        product=ProductType.MIS
                                    )
                                    
                                    if order:
                                        logger.info(f"Order placed successfully")
                    else:
                        # Update active trades
                        for trade in active_trades:
                            exit_reason = self.trade_manager.update_trade(
                                trade,
                                current_price=ltp,
                                current_delta=0.5,
                                current_gamma=0.005,
                                current_theta=0,
                                current_iv=25.0,
                                current_oi=1000,
                                prev_oi=900,
                                prev_price=ltp * 0.99,
                                expiry_rules=expiry_rules
                            )
                            
                            if exit_reason:
                                # Exit trade
                                self.trade_manager.exit_trade(trade, exit_reason)
                                
                                # Log to journal
                                self.trade_journal.log_trade(
                                    underlying=config.PRIMARY_UNDERLYING,
                                    strike=trade.strike,
                                    option_type=trade.option_type,
                                    expiry_date="weekly",
                                    entry_price=trade.entry_price,
                                    exit_price=trade.current_price,
                                    qty=trade.quantity,
                                    entry_delta=trade.entry_delta,
                                    entry_gamma=trade.entry_gamma,
                                    entry_theta=trade.entry_theta,
                                    entry_vega=0,
                                    entry_iv=trade.entry_iv,
                                    exit_delta=0,
                                    exit_gamma=0,
                                    exit_theta=0,
                                    exit_vega=0,
                                    exit_iv=25.0,
                                    entry_spread=0.5,
                                    exit_spread=0.5,
                                    entry_reason_tags=['demo'],
                                    exit_reason_tags=[exit_reason],
                                    original_sl_price=trade.sl_price,
                                    original_sl_percent=7.0,
                                    original_target_price=trade.target_price,
                                    original_target_percent=7.0
                                )
                                
                                self.daily_pnl += trade.pnl
                                self.daily_trades += 1
                    
                    time.sleep(1)
                
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.stop()
    
    def _check_daily_limits(self) -> bool:
        """Check if daily limits are exceeded"""
        # Check max daily loss
        if self.daily_pnl < -config.MAX_DAILY_LOSS_AMOUNT:
            logger.warning(f"Daily loss limit exceeded: ₹{self.daily_pnl:.2f}")
            return False
        
        # Check max trades
        if self.daily_trades >= config.MAX_TRADES_PER_DAY:
            logger.warning(f"Daily trade limit reached: {self.daily_trades}")
            return False
        
        return True
    
    def _is_trading_allowed(self) -> bool:
        """Check if trading is allowed at this time"""
        now = datetime.now().time()
        
        start_time = datetime.strptime(config.TRADING_SESSION_START, "%H:%M").time()
        end_time = datetime.strptime(config.TRADING_SESSION_END, "%H:%M").time()
        
        if not (start_time <= now <= end_time):
            return False
        
        return True
    
    def stop(self):
        """Stop the strategy"""
        logger.info("Stopping ANGEL-X strategy...")
        
        self.running = False
        
        # Close all positions
        active_trades = self.trade_manager.get_active_trades()
        for trade in active_trades:
            self.trade_manager.exit_trade(trade, "strategy_stop")
        
        # Disconnect and cleanup
        self.bias_engine.stop()
        self.data_feed.disconnect()
        
        # Stop network monitoring
        if hasattr(self, 'network_monitor'):
            logger.info("Network Health Summary:")
            health = self.network_monitor.get_health_status()
            logger.info(f"  API Calls: {health['api_calls']}")
            logger.info(f"  API Errors: {health['api_errors']} ({health['api_error_rate']:.1%})")
            logger.info(f"  WebSocket Reconnects: {health['websocket_reconnects']}")
            logger.info(f"  Alerts: {health['alerts_count']}")
            self.network_monitor.stop_monitoring()
        
        # Print summary
        stats = self.trade_manager.get_trade_statistics()
        logger.info("="*80)
        logger.info("STRATEGY STOPPED - DAILY SUMMARY")
        logger.info("="*80)
        logger.info(f"Total Trades: {stats['total']}")
        logger.info(f"Wins: {stats['wins']} | Losses: {stats['losses']}")
        logger.info(f"Win Rate: {stats['win_rate']:.2f}%")
        logger.info(f"Total P&L: ₹{stats['total_pnl']:.2f}")
        logger.info(f"Daily P&L: ₹{self.daily_pnl:.2f}")
        logger.info("="*80)
        
        # Export summary
        self.trade_journal.print_daily_summary()
        self.trade_journal.export_summary_report()


def main():
    """Main entry point"""
    strategy = AngelXStrategy()
    strategy.start()


if __name__ == "__main__":
    main()
